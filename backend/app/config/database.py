"""Local SQLite configuration and the schema migration mechanism.

Why migrations exist
--------------------
The schema is defined in code rather than in a web console (see the Firestore
versus SQLite discussion). That means every schema change must be applied by
us, explicitly, and also to databases that ALREADY exist.

``CREATE TABLE IF NOT EXISTS`` is not enough: when the table already exists
the statement is skipped entirely, so a new column added there never appears
on an older database. The result would be a ``no such column`` error in
production, on the Raspberry Pi, after an apparently harmless update.

The solution used here is schema versioning through ``PRAGMA user_version``,
an integer stored in the SQLite file header. At start-up we compare the
version in the file with the version in the code and apply only the missing
steps.

How to add a new migration
--------------------------
1. Append a new tuple at the end of ``MIGRATIONS``, with the next version.
2. Write the SQL as small steps, idempotent where possible.
3. NEVER modify a migration that has already shipped -- existing databases
   have applied it and will not run it again. Any correction becomes a new
   migration.

Example, for authentication:

    (
        2,
        "Add password_hash for authentication",
        ("ALTER TABLE users ADD COLUMN password_hash TEXT",),
    )
"""

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

DATABASE_PATH_ENV = "ACCESS_CONTROL_DB_PATH"
DEFAULT_DATABASE_PATH = Path(__file__).resolve().parents[2] / "data" / "access_control.sqlite3"


