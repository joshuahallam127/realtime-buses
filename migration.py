import functions

conn, cursor = functions.get_connection()
cursor.execute("""
    ALTER TABLE route_daily_delays 
    ADD COLUMN hits INT UNSIGNED NOT NULL DEFAULT 0;
""")
cursor.execute("""
    ALTER TABLE route_daily_delays
    MODIFY total_delay INT UNSIGNED NOT NULL DEFAULT 0,
    MODIFY total_early INT UNSIGNED NOT NULL DEFAULT 0,
    MODIFY total_count INT UNSIGNED NOT NULL DEFAULT 0;
""")
conn.commit()
cursor.close()
conn.close()