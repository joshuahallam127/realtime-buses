import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()

# def get_connection():
#     # Establish connection to the MySQL database
#     connection = mysql.connector.connect(
#         host='127.0.0.1',      # Docker container is accessible via localhost
#         port=3308,             # Port where your MySQL container is running
#         user='root',  # Replace with your MySQL username
#         password='password',  # Replace with your MySQL password
#         database='buses'    # Database name
#     )
#     cursor = connection.cursor()
#     return connection, cursor

def get_connection():
    # Connect to the Amazon RDS MySQL instance
    connection = mysql.connector.connect(
        host=os.getenv("RDS_HOST", '127.0.0.1'),         # e.g. my-db.xxxxxx.ap-southeast-2.rds.amazonaws.com
        port=int(os.getenv("RDS_PORT", 3308)),  # default MySQL port
        user=os.getenv("RDS_USER", 'root'),         # e.g. admin
        password=os.getenv("RDS_PASSWORD", 'password'), # your RDS password
        database=os.getenv("RDS_DB", 'buses')        # e.g. buses
    )
    cursor = connection.cursor()
    return connection, cursor