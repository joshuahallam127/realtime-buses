from functions import get_connection

conn, cursor = get_connection()
cursor.execute("""ALTER TABLE delays DROP COLUMN start_date""")
cursor.execute("""CREATE TABLE cancels (
    trip_id VARCHAR(9) PRIMARY KEY,
    route_id VARCHAR(10) REFERENCES routes(id)
)""")
conn.commit()
cursor.close()
conn.close()