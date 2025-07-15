import traceback
from flask import Flask, jsonify, request
import mysql.connector
from dotenv import load_dotenv
from flask_cors import CORS
import os
from zoneinfo import ZoneInfo
from datetime import datetime, timedelta
import json
from collections import defaultdict
import time

NUM_FEATURED_ROUTES = 5
FEATURED_ROUTES_TIME_PERIOD_DAYS = 7
CACHE_TIMEOUT_SECONDS = 60 * 2

featured_routes_cache = {
    "delay": {"data": None, "last_updated": 0},
    "early": {"data": None, "last_updated": 0},
}

load_dotenv()

app = Flask(__name__)
CORS(
    app,
    origins=[
        "https://howshitismybus.com.au",
        "https://www.howshitismybus.com.au",
        "https://howshitismytrain.com.au",
        "https://www.howshitismytrain.com.au",
    ],
)


def get_connection(database):
    connection = mysql.connector.connect(
        host=os.getenv("RDS_HOST", "127.0.0.1"),
        port=int(os.getenv("RDS_PORT", 3308)),
        user=os.getenv("RDS_USER", "root"),
        password=os.getenv("RDS_PASSWORD", "password"),
        database=database,
    )
    cursor = connection.cursor()
    cursor.execute("SET time_zone = 'Australia/Sydney'")
    return connection, cursor


with open("stops") as f:
    stops = json.load(f)

stop_name_to_id = {}
conn, cursor = get_connection("trains")
cursor.execute("SELECT id, name FROM stops")
rows = cursor.fetchall()
for row in rows:
    stop_name_to_id[row[1]] = row[0]
cursor.close()
conn.close()


