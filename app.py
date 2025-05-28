from flask import Flask, jsonify, request
import mysql.connector
from dotenv import load_dotenv
import functions
from flask_cors import CORS
import csv

load_dotenv()

app = Flask(__name__)
CORS(app,origins=["https://howshitismybus.com.au", "https://www.howshitismybus.com.au"])

@app.route('/api/bus-delays', methods=['GET'])
def get_average_delays():
    try:
        conn, cursor = functions.get_connection()

        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        sydney_only = request.args.get('sydney_only') == 'true'

        query = """
            SELECT rdd.route_id, routes.long_name, ROUND(SUM(rdd.total_delay) / SUM(rdd.total_count), 2) AS avg_delay
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
            result.append({'route': f'{row[0].split("_")[1]} {row[1]}', 'delay': row[2], 'rank': i + 1})
        return jsonify(result)

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
