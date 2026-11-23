"""Compatibility entry point for the interactive MySQL setup utility."""

from setup_db import setup_database


if __name__ == "__main__":
    raise SystemExit(0 if setup_database() else 1)