@app.route("/api/bus-delays", methods=["GET"])
def get_average_delays():
    try:
        conn, cursor = get_connection("buses")

        start_date = request.args.get("start_date")
        end_date = request.args.get("end_date")
        sydney_only = request.args.get("sydney_only") == "true"
        shit_type = "early" if request.args.get("shit_type") == "early" else "delay"

        query = f"""
            SELECT rdd.route_id, routes.long_name, ROUND(SUM(rdd.total_{shit_type}) / SUM(rdd.total_count), 2) AS avg_delay, SUM(rdd.hits)
            FROM route_daily_delays rdd
            JOIN routes ON rdd.route_id = routes.id
            WHERE rdd.date BETWEEN %s AND %s
        """
        if sydney_only:
            query += " AND routes.is_in_sydney = TRUE"
        query += """    GROUP BY rdd.route_id, routes.long_name"""

        cursor.execute(query, (start_date, end_date))
        rows = cursor.fetchall()

        return jsonify(
            [
                {
                    "agency_id": row[0].split("_")[0],
                    "route": f'{row[0].split("_")[1]} {row[1]}',
                    "delay": row[2],
                    "hits": row[3],
                }
                for row in rows
            ]
        )

    except mysql.connector.Error as err:
        return jsonify({"error": str(err)}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()


@app.route("/api/train-delays", methods=["GET"])
def get_average_train_delays():
    try:
        conn, cursor = get_connection("trains")

        start_date = request.args.get("start_date")
        end_date = request.args.get("end_date")
        sydney_only = request.args.get("sydney_only") == "true"
        shit_type = "early" if request.args.get("shit_type") == "early" else "delay"

        query = f"""
            SELECT routes.description, ROUND(SUM(rdd.total_{shit_type}) / SUM(rdd.total_count), 2) AS avg_delay, SUM(rdd.hits)
            FROM route_daily_delays rdd
            JOIN routes ON rdd.route_short_name = routes.short_name
            WHERE rdd.date BETWEEN %s AND %s
        """
        if sydney_only:
            query += " AND routes.is_in_sydney = TRUE"
        query += """    GROUP BY rdd.route_short_name, routes.description"""

        cursor.execute(query, (start_date, end_date))
        rows = cursor.fetchall()

        return jsonify(
            [
                {
                    "route": row[0],
                    "delay": row[1],
                    "hits": row[2],
                }
                for row in rows
            ]
        )

    except mysql.connector.Error as err:
        return jsonify({"error": str(err)}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()


@app.route("/api/train-stop-delays", methods=["GET"])
def get_average_train_stop_delays():
    try:
        conn, cursor = get_connection("trains")

        start_date = request.args.get("start_date")
        end_date = request.args.get("end_date")
        sydney_only = request.args.get("sydney_only") == "true"
        shit_type = "early" if request.args.get("shit_type") == "early" else "delay"

        query = f"""
            SELECT sdd.route_short_name, stops.name, ROUND(SUM(sdd.total_{shit_type}) / SUM(sdd.total_count), 2) AS avg_delay, SUM(sdd.hits)
            FROM stop_daily_delays sdd
            JOIN stops ON sdd.stop_id = stops.id
            JOIN routes ON sdd.route_short_name = routes.short_name
            WHERE sdd.date BETWEEN %s AND %s
        """
        if sydney_only:
            query += " AND routes.is_in_sydney = TRUE"
        query += """    GROUP BY sdd.route_short_name, stops.name"""

        cursor.execute(query, (start_date, end_date))
        rows = cursor.fetchall()

        grouped = defaultdict(list)
        for row in rows:
            grouped[row[0]].append(
                {
                    "station": row[1],
                    "delay": row[2],
                    "hits": row[3],
                }
            )
        return jsonify(grouped)

        # Sort each route's station list by stop order
        sorted_result = {}
        for route, data_list in grouped.items():
            stop_order = stops.get(route, [])
            # Map station name to its order index (for sorting)
            station_order = {station + " Station" if station != "Circular Quay" else station: i for i, station in enumerate(stop_order)}
            # Sort by index in the official stop list
            sorted_result[route] = sorted(data_list, key=lambda x: station_order.get(x["station"], float("inf")))
        return jsonify(sorted_result)

    except mysql.connector.Error as err:
        return jsonify({"error": str(err)}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()


@app.route("/api/hit_bus_route/<route_id>", methods=["POST"])
def hit_bus_route(route_id):
    referer = request.headers.get("Referer", "")
    if os.getenv("RDS_PORT") and "howshitismybus.com.au" not in referer:
        return jsonify({"error": "Bruh"}), 403

    user_agent = request.headers.get("User-Agent", "").lower()
    if any(bot in user_agent for bot in ["curl", "bot", "spider", "python", "scrapy"]):
        return jsonify({"error": "Bot detected"}), 403

    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    today = datetime.now(ZoneInfo("Australia/Sydney")).date()
    try:
        conn, cursor = get_connection("buses")

        update_query = """
            INSERT INTO route_daily_delays (route_id, date, hits)
            VALUES (%s, %s, 1)
            ON DUPLICATE KEY UPDATE hits = hits + 1
        """

        cursor.execute(update_query, (route_id, today))
        conn.commit()

        retrieve_query = """
            SELECT SUM(hits) 
            FROM route_daily_delays 
            WHERE route_id = %s AND date BETWEEN %s AND %s
        """

        cursor.execute(retrieve_query, (route_id, start_date, end_date))
        hits = cursor.fetchone()

        return jsonify({"hits": hits[0]})

    except mysql.connector.Error as err:
        return jsonify({"error": str(err)}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()


@app.route("/api/hit_train_route/<route_short_name>", methods=["POST"])
def hit_train_route(route_short_name):
    referer = request.headers.get("Referer", "")
    if os.getenv("RDS_PORT") and "howshitismytrain.com.au" not in referer:
        return jsonify({"error": "Bruh"}), 403

    user_agent = request.headers.get("User-Agent", "").lower()
    if any(bot in user_agent for bot in ["curl", "bot", "spider", "python", "scrapy"]):
        return jsonify({"error": "Bot detected"}), 403

    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    station = request.args.get("station")
    today = datetime.now(ZoneInfo("Australia/Sydney")).date()
    try:
        conn, cursor = get_connection("trains")

        update_query = """
            INSERT INTO route_daily_delays (route_short_name, date, hits)
            VALUES (%s, %s, 1)
            ON DUPLICATE KEY UPDATE hits = hits + 1
        """
        cursor.execute(update_query, (route_short_name, today))
        conn.commit()

        retrieve_query = """
            SELECT SUM(hits) 
            FROM route_daily_delays 
            WHERE route_short_name = %s AND date BETWEEN %s AND %s
        """
        cursor.execute(retrieve_query, (route_short_name, start_date, end_date))
        hits = cursor.fetchone()

        if not station or station not in stop_name_to_id:
            return jsonify({"hits": hits[0]})

        update_query = """
            INSERT INTO stop_daily_delays (route_short_name, stop_id, date, hits)
            VALUES (%s, %s, %s, 1)
            ON DUPLICATE KEY UPDATE hits = hits + 1
        """
        cursor.execute(update_query, (route_short_name, stop_name_to_id[station], today))
        conn.commit()

        retrieve_query = """
            SELECT SUM(hits) 
            FROM stop_daily_delays 
            WHERE route_short_name = %s AND stop_id = %s AND date BETWEEN %s AND %s
        """
        cursor.execute(retrieve_query, (route_short_name, stop_name_to_id[station], start_date, end_date))
        stop_hits = cursor.fetchone()

        return jsonify({"hits": hits[0], "stop_hits": stop_hits[0]})

    except mysql.connector.Error as err:
        return jsonify({"error": str(err)}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()


@app.route("/api/buses/routes/<route_id>/stops", methods=["GET"])
def get_bus_route_stops(route_id):
    """Returns delays for a bus stop

    Example response:
    {
        "stops": [
            {
                "avg_delay": "12",
                "id": "2204112",
                "lat": "-33.908492",
                "lon": "151.172193",
                "name": "Edinburgh Rd at Murray St",
                "on_time_percent": 0.0,
                "total_trips": 1
            }
        ]
    }
    """
    try:
        conn, cursor = get_connection("buses")

        start_date = request.args.get("start_date")
        end_date = request.args.get("end_date")
        shit_type = "early" if request.args.get("shit_type") == "early" else "delay"

        if not start_date or not end_date:
            return (
                jsonify({"error": "start_date and end_date parameters are required"}),
                400,
            )

        query = f"""
            SELECT
                s.id,
                s.name,
                s.lat,
                s.lon,
                SUM(sdd.total_{shit_type}),
                SUM(sdd.total_count),
                SUM(sdd.total_trips),
                (SUM(sdd.total_count) - SUM(sdd.above_1_minute)) * 100.0 / NULLIF(SUM(sdd.total_count), 0) as on_time_percent_delay,
                (SUM(sdd.total_count) - SUM(sdd.before_1_minute)) * 100.0 / NULLIF(SUM(sdd.total_count), 0) as on_time_percent_early
            FROM stop_daily_delays sdd
            JOIN stops s ON sdd.stop_id = s.id
            WHERE sdd.route_id = %s AND sdd.date BETWEEN %s AND %s
            GROUP BY s.id, s.name, s.lat, s.lon
        """

        cursor.execute(query, (route_id, start_date, end_date))
        rows = cursor.fetchall()

        result = []
        for row in rows:
            total_delay_or_early = row[4] if row[4] is not None else 0
            total_count = row[5] if row[5] is not None else 0
            avg_delay = total_delay_or_early / total_count if total_count > 0 else 0
            on_time_percent = row[7] if shit_type == "delay" else row[8]

            result.append(
                {
                    "id": row[0],
                    "name": row[1],
                    "lat": row[2],
                    "lon": row[3],
                    "avg_delay": avg_delay,
                    "on_time_percent": on_time_percent if on_time_percent is not None else 100,
                    "total_trips": row[6] if row[6] is not None else 0,
                }
            )

        # fetch route shapes
        # encoded_shapes = get_encoded_shapes_for_route(cursor, route_id)
        # TODO ensure all shapes line up with all dots before turning this back on

        # snap stops to route
        # snapped_stops = snap_stops_to_route(result, encoded_shapes)

        return jsonify({"stops": result})

    except mysql.connector.Error as err:
        return jsonify({"error": str(err)}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()


# helper functions for bus delay map
# TODO do this snapping at the data processing stage
# def haversine_distance(lat1, lon1, lat2, lon2):
#     """calculate distance between two points in meters"""
#     R = 6371000  # earth radius in meters
#     lat1_rad = math.radians(lat1)
#     lat2_rad = math.radians(lat2)
#     delta_lat = math.radians(lat2 - lat1)
#     delta_lon = math.radians(lon2 - lon1)

#     a = math.sin(delta_lat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
#     c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
#     return R * c

# def point_to_line_distance(point_lat, point_lon, line_start, line_end):
#     """calculate perpendicular distance from point to line segment and find closest point"""
#     # convert to vectors
#     p = [point_lat, point_lon]
#     a = [line_start[0], line_start[1]]
#     b = [line_end[0], line_end[1]]

#     # vector from a to b
#     ab = [b[0] - a[0], b[1] - a[1]]
#     # vector from a to p
#     ap = [p[0] - a[0], p[1] - a[1]]

#     # calculate t parameter (projection of ap onto ab)
#     ab_squared = ab[0] ** 2 + ab[1] ** 2
#     if ab_squared == 0:
#         # line segment is a point
#         return haversine_distance(point_lat, point_lon, a[0], a[1]), a

#     t = max(0, min(1, (ap[0] * ab[0] + ap[1] * ab[1]) / ab_squared))

#     # find closest point on line segment
#     closest = [a[0] + t * ab[0], a[1] + t * ab[1]]

#     # calculate distance
#     distance = haversine_distance(point_lat, point_lon, closest[0], closest[1])

#     return distance, closest

# def snap_stops_to_route(stops_data, route_shapes_encoded):
#     """snap stop coordinates to the nearest point on the route"""
#     if not route_shapes_encoded or not stops_data:
#         return stops_data

#     # decode the first shape (main route)
#     try:
#         route_points = polyline.decode(route_shapes_encoded[0])
#     except Exception:
#         return stops_data

#     # snap each stop to the nearest point on the route
#     snapped_stops = []
#     for stop in stops_data:
#         stop_lat = float(stop["lat"])
#         stop_lon = float(stop["lon"])

#         min_distance = float("inf")
#         best_point = None
#         best_segment_idx = None

#         # check each segment of the route
#         for i in range(len(route_points) - 1):
#             segment_start = route_points[i]
#             segment_end = route_points[i + 1]

#             distance, closest_point = point_to_line_distance(stop_lat, stop_lon, segment_start, segment_end)

#             if distance < min_distance:
#                 min_distance = distance
#                 best_point = closest_point
#                 best_segment_idx = i

#         # if stop is more than 50 meters from route, snap to middle of nearest segment
#         # otherwise, use the closest point on the route
#         if min_distance > 50 and best_point and best_segment_idx is not None:
#             # place stop in the middle of the nearest segment
#             segment_start = route_points[best_segment_idx]
#             segment_end = route_points[best_segment_idx + 1]
#             mid_lat = (segment_start[0] + segment_end[0]) / 2
#             mid_lon = (segment_start[1] + segment_end[1]) / 2

#             stop_copy = stop.copy()
#             stop_copy["lat"] = mid_lat
#             stop_copy["lon"] = mid_lon
#             stop_copy["snapped"] = True
#             stop_copy["original_lat"] = stop_lat
#             stop_copy["original_lon"] = stop_lon
#             snapped_stops.append(stop_copy)
#         elif best_point:
#             # use the closest point on the route
#             stop_copy = stop.copy()
#             stop_copy["lat"] = best_point[0]
#             stop_copy["lon"] = best_point[1]
#             stop_copy["snapped"] = True
#             stop_copy["original_lat"] = stop_lat
#             stop_copy["original_lon"] = stop_lon
#             snapped_stops.append(stop_copy)
#         else:
#             # keep original position (shouldn't happen)
#             stop_copy = stop.copy()
#             stop_copy["snapped"] = False
#             snapped_stops.append(stop_copy)

#     return snapped_stops


@app.route("/api/trains/routes/<route_short_name>/stats/daily", methods=["GET"])
def get_train_line_stats(route_short_name):
    try:
        conn, cursor = get_connection("trains")

        shit_type = "early" if request.args.get("shit_type") == "early" else "delay"

        query = f"""
            SELECT date,
                   ROUND(total_{shit_type} / total_count, 2) as avg_delay,
                   total_trips
            FROM route_daily_delays
            WHERE route_short_name = %s AND total_count > 0
            ORDER BY date;
        """

        cursor.execute(query, (route_short_name,))
        rows = cursor.fetchall()

        result = [
            {
                "date": row[0].strftime("%Y-%m-%d"),
                "avg_delay": float(row[1]),
                "total_trips": row[2],
            }
            for row in rows
        ]
        return jsonify(result)

    except mysql.connector.Error as err:
        return jsonify({"error": str(err)}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()


@app.route("/api/trains/routes/<route_short_name>/stats/distribution", methods=["GET"])
def get_train_distribution_stats(route_short_name):
    try:
        conn, cursor = get_connection("trains")

        query = """
            SELECT
                date,
                total_count,
                before_1_minute,
                above_1_minute,
                above_2_minutes,
                above_5_minutes,
                above_10_minutes,
                above_15_minutes,
                above_30_minutes
            FROM route_daily_delays
            WHERE route_short_name = %s AND total_count > 0
            ORDER BY date;
        """

        cursor.execute(query, (route_short_name,))
        rows = cursor.fetchall()

        result = []
        for row in rows:
            total = row[1]
            early = row[2]  # before_1_minute
            # total - before_1_minute - above_1_minute
            on_time = total - row[2] - row[3]

            delay_1_2 = row[3] - row[4]  # above_1_minute - above_2_minutes
            delay_2_5 = row[4] - row[5]  # above_2_minutes - above_5_minutes
            delay_5_10 = row[5] - row[6]  # above_5_minutes - above_10_minutes
            delay_10_15 = row[6] - row[7]  # above_10_minutes - above_15_minutes
            delay_15_30 = row[7] - row[8]  # above_15_minutes - above_30_minutes
            delay_30_plus = row[8]  # above_30_minutes

            if total == 0:
                continue

            early = max(0, early)
            on_time = max(0, on_time)
            delay_1_2 = max(0, delay_1_2)
            delay_2_5 = max(0, delay_2_5)
            delay_5_10 = max(0, delay_5_10)
            delay_10_15 = max(0, delay_10_15)
            delay_15_30 = max(0, delay_15_30)
            delay_30_plus = max(0, delay_30_plus)

            calculated_total = early + delay_1_2 + delay_2_5 + delay_5_10 + delay_10_15 + delay_15_30 + delay_30_plus
            if calculated_total != total:  # don't think this'll ever happen
                on_time = total - calculated_total
                on_time = max(0, on_time)

            result.append(
                {
                    "date": row[0].strftime("%Y-%m-%d"),
                    "total_count": total,
                    "distribution": {
                        "early": round(early / total * 100, 1),
                        "on_time": round(on_time / total * 100, 1),
                        "delay_1_2": round(delay_1_2 / total * 100, 1),
                        "delay_2_5": round(delay_2_5 / total * 100, 1),
                        "delay_5_10": round(delay_5_10 / total * 100, 1),
                        "delay_10_15": round(delay_10_15 / total * 100, 1),
                        "delay_15_30": round(delay_15_30 / total * 100, 1),
                        "delay_30_plus": round(delay_30_plus / total * 100, 1),
                    },
                }
            )

        return jsonify(result)

    except mysql.connector.Error as err:
        return jsonify({"error": str(err)}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()


@app.route("/api/trains/routes", methods=["GET"])
def get_train_routes():
    try:
        conn, cursor = get_connection("trains")

        query = """
            SELECT DISTINCT r.short_name, r.description
            FROM routes r
            JOIN route_daily_delays rdd ON r.short_name = rdd.route_short_name
            WHERE r.is_in_sydney = TRUE
            ORDER BY r.description;
        """

        cursor.execute(query)
        rows = cursor.fetchall()

        result = [{"short_name": row[0], "description": row[1]} for row in rows]
        return jsonify(result)

    except mysql.connector.Error as err:
        return jsonify({"error": str(err)}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()


@app.route("/api/buses/routes", methods=["GET"])
def get_bus_routes():
    """Returns all available bus routes

    Example response:
    [
        {
            "id": "2459_438X",
            "long_name": "Abbotsford to City Martin Place (Express Service)"
        },
        etc.
    ]
    """
    try:
        conn, cursor = get_connection("buses")

        # TODO filter by 'has time period' delays or not? (JOIN)
        query = """
            SELECT DISTINCT r.id, r.long_name
            FROM routes r
            JOIN route_daily_delays rdd ON r.id = rdd.route_id
            WHERE r.is_in_sydney = TRUE
            ORDER BY r.long_name;
        """

        cursor.execute(query)
        rows = cursor.fetchall()

        result = [{"id": row[0], "long_name": row[1]} for row in rows]
        return jsonify(result)

    except mysql.connector.Error as err:
        return jsonify({"error": str(err)}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()


@app.route("/api/trains/stations/delay-map", methods=["GET"])
def get_station_delay_map():
    """Returns per station delays and lines they belong to."""
    try:
        conn, cursor = get_connection("trains")

        start_date = request.args.get("start_date")
        end_date = request.args.get("end_date")
        route_short_name = request.args.get("route_short_name")

        # print(
        #     "station-delay-map params:",
        #     start_date,
        #     end_date,
        #     route_short_name,
        #     flush=True,
        # )

        if not start_date or not end_date:
            return (
                jsonify({"error": "start_date and end_date parameters are required"}),
                400,
            )

        query = """
            SELECT
                sdd.stop_id,
                s.name,
                sdd.route_short_name,
                SUM(sdd.total_delay),
                SUM(sdd.total_count),
                (SUM(sdd.total_count) - SUM(sdd.above_1_minute)) * 100.0 /
                NULLIF(SUM(sdd.total_count), 0) as on_time_percent
            FROM stop_daily_delays sdd
            JOIN stops s ON sdd.stop_id = s.id
            WHERE sdd.date BETWEEN %s AND %s
        """

        params = [start_date, end_date]

        if route_short_name:
            query += " AND sdd.route_short_name = %s"
            params.append(route_short_name)

        query += " GROUP BY sdd.stop_id, sdd.route_short_name, s.name"

        cursor.execute(query, params)
        rows = cursor.fetchall()

        # group by cleaned station name then by route
        stop_stats = {}
        route_stats = {}

        def clean_station_name(name):
            cleaned = name.replace("Station", "").strip()
            
            if cleaned == "Sydney International Airport":
                return "Intl. Airport"
            elif cleaned == "Sydney Domestic Airport":
                return "Domestic Airport"
            
            return cleaned

        for row in rows:
            stop_name = row[1]
            route = row[2]
            total_delay_seconds = float(row[3]) if row[3] is not None else 0
            total_trips = float(row[4]) if row[4] is not None else 0
            on_time_percent = round(float(row[5]) if row[5] is not None else 100, 1)

            avg_delay_minutes = (total_delay_seconds / 60) / total_trips if total_trips > 0 else 0
            cleaned_name = clean_station_name(stop_name)

            # store stop data by cleaned name per route
            if cleaned_name not in stop_stats:
                stop_stats[cleaned_name] = {}
            stop_stats[cleaned_name][route] = {
                "avg_delay": avg_delay_minutes,
                "total_trips": total_trips,
                "on_time_percent": on_time_percent,
            }

            if route not in route_stats:
                route_stats[route] = {
                    "total_delay_minutes": 0,
                    "total_trips": 0,
                    "stop_count": 0,
                }
            route_stats[route]["total_delay_minutes"] += total_delay_seconds / 60
            route_stats[route]["total_trips"] += total_trips
            route_stats[route]["stop_count"] += 1

        #  route averages
        for route, stats in route_stats.items():
            if stats["total_trips"] > 0:
                route_stats[route]["avg_delay"] = stats["total_delay_minutes"] / stats["total_trips"]
            else:
                route_stats[route]["avg_delay"] = 0
            del route_stats[route]["total_delay_minutes"]

        return jsonify({"stops": stop_stats, "routes": route_stats})

    except mysql.connector.Error as err:
        print("MySQL error in /api/trains/stations/delay-map:", err, flush=True)
        traceback.print_exc()
        return jsonify({"error": str(err)}), 500
    except Exception as e:
        print("Exception in /api/trains/stations/delay-map:", e, flush=True)
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()


def get_encoded_shapes_for_route(cursor, route_id):
    cursor.execute("SELECT shape_encoded FROM route_shapes WHERE route_id = %s", (route_id,))
    rows = cursor.fetchall()
    return [row[0] for row in rows if row[0]]


@app.route("/api/buses/routes/featured", methods=["GET"])
def get_featured_bus_routes():
    now = time.time()
    shit_type = "early" if request.args.get("shit_type") == "early" else "delay"

    start_date_param = request.args.get("start_date")
    end_date_param = request.args.get("end_date")

    if start_date_param and end_date_param:
        start_date = start_date_param
        end_date = end_date_param

        cache_key = f"{shit_type}_{start_date}_{end_date}"
    else:
        # fallback to 7-day period
        today = datetime.now(ZoneInfo("Australia/Sydney")).date()
        end_date = today.strftime("%Y-%m-%d")
        start_date = (today - timedelta(days=FEATURED_ROUTES_TIME_PERIOD_DAYS - 1)).strftime("%Y-%m-%d")
        cache_key = shit_type

    if (now - featured_routes_cache.get(cache_key, {"last_updated": 0})["last_updated"]) < CACHE_TIMEOUT_SECONDS:
        if featured_routes_cache.get(cache_key, {}).get("data") is not None:
            # print(f"Returning cached featured routes for cache_key: {cache_key}", flush=True)
            return jsonify(featured_routes_cache[cache_key]["data"])

    # print(f"Fetching fresh featured routes data for cache_key: {cache_key}, date range: {start_date} to {end_date}", flush=True)

    try:
        conn, cursor = get_connection("buses")

        routes_query = f"""
            SELECT
                r.id,
                r.long_name
            FROM route_daily_delays rdd
            JOIN routes r ON rdd.route_id = r.id
            WHERE
                rdd.date BETWEEN %s AND %s
                AND r.is_in_sydney = TRUE
                AND rdd.total_count > 0
            GROUP BY r.id, r.long_name
            ORDER BY SUM(rdd.total_{shit_type}) / SUM(rdd.total_count) DESC
            LIMIT %s
        """
        cursor.execute(routes_query, (start_date, end_date, NUM_FEATURED_ROUTES))
        selected_routes_info = cursor.fetchall()

        if not selected_routes_info:
            return jsonify({"routes": []})

        # print("The worst/best routes are", selected_routes_info, flush=True)

        result_data = []
        for route_id, route_long_name in selected_routes_info:
            encoded_shapes = get_encoded_shapes_for_route(cursor, route_id)

            stops_query = f"""
                SELECT
                    s.id, s.name, s.lat, s.lon,
                    SUM(sdd.total_{shit_type}),
                    SUM(sdd.total_count),
                    SUM(sdd.total_trips),
                    (SUM(sdd.total_count) - SUM(sdd.above_1_minute)) * 100.0 / NULLIF(SUM(sdd.total_count), 0),
                    (SUM(sdd.total_count) - SUM(sdd.before_1_minute)) * 100.0 / NULLIF(SUM(sdd.total_count), 0)
                FROM stop_daily_delays sdd
                JOIN stops s ON sdd.stop_id = s.id
                WHERE sdd.route_id = %s AND sdd.date BETWEEN %s AND %s
                GROUP BY s.id, s.name, s.lat, s.lon
            """
            cursor.execute(stops_query, (route_id, start_date, end_date))
            stops_rows = cursor.fetchall()

            route_stats_query = """
                SELECT SUM(total_trips)
                FROM route_daily_delays
                WHERE route_id = %s AND date BETWEEN %s AND %s
            """
            cursor.execute(route_stats_query, (route_id, start_date, end_date))
            route_total_trips = cursor.fetchone()[0] or 0

            stops_data = []
            for row in stops_rows:
                total_delay_or_early = row[4] if row[4] is not None else 0
                total_count = row[5] if row[5] is not None else 0
                avg_delay = total_delay_or_early / total_count if total_count > 0 else 0
                on_time_percent = row[7] if shit_type == "delay" else row[8]
                stops_data.append(
                    {
                        "id": row[0],
                        "name": row[1],
                        "lat": row[2],
                        "lon": row[3],
                        "avg_delay": avg_delay,
                        "on_time_percent": on_time_percent if on_time_percent is not None else 100,
                        "total_trips": 0,
                    }
                )

            # snapped_stops = snap_stops_to_route(stops_data, encoded_shapes)
            # TODO sometimes overlaps when snapping

            for stop in stops_data:
                stop["avg_delay"] = round(float(stop["avg_delay"]) / 60, 2)

            result_data.append(
                {
                    "route": {"id": route_id, "long_name": route_long_name},
                    "shapes": encoded_shapes,
                    "stops": stops_data,
                    "total_trips": route_total_trips,
                }
            )

        response_data = {"routes": result_data}

        if cache_key not in featured_routes_cache:
            featured_routes_cache[cache_key] = {"data": None, "last_updated": 0}
        featured_routes_cache[cache_key]["data"] = response_data
        featured_routes_cache[cache_key]["last_updated"] = now
        return jsonify(response_data)

    except mysql.connector.Error as err:
        print("MySQL error in /api/buses/routes/featured:", err, flush=True)
        traceback.print_exc()
        return jsonify({"error": str(err)}), 500
    except Exception as e:
        print("Exception in /api/buses/routes/featured:", e, flush=True)
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    finally:
        if "conn" in locals() and conn.is_connected():
            cursor.close()
            conn.close()


@app.route("/api/buses/routes/<route_id>/shapes", methods=["GET"])
def get_bus_shapes(route_id):
    """Returns shape of a bus route, using polyline encoding

    Example response:
    [
    "rhzmEwrcz[GhAhEZaJte@lDnVIbD_C~J}CvJqKzL_KlOaAnDaAzMoFtT_@|@aHxFiGtPmGrInkAtNY`EkHrW{K`xADnBdFrL",
    etc.
    ]
    """
    conn = None
    try:
        conn, cursor = get_connection("buses")
        encoded_shapes = get_encoded_shapes_for_route(cursor, route_id)
        return jsonify(encoded_shapes)

    except mysql.connector.Error as err:
        return jsonify({"error": str(err)}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


@app.route("/api/buses/routes/<route_id>/stats", methods=["GET"])
def get_bus_route_stats(route_id):
    """Returns statistics for a bus route directly from the route_daily_delays table

    Example response:
    {
        "avg_delay": 2.5,
        "total_trips": 120,
        "total_count": 150
    }
    """
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    shit_type = "early" if request.args.get("shit_type") == "early" else "delay"

    if not route_id or not start_date or not end_date:
        return (
            jsonify({"error": "route_id, start_date and end_date parameters are required"}),
            400,
        )

    conn = None
    try:
        conn, cursor = get_connection("buses")

        query = f"""
            SELECT
                SUM(total_{shit_type}),
                SUM(total_count),
                SUM(above_1_minute),
                SUM(above_2_minutes),
                SUM(above_5_minutes),
                SUM(above_10_minutes),
                SUM(above_15_minutes),
                SUM(above_30_minutes),
                SUM(total_trips)
            FROM route_daily_delays
            WHERE route_id = %s AND date BETWEEN %s AND %s
        """

        cursor.execute(query, (route_id, start_date, end_date))
        row = cursor.fetchone()

        if not row or not row[1] or row[1] == 0:
            return jsonify({"avg_delay": 0, "total_trips": 0, "total_count": 0})

        total_delay_or_early = row[0] if row[0] is not None else 0
        total_count = row[1] if row[1] is not None else 0
        total_trips = row[8] if row[8] is not None else 0
        avg_delay = total_delay_or_early / total_count if total_count > 0 else 0

        return jsonify(
            {
                "avg_delay": avg_delay,
                "total_trips": total_trips,
                "total_count": total_count,
                "delay_distribution": {
                    "above_1_minute": row[2],
                    "above_2_minutes": row[3],
                    "above_5_minutes": row[4],
                    "above_10_minutes": row[5],
                    "above_15_minutes": row[6],
                    "above_30_minutes": row[7],
                },
            }
        )

    except mysql.connector.Error as err:
        return jsonify({"error": str(err)}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


@app.route("/api/buses/stops/<stop_id>/history", methods=["GET"])
def get_bus_stop_history(stop_id):
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    route_id = request.args.get("route_id")

    if not all([stop_id, route_id, start_date, end_date]):
        return jsonify({"error": "stop_id, route_id, start_date, and end_date are required"}), 400

    conn = None
    try:
        conn, cursor = get_connection("buses")
        query = """
            SELECT timestamp, arrival_delay, departure_early
            FROM delay_history
            WHERE stop_id = %s AND route_id = %s AND timestamp >= %s AND timestamp < DATE_ADD(%s, INTERVAL 1 DAY)
            ORDER BY timestamp DESC
            LIMIT 10
        """
        cursor.execute(query, (stop_id, route_id, start_date, end_date))
        rows = cursor.fetchall()

        history = [
            {
                "timestamp": row[0].isoformat(),
                "arrival_delay": row[1],
                "departure_early": row[2],
            }
            for row in rows
        ]
        return jsonify(history)

    except mysql.connector.Error as err:
        return jsonify({"error": str(err)}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


@app.route("/api/buses/recent-visits", methods=["GET"])
def get_recent_bus_visits():
    """Returns the 5 most recent bus visits from delay_history table

    Example response:
    [
        {
            "trip_id": "12345",
            "route_id": "2459_370",
            "stop_id": "200057",
            "stop_name": "Town Hall Station",
            "route_name": "370 Leichhardt to Coogee",
            "arrival_delay": 120,
            "departure_early": 0,
            "timestamp": "2024-01-15T14:30:00"
        }
    ]
    """
    conn = None
    try:
        conn, cursor = get_connection("buses")

        query = """
            SELECT 
                dh.trip_id,
                dh.route_id,
                dh.stop_id,
                s.name as stop_name,
                r.long_name as route_name,
                dh.arrival_delay,
                dh.departure_early,
                dh.timestamp
            FROM delay_history dh
            JOIN stops s ON dh.stop_id = s.id
            JOIN routes r ON dh.route_id = r.id
            WHERE r.is_in_sydney = TRUE
            ORDER BY dh.timestamp DESC
            LIMIT 5
        """

        cursor.execute(query)
        rows = cursor.fetchall()

        visits = []
        for row in rows:
            route_number = row[1].split("_")[1] if "_" in row[1] else row[1]
            visits.append(
                {
                    "trip_id": row[0],
                    "route_id": row[1],
                    "route_number": route_number,
                    "stop_id": row[2],
                    "stop_name": row[3],
                    "route_name": row[4],
                    "arrival_delay": row[5],
                    "departure_early": row[6],
                    "timestamp": row[7].isoformat() if row[7] else None,
                }
            )

        return jsonify(visits)

    except mysql.connector.Error as err:
        return jsonify({"error": str(err)}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if conn and conn.is_connected():
            cursor.close()
            conn.close()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