# ---------------------------------------------------------------------------
# Migration definitions
# ---------------------------------------------------------------------------
# Each entry: (version, description, SQL statements executed in order).
#
# Migration 1 is a "baseline" migration: it uses IF NOT EXISTS because it has
# to work in TWO different situations:
#   - a brand new, completely empty database -> creates everything
#   - a database created before migrations were introduced (user_version=0 but
#     the tables already exist) -> breaks nothing, only records version 1
MIGRATIONS: tuple[tuple[int, str, tuple[str, ...]], ...] = (
    (
        1,
        "Initial schema: users, logs and their indexes",
        (
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
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS logs (
                id TEXT PRIMARY KEY,
                hub_id TEXT NOT NULL,
                camera_id TEXT NOT NULL,
                user_id TEXT,
                user_name TEXT,
                status TEXT NOT NULL CHECK (status IN ('GRANTED', 'DENIED')),
                timestamp TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_users_hub ON users(hub_id)",
            """
            CREATE INDEX IF NOT EXISTS idx_logs_hub_camera_timestamp
                ON logs(hub_id, camera_id, timestamp DESC)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_logs_user_timestamp
                ON logs(user_id, timestamp DESC)
            """,
        ),
    ),
    (
        2,
        "Authentication: password_hash and email uniqueness",
        (
            # The column is optional (NULL allowed) by construction: a person
            # without application access never has a password, so they can
            # never authenticate. The third RBAC tier follows from the schema.
            "ALTER TABLE users ADD COLUMN password_hash TEXT",
            # Email is the login identity, so it must be unique. The index is
            # PARTIAL (`WHERE email IS NOT NULL`) because people without
            # application access may have a NULL email, and SQLite would treat
            # several NULLs as distinct anyway -- the partial index makes the
            # intent explicit and avoids the cost on rows without an email.
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_unique
                ON users(email) WHERE email IS NOT NULL
            """,
        ),
    ),
    (
        3,
        "Cameras entity, per-camera permissions and snapshot_path on logs",
        (
            # The primary key is composite (hub_id, camera_id): `camera_id` is
            # the readable identifier used in `allowed_cameras` and in the
            # journal, and it must be unique WITHIN a hub, not globally. Two
            # hubs may each have a camera with the same name without clashing.
            """
            CREATE TABLE IF NOT EXISTS cameras (
                hub_id TEXT NOT NULL,
                camera_id TEXT NOT NULL,
                name TEXT NOT NULL,
                kind TEXT NOT NULL DEFAULT 'USB'
                    CHECK (kind IN ('USB', 'CSI', 'RTSP')),
                source TEXT,
                enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
                created_at TEXT NOT NULL,
                PRIMARY KEY (hub_id, camera_id)
            )
            """,
            "CREATE INDEX IF NOT EXISTS idx_cameras_hub ON cameras(hub_id)",
            # A DATA migration, not just a schema one: existing people already
            # have a default entry in `allowed_cameras`. Once permissions are
            # validated against this table, an empty table would invalidate
            # every existing permission at once. So the default camera is
            # created for each hub that already has people.
            #
            # The Romanian literals below are HISTORICAL and must stay exactly
            # as shipped: this migration has already run on existing
            # databases, so editing it would give a fresh database a different
            # result from an upgraded one while both report version 3.
            # Migration 4 renames the id and the label to English, which is
            # the correct way to change a value that has already been written.
            """
            INSERT OR IGNORE INTO cameras (
                hub_id, camera_id, name, kind, source, enabled, created_at
            )
            SELECT DISTINCT
                hub_id,
                'cam_intrare',
                'Cameră intrare',
                'USB',
                NULL,
                1,
                strftime('%Y-%m-%dT%H:%M:%SZ', 'now')
            FROM users
            """,
            # Decision D2: a photo is stored ONLY for events involving an
            # unidentified person. The column is optional; a journal row with
            # no image (a known person, or a photo removed by the retention
            # policy) holds NULL.
            "ALTER TABLE logs ADD COLUMN snapshot_path TEXT",
        ),
    ),
    (
        4,
        "Decision D3: surveillance vocabulary (MONITORED role, detection outcomes)",
        (
            # Decision D3 removed the lock: the system observes and alerts, it
            # does not grant physical access. Two schema consequences:
            #   - the `PHYSICAL_ONLY` role no longer describes anything
            #     -> `MONITORED`;
            #   - `logs.status` is no longer `GRANTED`/`DENIED` but the
            #     detection reason, at the granularity the thesis evaluation
            #     chapter needs.
            #
            # Both are CHECK constraints, and SQLite CANNOT alter a CHECK with
            # ALTER TABLE. The only way is the documented rebuild procedure:
            # new table -> copy -> DROP -> RENAME -> recreate indexes.
            #
            # IMPORTANT: this works because `_get_migration_connection` does
            # NOT enable `PRAGMA foreign_keys`. With foreign keys enforced,
            # `DROP TABLE users` would fail due to the reference from `logs`,
            # and `PRAGMA foreign_keys` is a no-op inside a transaction, so it
            # could not be turned off here. If anyone ever enables foreign
            # keys on the migration connection, this migration breaks on
            # existing databases.
            #
            # Indexes are dropped together with their table and MUST be
            # recreated explicitly at the end, otherwise log pagination loses
            # its index.
            """
            CREATE TABLE users_v4 (
                id TEXT PRIMARY KEY,
                hub_id TEXT NOT NULL,
                name TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('ADMIN', 'APP_USER', 'MONITORED')),
                has_app_access INTEGER NOT NULL DEFAULT 0 CHECK (has_app_access IN (0, 1)),
                email TEXT,
                allowed_cameras TEXT NOT NULL,
                embedding TEXT,
                password_hash TEXT
            )
            """,
            # Columns are listed explicitly rather than using `SELECT *`:
            # migration 2 appended `password_hash` via ALTER, so the physical
            # column order differs between a database created from scratch and
            # one that was migrated.
            """
            INSERT INTO users_v4 (
                id, hub_id, name, role, has_app_access,
                email, allowed_cameras, embedding, password_hash
            )
            SELECT
                id, hub_id, name,
                CASE role WHEN 'PHYSICAL_ONLY' THEN 'MONITORED' ELSE role END,
                has_app_access, email, allowed_cameras, embedding, password_hash
            FROM users
            """,
            "DROP TABLE users",
            "ALTER TABLE users_v4 RENAME TO users",
            "CREATE INDEX idx_users_hub ON users(hub_id)",
            """
            CREATE UNIQUE INDEX idx_users_email_unique
                ON users(email) WHERE email IS NOT NULL
            """,
            """
            CREATE TABLE logs_v4 (
                id TEXT PRIMARY KEY,
                hub_id TEXT NOT NULL,
                camera_id TEXT NOT NULL,
                user_id TEXT,
                user_name TEXT,
                status TEXT NOT NULL CHECK (status IN (
                    'KNOWN',
                    'INTRUDER',
                    'UNEXPECTED_ZONE',
                    'EMPTY_WHITELIST',
                    'CAMERA_UNKNOWN',
                    'CAMERA_DISABLED',
                    'DEGRADED'
                )),
                timestamp TEXT NOT NULL,
                snapshot_path TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
            )
            """,
            # DATA migration. Old journal rows only kept `GRANTED`/`DENIED`
            # with no reason, so the exact reason can no longer be recovered.
            # The only information available in the row is used: a denial with
            # a NULL `user_id` was an unidentified person (`INTRUDER`), while a
            # denial with a populated `user_id` was a known person without
            # permission on that camera (`UNEXPECTED_ZONE`). This
            # reconstruction is a documented approximation, not a certainty.
            """
            INSERT INTO logs_v4 (
                id, hub_id, camera_id, user_id, user_name,
                status, timestamp, snapshot_path
            )
            SELECT
                id, hub_id, camera_id, user_id, user_name,
                CASE
                    WHEN status = 'GRANTED' THEN 'KNOWN'
                    WHEN user_id IS NULL THEN 'INTRUDER'
                    ELSE 'UNEXPECTED_ZONE'
                END,
                timestamp, snapshot_path
            FROM logs
            """,
            "DROP TABLE logs",
            "ALTER TABLE logs_v4 RENAME TO logs",
            """
            CREATE INDEX idx_logs_hub_camera_timestamp
                ON logs(hub_id, camera_id, timestamp DESC)
            """,
            "CREATE INDEX idx_logs_user_timestamp ON logs(user_id, timestamp DESC)",
            # All identifiers and display names move to English. Migration 3
            # seeded a Romanian camera id and label; they are renamed here
            # rather than by editing migration 3, which must stay untouched
            # once released. These statements run AFTER both table rebuilds so
            # they operate on the final tables.
            #
            # `allowed_cameras` is stored as a JSON text array, so the id
            # inside it is rewritten textually. The quotes are part of the
            # pattern on purpose: without them a camera called
            # "cam_intrare_spate" would also be partially rewritten.
            """
            UPDATE cameras
               SET camera_id = 'cam_entrance',
                   name = 'Front Entrance'
             WHERE camera_id = 'cam_intrare'
            """,
            "UPDATE logs SET camera_id = 'cam_entrance' WHERE camera_id = 'cam_intrare'",
            """
            UPDATE users
               SET allowed_cameras = REPLACE(
                       allowed_cameras, '"cam_intrare"', '"cam_entrance"'
                   )
             WHERE allowed_cameras LIKE '%"cam_intrare"%'
            """,
            # The placeholder name written for an unidentified person also
            # becomes English, so old and new journal rows read consistently.
            """
            UPDATE logs
               SET user_name = 'Unknown Person'
             WHERE user_name = 'Persoană Necunoscută'
            """,
        ),
    ),
)

# The version the current code expects. Computed automatically from
# MIGRATIONS, so there is no risk of forgetting to update a separate constant.
LATEST_SCHEMA_VERSION = max(version for version, _, _ in MIGRATIONS)


def get_database_path() -> Path:
    """The path of the SQLite file.

    The ACCESS_CONTROL_DB_PATH environment variable takes priority, so the
    tests can run against a temporary database and the database can be moved
    to a persistent location on the Raspberry Pi without code changes.
    """
    configured_path = os.getenv(DATABASE_PATH_ENV)
    if configured_path:
        return Path(configured_path).expanduser().resolve()
    return DEFAULT_DATABASE_PATH


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    """A connection for the application's normal operations (repositories).

    Commits on a normal exit from the block and rolls back when an exception
    occurs, so an operation cannot be left half written.
    """
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


@contextmanager
def _get_migration_connection() -> Iterator[sqlite3.Connection]:
    """A separate connection, used EXCLUSIVELY for migrations.

    The difference from ``get_connection``: ``isolation_level=None`` puts the
    driver into autocommit, so we control transactions with explicit
    BEGIN/COMMIT. That is necessary because:
      - ``PRAGMA journal_mode = WAL`` cannot run inside a transaction;
      - each migration must be atomic: either it applies in full together
        with the version bump, or not at all.
    """
    database_path = get_database_path()
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path, timeout=10, isolation_level=None)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
    finally:
        connection.close()


def get_schema_version(connection: sqlite3.Connection) -> int:
    """The schema version recorded in the database file.

    A brand new database, or one created before migrations were introduced,
    reports 0.
    """
    return int(connection.execute("PRAGMA user_version").fetchone()[0])


def apply_migrations(connection: sqlite3.Connection) -> list[int]:
    """Apply the missing migrations, in ascending order.

    Returns the list of versions actually applied (empty when the database was
    already up to date), so the caller can log or test what happened.

    Raises RuntimeError when the file has a version NEWER than the code: that
    happens when an old build of the application runs against an
    already-migrated database, and carrying on would write data into a schema
    the code does not understand. Stopping immediately is preferable to
    corrupting the data.
    """
    current_version = get_schema_version(connection)

    if current_version > LATEST_SCHEMA_VERSION:
        raise RuntimeError(
            f"The database is at version {current_version}, but this code only "
            f"knows up to {LATEST_SCHEMA_VERSION}. "
            "Update the application, or use a compatible database."
        )

    applied: list[int] = []

    for version, description, statements in MIGRATIONS:
        if version <= current_version:
            continue

        # Explicit transaction: the SQL statements and the version bump must
        # succeed or fail together. Otherwise the database could be left with
        # a half-applied schema while being marked as migrated.
        connection.execute("BEGIN")
        try:
            for statement in statements:
                connection.execute(statement)
            # PRAGMA user_version does not accept bound parameters (?), so the
            # value is interpolated. It comes from the MIGRATIONS constant in
            # this file and is cast to int, so there is no external input.
            connection.execute(f"PRAGMA user_version = {int(version)}")
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise RuntimeError(
                f"Migration {version} ({description}) failed. "
                "The database was rolled back to its previous state."
            ) from None

        applied.append(version)

    return applied


def initialize_database() -> list[int]:
    """Prepare the database when the application starts.

    Called from ``lifespan`` in main.py. It is idempotent: on a second start
    nothing is applied, because the version in the file is already current.
    """
    with _get_migration_connection() as connection:
        # WAL (Write-Ahead Logging) allows concurrent reads alongside one
        # write. Necessary on the Pi: the camera loop writes journal entries
        # while the mobile application reads them. Set outside any
        # transaction.
        connection.execute("PRAGMA journal_mode = WAL")
        return apply_migrations(connection)
