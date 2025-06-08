import csv

route_desc_to_route_ids = {}
max_short_name_length = 0
with open('sydneytrains.csv', newline='', encoding='utf-8') as csvfile:
    reader = csv.DictReader(csvfile)
    for row in reader:
        if row['agency_id'] == 'SydneyTrains':
            row['is_in_sydney'] = True
        if row['route_desc'] not in route_desc_to_route_ids:
            route_desc_to_route_ids[row['route_desc']] = []
        route_desc_to_route_ids[row['route_desc']].append(row['route_id'])
        max_short_name_length = max(max_short_name_length, len(row['route_short_name']))

print(f"Max short name length: {max_short_name_length}")
exit()

for k, v in route_desc_to_route_ids.items():
    print(f"{k.ljust(40)}: {v}")