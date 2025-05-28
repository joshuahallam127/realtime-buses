import csv

route_id_to_long_name = {}
school_bus_route_ids = set()
agency_route_to_route_id = {}
with open('routes.txt', newline='', encoding='utf-8') as csvfile:
    reader = csv.DictReader(csvfile)
    for row in reader:
        if row['route_desc'] == 'School buses':
            school_bus_route_ids.add(row['\ufeffroute_id'])
            continue
        route_id_to_long_name[row['\ufeffroute_id']] = row['route_long_name']
        agency_route_to_route_id[(row['agency_id'], row['route_short_name'])] = row['\ufeffroute_id']

trip_id_to_route_id = {}
with open('trips.txt', newline='', encoding='utf-8') as csvfile:
    reader = csv.DictReader(csvfile)
    for row in reader:
        trip_id_to_route_id[row['trip_id']] = row['\ufeffroute_id']

route_id_to_stop_ids = {
    route_id: set() for route_id in route_id_to_long_name.keys()
}
with open('stop_times.txt', newline='', encoding='utf-8') as csvfile:
    reader = csv.DictReader(csvfile)
    for row in reader:
        if trip_id_to_route_id[row['\ufefftrip_id']] in school_bus_route_ids:
            continue
        route_id_to_stop_ids[trip_id_to_route_id[row['\ufefftrip_id']]].add(row['stop_id'])

stop_id_to_lat_long = {}
with open('stops.txt', newline='', encoding='utf-8') as csvfile:
    reader = csv.DictReader(csvfile)
    for row in reader:
        stop_id_to_lat_long[row['\ufeffstop_id']] = {
            'lat' : row['stop_lat'], 
            'long' : row['stop_lon'],
        }

sydney_bottom_right = (-34.114276, 151.236798)
sydney_top_right = (-33.577069, 151.404339)
sydney_top_left = (-33.535870, 150.771252)
sydney_bottom_left = (-34.072197, 150.547406)

sydney_routes = set()
for route_id, stop_ids in route_id_to_stop_ids.items():
    if len(stop_ids) < 2:
        print('Route has less than 2 stops:', route_id)
        continue
    for stop_id in stop_ids:
        if stop_id not in stop_id_to_lat_long:
            print('Stop ID not found in stop_id_to_lat_long:', stop_id)
            continue
        lat = float(stop_id_to_lat_long[stop_id]['lat'])
        long = float(stop_id_to_lat_long[stop_id]['long'])
        if (sydney_bottom_right[0] <= lat <= sydney_top_right[0] and
            sydney_bottom_left[1] <= long <= sydney_bottom_right[1]):
            sydney_routes.add(route_id)
            break
    else:
        print('No valid stops found for route:', route_id)

for route_id in sydney_routes:
    if route_id not in route_id_to_long_name:
        print('Route ID not found in route_id_to_long_name:', route_id)
        continue
    print(f'Route: {route_id_to_long_name[route_id]}')
print(f'Total routes found: {len(sydney_routes)}')