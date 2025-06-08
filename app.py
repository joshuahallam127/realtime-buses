from flask import Flask, jsonify, request
import mysql.connector
from dotenv import load_dotenv
import functions
from flask_cors import CORS
import os
from zoneinfo import ZoneInfo
from datetime import datetime

load_dotenv()

app = Flask(__name__)
# CORS(app,origins=["https://howshitismybus.com.au", "https://www.howshitismybus.com.au"])
CORS(app)

@app.route('/api/bus-delays', methods=['GET'])
def get_average_delays():
    try:
        conn, cursor = functions.get_connection('buses')

        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        sydney_only = request.args.get('sydney_only') == 'true'

        query = """
            SELECT rdd.route_id, routes.long_name, ROUND(SUM(rdd.total_delay) / SUM(rdd.total_count), 2) AS avg_delay, SUM(rdd.hits)
            FROM route_daily_delays rdd
            JOIN routes ON rdd.route_id = routes.id
            WHERE rdd.date BETWEEN %s AND %s
        """

        if sydney_only:
            query += " AND routes.is_in_sydney = TRUE"

        query += """    GROUP BY rdd.route_id, routes.long_name
            ORDER BY avg_delay DESC
        """

        cursor.execute(query, (start_date, end_date))
        rows = cursor.fetchall()

        result = []
        for i, row in enumerate(rows):
            result.append({
                'agency_id': row[0].split("_")[0],
                'route': f'{row[0].split("_")[1]} {row[1]}', 
                'delay': row[2], 
                'rank': i + 1,
                'hits': row[3],
            })
        return jsonify(result)

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
        conn, cursor = functions.get_connection('trains')

        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        sydney_only = request.args.get('sydney_only') == 'true'

        query = """
            SELECT routes.description, ROUND(SUM(rdd.total_delay) / SUM(rdd.total_count), 2) AS avg_delay, SUM(rdd.hits)
            FROM route_daily_delays rdd
            JOIN routes ON rdd.route_short_name = routes.short_name
            WHERE rdd.date BETWEEN %s AND %s
        """

        if sydney_only:
            query += " AND routes.is_in_sydney = TRUE"

        query += """    GROUP BY rdd.route_short_name
            ORDER BY avg_delay DESC
        """

        cursor.execute(query, (start_date, end_date))
        rows = cursor.fetchall()

        result = []
        for i, row in enumerate(rows):
            result.append({
                'route': row[0],
                'delay': row[1], 
                'rank': i + 1,
                'hits': row[2],
            })
        return jsonify(result)

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
        conn, cursor = functions.get_connection('trains')

        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        sydney_only = request.args.get('sydney_only') == 'true'

        query = """
            SELECT sdd.route_short_name, stops.name, ROUND(SUM(sdd.total_delay) / SUM(sdd.total_count), 2) AS avg_delay, SUM(sdd.hits)
            FROM stop_daily_delays sdd
            JOIN stops ON sdd.stop_id = stops.id
            JOIN routes ON sdd.route_short_name = routes.short_name
            WHERE sdd.date BETWEEN %s AND %s
        """

        if sydney_only:
            query += " AND routes.is_in_sydney = TRUE"

        query += """    GROUP BY stops.name, sdd.route_short_name, stops.id
            ORDER BY avg_delay DESC
        """

        cursor.execute(query, (start_date, end_date))
        rows = cursor.fetchall()

        result = []
        for i, row in enumerate(rows):
            result.append({
                'route': f'{row[0]} {row[1]}',
                'delay': row[2], 
                'rank': i + 1,
                'hits': row[3],
            })
        return jsonify(result)

    except mysql.connector.Error as err:
        return jsonify({"error": str(err)}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()

@app.route("/api/hit_route/<route_id>", methods=["POST"])
def hit_route(route_id):
    # 🔒 Minimal protection

    # 1. Check Referer header to see if it came from your own frontend
    referer = request.headers.get("Referer", "")
    if os.getenv('RDS_PORT') and "howshitismybus.com.au" not in referer:
        return jsonify({"error": "Bruh"}), 403

    # 2. Basic User-Agent filter (avoid obvious bots)
    user_agent = request.headers.get("User-Agent", "").lower()
    if any(bot in user_agent for bot in ["curl", "bot", "spider", "python", "scrapy"]):
        return jsonify({"error": "Bot detected"}), 403

    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    today = datetime.now(ZoneInfo('Australia/Sydney')).date()
    # 🔢 Update the counter
    try:
        conn, cursor = functions.get_connection('buses')

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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
