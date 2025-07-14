# echo "Type confirm to run the script:"
# read confirm
# if [ "$confirm" != "confirm" ]; then
#     echo "Exiting..."
#     exit 1
# fi

python3 download_txt_files.py
python3 migration.py
python3 routes.py
python3 stops.py
python3 route_shapes.py

# TODO just put this in one script, and work out when we have to refresh 
# these things