import polyline
import math
import csv
from collections import defaultdict
from functions import get_connection

def haversine_distance(lat1, lon1, lat2, lon2):
    """calculate distance between two points in meters"""
    R = 6371000  # earth radius in meters
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = math.sin(delta_lat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def find_closest_point_on_shape(stop_lat, stop_lon, shape_points):
    """find the minimum distance from a stop to any point on a shape"""
    min_distance = float('inf')
    
    for i in range(len(shape_points) - 1):
        segment_start = shape_points[i]
        segment_end = shape_points[i + 1]
        
        # convert lon,lat to lat,lon for distance calculation
        start_lat, start_lon = segment_start[1], segment_start[0]
        end_lat, end_lon = segment_end[1], segment_end[0]
        
        # vector from start to end
        dx = end_lon - start_lon
        dy = end_lat - start_lat
        
        # vector from start to stop
        px = stop_lon - start_lon
        py = stop_lat - start_lat
        
        # calculate t parameter (projection)
        length_squared = dx * dx + dy * dy
        if length_squared == 0:
            # segment is a point
            distance = haversine_distance(stop_lat, stop_lon, start_lat, start_lon)
        else:
            t = max(0, min(1, (px * dx + py * dy) / length_squared))
            
            # find closest point on segment
            closest_lat = start_lat + t * dy
            closest_lon = start_lon + t * dx
            
            distance = haversine_distance(stop_lat, stop_lon, closest_lat, closest_lon)
        
        min_distance = min(min_distance, distance)
    
    return min_distance


def score_shape_for_stops(shape_points, stops):
    """score how well a shape covers the given stops"""
    if not shape_points or not stops:
        return 0
    
    total_score = 0
    stops_within_500m = 0
    
    for stop in stops:
        stop_lat = float(stop['lat'])
        stop_lon = float(stop['lon'])
        
        min_distance = find_closest_point_on_shape(stop_lat, stop_lon, shape_points)
        
        # scoring: closer stops get higher scores
        if min_distance <= 100:  # within 100m
            total_score += 100
            stops_within_500m += 1
        elif min_distance <= 200:  # within 200m
            total_score += 50
            stops_within_500m += 1
        elif min_distance <= 500:  # within 500m
            total_score += 10
            stops_within_500m += 1
        # stops further than 500m get 0 points
    
    # bonus for covering more stops
    coverage_bonus = (stops_within_500m / len(stops)) * 100
    
    return total_score + coverage_bonus


def get_route_stops_from_gtfs():
    """Load stops for each route from GTFS files"""
    print("Loading GTFS data...")
    
    # Load all stops
    stops_data = {}
    with open('stops.txt', 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            stops_data[row['stop_id']] = {
                'lat': float(row['stop_lat']),
                'lon': float(row['stop_lon']),
                'name': row['stop_name']
            }
    
    # Load trips to get route_id for each trip
    trip_to_route = {}
    with open('trips.txt', 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            trip_to_route[row['trip_id']] = row['route_id']
    
    # Load stop_times and group stops by route
    route_stops = defaultdict(set)
    with open('stop_times.txt', 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            trip_id = row['trip_id']
            stop_id = row['stop_id']
            
            if trip_id in trip_to_route and stop_id in stops_data:
                route_id = trip_to_route[trip_id]
                route_stops[route_id].add(stop_id)
    
    # Convert to final format
    route_stops_data = {}
    for route_id, stop_ids in route_stops.items():
        route_stops_data[route_id] = [
            {
                'lat': stops_data[stop_id]['lat'],
                'lon': stops_data[stop_id]['lon'],
                'name': stops_data[stop_id]['name']
            }
            for stop_id in stop_ids
        ]
    
    print(f"Loaded stops for {len(route_stops_data)} routes")
    return route_stops_data


def consolidate_route_shapes():
    """replace multiple shapes per route with the single best shape"""
    conn, cursor = get_connection()
    
    # Load route stops from GTFS
    route_stops_data = get_route_stops_from_gtfs()
    
    # get all routes with multiple shapes
    print("Fetching routes with multiple shapes...")
    cursor.execute("""
        SELECT route_id, COUNT(*) as shape_count
        FROM route_shapes
        GROUP BY route_id
        HAVING COUNT(*) > 1
        ORDER BY shape_count DESC
    """)
    routes_with_multiple_shapes = cursor.fetchall()
    
    print(f"Found {len(routes_with_multiple_shapes)} routes with multiple shapes")
    
    for route_id, shape_count in routes_with_multiple_shapes:
        print(f"\nProcessing route {route_id} ({shape_count} shapes)...")
        
        # get all shapes for this route
        cursor.execute("""
            SELECT id, shape_id, shape_encoded
            FROM route_shapes
            WHERE route_id = %s
        """, (route_id,))
        shape_rows = cursor.fetchall()
        
        # get stops for this route from GTFS data
        stops = route_stops_data.get(route_id, [])
        
        if not stops:
            print(f"  No stops found for route {route_id}, keeping first shape...")
            # keep only the first shape
            shapes_to_delete = [row[0] for row in shape_rows[1:]]
            if shapes_to_delete:
                placeholders = ','.join(['%s'] * len(shapes_to_delete))
                cursor.execute(f"DELETE FROM route_shapes WHERE id IN ({placeholders})", shapes_to_delete)
            continue

        print(f"  Found {len(shape_rows)} shapes and {len(stops)} stops")
        
        # score each shape
        best_shape = None
        best_score = -1
        
        for shape_row in shape_rows:
            _, shape_name, encoded_shape = shape_row
            
            if not encoded_shape:
                continue
                
            try:
                decoded = polyline.decode(encoded_shape)
                # convert lat,lon to lon,lat for internal processing
                shape_points = [[point[1], point[0]] for point in decoded]
                
                score = score_shape_for_stops(shape_points, stops)
                print(f"    Shape {shape_name}: score = {score:.1f}")
                
                if score > best_score:
                    best_score = score
                    best_shape = shape_row
                    
            except Exception as e:
                print(f"    Error decoding shape {shape_name}: {e}")
                continue
        
        if not best_shape:
            print(f"  No valid shapes found for route {route_id}")
            continue
            
        best_shape_id = best_shape[0]
        print(f"  Best shape: {best_shape[1]} (score: {best_score:.1f})")
        
        # delete all other shapes for this route
        cursor.execute("""
            DELETE FROM route_shapes 
            WHERE route_id = %s AND id != %s
        """, (route_id, best_shape_id))
        
        deleted_count = cursor.rowcount
        print(f"  Deleted {deleted_count} inferior shapes")
        
    conn.commit()
    print(f"\nSuccessfully consolidated shapes for {len(routes_with_multiple_shapes)} routes")
        
    cursor.close()
    conn.close()


if __name__ == "__main__":
    consolidate_route_shapes() 