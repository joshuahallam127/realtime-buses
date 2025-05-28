from google.transit import gtfs_realtime_pb2
from google.protobuf.json_format import MessageToDict
import requests
import os
from dotenv import load_dotenv
import json
import functions
import time
from mysql.connector.errors import OperationalError
from zoneinfo import ZoneInfo
from datetime import datetime
import csv

load_dotenv()

INTERVAL = 5

url = 'https://api.transport.nsw.gov.au/v1/gtfs/realtime/buses'
headers = {
    'Authorization': f'apikey {os.getenv("APIKEY")}',
}

# get valid routes from the database
conn, cursor = functions.get_connection()
cursor.execute("SELECT id FROM routes")
valid_routes = set(row[0] for row in cursor.fetchall())
cursor.close()
conn.close()

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
        'route_id' : [],
        'stop_sequence' : [],
        'arrival_delay' : [],
        'departure_early' : [],
    }
    for entity in feed.entity:
        if entity.trip_update.trip.schedule_relationship == 0 and entity.trip_update.stop_time_update[0].stop_sequence != 1:
            result['trip_id'].append(entity.trip_update.trip.trip_id)
            result['route_id'].append(entity.trip_update.trip.route_id)
            result['stop_sequence'].append(entity.trip_update.stop_time_update[0].stop_sequence)
            result['arrival_delay'].append(max(0, entity.trip_update.stop_time_update[0].arrival.delay))
            result['departure_early'].append(min(0, entity.trip_update.stop_time_update[0].departure.delay) * -1)
    result['start_date'] = [datetime.now(ZoneInfo('Australia/Sydney')).date()]*len(result['trip_id'])
    return result

def write_json(feed):
    feed_dict = MessageToDict(feed)
    with open("feed_data.json", "w") as f:
        json.dump(feed_dict, f, indent=2)

def write_cancelled(trip_id):
    with open("cancelled_trips.txt", "r") as f:
        cancelled = set(f.read().splitlines())
    if trip_id in cancelled:
        return
    print('Trip was running but has now been canceled:', trip_id)
    with open("cancelled_trips.txt", "a") as f:
        f.write(f"{trip_id}\n")

def write_duplicate(trip_id):
    with open("duplicate_trips.txt", "r") as f:
        duplicates = set(f.read().splitlines())
    if trip_id in duplicates:
        return
    with open("duplicate_trips.txt", "a") as f:
        f.write(f"{trip_id}\n")

def cache_data(cursor, delay_data):
    # get a map of trip_id to stop_sequence
    trip_id_map = {}
    cursor.execute("SELECT trip_id, stop_sequence FROM delays")
    rows = cursor.fetchall() 
    for row in rows:
        trip_id, stop_sequence = row
        trip_id_map[trip_id] = stop_sequence
    
    # go through new data to see what current data should be cached
    # we need to cache if the next stop_sequence of trip_id has been received
    to_cache = set()
    for i in range(len(delay_data['trip_id'])):
        trip_id = delay_data['trip_id'][i]
        stop_sequence = delay_data['stop_sequence'][i]

        # cache the data if trip_id stop_sequence is greater than the current stop_sequence
        if trip_id in trip_id_map and stop_sequence > trip_id_map[trip_id]:
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
        SELECT trip_id, route_id, start_date, arrival_delay, departure_early
        FROM delays
        WHERE trip_id IN ({placeholders})
    """
    cursor.execute(query, tuple(to_cache))
    rows_to_cache = cursor.fetchall()

    # aggregate the data to cache based on route and start_date
    aggregate_cached = {}
    for trip_id, route_id, start_date, arrival_delay, departure_early in rows_to_cache:
        if (route_id, start_date) not in aggregate_cached:
            aggregate_cached[(route_id, start_date)] = {'total_delay': 0, 'total_early' : 0, 'total_count': 0}
        aggregate_cached[(route_id, start_date)]['total_delay'] += arrival_delay
        aggregate_cached[(route_id, start_date)]['total_early'] += departure_early
        aggregate_cached[(route_id, start_date)]['total_count'] += 1
    
    # insert the aggregated data
    data_to_insert = [
        (route_id, start_date, data['total_delay'], data['total_early'], data['total_count'])
        for (route_id, start_date), data in aggregate_cached.items()
    ]
    cursor.executemany("""
        INSERT INTO route_daily_delays (route_id, date, total_delay, total_early, total_count)
        VALUES (%s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            total_delay = total_delay + VALUES(total_delay),
            total_early = total_early + VALUES(total_early),
            total_count = total_count + VALUES(total_count)
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
        delay_data['route_id'],
        delay_data['stop_sequence'],
        delay_data['arrival_delay'],
        delay_data['departure_early'],
        delay_data['start_date'],
    ))

    cleaned_data = [row for row in data if row[1] in valid_routes]

    query = """
        INSERT INTO delays (trip_id, route_id, stop_sequence, arrival_delay, departure_early, start_date)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            arrival_delay = VALUES(arrival_delay),
            departure_early = VALUES(departure_early),
            start_date = VALUES(start_date)
    """
    for i in range(0, len(cleaned_data), chunk_size):
        chunk = cleaned_data[i:i+chunk_size]
        cursor.executemany(query, chunk)

    print(f'Inserted/Updated {len(cleaned_data)} rows')

# Open connection once
conn, cursor = None, None

while True:
    start_time = time.time()

    try:
        if conn is None or not conn.is_connected():
            conn, cursor = functions.get_connection()

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