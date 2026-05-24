from flask import Flask, render_template
import mysql.connector

app = Flask(__name__)

# Database configuration
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': '', # XAMPP default is usually empty
    'database': 'py23db'
}

def get_db_connection():
    try:
        conn = mysql.connector.connect(**db_config)
        return conn
    except mysql.connector.Error as err:
        print(f"Error: {err}")
        return None

@app.route('/')
def index():
    conn = get_db_connection()
    if conn is None:
        return "Database connection failed. Please check if XAMPP MySQL is running."
    
    cursor = conn.cursor(dictionary=
True)
    try:
        cursor.execute("SELECT * FROM items")
        items = cursor.fetchall()
    except mysql.connector.Error as err:
        return f"Query error: {err}"
    finally:
        cursor.close()
        conn.close()
        
    return render_template('index.html', items=items)

if __name__ == '__main__':
    app.run(debug=True, port=5000)
