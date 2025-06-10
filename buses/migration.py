from functions import get_connection

conn, cursor = get_connection()
cursor.execute("""ALTER TABLE delays
    DROP COLUMN IF EXISTS date
""")