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
route_id_name = {}
with open('routes.txt', newline='', encoding='utf-8') as csvfile:
    reader = csv.DictReader(csvfile)
    for row in reader:
        if row['route_desc'] == 'Sydney Buses Network':
            route_id_name[row['agency_id'] + '_' + row['route_short_name']] = row['route_long_name']

@app.route('/api/bus-delays', methods=['GET'])
def get_average_delays():
    try:
        conn, cursor = functions.get_connection()

        now = datetime.now(ZoneInfo('Australia/Sydney'))

        period = request.args.get('period')

        if period == 'daily':
            start_date = now.date()
        elif period == 'weekly':
            start_date = (now - timedelta(days=now.weekday())).date()
        elif period == 'monthly':
            start_date = now.replace(day=1).date()
        elif period == 'all':
            start_date = '2025-01-01'
        else:
            return jsonify({"error": 'invalid period!'}), 422

        query = """
            SELECT route_id, ROUND(SUM(total_delay) / SUM(delay_count), 2) AS avg_delay
            FROM route_daily_delays
            WHERE date >= %s
            GROUP BY route_id
            ORDER BY avg_delay DESC
        """

        cursor.execute(query, (start_date, ))
        rows = cursor.fetchall()

        result = []
        for row in rows:
            route_name = route_id_name.get(row[0], 'Unknown Route')
            result.append({'route': f'{row[0].split('_')[1]} {route_name}', 'delay': row[1]})
        return jsonify(result)

    except mysql.connector.Error as err:
        return jsonify({"error": str(err)}), 500

    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
