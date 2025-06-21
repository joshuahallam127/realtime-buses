import csv
from functions import get_connection

conn, cursor = get_connection()

# Clear existing data
cursor.execute("DELETE FROM stops")

with open('stops.txt', 'r') as f:
    reader = csv.reader(f)
    next(reader)  # Skip header row
    for row in reader:
        stop_id = row[0]
        stop_name = row[1]
        stop_lat = row[2]
        stop_lon = row[3]
        
        # The stops table uses VARCHAR(10) for id, let's check length
        if len(stop_id) > 10:
            print(f"Skipping stop_id {stop_id} as it is longer than 10 characters.")
            continue
            
        query = "INSERT INTO stops (id, name, lat, lon) VALUES (%s, %s, %s, %s)"
        values = (stop_id, stop_name, stop_lat, stop_lon)
        cursor.execute(query, values)

conn.commit()
cursor.close()
conn.close()

print("Stops table populated successfully.") 