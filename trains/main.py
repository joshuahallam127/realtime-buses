from google.transit import gtfs_realtime_pb2
from google.protobuf.json_format import MessageToDict
import requests
import os
from dotenv import load_dotenv
import json
from functions import get_connection
import time
from mysql.connector.errors import OperationalError
from zoneinfo import ZoneInfo
from datetime import datetime
import csv

load_dotenv()

INTERVAL = 5

url = 'https://api.transport.nsw.gov.au/v2/gtfs/realtime/sydneytrains'
headers = {
    'Authorization': f'apikey {os.getenv("APIKEY")}',
}

# get valid routes from the database
conn, cursor = get_connection()
cursor.execute("SELECT short_name FROM routes")
valid_routes = set(row[0] for row in cursor.fetchall())
cursor.close()
conn.close()

# get route_id to short_name mapping
route_id_to_short_name = {}
with open('sydneytrains.csv', newline='', encoding='utf-8') as csvfile:
    reader = csv.DictReader(csvfile)
    for row in reader:
        route_id_to_short_name[row['route_id']] = row['route_short_name']

# get stop_id to parent_id mapping
with open('stop_to_parent.csv', newline='', encoding='utf-8') as csvfile:
    reader = csv.DictReader(csvfile)
    stop_id_to_parent_id = {row['stop_id']: row['parent_station'] for row in reader if row['parent_station']}
        
def get_feed():
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(response.content)
        return feed
    else:
        print(f'Error: {response.status_code}')
        print(response.text)

def parse_feed(feed):
    result = {
        'trip_id' : [],
        'route_short_name' : [],
        'stop_id' : [],
        'arrival_delay' : [],
        'departure_early' : [],
    }
    for entity in feed.entity:
        if entity.trip_update.trip.route_id in route_id_to_short_name and \
            entity.trip_update.trip.schedule_relationship == 0 and \
            len(entity.trip_update.stop_time_update) > 0 and \
            entity.trip_update.stop_time_update[0].stop_id in stop_id_to_parent_id:
            result['trip_id'].append(entity.trip_update.trip.trip_id)
            result['route_short_name'].append(route_id_to_short_name[entity.trip_update.trip.route_id])
            result['stop_id'].append(stop_id_to_parent_id[entity.trip_update.stop_time_update[0].stop_id])
            result['arrival_delay'].append(max(0, entity.trip_update.stop_time_update[0].arrival.delay))
            result['departure_early'].append(min(0, entity.trip_update.stop_time_update[0].departure.delay) * -1)
    result['start_date'] = [datetime.now(ZoneInfo('Australia/Sydney')).date()]*len(result['trip_id'])
    return result

def write_json(feed):
    feed_dict = MessageToDict(feed)
    with open("train_feed_data.json", "w") as f:
        json.dump(feed_dict, f, indent=2)

