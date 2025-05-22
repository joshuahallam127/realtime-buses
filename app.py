from flask import Flask, jsonify
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

        # Calculate dates for filtering
        now_in_sydney = datetime.now(ZoneInfo('Australia/Sydney'))
        today = now_in_sydney.date()
        seven_days_ago = today - timedelta(days=7)
        thirty_days_ago = today - timedelta(days=30)

        query = """
            SELECT
                route,
                ROUND(AVG(CASE WHEN DATE(start_date) = %s THEN arrival_delay END), 2) AS daily_avg,
                ROUND(AVG(CASE WHEN DATE(start_date) >= %s THEN arrival_delay END), 2) AS weekly_avg,
                ROUND(AVG(CASE WHEN DATE(start_date) >= %s THEN arrival_delay END), 2) AS monthly_avg,
                ROUND(AVG(arrival_delay), 2) AS all_time_avg
            FROM delays
            WHERE stop_sequence > 1
            GROUP BY route
            ORDER BY all_time_avg DESC
        """
        query = """
            SELECT
                route,
                ROUND(AVG(CASE WHEN DATE(start_date) = %s THEN arrival_delay END), 2) AS daily_avg,
            FROM delays
            WHERE stop_sequence > 1
            GROUP BY route
            ORDER BY all_time_avg DESC
        """

        # cursor.execute(query, (today, seven_days_ago, thirty_days_ago))
        cursor.execute(query, (today))
        rows = cursor.fetchall()

        # Transform to desired JSON structure
        results = []
        for row in rows:
            route = row[0]
            daily = row[1] if row[1] is not None else 0
            # weekly = row[2] if row[2] is not None else 0
            # monthly = row[3] if row[3] is not None else 0
            # all_time = row[4] if row[4] is not None else 0

            results.append({
                "route": route,
                "delays": {
                    "daily": float(daily),
                    # "weekly": float(weekly),
                    # "monthly": float(monthly),
                    # "all time": float(all_time)
                }
            })

        return jsonify(results)

    except mysql.connector.Error as err:
        return jsonify({"error": str(err)}), 500

    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
