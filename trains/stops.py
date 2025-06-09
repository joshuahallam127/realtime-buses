import csv
from functions import get_connection

stop_ids = set()
parent_stop_ids = set()
with open('stops.txt', newline='', encoding='utf-8') as csvfile:
    reader = csv.DictReader(csvfile)
    for row in reader:
        if ' Station, Platform ' in row['stop_name']:
            stop_ids.add(row['\ufeffstop_id'])
            parent_stop_ids.add(row['parent_station'])

conn, cursor = get_connection()
with open('stops.txt', newline='', encoding='utf-8') as csvfile:
    reader = csv.DictReader(csvfile)
    for row in reader:
        if row['\ufeffstop_id'] in parent_stop_ids:
            cursor.execute("""
                INSERT INTO stops (id, name)
                VALUES (%s, %s)
            """, (row['\ufeffstop_id'], row['stop_name']))
conn.commit()
cursor.close()
conn.close()

with open('stops.txt', newline='', encoding='utf-8') as csvfile:
    reader = csv.DictReader(csvfile)
    data = [row for row in reader if row['\ufeffstop_id'] in stop_ids]

with open('train_stops.csv', 'w', newline='', encoding='utf-8') as outfile:
    fieldnames = ['stop_id', 'parent_station']
    writer = csv.DictWriter(outfile, fieldnames=fieldnames)
    writer.writeheader()
    for row in data:
        writer.writerow({
            'stop_id': row['\ufeffstop_id'],
            'parent_station': row['parent_station']
        })