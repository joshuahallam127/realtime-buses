from functions import get_connection

conn, cursor = get_connection()
cursor.execute("TRUNCATE TABLE stops")
cursor.execute(
    """CREATE TABLE stops (
    id VARCHAR(10) PRIMARY KEY,
    name VARCHAR(255),
    lat DECIMAL(9, 6),
    lon DECIMAL(9, 6)
)"""
)
cursor.execute("TRUNCATE TABLE delays")
cursor.execute("""ALTER TABLE delays 
    ADD COLUMN stop_id VARCHAR(10) NOT NULL,
    ADD COLUMN timestamp DATETIME
""")
cursor.execute("""ALTER TABLE delays 
    ADD FOREIGN KEY (stop_id) REFERENCES stops(id)
""")
cursor.execute(
    """CREATE TABLE stop_daily_delays (
    route_id VARCHAR(10) NOT NULL REFERENCES routes(id),
    stop_id VARCHAR(10) NOT NULL REFERENCES stops(id),
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
    PRIMARY KEY (route_id, stop_id, date)
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