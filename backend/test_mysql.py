"""Manual MySQL connectivity diagnostic. Safe to import during test collection."""

import pymysql
from sqlalchemy.engine import make_url

from app.core.config import get_settings


def main() -> int:
    url = make_url(get_settings().DATABASE_URL)
    if url.get_backend_name() != "mysql":
        print("DATABASE_URL must target MySQL")
        return 2

    print(f"Connecting to MySQL at {url.host}:{url.port or 3306}/{url.database} ...")
    try:
        connection = pymysql.connect(
            host=url.host,
            port=url.port or 3306,
            user=url.username,
            password=url.password,
            database=url.database,
            connect_timeout=3,
            read_timeout=3,
            write_timeout=3,
        )
        with connection.cursor() as cursor:
            cursor.execute("SELECT VERSION()")
            version = cursor.fetchone()[0]
        connection.close()
    except Exception as exc:
        print(f"MySQL connection failed ({type(exc).__name__})")
        return 1

    print(f"MySQL connection successful (server {version})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
