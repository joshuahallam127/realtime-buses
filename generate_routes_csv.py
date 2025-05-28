import csv

'''
This script needs routes.txt, trips.txt, stop_times.txt, and stops.txt files from the GTFS data.
It is only to be run locally to generate a CSV file of bus routes in Sydney.
After git pushing to the server, the update_routes.py script will be run to update the database with the new routes.
'''

# get routes data excluding school buses
routes_data = []
with open('routes.txt', newline='', encoding='utf-8') as csvfile:
    reader = csv.DictReader(csvfile)
    for row in reader:
        if row['route_desc'] in [
            'School buses',
            'Temporary buses',
            'Temporary coaches',
        ]:
            continue
        routes_data.append(row)

# link trip_id to route_id because stop_times.txt uses trip_id which is how we will get each stop on the route
trip_id_to_route_id = {}
with open('trips.txt', newline='', encoding='utf-8') as csvfile:
    reader = csv.DictReader(csvfile)
    for row in reader:
        trip_id_to_route_id[row['trip_id']] = row['\ufeffroute_id']

# get all the stop_ids for each route_id
route_id_to_stop_ids = {
    route_id: set() for route_id in [row['\ufeffroute_id'] for row in routes_data]
}
with open('stop_times.txt', newline='', encoding='utf-8') as csvfile:
    reader = csv.DictReader(csvfile)
    for row in reader:
        if trip_id_to_route_id[row['\ufefftrip_id']] not in route_id_to_stop_ids:
            continue
        route_id_to_stop_ids[trip_id_to_route_id[row['\ufefftrip_id']]].add(row['stop_id'])

# get stop_id to lat/long mapping
stop_id_to_lat_long = {}
with open('stops.txt', newline='', encoding='utf-8') as csvfile:
    reader = csv.DictReader(csvfile)
    for row in reader:
        stop_id_to_lat_long[row['\ufeffstop_id']] = {
            'lat' : row['stop_lat'], 
            'long' : row['stop_lon'],
        }

# define the bounding box for Sydney
sydney_bottom_right = (-34.114276, 151.236798)
sydney_top_right = (-33.577069, 151.404339)
sydney_top_left = (-33.535870, 150.771252)
sydney_bottom_left = (-34.072197, 150.547406)

# filter routes that have at least one stop within the bounding box
sydney_routes = set()
for route_id, stop_ids in route_id_to_stop_ids.items():
    for stop_id in stop_ids:
        lat = float(stop_id_to_lat_long[stop_id]['lat'])
        long = float(stop_id_to_lat_long[stop_id]['long'])
        if (sydney_bottom_right[0] <= lat <= sydney_top_right[0] and
            sydney_bottom_left[1] <= long <= sydney_bottom_right[1]):
            sydney_routes.add(route_id)
            break

# write the filtered routes to a new CSV file
with open('routes.csv', 'w', newline='', encoding='utf-8') as csvfile:
    fieldnames = ['id', 'long_name', 'is_in_sydney']
    writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
    writer.writeheader()
    for route in routes_data:
        writer.writerow({
            'id': route['agency_id'] + '_' + route['route_short_name'],
            'long_name': route['route_long_name'],
            'is_in_sydney': route['\ufeffroute_id'] in sydney_routes
        })
