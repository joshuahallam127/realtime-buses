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

load_dotenv()

INTERVAL = 5

url = 'https://api.transport.nsw.gov.au/v1/gtfs/realtime/buses'
headers = {
    'Authorization': f'apikey {os.getenv("APIKEY")}',
}

# get valid routes from the database
conn, cursor = get_connection()
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
    delay_data = {
        'trip_id' : [],
        'route_id' : [],
        'stop_sequence' : [],
        'arrival_delay' : [],
        'departure_early' : [],
    }
    cancel_data = {
        'trip_id' : [],
        'route_id' : [],
    }
    for entity in feed.entity:
        if entity.trip_update.trip.route_id not in valid_routes: continue
        if 'schedule_relationship' not in entity.trip_update.trip: continue
        if entity.trip_update.trip.schedule_relationship == 3:
            cancel_data['trip_id'].append(entity.trip_update.trip.trip_id)
            cancel_data['route_id'].append(entity.trip_update.trip.route_id)
        elif entity.trip_update.trip.schedule_relationship == 0 and entity.trip_update.stop_time_update:
            first_stop_time_update = entity.trip_update.stop_time_update[0]
            if 'arrival' in first_stop_time_update and 'delay' in first_stop_time_update.arrival and \
                'departure' in first_stop_time_update and 'delay' in first_stop_time_update.departure:
                delay_data['trip_id'].append(entity.trip_update.trip.trip_id)
                delay_data['route_id'].append(entity.trip_update.trip.route_id)
                delay_data['stop_sequence'].append(entity.trip_update.stop_time_update[0].stop_sequence)
                delay_data['arrival_delay'].append(max(0, entity.trip_update.stop_time_update[0].arrival.delay))
                delay_data['departure_early'].append(min(0, entity.trip_update.stop_time_update[0].departure.delay) * -1)
    return delay_data, cancel_data

def write_json(feed):
    feed_dict = MessageToDict(feed)
    with open("feed_data_2.json", "w") as f:
        json.dump(feed_dict, f, indent=2)

def cache_delay_data(cursor, delay_data):
    # get a map of trip_id to stop_sequence that we currently have in the database
    cursor.execute("SELECT trip_id, stop_sequence FROM delays")
    trip_id_map = {row[0]: row[1] for row in cursor.fetchall()}
    
    # we need to cache if the next stop_sequence of trip_id has been received
    to_cache = set()
    for i, trip_id in enumerate(delay_data['trip_id']):
        if trip_id in trip_id_map and delay_data['stop_sequence'][i] > trip_id_map[trip_id]:
            to_cache.add(trip_id)

    # we also need to cache if trip_id from the database is not in the new data
    missing_trip_ids = set(trip_id_map.keys()) - set(delay_data['trip_id']) # used later to know a route has been completed
    to_cache.update(missing_trip_ids)

    if not to_cache:
        return

    # get the data to cache
    placeholders = ','.join(['%s']*len(to_cache))
    query = f"""
        SELECT trip_id, route_id, arrival_delay, departure_early
        FROM delays
        WHERE trip_id IN ({placeholders})
    """
    cursor.execute(query, tuple(to_cache))
    rows_to_cache = cursor.fetchall()

    # aggregate the data to cache based on route and start_date
    aggregate_cached = {}
    above_ranges = [1, 2, 5, 10, 15, 30]
    before_ranges = [1, 2, 5, 10]
    for trip_id, route_id, arrival_delay, departure_early in rows_to_cache:
        if route_id not in aggregate_cached:
            aggregate_cached[route_id] = {
                'total_delay': 0, 
                'total_early' : 0, 
                'total_count': 0,
                **{f'above_{n}_minutes': 0 for n in above_ranges},
                **{f'before_{n}_minutes': 0 for n in before_ranges},
                'total_trips': 0,
            }
        aggregate_cached[route_id]['total_delay'] += arrival_delay
        aggregate_cached[route_id]['total_early'] += departure_early
        aggregate_cached[route_id]['total_count'] += 1
        if trip_id in missing_trip_ids:
            aggregate_cached[route_id]['total_trips'] += 1
        for x in above_ranges:
            if arrival_delay > x * 60:
                aggregate_cached[route_id][f'above_{x}_minutes'] += 1
        for x in before_ranges:
            if departure_early > x * 60:
                aggregate_cached[route_id][f'before_{x}_minutes'] += 1
    
    # insert the aggregated data
    data_to_insert = [
        (
            route_id,
            datetime.now(ZoneInfo('Australia/Sydney')).date(),
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
            data['total_trips'],
        )
        for route_id, data in aggregate_cached.items()
    ]
    cursor.executemany("""
        INSERT INTO route_daily_delays (route_id, date, total_delay, total_early, total_count, above_1_minute, above_2_minutes, above_5_minutes, above_10_minutes, above_15_minutes, above_30_minutes, before_1_minute, before_2_minutes, before_5_minutes, before_10_minutes, total_trips)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
            total_trips = total_trips + VALUES(total_trips)
    """, data_to_insert)

    query = f"""
        DELETE FROM delays
        WHERE trip_id IN ({placeholders})
    """
    cursor.execute(query, tuple(to_cache))

    print(f"Archived and deleted {len(to_cache)} rows from delays")

