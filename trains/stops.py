import csv
from functions import get_connection

conn, cursor = get_connection()
with open('stops.csv', newline='', encoding='utf-8') as csvfile:
    reader = csv.DictReader(csvfile)
    for row in reader:
        cursor.execute("""
            INSERT INTO stops (id, name)
            VALUES (%s, %s)
        """, (row['stop_id'], row['name']))
conn.commit()
cursor.close()
conn.close()
