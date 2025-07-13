import csv
from collections import defaultdict
import polyline
from simplification.cutil import simplify_coords
from functions import get_connection

with open('routes.txt', newline='', encoding='utf-8') as csvfile:
    valid_routes = set(row['route_id'] for row in csv.DictReader(csvfile) if row['route_desc'] not in ['School Buses', 'Temporary Buses', 'Newcastle Ferries'])

route_id_to_shape_ids = defaultdict(dict)
with open('trips.txt', "r", encoding="utf-8-sig") as csvfile:
    reader = csv.DictReader(csvfile)
    for row in reader:
        if row['route_id'] in valid_routes:
            if row['shape_id'] not in route_id_to_shape_ids[row['route_id']]:
                route_id_to_shape_ids[row['route_id']][row['shape_id']] = 0
            route_id_to_shape_ids[row['route_id']][row['shape_id']] += 1
            
route_id_to_shape_ids = {k: [s[0] for s in sorted(v.items(), key=lambda x: -x[1])[:2]] for k, v in route_id_to_shape_ids.items()}
# route_id_to_shape_ids = {k: [s[0] for s in v.items()] for k, v in route_id_to_shape_ids.items()}

shape_points = defaultdict(list)
with open('shapes.txt', "r", encoding="utf-8-sig") as f:
    reader = csv.DictReader(f)
    for i, row in enumerate(reader):
        shape_points[row['shape_id']].append([float(row["shape_pt_lon"]), float(row["shape_pt_lat"])])

conn, cursor = get_connection()
shapes_to_insert = []
for route_id, shape_ids in route_id_to_shape_ids.items():
    for shape_id in shape_ids:
        simplified_points = simplify_coords(shape_points[shape_id], 0.0001)
        lat_lon_points = [[p[1], p[0]] for p in simplified_points]
        encoded_polyline = polyline.encode(lat_lon_points)
        shapes_to_insert.append((route_id, shape_id, encoded_polyline))
cursor.executemany("INSERT INTO route_shapes (route_id, shape_id, shape_encoded) VALUES (%s, %s, %s)", shapes_to_insert)
conn.commit()
cursor.close()
conn.close()