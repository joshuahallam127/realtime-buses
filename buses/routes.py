import csv
from functions import get_connection

with open('routes.txt', newline='', encoding='utf-8') as csvfile:
    routes_data = [row for row in csv.DictReader(csvfile) if row['route_desc'] not in ['School Buses', 'Temporary Buses', 'Newcastle Ferries']]

with open('trips.txt', newline='', encoding='utf-8') as csvfile:
    trip_id_to_route_id = { row['trip_id']: row['route_id'] for row in csv.DictReader(csvfile)}

# get all the stop_ids for each route_id
route_id_to_stop_ids = { route_id: set() for route_id in [row['route_id'] for row in routes_data] }
with open('stop_times.txt', newline='', encoding='utf-8') as csvfile:
    reader = csv.DictReader(csvfile)
    for row in reader:
        if trip_id_to_route_id[row['trip_id']] not in route_id_to_stop_ids:
            continue
        route_id_to_stop_ids[trip_id_to_route_id[row['trip_id']]].add(row['stop_id'])

# get stop_id to lat/long mapping
stop_id_to_lat_long = {}
with open('stops.txt', newline='', encoding='utf-8') as csvfile:
    reader = csv.DictReader(csvfile)
    for row in reader:
        stop_id_to_lat_long[row['stop_id']] = {
            'lat' : row['stop_lat'], 
            'long' : row['stop_lon'],
        }

sydney_bottom_right = (-34.114276, 151.236798)
sydney_top_right = (-33.577069, 151.404339)
sydney_top_left = (-33.535870, 150.771252)
sydney_bottom_left = (-34.072197, 150.547406)
sydney_routes = set()
for route_id, stop_ids in route_id_to_stop_ids.items():
    for stop_id in stop_ids:
        lat = float(stop_id_to_lat_long[stop_id]['lat'])
        long = float(stop_id_to_lat_long[stop_id]['long'])
        if (sydney_bottom_right[0] <= lat <= sydney_top_right[0] and
            sydney_bottom_left[1] <= long <= sydney_bottom_right[1]):
            sydney_routes.add(route_id)
            break

conn, cursor = get_connection()
cursor.executemany("""
    INSERT INTO routes (id, long_name, is_in_sydney)
    VALUES (%s, %s, %s)
    ON DUPLICATE KEY UPDATE
        long_name = VALUES(long_name),
        is_in_sydney = VALUES(is_in_sydney)
""", [(route['route_id'], route['route_long_name'], route['route_id'] in sydney_routes) for route in routes_data])
conn.commit()
cursor.close()
conn.close()
