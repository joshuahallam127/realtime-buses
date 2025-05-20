import functions  # Assumes you have get_connection() defined here

def get_average_delay_by_route():
    conn, cursor = functions.get_connection()
    
    query = """
        SELECT route, ROUND(AVG(arrival_delay), 2) as avg_delay
        FROM delays
        GROUP BY route
        ORDER BY avg_delay DESC
    """
    
    cursor.execute(query)
    results = cursor.fetchall()

    print("Average Arrival Delay by Route:")
    print("--------------------------------")
    for route, avg_delay in results:
        print(f"Route {route}: {avg_delay} seconds")

    cursor.close()
    conn.close()

get_average_delay_by_route()