import mysql.connector
def get_connection():
    # Establish connection to the MySQL database
    connection = mysql.connector.connect(
        host='127.0.0.1',      # Docker container is accessible via localhost
        port=3308,             # Port where your MySQL container is running
        user='root',  # Replace with your MySQL username
        password='password',  # Replace with your MySQL password
        database='buses'    # Database name
    )
    cursor = connection.cursor()
    return connection, cursor