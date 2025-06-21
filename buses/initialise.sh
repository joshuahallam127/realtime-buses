# echo "Type confirm to run the script:"
# read confirm
# if [ "$confirm" != "confirm" ]; then
#     echo "Exiting..."
#     exit 1
# fi

python3 schema.py
python3 generate_routes_csv.py
python3 routes.py
python3 load_stops.py
python3 populate_routes_shapes.py