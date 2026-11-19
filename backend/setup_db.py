"""Create the KingFlow MySQL database and a least-privilege application user."""

import getpass
import sys
import pymysql


def setup_database() -> bool:
    host = input("MySQL host [127.0.0.1]: ").strip() or "127.0.0.1"
    port_text = input("MySQL port [3307]: ").strip() or "3307"
    admin_user = input("MySQL administrator user [root]: ").strip() or "root"
    admin_password = getpass.getpass("MySQL administrator password: ")
    app_password = getpass.getpass("New password for the KingFlow database user: ")
    if len(app_password) < 20:
        print("Use a randomly generated database password with at least 20 characters.")
        return False

    connection = None
    try:
        connection = pymysql.connect(
            host=host,
            port=int(port_text),
            user=admin_user,
            password=admin_password,
            charset="utf8mb4",
            connect_timeout=5,
            autocommit=True,
        )
        with connection.cursor() as cursor:
            cursor.execute(
                "CREATE DATABASE IF NOT EXISTS kingflow_barber "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
            escaped_password = connection.escape(app_password)
            cursor.execute(
                f"CREATE USER IF NOT EXISTS 'kingflow'@'%' IDENTIFIED BY {escaped_password}"
            )
            cursor.execute(
                f"ALTER USER 'kingflow'@'%' IDENTIFIED BY {escaped_password}"
            )
            cursor.execute(
                "GRANT ALL PRIVILEGES ON kingflow_barber.* TO 'kingflow'@'%'"
            )
        print("Created/verified the kingflow_barber database and application user.")
        print("Set DATABASE_URL in backend/.env using the password you entered.")
        print(
            "URL template: mysql+pymysql://kingflow:<URL-ENCODED-PASSWORD>@"
            f"{host}:{int(port_text)}/kingflow_barber"
        )
        print("URL-encode special characters in the password before placing it in DATABASE_URL.")
        return True
    except Exception as exc:
        print(f"MySQL setup failed ({type(exc).__name__}). Check the host and administrator access.")
        return False
    finally:
        if connection:
            connection.close()


if __name__ == "__main__":
    sys.exit(0 if setup_database() else 1)
