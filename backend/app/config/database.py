import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

DATABASE_PATH_ENV = "ACCESS_CONTROL_DB_PATH"
DEFAULT_DATABASE_PATH = Path(__file__).resolve().parents[2] / "data" / "access_control.sqlite3"


def get_database_path() -> Path:
    configured_path = os.getenv(DATABASE_PATH_ENV)
    if configured_path:
        return Path(configured_path).expanduser().resolve()
    return DEFAULT_DATABASE_PATH


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    database_path = get_database_path()
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database() -> None:
    with get_connection() as connection:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                hub_id TEXT NOT NULL,
                name TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('ADMIN', 'APP_USER', 'PHYSICAL_ONLY')),
                has_app_access INTEGER NOT NULL DEFAULT 0 CHECK (has_app_access IN (0, 1)),
                email TEXT,
                allowed_cameras TEXT NOT NULL,
                embedding TEXT
            );

            CREATE TABLE IF NOT EXISTS logs (
                id TEXT PRIMARY KEY,
                hub_id TEXT NOT NULL,
                camera_id TEXT NOT NULL,
                user_id TEXT,
                user_name TEXT,
                status TEXT NOT NULL CHECK (status IN ('GRANTED', 'DENIED')),
                timestamp TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
            );

            CREATE INDEX IF NOT EXISTS idx_users_hub
                ON users(hub_id);
            CREATE INDEX IF NOT EXISTS idx_logs_hub_camera_timestamp
                ON logs(hub_id, camera_id, timestamp DESC);
            CREATE INDEX IF NOT EXISTS idx_logs_user_timestamp
                ON logs(user_id, timestamp DESC);
            """
        )
