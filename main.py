from google.transit import gtfs_realtime_pb2
from google.protobuf.json_format import MessageToDict
import requests
import os
from dotenv import load_dotenv
import json
import functions
import time

load_dotenv()

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
        feed_dict = MessageToDict(feed)
        # with open("feed_data.json", "w") as f:
        #     json.dump(feed_dict, f, indent=2)
        return feed
    else:
        print(f'Error: {response.status_code}')
        print(response.text)
def parse_feed(feed):
    result = {
        'trip_id' : [],
        'route' : [],
        'stop_sequence' : [],
        'arrival_delay' : [],
        'start_date' : [],
    }
    trip_ids = set()
    for entity in feed.entity:
        if entity.trip_update.trip.trip_id in trip_ids:
            print('Duplicate trip_id:', entity.trip_update.trip.trip_id)
            continue
        trip_ids.add(entity.trip_update.trip.trip_id)
        if len(entity.trip_update.stop_time_update) == 0:
            continue
        result['trip_id'].append(entity.trip_update.trip.trip_id)
        result['route'].append(entity.trip_update.trip.route_id.split('_')[1])
        result['stop_sequence'].append(entity.trip_update.stop_time_update[0].stop_sequence)
        result['arrival_delay'].append(entity.trip_update.stop_time_update[0].arrival.delay)
        result['start_date'].append(entity.trip_update.trip.start_date)
    return result

while True:
    feed = run()
    delay_data = parse_feed(feed)

    conn, cursor = functions.get_connection()
    for i in range(len(delay_data['trip_id'])):
        cursor.execute("""
            INSERT INTO delays (trip_id, route, stop_sequence, arrival_delay, start_date)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE arrival_delay = VALUES(arrival_delay)
        """, (
            delay_data['trip_id'][i],
            delay_data['route'][i],
            delay_data['stop_sequence'][i],
            delay_data['arrival_delay'][i],
            delay_data['start_date'][i],
        ))
    conn.commit()
    cursor.close()
    conn.close()
    print('Inserted/Updated', len(delay_data['trip_id']), 'rows')
    time.sleep(5)
