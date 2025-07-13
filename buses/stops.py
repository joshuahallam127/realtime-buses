import csv
from functions import get_connection

conn, cursor = get_connection()

with open('stops.txt', newline='', encoding='utf-8') as csvfile:
    stops = [(row['stop_id'], row['stop_name'], row['stop_lat'], row['stop_lon']) for row in csv.DictReader(csvfile)]

cursor.executemany("INSERT INTO stops (id, name, lat, lon) VALUES (%s, %s, %s, %s)", stops)
conn.commit()
cursor.close()
conn.close()