from flask import Flask, jsonify, request
import mysql.connector
from dotenv import load_dotenv
from flask_cors import CORS
import os
from zoneinfo import ZoneInfo
from datetime import datetime
import json
from collections import defaultdict

load_dotenv()

app = Flask(__name__)
CORS(app,origins=["https://howshitismybus.com.au", "https://www.howshitismybus.com.au"])

def get_connection(database):
    connection = mysql.connector.connect(
        host=os.getenv("RDS_HOST", '127.0.0.1'),
        port=int(os.getenv("RDS_PORT", 3308)),
        user=os.getenv("RDS_USER", 'root'),     
        password=os.getenv("RDS_PASSWORD", 'password'),
        database=database
    )
    cursor = connection.cursor()
    cursor.execute("SET time_zone = 'Australia/Sydney'")
    return connection, cursor

with open('stops') as f:
    stops = json.load(f)

stop_name_to_id = {}
conn, cursor = get_connection('trains')
cursor.execute("SELECT id, name FROM stops")
rows = cursor.fetchall()
for row in rows:
    stop_name_to_id[row[1]] = row[0]
cursor.close()
conn.close()

@app.route('/api/bus-delays', methods=['GET'])
def get_average_delays():
    try:
        conn, cursor = get_connection('buses')

        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        sydney_only = request.args.get('sydney_only') == 'true'
        shit_type = 'early' if request.args.get('shit_type') == 'early' else 'delay'

        query = f"""
            SELECT rdd.route_id, routes.long_name, ROUND(SUM(rdd.total_{shit_type}) / SUM(rdd.total_count), 2) AS avg_delay, SUM(rdd.hits)
            FROM route_daily_delays rdd
            JOIN routes ON rdd.route_id = routes.id
            WHERE rdd.date BETWEEN %s AND %s
        """
        if sydney_only: query += " AND routes.is_in_sydney = TRUE"
        query += """    GROUP BY rdd.route_id, routes.long_name"""

        cursor.execute(query, (start_date, end_date))
        rows = cursor.fetchall()

        return jsonify([{
            'agency_id': row[0].split("_")[0],
            'route': f'{row[0].split("_")[1]} {row[1]}', 
            'delay': row[2], 
            'hits': row[3],
        } for row in rows])

    except mysql.connector.Error as err:
        return jsonify({"error": str(err)}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()

@app.route('/api/train-delays', methods=['GET'])
def get_average_train_delays():
    try:
        conn, cursor = get_connection('trains')

        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        sydney_only = request.args.get('sydney_only') == 'true'
        shit_type = 'early' if request.args.get('shit_type') == 'early' else 'delay'

        query = f"""
            SELECT routes.description, ROUND(SUM(rdd.total_{shit_type}) / SUM(rdd.total_count), 2) AS avg_delay, SUM(rdd.hits)
            FROM route_daily_delays rdd
            JOIN routes ON rdd.route_short_name = routes.short_name
            WHERE rdd.date BETWEEN %s AND %s
        """
        if sydney_only: query += " AND routes.is_in_sydney = TRUE"
        query += """    GROUP BY rdd.route_short_name, routes.description"""

        cursor.execute(query, (start_date, end_date))
        rows = cursor.fetchall()

        return jsonify([{
            'route': row[0],
            'delay': row[1],
            'hits': row[2],
        } for row in rows])

    except mysql.connector.Error as err:
        return jsonify({"error": str(err)}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()

@app.route('/api/train-stop-delays', methods=['GET'])
def get_average_train_stop_delays():
    try:
        conn, cursor = get_connection('trains')

        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        sydney_only = request.args.get('sydney_only') == 'true'
        shit_type = 'early' if request.args.get('shit_type') == 'early' else 'delay'

        query = f"""
            SELECT sdd.route_short_name, stops.name, ROUND(SUM(sdd.total_{shit_type}) / SUM(sdd.total_count), 2) AS avg_delay, SUM(sdd.hits)
            FROM stop_daily_delays sdd
            JOIN stops ON sdd.stop_id = stops.id
            JOIN routes ON sdd.route_short_name = routes.short_name
            WHERE sdd.date BETWEEN %s AND %s
        """
        if sydney_only: query += " AND routes.is_in_sydney = TRUE"
        query += """    GROUP BY sdd.route_short_name, stops.name"""

        cursor.execute(query, (start_date, end_date))
        rows = cursor.fetchall()

        grouped = defaultdict(list)
        for row in rows:
            grouped[row[0]].append({
                "station" : row[1],
                "delay" : row[2],
                "hits" : row[3],
            })
        return jsonify(grouped)

        # Sort each route's station list by stop order
        sorted_result = {}
        for route, data_list in grouped.items():
            stop_order = stops.get(route, [])
            # Map station name to its order index (for sorting)
            station_order = {station + ' Station' if station != 'Circular Quay' else station: i for i, station in enumerate(stop_order)}
            # Sort by index in the official stop list
            sorted_result[route] = sorted(
                data_list,
                key=lambda x: station_order.get(x["station"], float("inf"))
            )
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
    if os.getenv('RDS_PORT') and "howshitismybus.com.au" not in referer:
        return jsonify({"error": "Bruh"}), 403

    user_agent = request.headers.get("User-Agent", "").lower()
    if any(bot in user_agent for bot in ["curl", "bot", "spider", "python", "scrapy"]):
        return jsonify({"error": "Bot detected"}), 403

    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    today = datetime.now(ZoneInfo('Australia/Sydney')).date()
    try:
        conn, cursor = get_connection('buses')

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
    if os.getenv('RDS_PORT') and "howshitismybus.com.au" not in referer:
        return jsonify({"error": "Bruh"}), 403

    user_agent = request.headers.get("User-Agent", "").lower()
    if any(bot in user_agent for bot in ["curl", "bot", "spider", "python", "scrapy"]):
        return jsonify({"error": "Bot detected"}), 403

    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    station = request.args.get('station')
    today = datetime.now(ZoneInfo('Australia/Sydney')).date()
    try:
        conn, cursor = get_connection('trains')

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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
