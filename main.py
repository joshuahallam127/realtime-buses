from google.transit import gtfs_realtime_pb2
from google.protobuf.json_format import MessageToDict
import requests
import os
from dotenv import load_dotenv
import json
import functions
import time
from mysql.connector.errors import OperationalError

load_dotenv()

INTERVAL = 5

def print_example_data(data, items = 10, start = 0):
    for k, v in data.items():
        print(f'{k}: {v[start:start+items]}')

url = 'https://api.transport.nsw.gov.au/v1/gtfs/realtime/buses'
headers = {
    'Authorization': f'apikey {os.getenv("APIKEY")}',
}

def run():
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        feed = gtfs_realtime_pb2.FeedMessage()
        feed.ParseFromString(response.content)
        return feed
    else:
        print(f'Error: {response.status_code}')
        print(response.text)

def parse_feed(feed, cursor=None):
    result = {
        'trip_id' : [],
        'route' : [],
        'stop_sequence' : [],
        'arrival_delay' : [],
        'departure_early' : [],
        'start_date' : [],
    }
    # trip_ids = set()
    # cursor.execute("SELECT trip_id FROM delays")
    # curr_trip_ids = cursor.fetchall()
    # database_trip_ids = set([trip[0] for trip in curr_trip_ids])
    for entity in feed.entity:
        trip_id = entity.trip_update.trip.trip_id
        # if trip_id in trip_ids:
        #     # print('Duplicate trip_id:', trip_id)
        #     # write_json(feed)
        #     continue
        # trip_ids.add(trip_id)
        # if entity.trip_update.trip.schedule_relationship == 3:
        #     if trip_id in database_trip_ids:
        #         write_cancelled(trip_id)
        #     continue
        if entity.trip_update.trip.schedule_relationship == 0 and entity.trip_update.stop_time_update[0].stop_sequence != 1:
            result['trip_id'].append(trip_id)
            result['route'].append(entity.trip_update.trip.route_id.split('_')[1])
            result['stop_sequence'].append(entity.trip_update.stop_time_update[0].stop_sequence)
            result['arrival_delay'].append(max(0, entity.trip_update.stop_time_update[0].arrival.delay))
            result['departure_early'].append(min(0, entity.trip_update.stop_time_update[0].departure.delay) * -1)
            result['start_date'].append(entity.trip_update.trip.start_date)
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

def insert_or_update_delays(cursor, delay_data, chunk_size=1000):
    data = list(zip(
        delay_data['trip_id'],
        delay_data['route'],
        delay_data['stop_sequence'],
        delay_data['arrival_delay'],
        delay_data['departure_early'],
        delay_data['start_date'],
    ))

    query = """
        INSERT INTO delays (trip_id, route, stop_sequence, arrival_delay, departure_early, start_date)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE arrival_delay = VALUES(arrival_delay) AND departure_early = VALUES(departure_early)
    """

    for i in range(0, len(data), chunk_size):
        chunk = data[i:i+chunk_size]
        cursor.executemany(query, chunk)

    print(f'Inserted/Updated {len(data)} rows')

# Open connection once
conn, cursor = None, None

while True:
    start_time = time.time()

    try:
        if conn is None or not conn.is_connected():
            conn, cursor = functions.get_connection()

        feed = run()
        delay_data = parse_feed(feed, cursor)

        insert_or_update_delays(cursor, delay_data)

        conn.commit()

    except OperationalError as e:
        print("Database connection error, retrying:", e)
        conn, cursor = None, None
        time.sleep(5)
        continue

    except Exception as e:
        print("Unexpected error:", e)

    elapsed = time.time() - start_time
    print(f'Elapsed time: {elapsed:.2f} seconds')
    sleep_time = max(0, INTERVAL - elapsed)
    print(f'Sleeping for {sleep_time:.2f} seconds')
    time.sleep(sleep_time)