def cache_cancel_data(cursor, cancel_data):
    # get current cancellations in the database
    cursor.execute("SELECT trip_id, route_id FROM cancels")
    rows = cursor.fetchall()
    curr_cancel_data = {
        'trip_id' : [row[0] for row in rows],
        'route_id' : [row[1] for row in rows],
    }

    # see what cancellations are in the database but not in the new data
    to_cache = set(curr_cancel_data['trip_id']) - set(cancel_data['trip_id'])

    if not to_cache:
        return
    
    query = """
        INSERT INTO route_daily_delays (route_id, date, total_cancelled, total_trips)
        VALUES (%s, %s, 1, 1)
        ON DUPLICATE KEY UPDATE
            total_cancelled = total_cancelled + 1,
            total_trips = total_trips + 1
    """
    data_to_cache = [[
        curr_cancel_data['route_id'][i],
        datetime.now(ZoneInfo('Australia/Sydney')).date()
    ] for i in range(len(curr_cancel_data['trip_id'])) if curr_cancel_data['trip_id'][i] in to_cache]
    cursor.executemany(query, data_to_cache)

    placeholders = ','.join(['%s']*len(to_cache))
    query = f"""
        DELETE FROM cancels
        WHERE trip_id IN ({placeholders})
    """
    cursor.execute(query, tuple(to_cache))

    print(f'Cached {len(data_to_cache)} cancellations')

def insert_or_update_delays(cursor, delay_data):
    data = list(zip(
        delay_data['trip_id'],
        delay_data['route_id'],
        delay_data['stop_sequence'],
        delay_data['arrival_delay'],
        delay_data['departure_early'],
    ))

    query = """
        INSERT INTO delays (trip_id, route_id, stop_sequence, arrival_delay, departure_early)
        VALUES (%s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            arrival_delay = VALUES(arrival_delay),
            departure_early = VALUES(departure_early)
    """
    cursor.executemany(query, data)

    print(f'Inserted/Updated {len(data)} delays')

def insert_or_update_cancels(cursor, cancel_data):
    cursor.execute("SELECT trip_id FROM cancels")
    current_cancels = set(row[0] for row in cursor.fetchall())
    new_cancels = set(cancel_data['trip_id']) - current_cancels
    if not new_cancels:
        return
    query = """
        INSERT INTO cancels (trip_id, route_id)
        VALUES (%s, %s)
    """
    data = [[
        cancel_data['trip_id'][i], 
        cancel_data['route_id'][i]
    ] for i in range(len(cancel_data['trip_id'])) if cancel_data['trip_id'][i] in new_cancels]
    cursor.executemany(query, data)

    print(f'Inserted {len(data)} new cancellations')

def catch_changes(cursor, delay_data, cancel_data):
    # Check for changes in trip_ids between delays and cancellations
    cursor.execute("SELECT trip_id FROM delays")
    current_delays = set(row[0] for row in cursor.fetchall())
    cursor.execute("SELECT trip_id FROM cancels")
    current_cancels  = set(row[0] for row in cursor.fetchall())

    # find trips that have changed status
    cancelled_to_delayed = current_cancels.intersection(set(delay_data['trip_id']))
    delayed_to_cancelled = current_delays.intersection(set(cancel_data['trip_id']))

    # delete these trip_ids from the database, we don't want them to be cached
    if cancelled_to_delayed:
        query = f"DELETE FROM cancels WHERE trip_id IN ({','.join(['%s'] * len(cancelled_to_delayed))})"
        cursor.execute(query, tuple(cancelled_to_delayed))
        print(f'Saved {len(cancelled_to_delayed)} trips that were cancelled but are now delayed from being cached')
    if delayed_to_cancelled:
        query = f"DELETE FROM delays WHERE trip_id IN ({','.join(['%s'] * len(delayed_to_cancelled))})"
        cursor.execute(query, tuple(delayed_to_cancelled))
        print(f'Saved {len(delayed_to_cancelled)} trips that were delayed but are now cancelled from being cached')

# Open connection once
conn, cursor = None, None

while True:
    start_time = time.time()

    try:
        if conn is None or not conn.is_connected():
            conn, cursor = get_connection()

        feed = get_feed()
        delay_data, cancel_data = parse_feed(feed)
        
        catch_changes(cursor, delay_data, cancel_data)

        cache_delay_data(cursor, delay_data)
        insert_or_update_delays(cursor, delay_data)

        cache_cancel_data(cursor, cancel_data)
        insert_or_update_cancels(cursor, cancel_data)

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
    sleep_time = max(0, INTERVAL - elapsed)
    print(f'Sleeping for {sleep_time:.2f} seconds')
    print()
    time.sleep(sleep_time)