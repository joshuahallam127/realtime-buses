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

# TODO interval shouldn't need to be 5 seconds for trains, even like a minute should be fine
INTERVAL = 10

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
    delay_data = {
        'trip_id' : [],
        'route_short_name' : [],
        'stop_id' : [],
        'arrival_delay' : [],
        'departure_early' : [],
    }
    cancel_data = {
        'trip_id' : [],
        'route_short_name' : [],
    }
    skip_data = {
        'trip_id' : [],
        'route_short_name' : [],
        'stop_id' : [],
    }
    for entity in feed.entity:
        if entity.trip_update.trip.route_id not in route_id_to_short_name: continue
        if 'schedule_relationship' not in entity.trip_update.trip: continue

        # get entities that are cancelled
        if entity.trip_update.trip.schedule_relationship == 3:
            cancel_data['trip_id'].append(entity.trip_update.trip.trip_id)
            cancel_data['route_short_name'].append(route_id_to_short_name[entity.trip_update.trip.route_id])
        elif entity.trip_update.trip.schedule_relationship == 0 and entity.trip_update.stop_time_update:
            first_stop_time_update = entity.trip_update.stop_time_update[0]
            if first_stop_time_update.stop_id not in stop_id_to_parent_id:
                continue
            # if all data is there, add to delay_data
            if 'arrival' in first_stop_time_update and 'delay' in first_stop_time_update.arrival and \
                'departure' in first_stop_time_update and 'delay' in first_stop_time_update.departure:
                delay_data['trip_id'].append(entity.trip_update.trip.trip_id)
                delay_data['route_short_name'].append(route_id_to_short_name[entity.trip_update.trip.route_id])
                delay_data['stop_id'].append(stop_id_to_parent_id[first_stop_time_update.stop_id])
                delay_data['arrival_delay'].append(max(0, first_stop_time_update.arrival.delay))
                delay_data['departure_early'].append(min(0, first_stop_time_update.departure.delay) * -1)
            # otherwise look for skipped stops
            else:
                for stop_time_update in entity.trip_update.stop_time_update:
                    if stop_time_update.stop_id not in stop_id_to_parent_id:
                        continue
                    if stop_time_update.schedule_relationship == 1:
                        skip_data['trip_id'].append(entity.trip_update.trip.trip_id)
                        skip_data['route_short_name'].append(route_id_to_short_name[entity.trip_update.trip.route_id])
                        skip_data['stop_id'].append(stop_id_to_parent_id[stop_time_update.stop_id])
    return delay_data, cancel_data, skip_data

def test_feed(feed):
    trip_ids = set()
    for entity in feed.entity:
        if entity.trip_update.trip.trip_id in trip_ids:
            print(f"Duplicate trip_id found: {entity.trip_update.trip.trip_id}")
        trip_ids.add(entity.trip_update.trip.trip_id)
        if 'schedule_relationship' not in entity.trip_update.trip:
            for stop_time_update in entity.trip_update.stop_time_update:
                if 'arrival' in stop_time_update and 'delay' in stop_time_update.arrival:
                    print(f"Trip {entity.trip_update.trip.trip_id} with no schedule relationship has stop time updates with arrival delay")
                    break
        if 'schedule_relationship' in entity.trip_update.trip and entity.trip_update.trip.schedule_relationship == 0:
            if not entity.trip_update.stop_time_update:
                # print(f"Trip {entity.trip_update.trip.trip_id} has schedule relationship but no stop time updates")
                continue
            found_delay = False
            for stop_time_update in entity.trip_update.stop_time_update:
                if 'schedule_relationship' not in stop_time_update:
                    print(f"Trip {entity.trip_update.trip.trip_id} with schedule relationship has a stop time update with no schedule relationship")
                    break
                if 'arrival' in stop_time_update and 'delay' in stop_time_update.arrival:
                    found_delay = True
                    break
            if not found_delay:
                print(f"Trip {entity.trip_update.trip.trip_id} with schedule relationship has stop time updates but no arrival delay")
                continue
    # what we get from this is that we don't care about trips with no schedule relationship,
    # we only care about trips with schedule relationship 0 (on time) or 3 (cancelled)
    # if it is 3 it should not have any stop time updates and we don't care about them anyway
    # if it is 0, it should have stop time updates with arrival delays etc, if it doesn't, then
    # it has skipped stops which stays for the day.

