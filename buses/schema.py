from functions import get_connection

conn, cursor = get_connection()

cursor.execute("""DROP TABLE IF EXISTS delay_history""")
cursor.execute("""DROP TABLE IF EXISTS route_shapes""")
cursor.execute("""DROP TABLE IF EXISTS stop_daily_delays""")
cursor.execute("""DROP TABLE IF EXISTS route_daily_delays""")
cursor.execute("""DROP TABLE IF EXISTS cancels""")
cursor.execute("""DROP TABLE IF EXISTS delays""")
cursor.execute("""DROP TABLE IF EXISTS routes""")
cursor.execute("DROP TABLE IF EXISTS stops")

cursor.execute(
    """CREATE TABLE routes (
    id VARCHAR(10) PRIMARY KEY,
    long_name VARCHAR(255),
    is_in_sydney BOOLEAN
)"""
)
cursor.execute(
    """CREATE TABLE stops (
    id VARCHAR(10) PRIMARY KEY,
    name VARCHAR(255),
    lat DECIMAL(9, 6),
    lon DECIMAL(9, 6)
)"""
)
# i think we use stop_sequence instead of stop_id because of loop services with buses
cursor.execute(
    """CREATE TABLE delays (
    trip_id VARCHAR(9) PRIMARY KEY,
    route_id VARCHAR(10) REFERENCES routes(id),
    stop_id VARCHAR(10) REFERENCES stops(id),
    stop_sequence SMALLINT UNSIGNED,
    arrival_delay SMALLINT UNSIGNED,
    departure_early SMALLINT UNSIGNED,
    timestamp DATETIME
)"""
)
cursor.execute(
    """CREATE TABLE cancels (
    trip_id VARCHAR(9) PRIMARY KEY,
    route_id VARCHAR(10) REFERENCES routes(id)
)"""
)
cursor.execute(
    """CREATE TABLE route_daily_delays (
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
)"""
)
cursor.execute(
    """CREATE TABLE stop_daily_delays (
    route_id VARCHAR(10),
    stop_id VARCHAR(10),
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
    total_trips SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    PRIMARY KEY (route_id, stop_id, date),
    FOREIGN KEY (route_id) REFERENCES routes(id),
    FOREIGN KEY (stop_id) REFERENCES stops(id)
)"""
)
cursor.execute(
    """CREATE TABLE route_shapes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    route_id VARCHAR(255) NOT NULL,
    shape_id VARCHAR(255) NOT NULL,
    shape_encoded TEXT,
    UNIQUE KEY (route_id, shape_id(191)),
    FOREIGN KEY (route_id) REFERENCES routes(id) ON DELETE CASCADE
)"""
)
cursor.execute(
    """CREATE TABLE delay_history (
    trip_id VARCHAR(9) NOT NULL,
    route_id VARCHAR(10),
    stop_id VARCHAR(10),
    stop_sequence SMALLINT UNSIGNED,
    arrival_delay SMALLINT UNSIGNED,
    departure_early SMALLINT UNSIGNED,
    timestamp DATETIME,
    PRIMARY KEY (trip_id, stop_id, timestamp)
)"""
)

conn.commit()

cursor.close()
conn.close()
