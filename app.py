from flask import Flask, jsonify, request
import mysql.connector
from dotenv import load_dotenv
import functions
from flask_cors import CORS

load_dotenv()

app = Flask(__name__)
CORS(app,origins=["https://howshitismybus.com.au", "https://www.howshitismybus.com.au"])

@app.route('/bus-delays', methods=['GET'])
def get_average_delays():
    try:
        conn, cursor = functions.get_connection()

        cursor.execute("""
            SELECT route, ROUND(AVG(arrival_delay), 2) AS average_delay
            FROM delays
            WHERE stop_sequence > 1
            GROUP BY route
            ORDER BY average_delay DESC
        """)

        result = cursor.fetchall()
        return jsonify(result)
    
    except mysql.connector.Error as err:
        return jsonify({"error": str(err)}), 500
    
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()

@app.route('/route-delay')
def get_route_delay():
    try:
        conn, cursor = functions.get_connection()
        route = request.args.get('route')
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*), AVG(arrival_delay), MAX(arrival_delay)
            FROM delays
            WHERE route = %s AND start_date = CURRENT_DATE()
        """, (route,))
        count, avg, max_delay = cursor.fetchone()
        return jsonify({
            'total': count,
            'avgDelay': round(avg or 0, 2),
            'latestDelay': max_delay or 0
        })
    except mysql.connector.Error as err:
        return jsonify({"error": str(err)}), 500
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()

@app.route('/leaderboard')
def leaderboard():
    try:
        range = request.args.get('range', 'daily')
        conn, cursor = functions.get_connection()
        cursor = conn.cursor()

        if range == 'daily':
            date_clause = "start_date = CURRENT_DATE()"
        elif range == 'weekly':
            date_clause = "start_date >= CURRENT_DATE() - INTERVAL 7 DAY"
        elif range == 'monthly':
            date_clause = "start_date >= CURRENT_DATE() - INTERVAL 30 DAY"
        else:
            date_clause = "1=1"

        cursor.execute(f"""
            SELECT route, COUNT(*) as count, AVG(arrival_delay) as avg
            FROM delays
            WHERE {date_clause}
            GROUP BY route
            HAVING count > 5
            ORDER BY avg DESC
            LIMIT 10
        """)
        rows = cursor.fetchall()
        return jsonify([{'route': r[0], 'count': r[1], 'avg': round(r[2], 2)} for r in rows])
    except mysql.connector.Error as err:
        return jsonify({"error": str(err)}), 500
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