def print_replaced(feed):
    replaced = set()
    cancelled = set()
    for entity in feed.entity:
        if entity.trip_update.trip.schedule_relationship == 5:
            replaced.add(entity.trip_update.trip.trip_id)
        elif entity.trip_update.trip.schedule_relationship == 3:
            cancelled.add(entity.trip_update.trip.trip_id)
    else:
        print(f"Replaced trips: {replaced.intersection(cancelled)}")
    print(f"Cancelled trips: {len(cancelled)}")

def write_json(feed):
    feed_dict = MessageToDict(feed)
    with open("train_feed_data.json", "w") as f:
        json.dump(feed_dict, f, indent=2)

def cache_delay_data(cursor, delay_data):
    # get a map of trip_id to stop_id that we currently have in the database
    cursor.execute("SELECT trip_id, stop_id FROM delays")
    trip_id_map = {row[0]: row[1] for row in cursor.fetchall()}
    
    # we need to cache if the next stop_id of trip_id has been received
    to_cache = set()
    for i, trip_id in enumerate(delay_data['trip_id']):
        if trip_id in trip_id_map and delay_data['stop_id'][i] != trip_id_map[trip_id]:
            to_cache.add(trip_id)

    # we also need to cache if trip_id from the database is not in the new data
    missing_trip_ids = set(trip_id_map.keys()) - set(delay_data['trip_id']) # used later to know a route has been completed
    to_cache.update(missing_trip_ids)

    if not to_cache:
        return

    # get the data to cache
    placeholders = ','.join(['%s']*len(to_cache))
    query = f"""
        SELECT route_short_name, stop_id, arrival_delay, departure_early
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
            datetime.now(ZoneInfo('Australia/Sydney')).date(),
            arrival_delay, 
            departure_early,
        ] + [
            1 if arrival_delay > above_value * 60 else 0 for above_value in above_ranges
        ] + [
            1 if departure_early > before_value * 60 else 0 for before_value in before_ranges
        ]
        for route_short_name, stop_id, arrival_delay, departure_early in rows_to_cache
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
    for route_short_name, trip_id, arrival_delay, departure_early in rows_to_cache:
        if route_short_name not in aggregate_cached:
            aggregate_cached[route_short_name] = {
                'total_delay': 0, 
                'total_early' : 0, 
                'total_count': 0,
                **{f'above_{n}_minutes': 0 for n in above_ranges},
                **{f'before_{n}_minutes': 0 for n in before_ranges},
                'total_trips': 0,
            }
        aggregate_cached[route_short_name]['total_delay'] += arrival_delay
        aggregate_cached[route_short_name]['total_early'] += departure_early
        aggregate_cached[route_short_name]['total_count'] += 1
        if trip_id in missing_trip_ids:
            aggregate_cached[route_short_name]['total_trips'] += 1
        for x in above_ranges:
            if arrival_delay > x * 60:
                aggregate_cached[route_short_name][f'above_{x}_minutes'] += 1
        for x in before_ranges:
            if departure_early > x * 60:
                aggregate_cached[route_short_name][f'before_{x}_minutes'] += 1
    
    # insert the aggregated data
    data_to_insert = [
        (
            route_short_name, 
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
        for route_short_name, data in aggregate_cached.items()
    ]
    cursor.executemany("""
        INSERT INTO route_daily_delays (route_short_name, date, total_delay, total_early, total_count, above_1_minute, above_2_minutes, above_5_minutes, above_10_minutes, above_15_minutes, above_30_minutes, before_1_minute, before_2_minutes, before_5_minutes, before_10_minutes, total_trips)
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
    cursor.execute("SELECT trip_id, route_short_name, date FROM cancels")
    rows = cursor.fetchall()
    curr_cancel_data = {
        'trip_id' : [row[0] for row in rows],
        'route_short_name' : [row[1] for row in rows],
        'date' : [row[2] for row in rows],
    }

    # see what cancellations are in the database but not in the new data
    to_cache = set(curr_cancel_data['trip_id']) - set(cancel_data['trip_id'])

    if not to_cache:
        return
    
    query = """
        INSERT INTO route_daily_delays (route_short_name, date, total_cancelled, total_trips)
        VALUES (%s, %s, 1, 1)
        ON DUPLICATE KEY UPDATE
            total_cancelled = total_cancelled + 1,
            total_trips = total_trips + 1
    """
    data_to_cache = [[
        curr_cancel_data['route_short_name'][i],
        curr_cancel_data['date'][i],
    ] for i in range(len(curr_cancel_data['trip_id'])) if curr_cancel_data['trip_id'][i] in to_cache]
    cursor.executemany(query, data_to_cache)

    placeholders = ','.join(['%s']*len(to_cache))
    query = f"""
        DELETE FROM cancels
        WHERE trip_id IN ({placeholders})
    """
    cursor.execute(query, tuple(to_cache))

    print(f'Cached {len(data_to_cache)} cancellations')

