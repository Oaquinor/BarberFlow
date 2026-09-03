import pymysql
import sys

def test_connection(host, port, user, password):
    try:
        connection = pymysql.connect(host=host, port=port, user=user, password=password, charset='utf8mb4', connect_timeout=5)
        connection.close()
        return True, "OK"
    except Exception as e:
        return False, str(e)

def setup_database():
    print("Probando configuraciones...\n")
    configs = [
        {'host': '127.0.0.1', 'port': 3306, 'user': 'root', 'password': ''},
        {'host': 'localhost', 'port': 3306, 'user': 'root', 'password': ''},
        {'host': '127.0.0.1', 'port': 3306, 'user': 'root', 'password': 'root'},
    ]
    working_config = None
    for i, config in enumerate(configs, 1):
        print(f"{i}. {config['host']}:{config['port']} user={config['user']}", end='')
        success, message = test_connection(**config)
        if success:
            print(f" -> OK")
            working_config = config
            break
        else:
            print(f" -> FAIL")
    if not working_config:
        print("\nNo se pudo conectar. Verifica que MySQL este corriendo en Laragon.")
        return False
    try:
        print(f"\nConectando con {working_config['host']}...")
        connection = pymysql.connect(**working_config, charset='utf8mb4')
        cursor = connection.cursor()
        print("Creando base de datos...")
        cursor.execute("CREATE DATABASE IF NOT EXISTS kingflow_barber CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        print("Creando usuario...")
        cursor.execute("DROP USER IF EXISTS 'kingflow'@'localhost'")
        cursor.execute("CREATE USER 'kingflow'@'localhost' IDENTIFIED BY 'kingflow123'")
        cursor.execute("GRANT ALL PRIVILEGES ON kingflow_barber.* TO 'kingflow'@'localhost'")
        cursor.execute("FLUSH PRIVILEGES")
        cursor.execute("USE kingflow_barber")
        print("\nCONFIGURACION COMPLETADA!")
        print(f"Host: {working_config['host']}")
        print(f"DATABASE_URL=mysql+pymysql://kingflow:kingflow123@{working_config['host']}:3306/kingflow_barber")
        cursor.close()
        connection.close()
        return True
    except Exception as e:
        print(f"\nError: {e}")
        return False

if __name__ == "__main__":
    success = setup_database()
    sys.exit(0 if success else 1)
