from flask import Flask, jsonify, request
import mysql.connector
from dotenv import load_dotenv
import functions
from flask_cors import CORS
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import csv

load_dotenv()

app = Flask(__name__)
CORS(app,origins=["https://howshitismybus.com.au", "https://www.howshitismybus.com.au"])

# get all the valid bus_routes before running the script
route_to_name = {}
to_ignore = [
    ("5405","594"),
    ("5405","595"),
    ("5405","596"),
    ("5405","597"),
    ("5979","953"),
    ("5979","954"),
    ("5493","870"),
]
with open('routes.txt', newline='', encoding='utf-8') as csvfile:
    reader = csv.DictReader(csvfile)
    for row in reader:
        if row['route_desc'] == 'Sydney Buses Network' and (row['agency_id'], row['route_short_name']) not in to_ignore:
            if row['route_short_name'] in route_to_name:
                print('bad bad for route:', row['route_short_name'])
            route_to_name[row['route_short_name']] = row['route_long_name']

@app.route('/api/bus-delays', methods=['GET'])
def get_average_delays():
    try:
        conn, cursor = functions.get_connection()

        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')        

        query = """
            SELECT route, ROUND(SUM(total_delay) / SUM(delay_count), 2) AS avg_delay
            FROM route_daily_delays
            WHERE date BETWEEN %s AND %s
            GROUP BY route
            ORDER BY avg_delay DESC
        """

        cursor.execute(query, (start_date, end_date))
        rows = cursor.fetchall()

        result = []
        for i, row in enumerate(rows):
            route_name = route_to_name.get(row[0], 'Unknown Route')
            result.append({'route': f'{row[0]} {route_name}', 'delay': row[1], 'rank': i + 1})
        return jsonify(result)

    except mysql.connector.Error as err:
        return jsonify({"error": str(err)}), 500

    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