def cache_skip_data(cursor, skip_data):
    # get current cancellations in the database
    cursor.execute("SELECT trip_id, route_short_name, stop_id, date FROM skips")
    rows = cursor.fetchall()
    curr_skip_data = {
        'trip_id' : [row[0] for row in rows],
        'route_short_name' : [row[1] for row in rows],
        'stop_id' : [row[2] for row in rows],
        'date' : [row[3] for row in rows],
    }

    # see what cancellations are in the database but not in the new data
    to_cache = set(list(zip(curr_skip_data['trip_id'], curr_skip_data['stop_id']))) - set(list(zip(skip_data['trip_id'], skip_data['stop_id'])))
    
    if not to_cache:
        return
    
    query = """
        INSERT INTO stop_daily_delays (route_short_name, stop_id, date, total_cancelled, total_trips)
        VALUES (%s, %s, %s, 1, 1)
        ON DUPLICATE KEY UPDATE
            total_cancelled = total_cancelled + 1,
            total_trips = total_trips + 1
    """
    data_to_cache = [[
        curr_skip_data['route_short_name'][i],
        curr_skip_data['stop_id'][i],
        curr_skip_data['date'][i],
    ] for i in range(len(curr_skip_data['trip_id'])) if (curr_skip_data['trip_id'][i], curr_skip_data['stop_id'][i]) in to_cache]
    cursor.executemany(query, data_to_cache)

    query = f"""
        DELETE FROM skips
        WHERE trip_id = %s AND stop_id = %s
    """
    cursor.executemany(query, tuple(to_cache))

    print(f'Cached {len(data_to_cache)} skips')

def insert_or_update_delays(cursor, delay_data):
    data = list(zip(
        delay_data['trip_id'],
        delay_data['route_short_name'],
        delay_data['stop_id'],
        delay_data['arrival_delay'],
        delay_data['departure_early'],
    ))

    query = """
        INSERT INTO delays (trip_id, route_short_name, stop_id, arrival_delay, departure_early)
        VALUES (%s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            arrival_delay = VALUES(arrival_delay),
            departure_early = VALUES(departure_early)
    """

    cursor.executemany(query, data)

    print(f'Inserted/Updated {len(data)} rows')

def insert_or_update_cancels(cursor, cancel_data):
    cursor.execute("SELECT trip_id FROM cancels")
    current_cancels = set(row[0] for row in cursor.fetchall())
    new_cancels = set(cancel_data['trip_id']) - current_cancels
    if not new_cancels:
        return
    query = """
        INSERT INTO cancels (trip_id, route_short_name, date)
        VALUES (%s, %s, %s)
    """
    data = [[
        cancel_data['trip_id'][i], 
        cancel_data['route_short_name'][i],
        datetime.now(ZoneInfo('Australia/Sydney')).date()
    ] for i in range(len(cancel_data['trip_id'])) if cancel_data['trip_id'][i] in new_cancels]
    cursor.executemany(query, data)

    print(f'Inserted {len(data)} new cancellations')

def insert_or_update_skips(cursor, skip_data):
    cursor.execute("SELECT trip_id, stop_id FROM skips")
    current_skips = set((row[0], row[1]) for row in cursor.fetchall())
    new_skips = set(list(zip(skip_data['trip_id'], skip_data['stop_id']))) - current_skips
    if not new_skips:
        return
    query = """
        INSERT INTO skips (trip_id, route_short_name, stop_id, date)
        VALUES (%s, %s, %s, %s)
    """
    data = [[
        skip_data['trip_id'][i], 
        skip_data['route_short_name'][i],
        skip_data['stop_id'][i],
        datetime.now(ZoneInfo('Australia/Sydney')).date()
    ] for i in range(len(skip_data['trip_id'])) if (skip_data['trip_id'][i], skip_data['stop_id'][i]) in new_skips]
    cursor.executemany(query, data)

    print(f'Inserted {len(data)} new skips')

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
        delay_data, cancel_data, skip_data = parse_feed(feed)

        catch_changes(cursor, delay_data, cancel_data)

        cache_delay_data(cursor, delay_data)
        insert_or_update_delays(cursor, delay_data)

        cache_cancel_data(cursor, cancel_data)
        insert_or_update_cancels(cursor, cancel_data)

        cache_skip_data(cursor, skip_data)
        insert_or_update_skips(cursor, skip_data)

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

