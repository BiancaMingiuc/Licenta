"""Tests for the SQLite schema migration mechanism.

Run (from the backend folder, with the venv active):
    python -m unittest discover -s tests -v

Every test works on its own temporary database, so the real database under
backend/data is never touched.
"""

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config.database import (
    LATEST_SCHEMA_VERSION,
    apply_migrations,
    get_schema_version,
    initialize_database,
)


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "migrations.sqlite3"
        self.database_override = patch.dict(
            os.environ,
            {"ACCESS_CONTROL_DB_PATH": str(self.database_path)},
        )
        self.database_override.start()

    def tearDown(self):
        self.database_override.stop()
        self.temp_dir.cleanup()

    def _table_names(self) -> list[str]:
        connection = sqlite3.connect(self.database_path)
        try:
            return [
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master "
                    "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
                    "ORDER BY name"
                )
            ]
        finally:
            connection.close()

    def _user_version(self) -> int:
        connection = sqlite3.connect(self.database_path)
        try:
            return get_schema_version(connection)
        finally:
            connection.close()

    def _query_one(self, sql: str, parameters: tuple = ()):
        connection = sqlite3.connect(self.database_path)
        try:
            return connection.execute(sql, parameters).fetchone()
        finally:
            connection.close()

    def _seed_legacy_database(self) -> None:
        """Build a database as it looked BEFORE migrations were introduced.

        The tables exist but user_version is 0, and crucially there are no
        CHECK constraints, so the pre-D3 vocabulary can still be inserted.
        This is what makes it possible to test the data translation performed
        by migration 4 on a database that already holds rows.
        """
        connection = sqlite3.connect(self.database_path)
        connection.executescript(
            """
            CREATE TABLE users (
                id TEXT PRIMARY KEY,
                hub_id TEXT NOT NULL,
                name TEXT NOT NULL,
                role TEXT NOT NULL,
                has_app_access INTEGER NOT NULL DEFAULT 0,
                email TEXT,
                allowed_cameras TEXT NOT NULL,
                embedding TEXT
            );
            CREATE TABLE logs (
                id TEXT PRIMARY KEY,
                hub_id TEXT NOT NULL,
                camera_id TEXT NOT NULL,
                user_id TEXT,
                user_name TEXT,
                status TEXT NOT NULL,
                timestamp TEXT NOT NULL
            );
            INSERT INTO users (id, hub_id, name, role, has_app_access, allowed_cameras)
            VALUES ('u1', 'HUB_001', 'Existing Person', 'ADMIN', 1, '["cam_intrare"]');
            """
        )
        connection.commit()
        connection.close()

    def test_empty_database_is_migrated_to_latest_version(self):
        """A non-existent database is created and brought to the current version."""
        applied = initialize_database()

        # The expected list is derived from MIGRATIONS rather than hard-coded:
        # otherwise every new migration would break this test for no real
        # reason.
        self.assertEqual(applied, list(range(1, LATEST_SCHEMA_VERSION + 1)))
        self.assertEqual(self._user_version(), LATEST_SCHEMA_VERSION)
        self.assertEqual(self._table_names(), ["cameras", "logs", "users"])

    def test_second_run_applies_nothing(self):
        """Starting the application again does not reapply migrations."""
        initialize_database()
        applied_again = initialize_database()

        self.assertEqual(applied_again, [])
        self.assertEqual(self._user_version(), LATEST_SCHEMA_VERSION)

    def test_legacy_database_without_version_is_adopted_without_data_loss(self):
        """A database created BEFORE migrations existed.

        The baseline migration must record the version without deleting
        existing data -- which is exactly the case of the real database under
        backend/data.
        """
        self._seed_legacy_database()
        self.assertEqual(self._user_version(), 0)

        applied = initialize_database()

        self.assertEqual(applied, list(range(1, LATEST_SCHEMA_VERSION + 1)))
        self.assertEqual(self._user_version(), LATEST_SCHEMA_VERSION)

        # Existing data must be intact.
        self.assertEqual(
            self._query_one("SELECT name FROM users WHERE id = 'u1'")[0],
            "Existing Person",
        )

    def test_migration_translates_the_pre_d3_vocabulary(self):
        """Decision D3 renamed the vocabulary; existing rows must follow.

        Without this, an upgraded database would keep rows the current schema
        rejects, and the journal would mix two vocabularies -- which would
        make the counts in the thesis evaluation chapter meaningless.
        """
        self._seed_legacy_database()
        connection = sqlite3.connect(self.database_path)
        # The Romanian literals here are the OLD values, deliberately kept:
        # they are the input of the translation under test, not text to
        # localise. Changing them would make the test pass while proving
        # nothing.
        connection.executescript(
            """
            INSERT INTO users (id, hub_id, name, role, has_app_access, allowed_cameras)
            VALUES ('u2', 'HUB_001', 'Enrolled Person', 'PHYSICAL_ONLY', 0,
                    '["cam_intrare"]');
            INSERT INTO logs (id, hub_id, camera_id, user_id, user_name, status, timestamp)
            VALUES ('l1', 'HUB_001', 'cam_intrare', 'u2', 'Enrolled Person',
                    'GRANTED', '2026-10-01T10:00:00Z');
            INSERT INTO logs (id, hub_id, camera_id, user_id, user_name, status, timestamp)
            VALUES ('l2', 'HUB_001', 'cam_intrare', NULL, 'Persoană Necunoscută',
                    'DENIED', '2026-10-01T11:00:00Z');
            """
        )
        connection.commit()
        connection.close()

        initialize_database()

        # Role renamed.
        self.assertEqual(self._query_one("SELECT role FROM users WHERE id = 'u2'")[0], "MONITORED")
        # Camera id renamed, including inside the JSON permission list.
        self.assertEqual(
            self._query_one("SELECT allowed_cameras FROM users WHERE id = 'u2'")[0],
            '["cam_entrance"]',
        )
        # Journal statuses translated: a granted entry becomes KNOWN, and a
        # denial with no identified person becomes an intruder alert.
        self.assertEqual(self._query_one("SELECT status FROM logs WHERE id = 'l1'")[0], "KNOWN")
        self.assertEqual(self._query_one("SELECT status FROM logs WHERE id = 'l2'")[0], "INTRUDER")
        # Placeholder name translated as well.
        self.assertEqual(
            self._query_one("SELECT user_name FROM logs WHERE id = 'l2'")[0],
            "Unknown Person",
        )
        self.assertEqual(
            self._query_one("SELECT camera_id FROM logs WHERE id = 'l1'")[0],
            "cam_entrance",
        )

    def test_old_vocabulary_is_rejected_by_the_schema(self):
        """The rename is enforced by a constraint, not merely applied once.

        Without the CHECK, any later code path could reintroduce the old
        value and the translation above would be undone silently.
        """
        initialize_database()
        connection = sqlite3.connect(self.database_path)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO users (id, hub_id, name, role, has_app_access,"
                    " allowed_cameras) VALUES (?,?,?,?,?,?)",
                    ("u9", "HUB_001", "Old Role", "PHYSICAL_ONLY", 0, "[]"),
                )
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO logs (id, hub_id, camera_id, status, timestamp)"
                    " VALUES (?,?,?,?,?)",
                    ("l9", "HUB_001", "cam_entrance", "GRANTED", "2026-10-01T10:00:00Z"),
                )
        finally:
            connection.close()

    def test_database_newer_than_code_is_rejected(self):
        """A database migrated by newer code must stop startup.

        Continuing would mean writing into an unknown schema.
        """
        initialize_database()

        connection = sqlite3.connect(self.database_path, isolation_level=None)
        try:
            connection.execute(f"PRAGMA user_version = {LATEST_SCHEMA_VERSION + 5}")
            with self.assertRaises(RuntimeError) as context:
                apply_migrations(connection)
        finally:
            connection.close()

        # The message must state both the database version and the version the
        # code knows about, otherwise the error is not diagnosable on the Pi.
        message = str(context.exception)
        self.assertIn(str(LATEST_SCHEMA_VERSION + 5), message)
        self.assertIn(str(LATEST_SCHEMA_VERSION), message)


if __name__ == "__main__":
    unittest.main()
