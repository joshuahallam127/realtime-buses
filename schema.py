import functions

conn, cursor = functions.get_connection()

# Create the 'stops' table
cursor.execute("""DROP TABLE IF EXISTS delays""")
cursor.execute("""CREATE TABLE delays (
    trip_id VARCHAR(9) PRIMARY KEY,
    route_id VARCHAR(9),
    stop_sequence SMALLINT UNSIGNED,
    arrival_delay SMALLINT UNSIGNED,
    departure_early SMALLINT UNSIGNED,
    start_date DATE
)""")
cursor.execute("""DROP TABLE IF EXISTS route_daily_delays""")
cursor.execute("""CREATE TABLE route_daily_delays (
    route_id VARCHAR(9),
    date DATE,
    total_delay INT UNSIGNED,
    delay_count INT UNSIGNED,
    PRIMARY KEY (route_id, date)
)""")
cursor.execute("""DROP TABLE IF EXISTS routes""")
cursor.execute("""CREATE TABLE routes (
    route_id VARCHAR(4) PRIMARY KEY,
    route_long_name VARCHAR(255),
    route_short_name VARCHAR(4),
    agency_id VARCHAR(4)
)""")

conn.commit()

# Close the cursor and connection
cursor.close()
conn.close()