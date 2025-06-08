import csv
import functions

data = set()
with open('sydneytrains.csv', newline='', encoding='utf-8') as csvfile:
    reader = csv.DictReader(csvfile)
    for row in reader:
        if row['route_short_name'] == 'T1':
            continue
        if row['agency_id'] == 'SydneyTrains':
            data.add((row['route_short_name'], row['route_desc'], True))
        else:
            data.add((row['route_short_name'], row['route_short_name'] + ' ' + row['route_desc'], False))
            
data.add(('T1', 'T1 North Shore & Western Line', True))  # Add T1 route manually

conn, cursor = functions.get_connection('trains')
cursor.executemany("""
    INSERT INTO routes (short_name, description, is_in_sydney)
    VALUES (%s, %s, %s)
""", list(data))

conn.commit()

cursor.close()
conn.close()