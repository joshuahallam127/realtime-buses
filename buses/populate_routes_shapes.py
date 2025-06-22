import csv
from collections import defaultdict
import os
import mysql.connector
from dotenv import load_dotenv
import polyline
from simplification.cutil import simplify_coords


def get_connection():
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
    """Establishes a connection to the 'buses' database."""
    try:
        connection = mysql.connector.connect(
            host=os.getenv("RDS_HOST", "127.0.0.1"),
            port=int(os.getenv("RDS_PORT", 3308)),
            user=os.getenv("RDS_USER", "root"),
            password=os.getenv("RDS_PASSWORD", "password"),
            database="buses",
        )
        return connection
    except mysql.connector.Error as err:
        print(f"Error connecting to the database: {err}")
        return None


def populate_bus_shapes():
    """
    Parses GTFS data to populate the 'route_shapes' table in the database
    with route geographical data.
    """
    buses_dir = os.path.dirname(os.path.abspath(__file__))
    routes_file = os.path.join(buses_dir, "routes.txt")
    trips_file = os.path.join(buses_dir, "trips.txt")
    shapes_file = os.path.join(buses_dir, "shapes.txt")

    # Mapping from GTFS route_id to the application's database id
    print("Mapping GTFS route_id to database-compatible id from routes.txt...")
    gtfs_id_to_db_id = {}
    try:
        with open(routes_file, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                gtfs_route_id = row.get("\ufeffroute_id") or row.get("route_id")
                agency_id = row.get("agency_id")
                short_name = row.get("route_short_name")
                if gtfs_route_id and agency_id and short_name:
                    db_id = f"{agency_id}_{short_name}"
                    gtfs_id_to_db_id[gtfs_route_id] = db_id
    except FileNotFoundError:
        print(f"Error: {routes_file} not found.")
        return

    # Mapping of database-compatible route id to shape_ids
    print("Mapping route ids to shape IDs from trips.txt...")
    db_id_to_shape_ids = defaultdict(set)
    try:
        with open(trips_file, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                gtfs_route_id = row.get("\ufeffroute_id") or row.get("route_id")
                shape_id = row.get("shape_id")
                if gtfs_route_id in gtfs_id_to_db_id and shape_id:
                    db_id = gtfs_id_to_db_id[gtfs_route_id]
                    db_id_to_shape_ids[db_id].add(shape_id)
    except FileNotFoundError:
        print(f"Error: {trips_file} not found.")
        return
    print(f"Found {len(db_id_to_shape_ids)} routes with shapes.")

    # Reading shape data points
    print("Reading shape data from shapes.txt...")
    shape_points = defaultdict(list)
    try:
        with open(shapes_file, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for i, row in enumerate(reader):
                if i > 0 and i % 2000000 == 0:
                    print(f"  ...processed {i} shape points")

                shape_id = row.get("shape_id")
                if not shape_id:
                    continue
                try:
                    lon = float(row["shape_pt_lon"])
                    lat = float(row["shape_pt_lat"])
                    seq = int(row["shape_pt_sequence"])
                    shape_points[shape_id].append({"lon": lon, "lat": lat, "seq": seq})
                except (ValueError, KeyError):
                    continue
    except FileNotFoundError:
        print(f"Error: {shapes_file} not found.")
        return
    print(f"Read {len(shape_points)} distinct shapes.")

    # Sorting points by sequence to form paths
    print("Sorting shape points by sequence...")
    sorted_shapes = {}
    for shape_id, points in shape_points.items():
        points.sort(key=lambda p: p["seq"])
        sorted_shapes[shape_id] = [[p["lon"], p["lat"]] for p in points]
    del shape_points

    # Database insertion
    conn = get_connection()
    if not conn:
        return
    cursor = conn.cursor()

    sydney_bounds = {
        "west": 151.1,
        "east": 151.25,
        "south": -33.95,
        "north": -33.82,
    }

    def is_shape_in_bounds(points, bounds):
        for lon, lat in points:
            if not (bounds["west"] <= lon <= bounds["east"] and bounds["south"] <= lat <= bounds["north"]):
                return False
        return True

    try:
        print("Connected to database. Clearing existing shapes...")
        cursor.execute("DELETE FROM route_shapes")
        conn.commit()

        print("Inserting new shapes into database...")
        insert_query = "INSERT INTO route_shapes (route_id, shape_id, shape_encoded, is_fully_in_central_sydney) VALUES (%s, %s, %s, %s)"
        shapes_to_insert = []
        for db_id, shape_ids in db_id_to_shape_ids.items():
            for shape_id in shape_ids:
                if shape_id in sorted_shapes:
                    points = sorted_shapes[shape_id]
                    if len(points) > 1:
                        simplified_points = simplify_coords(points, 0.0001)
                        lat_lon_points = [[p[1], p[0]] for p in simplified_points]
                        encoded_polyline = polyline.encode(lat_lon_points)

                        is_central = is_shape_in_bounds(points, sydney_bounds)

                        shapes_to_insert.append((db_id, shape_id, encoded_polyline, is_central))

        if shapes_to_insert:
            chunk_size = 500
            total_inserted = 0
            for i in range(0, len(shapes_to_insert), chunk_size):
                chunk = shapes_to_insert[i : i + chunk_size]
                cursor.executemany(insert_query, chunk)
                conn.commit()
                total_inserted += cursor.rowcount
                print(f"Inserted {total_inserted}/{len(shapes_to_insert)} shapes...")

            print(f"Successfully inserted {total_inserted} shapes into the database.")
        else:
            print("No shapes to insert.")

    except mysql.connector.Error as err:
        print(f"Database error: {err}")
    finally:
        cursor.close()
        conn.close()
        print("Database connection closed.")


if __name__ == "__main__":
    populate_bus_shapes()
