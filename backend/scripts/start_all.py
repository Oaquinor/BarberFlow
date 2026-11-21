#!/usr/bin/env python3
"""Start the MySQL-backed FastAPI app, which also serves its frontend."""

import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser

from sqlalchemy import create_engine, text

from app.core.config import get_settings


def check_mysql() -> bool:
    settings = get_settings()
    if not settings.DATABASE_URL.startswith("mysql+pymysql://"):
        print("DATABASE_URL must use mysql+pymysql.")
        return False
    engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        print("MySQL connection is ready.")
        return True
    except Exception as exc:
        print(f"MySQL connection failed ({type(exc).__name__}). Check backend/.env and the MySQL service.")
        return False
    finally:
        engine.dispose()


def wait_for_backend(url: str, process: subprocess.Popen, timeout_seconds: int = 30) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline and process.poll() is None:
        try:
            with urllib.request.urlopen(f"{url}/health", timeout=2) as response:
                if response.status == 200:
                    return True
        except (urllib.error.URLError, TimeoutError):
            time.sleep(0.5)
    return False


def main() -> int:
    if not check_mysql():
        return 1
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    command = [
        sys.executable, "-m", "uvicorn", "app.main:app", "--reload",
        "--host", "127.0.0.1", "--port", "8000",
    ]
    process = subprocess.Popen(command, cwd=backend_dir)
    base_url = "http://127.0.0.1:8000"
    try:
        if not wait_for_backend(base_url, process):
            print("Backend did not become healthy. Check its startup output above.")
            return 1
        print("KingFlow is available at http://127.0.0.1:8000")
        print("Create the first administrator with: python -m scripts.create_admin")
        webbrowser.open(base_url)
        process.wait()
        return process.returncode or 0
    except KeyboardInterrupt:
        print("Stopping KingFlow...")
        return 0
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    raise SystemExit(main())
