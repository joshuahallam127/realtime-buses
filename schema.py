'''
stop_times:
    trip_id: string
    stop_id: string
    departure_time: time

stops:
    stop_id: string
    stop_lat: float
    stop_lon: float
'''

'''
delays:
    trip_id: string
    route: string
    stop_sequence: int
    arrival_delay: int
    start_date: date
'''
import functions

conn, cursor = functions.get_connection()



# Create the 'stops' table
cursor.execute("""DROP TABLE IF EXISTS delays""")
cursor.execute("""CREATE TABLE delays (
    trip_id VARCHAR(255),
    route VARCHAR(255),
    stop_sequence INT,
    arrival_delay INT,
    start_date DATE,
    UNIQUE KEY (trip_id, stop_sequence, start_date)
)""")

# Close the cursor and connection
cursor.close()
conn.close()