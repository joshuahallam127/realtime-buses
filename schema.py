import functions

conn, cursor = functions.get_connection()

# drop existing tables if they exist
cursor.execute("""DROP TABLE IF EXISTS route_daily_delays""")
cursor.execute("""DROP TABLE IF EXISTS delays""")
cursor.execute("""DROP TABLE IF EXISTS routes""")

# create new tables
cursor.execute("""CREATE TABLE routes (
    id VARCHAR(10) PRIMARY KEY,
    long_name VARCHAR(255),
    is_in_sydney BOOLEAN
)""")
cursor.execute("""CREATE TABLE delays (
    trip_id VARCHAR(9) PRIMARY KEY,
    route_id VARCHAR(10) REFERENCES routes(id),
    stop_sequence SMALLINT UNSIGNED,
    arrival_delay SMALLINT UNSIGNED,
    departure_early SMALLINT UNSIGNED,
    start_date DATE
)""")
cursor.execute("""CREATE TABLE route_daily_delays (
    route_id VARCHAR(10) REFERENCES routes(id),
    date DATE,
    total_delay INT UNSIGNED NOT NULL DEFAULT 0,
    total_early INT UNSIGNED NOT NULL DEFAULT 0,
    total_count INT UNSIGNED NOT NULL DEFAULT 0,
    hits INT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (route_id, date)
)""")

# commit the changes
conn.commit()

# Close the cursor and connection
cursor.close()
conn.close()