from flask import Flask, jsonify, request
import mysql.connector
from dotenv import load_dotenv
from flask_cors import CORS
import os
from zoneinfo import ZoneInfo
from datetime import datetime
import json
from collections import defaultdict
import traceback

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
            SELECT rdd.route_id, routes.long_name, 
                   ROUND(SUM(rdd.total_{shit_type}) / SUM(rdd.total_count), 2) AS avg_delay, 
                   SUM(rdd.hits)
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
            SELECT routes.description, 
                   ROUND(SUM(rdd.total_{shit_type}) / SUM(rdd.total_count), 2) AS avg_delay, 
                   SUM(rdd.hits)
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
            SELECT sdd.route_short_name, stops.name, 
                   ROUND(SUM(sdd.total_{shit_type}) / SUM(sdd.total_count), 2) AS avg_delay, 
                   SUM(sdd.hits)
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
        cursor.execute(
            retrieve_query,
            (route_short_name, stop_name_to_id[station], start_date, end_date),
        )
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


@app.route("/api/train-line-stats", methods=["GET"])
def get_train_line_stats():
    try:
        conn, cursor = get_connection("trains")

        route_short_name = request.args.get("route_short_name")
        if not route_short_name:
            return jsonify({"error": "route_short_name parameter is required"}), 400

        shit_type = "early" if request.args.get("shit_type") == "early" else "delay"

        query = f"""
            SELECT date, ROUND(total_{shit_type} / total_count, 2) as avg_delay, total_trips
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


@app.route("/api/train-distribution-stats", methods=["GET"])
def get_train_distribution_stats():
    try:
        conn, cursor = get_connection("trains")

        route_short_name = request.args.get("route_short_name")
        if not route_short_name:
            return jsonify({"error": "route_short_name parameter is required"}), 400

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
            on_time = total - row[2] - row[3]  # total - before_1_minute - above_1_minute

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


@app.route("/api/train-routes", methods=["GET"])
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


@app.route("/api/station-delay-map", methods=["GET"])
def get_station_delay_map():
    """Returns per station delays and lines they belong to."""
    try:
        conn, cursor = get_connection("trains")

        start_date = request.args.get("start_date")
        end_date = request.args.get("end_date")
        route_short_name = request.args.get("route_short_name")

        print("station-delay-map params:", start_date, end_date, route_short_name, flush=True)

        if not start_date or not end_date:
            return jsonify({"error": "start_date and end_date parameters are required"}), 400

        query = """
            SELECT 
                sdd.stop_id,
                s.name,
                sdd.route_short_name,
                SUM(sdd.total_delay) / NULLIF(SUM(sdd.total_count), 0) as avg_delay,
                SUM(sdd.total_count) as total_trips,
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
            return name.replace("Station", "").strip()

        for row in rows:
            stop_name = row[1]
            route = row[2]
            avg_delay = float(row[3]) / 60 if row[3] else 0  # min
            total_trips = float(row[4])
            on_time_percent = round(float(row[5]) if row[5] else 100, 1)

            cleaned_name = clean_station_name(stop_name)

            # store stop data by cleaned name per route
            if cleaned_name not in stop_stats:
                stop_stats[cleaned_name] = {}
            stop_stats[cleaned_name][route] = {
                "avg_delay": avg_delay,
                "total_trips": total_trips,
                "on_time_percent": on_time_percent,
            }

            if route not in route_stats:
                route_stats[route] = {"total_delay": 0, "total_trips": 0, "stop_count": 0}
            route_stats[route]["total_delay"] += avg_delay * total_trips
            route_stats[route]["total_trips"] += total_trips
            route_stats[route]["stop_count"] += 1

        #  route averages
        for route, stats in route_stats.items():
            if stats["total_trips"] > 0:
                route_stats[route]["avg_delay"] = stats["total_delay"] / stats["total_trips"]
            else:
                route_stats[route]["avg_delay"] = 0

        return jsonify({"stops": stop_stats, "routes": route_stats})

    except mysql.connector.Error as err:
        print("MySQL error in /api/station-delay-map:", err, flush=True)
        traceback.print_exc()
        return jsonify({"error": str(err)}), 500
    except Exception as e:
        print("Exception in /api/station-delay-map:", e, flush=True)
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
