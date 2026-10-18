"""Teste pentru mecanismul de migrare a schemei SQLite.

Rulare (din folderul backend, cu venv activat):
    python -m unittest discover -s tests -v

Fiecare test lucrează pe o bază temporară proprie, deci baza reală din
backend/data nu este atinsă.
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

    def test_empty_database_is_migrated_to_latest_version(self):
        """O bază inexistentă este creată și adusă la versiunea curentă."""
        applied = initialize_database()

        self.assertEqual(applied, [1])
        self.assertEqual(self._user_version(), LATEST_SCHEMA_VERSION)
        self.assertEqual(self._table_names(), ["logs", "users"])

    def test_second_run_applies_nothing(self):
        """Pornirea repetată a aplicației nu reaplică migrările (idempotență)."""
        initialize_database()
        applied_again = initialize_database()

        self.assertEqual(applied_again, [])
        self.assertEqual(self._user_version(), LATEST_SCHEMA_VERSION)

    def test_legacy_database_without_version_is_adopted_without_data_loss(self):
        """Bază creată ÎNAINTE de introducerea migrărilor.

        Tabelele există, dar user_version este 0. Migrarea de bază trebuie să
        marcheze versiunea fără să șteargă datele existente — acesta este
        exact cazul bazei reale din backend/data.
        """
        # Simulăm o bază veche: tabele create manual, fără user_version.
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
            VALUES ('u1', 'HUB_001', 'Utilizator existent', 'ADMIN', 1, '["cam_intrare"]');
            """
        )
        connection.commit()
        connection.close()

        self.assertEqual(self._user_version(), 0)

        applied = initialize_database()

        self.assertEqual(applied, [1])
        self.assertEqual(self._user_version(), LATEST_SCHEMA_VERSION)

        # Datele existente trebuie să fie intacte.
        connection = sqlite3.connect(self.database_path)
        try:
            name = connection.execute(
                "SELECT name FROM users WHERE id = 'u1'"
            ).fetchone()[0]
        finally:
            connection.close()
        self.assertEqual(name, "Utilizator existent")

    def test_database_newer_than_code_is_rejected(self):
        """O bază migrată de o versiune mai nouă a codului oprește pornirea.

        Continuarea ar însemna scrieri într-o schemă necunoscută.
        """
        initialize_database()

        connection = sqlite3.connect(self.database_path, isolation_level=None)
        try:
            connection.execute(f"PRAGMA user_version = {LATEST_SCHEMA_VERSION + 5}")
            with self.assertRaises(RuntimeError) as context:
                apply_migrations(connection)
        finally:
            connection.close()

        # Mesajul trebuie să spună clar ce versiune are baza și ce versiune
        # cunoaște codul, altfel eroarea nu e diagnosticabilă pe Pi.
        message = str(context.exception)
        self.assertIn(str(LATEST_SCHEMA_VERSION + 5), message)
        self.assertIn(str(LATEST_SCHEMA_VERSION), message)


if __name__ == "__main__":
    unittest.main()
