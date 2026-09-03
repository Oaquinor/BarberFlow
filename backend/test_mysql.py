import pymysql
import sys

configs = [
    {"host": "127.0.0.1", "port": 3306, "user": "kingflow", "password": "kingflow123"},
    {"host": "localhost", "port": 3306, "user": "kingflow", "password": "kingflow123"},
]

for config in configs:
    try:
        print(f"Probando: {config['host']}:{config['port']} user={config['user']}")
        conn = pymysql.connect(**config, database="kingflow_barber", connect_timeout=10)
        cursor = conn.cursor()
        cursor.execute("SELECT VERSION()")
        version = cursor.fetchone()
        print(f"  -> EXITO! MySQL version: {version[0]}")
        cursor.close()
        conn.close()
        break
    except Exception as e:
        print(f"  -> FALLO: {e}")
