from flask import Flask, render_template
import mysql.connector

app = Flask(__name__)

# XAMPP MySQL Configuration
db_config = {
    'user': 'root',
    'password': '',
    'host': '127.0.0.1',
    'port': 3306,
    'unix_socket': '/Applications/XAMPP/xamppfiles/var/mysql/mysql.sock',
    'database': 'py23db'
}

@app.route('/')
def index():
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)
        
        # Fetching items from the 'items' table
        cursor.execute("SELECT * FROM items")
        items = cursor.fetchall()
        
        cursor.close()
        conn.close()
        return render_template('index.html', items=items)
    except Exception as e:
        return f"Database Error: {str(e)}"

if __name__ == '__main__':
    # Running on port 5001 to avoid conflict with macOS Control Center
    app.run(host='0.0.0.0', port=5001, debug=True)
