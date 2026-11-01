"""Quick inspection of the local SQLite database, with no external tool.

Usage (from the backend folder, with the virtual environment active):
    python tools/inspect_db.py

The script only READS the database. It modifies and deletes nothing.
The database path can be overridden with the ACCESS_CONTROL_DB_PATH
environment variable, exactly as in the FastAPI application.
"""

import os
import sqlite3
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parents[1] / "data" / "access_control.sqlite3"


def resolve_db_path() -> Path:
    configured = os.getenv("ACCESS_CONTROL_DB_PATH")
    return Path(configured).expanduser().resolve() if configured else DEFAULT_DB


def main() -> None:
    db_path = resolve_db_path()
    print(f"Database: {db_path}")

    if not db_path.exists():
        print("The file does not exist yet. Start the backend once to create it:")
        print("  python -m uvicorn main:app --reload --port 8000")
        return

    print(f"Size: {db_path.stat().st_size} bytes\n")

    # mode=ro -> strictly read-only, so the data cannot be damaged by accident
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row

    schema_version = connection.execute("PRAGMA user_version").fetchone()[0]
    print(f"Schema version: {schema_version}\n")

    tables = [
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    ]
    print(f"Tables: {', '.join(tables) or '(none)'}\n")

    for table in tables:
        count = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        columns = [row["name"] for row in connection.execute(f"PRAGMA table_info({table})")]
        print(f"--- {table}: {count} rows ---")
        print(f"Columns: {', '.join(columns)}")

        for row in connection.execute(f"SELECT * FROM {table} LIMIT 5"):
            print("  ", dict(row))
        if count > 5:
            print(f"   ... and {count - 5} more rows")
        print()

    connection.close()


if __name__ == "__main__":
    main()