def cache_data(cursor, delay_data):
    # get a map of trip_id to stop_id
    trip_id_map = {}
    cursor.execute("SELECT trip_id, stop_id FROM delays")
    rows = cursor.fetchall()
    for row in rows:
        trip_id, stop_id = row
        trip_id_map[trip_id] = stop_id 
    
    # go through new data to see what current data should be cached
    # we need to cache if the next stop_id of trip_id has been received
    to_cache = set()
    for i in range(len(delay_data['trip_id'])):
        trip_id = delay_data['trip_id'][i]
        stop_id = delay_data['stop_id'][i]

        # cache the data if trip_id stop_id is not the current stop_id
        if trip_id in trip_id_map and stop_id != trip_id_map[trip_id]:
            to_cache.add(trip_id)
    # we also need to cache if trip_id from the database is not in the new data
    new_trip_ids = set(delay_data['trip_id'])
    old_trip_ids = set(trip_id_map.keys())
    missing_trip_ids = old_trip_ids - new_trip_ids
    to_cache.update(missing_trip_ids) # we can put this into one line later

    if not to_cache:
        return

    # get the data to cache
    placeholders = ','.join(['%s']*len(to_cache))
    query = f"""
        SELECT route_short_name, stop_id, start_date, arrival_delay, departure_early
        FROM delays
        WHERE trip_id IN ({placeholders})
    """
    cursor.execute(query, tuple(to_cache))
    rows_to_cache = cursor.fetchall()

    # cache the data into stop_daily_delays
    above_ranges = [1, 2, 5, 10, 15, 30]
    before_ranges = [1, 2, 5, 10]
    data_to_insert = [
        [
            route_short_name, 
            stop_id, 
            start_date, 
            arrival_delay, 
            departure_early,
        ] + [
            1 if arrival_delay > above_value * 60 else 0 for above_value in above_ranges
        ] + [
            1 if departure_early > before_value * 60 else 0 for before_value in before_ranges
        ]
        for route_short_name, stop_id, start_date, arrival_delay, departure_early in rows_to_cache
    ]
    cursor.executemany("""
        INSERT INTO stop_daily_delays (route_short_name, stop_id, date, total_delay, total_early, total_count, above_1_minute, above_2_minutes, above_5_minutes, above_10_minutes, above_15_minutes, above_30_minutes, before_1_minute, before_2_minutes, before_5_minutes, before_10_minutes)
        VALUES (%s, %s, %s, %s, %s, 1, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            total_delay = total_delay + VALUES(total_delay),
            total_early = total_early + VALUES(total_early),
            total_count = total_count + 1,
            above_1_minute = above_1_minute + VALUES(above_1_minute),
            above_2_minutes = above_2_minutes + VALUES(above_2_minutes),
            above_5_minutes = above_5_minutes + VALUES(above_5_minutes),
            above_10_minutes = above_10_minutes + VALUES(above_10_minutes),
            above_15_minutes = above_15_minutes + VALUES(above_15_minutes),
            above_30_minutes = above_30_minutes + VALUES(above_30_minutes),
            before_1_minute = before_1_minute + VALUES(before_1_minute),
            before_2_minutes = before_2_minutes + VALUES(before_2_minutes),
            before_5_minutes = before_5_minutes + VALUES(before_5_minutes),
            before_10_minutes = before_10_minutes + VALUES(before_10_minutes)
    """, data_to_insert)

    # aggregate the data to cache based on route and start_date
    aggregate_cached = {}
    for route_short_name, stop_id, start_date, arrival_delay, departure_early in rows_to_cache:
        if (route_short_name, start_date) not in aggregate_cached:
            aggregate_cached[(route_short_name, start_date)] = {
                'total_delay': 0, 
                'total_early' : 0, 
                'total_count': 0,
                **{f'above_{n}_minutes': 0 for n in above_ranges},
                **{f'before_{n}_minutes': 0 for n in before_ranges},
                'total_cancelled': 0,
                'total_trips': 0,
            }
        aggregate_cached[(route_short_name, start_date)]['total_delay'] += arrival_delay
        aggregate_cached[(route_short_name, start_date)]['total_early'] += departure_early
        aggregate_cached[(route_short_name, start_date)]['total_count'] += 1
        if trip_id in missing_trip_ids:
            aggregate_cached[(route_short_name, start_date)]['total_trips'] += 1
        for i in range(len(above_ranges)):
            if arrival_delay > above_ranges[i] * 60:
                aggregate_cached[(route_short_name, start_date)][f'above_{above_ranges[i]}_minutes'] += 1
        for i in range(len(before_ranges)):
            if departure_early > before_ranges[i] * 60:
                aggregate_cached[(route_short_name, start_date)][f'before_{before_ranges[i]}_minutes'] += 1
    
    # insert the aggregated data
    data_to_insert = [
        (
            route_short_name, 
            start_date, 
            data['total_delay'], 
            data['total_early'], 
            data['total_count'],
            data['above_1_minutes'],
            data['above_2_minutes'],
            data['above_5_minutes'],
            data['above_10_minutes'],
            data['above_15_minutes'],
            data['above_30_minutes'],
            data['before_1_minutes'],
            data['before_2_minutes'],
            data['before_5_minutes'],
            data['before_10_minutes'],
            data['total_cancelled'],
            data['total_trips'],
        )
        for (route_short_name, start_date), data in aggregate_cached.items()
    ]
    cursor.executemany("""
        INSERT INTO route_daily_delays (route_short_name, date, total_delay, total_early, total_count, above_1_minute, above_2_minutes, above_5_minutes, above_10_minutes, above_15_minutes, above_30_minutes, before_1_minute, before_2_minutes, before_5_minutes, before_10_minutes, total_cancelled, total_trips)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            total_delay = total_delay + VALUES(total_delay),
            total_early = total_early + VALUES(total_early),
            total_count = total_count + VALUES(total_count),
            above_1_minute = above_1_minute + VALUES(above_1_minute),
            above_2_minutes = above_2_minutes + VALUES(above_2_minutes),
            above_5_minutes = above_5_minutes + VALUES(above_5_minutes),
            above_10_minutes = above_10_minutes + VALUES(above_10_minutes),
            above_15_minutes = above_15_minutes + VALUES(above_15_minutes),
            above_30_minutes = above_30_minutes + VALUES(above_30_minutes),
            before_1_minute = before_1_minute + VALUES(before_1_minute),
            before_2_minutes = before_2_minutes + VALUES(before_2_minutes),
            before_5_minutes = before_5_minutes + VALUES(before_5_minutes),
            before_10_minutes = before_10_minutes + VALUES(before_10_minutes),
            total_cancelled = total_cancelled + VALUES(total_cancelled),
            total_trips = total_trips + VALUES(total_trips)
    """, data_to_insert)

    query = f"""
        DELETE FROM delays
        WHERE trip_id IN ({placeholders})
    """
    cursor.execute(query, tuple(to_cache))

    print(f"Archived and deleted {len(to_cache)} rows from delays")

def insert_or_update_delays(cursor, delay_data, chunk_size=1000):
    data = list(zip(
        delay_data['trip_id'],
        delay_data['route_short_name'],
        delay_data['stop_id'],
        delay_data['arrival_delay'],
        delay_data['departure_early'],
        delay_data['start_date'],
    ))

    query = """
        INSERT INTO delays (trip_id, route_short_name, stop_id, arrival_delay, departure_early, start_date)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            arrival_delay = VALUES(arrival_delay),
            departure_early = VALUES(departure_early),
            start_date = VALUES(start_date)
    """

    cursor.executemany(query, data)

    print(f'Inserted/Updated {len(data)} rows')

# Open connection once
conn, cursor = None, None

while True:
    start_time = time.time()

    try:
        if conn is None or not conn.is_connected():
            conn, cursor = get_connection()

        feed = get_feed()
        delay_data = parse_feed(feed)

        cache_data(cursor, delay_data)
        insert_or_update_delays(cursor, delay_data)

        conn.commit()

    except OperationalError as e:
        print("Database connection error, retrying:", e)
        conn, cursor = None, None
        time.sleep(5)
        continue

    except Exception as e:
        conn, cursor = None, None
        print("Unexpected error:", e)
        time.sleep(5)
        continue

    elapsed = time.time() - start_time
    print(f'Elapsed time: {elapsed:.2f} seconds')
    sleep_time = max(0, INTERVAL - elapsed)
    print(f'Sleeping for {sleep_time:.2f} seconds')
    time.sleep(sleep_time)

