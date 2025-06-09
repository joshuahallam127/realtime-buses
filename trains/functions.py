import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()

def get_connection():
    connection = mysql.connector.connect(
        host=os.getenv("RDS_HOST", '127.0.0.1'),
        port=int(os.getenv("RDS_PORT", 3308)),
        user=os.getenv("RDS_USER", 'root'),     
        password=os.getenv("RDS_PASSWORD", 'password'),
        database='trains'
    )
    cursor = connection.cursor()
    cursor.execute("SET time_zone = 'Australia/Sydney'")
    return connection, cursor