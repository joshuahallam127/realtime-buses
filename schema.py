import functions

conn, cursor = functions.get_connection()

# Create the 'stops' table
cursor.execute("""DROP TABLE IF EXISTS delays""")
cursor.execute("""CREATE TABLE delays (
    trip_id VARCHAR(9),
    route VARCHAR(4),
    stop_sequence SMALLINT UNSIGNED,
    arrival_delay SMALLINT UNSIGNED,
    start_date DATE,
    UNIQUE KEY (trip_id, stop_sequence, start_date)
)""")

# Close the cursor and connection
cursor.close()
conn.close()