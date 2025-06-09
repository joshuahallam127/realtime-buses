from functions import get_connection

conn, cursor = get_connection()

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
    above_1_minute SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    above_2_minutes SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    above_5_minutes SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    above_10_minutes SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    above_15_minutes SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    above_30_minutes SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    before_1_minute SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    before_2_minutes SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    before_5_minutes SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    before_10_minutes SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    total_cancelled SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    total_trips SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    hits INT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (route_short_name, date)      
)""")
# sometimes trains don't stop at a station, so we might need to track cancellations per station? or is it cancelled for the whole trip? who knows
cursor.execute("""CREATE TABLE IF NOT EXISTS stop_daily_delays (
    route_short_name VARCHAR(3) REFERENCES routes(short_name),
    stop_id VARCHAR(10) REFERENCES stops(id),
    date DATE,
    total_delay INT UNSIGNED NOT NULL DEFAULT 0,
    total_early INT UNSIGNED NOT NULL DEFAULT 0,
    total_count INT UNSIGNED NOT NULL DEFAULT 0,
    above_1_minute SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    above_2_minutes SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    above_5_minutes SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    above_10_minutes SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    above_15_minutes SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    above_30_minutes SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    before_1_minute SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    before_2_minutes SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    before_5_minutes SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    before_10_minutes SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    hits INT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (route_short_name, stop_id, date)
)""")

conn.commit()

cursor.close()
conn.close()