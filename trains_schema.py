import functions

conn, cursor = functions.get_connection('trains')

cursor.execute("DROP TABLE IF EXISTS route_daily_delays")
cursor.execute("DROP TABLE IF EXISTS stop_daily_delays")
cursor.execute("DROP TABLE IF EXISTS delays")
cursor.execute("DROP TABLE IF EXISTS stops")
cursor.execute("DROP TABLE IF EXISTS routes")

cursor.execute("""CREATE TABLE IF NOT EXISTS routes (
    short_name VARCHAR(3) PRIMARY KEY,
    description VARCHAR(255) NOT NULL,
    is_in_sydney BOOLEAN
)""")
cursor.execute("""CREATE TABLE IF NOT EXISTS stops (
    id VARCHAR(7) PRIMARY KEY,
    name VARCHAR(255) NOT NULL
)""")
cursor.execute("""CREATE TABLE IF NOT EXISTS delays (
    trip_id VARCHAR(50) PRIMARY KEY,
    route_short_name VARCHAR(3) REFERENCES routes(short_name),
    stop_id VARCHAR(10) REFERENCES stops(id),
    arrival_delay SMALLINT UNSIGNED,
    departure_early SMALLINT UNSIGNED,
    start_date DATE
)""")
cursor.execute("""CREATE TABLE IF NOT EXISTS route_daily_delays (
    route_short_name VARCHAR(3) REFERENCES routes(short_name),
    date DATE,
    total_delay INT UNSIGNED NOT NULL DEFAULT 0,
    total_early INT UNSIGNED NOT NULL DEFAULT 0,
    total_count INT UNSIGNED NOT NULL DEFAULT 0,
    hits INT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (route_short_name, date)      
)""")
cursor.execute("""CREATE TABLE IF NOT EXISTS stop_daily_delays (
    route_short_name VARCHAR(3) REFERENCES routes(short_name),
    stop_id VARCHAR(10) REFERENCES stops(id),
    date DATE,
    total_delay INT UNSIGNED NOT NULL DEFAULT 0,
    total_early INT UNSIGNED NOT NULL DEFAULT 0,
    total_count INT UNSIGNED NOT NULL DEFAULT 0,
    hits INT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (route_short_name, stop_id, date)
)""")

conn.commit()

cursor.close()
conn.close()