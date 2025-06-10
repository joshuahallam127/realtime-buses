from functions import get_connection

conn, cursor = get_connection()

cursor.execute("""DROP TABLE IF EXISTS route_daily_delays""")
cursor.execute("""DROP TABLE IF EXISTS cancels""")
cursor.execute("""DROP TABLE IF EXISTS delays""")
cursor.execute("""DROP TABLE IF EXISTS routes""")

cursor.execute("""CREATE TABLE routes (
    id VARCHAR(10) PRIMARY KEY,
    long_name VARCHAR(255),
    is_in_sydney BOOLEAN
)""")
# i think we use stop_sequence instead of stop_id because of loop services with buses
cursor.execute("""CREATE TABLE delays (
    trip_id VARCHAR(9) PRIMARY KEY,
    route_id VARCHAR(10) REFERENCES routes(id),
    stop_sequence SMALLINT UNSIGNED,
    arrival_delay SMALLINT UNSIGNED,
    departure_early SMALLINT UNSIGNED
)""")
cursor.execute("""CREATE TABLE cancels (
    trip_id VARCHAR(9) PRIMARY KEY,
    route_id VARCHAR(10) REFERENCES routes(id)
)""")
cursor.execute("""CREATE TABLE route_daily_delays (
    route_id VARCHAR(10) REFERENCES routes(id),
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
    PRIMARY KEY (route_id, date)
)""")

conn.commit()

cursor.close()
conn.close()