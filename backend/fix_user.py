import pymysql.cursors
import sys

# Intentar conectar como root sin password (default de Laragon)
configs = [
    {"host": "127.0.0.1", "port": 3306, "user": "root", "password": ""},
    {"host": "localhost", "port": 3306, "user": "root", "password": ""},
    {"host": "127.0.0.1", "port": 3306, "user": "root", "password": "root"},
]

connection = None
for config in configs:
    try:
        print(f"Intentando conectar como root con {config['host']}...")
        connection = pymysql.connect(**config, connect_timeout=10, charset='utf8mb4', cursorclass=pymysql.cursors.DictCursor)
        print(f"  -> Conectado exitosamente!\n")
        break
    except Exception as e:
        print(f"  -> Fallo: {e}")

if not connection:
    print("\nNo se pudo conectar como root. Por favor:")
    print("1. Abre HeidiSQL desde Laragon")
    print("2. Ejecuta el script SQL manualmente")
    sys.exit(1)

try:
    cursor = connection.cursor()
    
    print("Eliminando usuario anterior si existe...")
    cursor.execute("DROP USER IF EXISTS 'kingflow'@'localhost'")
    
    print("Creando usuario con mysql_native_password...")
    cursor.execute("CREATE USER 'kingflow'@'localhost' IDENTIFIED WITH mysql_native_password BY 'kingflow123'")
    
    print("Otorgando permisos...")
    cursor.execute("GRANT ALL PRIVILEGES ON kingflow_barber.* TO 'kingflow'@'localhost'")
    cursor.execute("FLUSH PRIVILEGES")
    
    print("Verificando usuario...")
    cursor.execute("SELECT user, host, plugin FROM mysql.user WHERE user='kingflow'")
    result = cursor.fetchone()
    
    print(f"\nUSUARIO CONFIGURADO EXITOSAMENTE!")
    print(f"Usuario: {result['user']}")
    print(f"Host: {result['host']}")
    print(f"Plugin: {result['plugin']}")
    
    cursor.close()
    connection.close()
    print("\nAhora puedes ejecutar: alembic upgrade head")
    
except Exception as e:
    print(f"\nError al configurar usuario: {e}")
    sys.exit(1)
