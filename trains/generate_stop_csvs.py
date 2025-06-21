import csv

stop_ids = set()
parent_stop_ids = set()
data = []
with open('stops.txt', newline='', encoding='utf-8') as csvfile:
    reader = csv.DictReader(csvfile)
    for row in reader:
        if ' Station, Platform ' in row['stop_name']:
            stop_ids.add(row['stop_id'])
            parent_stop_ids.add(row['parent_station'])
            data.append(row)

parent_data = []
with open('stops.txt', newline='', encoding='utf-8') as csvfile:
    reader = csv.DictReader(csvfile)
    for row in reader:
        if row['stop_id'] in parent_stop_ids:
            parent_data.append(row)

with open('stops.csv', 'w', newline='', encoding='utf-8') as outfile:
    fieldnames = ['stop_id', 'name']
    writer = csv.DictWriter(outfile, fieldnames=fieldnames)
    writer.writeheader()
    for row in parent_data:
        writer.writerow({
            'stop_id': row['stop_id'],
            'name': row['stop_name']
        })

with open('stop_to_parent.csv', 'w', newline='', encoding='utf-8') as outfile:
    fieldnames = ['stop_id', 'parent_station']
    writer = csv.DictWriter(outfile, fieldnames=fieldnames)
    writer.writeheader()
    for row in data:
        writer.writerow({
            'stop_id': row['stop_id'],
            'parent_station': row['parent_station']
        })