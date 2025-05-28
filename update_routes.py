import csv
import functions

conn, cursor = functions.get_connection()
with open('routes.csv', newline='', encoding='utf-8') as csvfile:
    reader = csv.DictReader(csvfile)
    for row in reader:
        cursor.execute("""
            INSERT INTO routes (id, long_name, is_in_sydney)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE
                long_name = VALUES(long_name),
                is_in_sydney = VALUES(is_in_sydney)
        """, (row['id'], row['long_name'], row['is_in_sydney'] == 'True'))
conn.commit()
cursor.close()
conn.close()