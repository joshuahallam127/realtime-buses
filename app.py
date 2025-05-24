from flask import Flask, jsonify, request
import mysql.connector
from dotenv import load_dotenv
import functions
from flask_cors import CORS
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

load_dotenv()

app = Flask(__name__)
CORS(app,origins=["https://howshitismybus.com.au", "https://www.howshitismybus.com.au"])

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
            SELECT route, ROUND(SUM(total_delay) / SUM(delay_count), 2) AS avg_delay
            FROM route_daily_delays
            WHERE date >= %s
            GROUP BY route
            ORDER BY avg_delay DESC
        """

        cursor.execute(query, (start_date, ))
        rows = cursor.fetchall()

        return jsonify([{'route': row[0], 'delay': row[1]} for row in rows])

    except mysql.connector.Error as err:
        return jsonify({"error": str(err)}), 500

    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
