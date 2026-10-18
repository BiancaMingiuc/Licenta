"""Inspectare rapidă a bazei SQLite locale, fără niciun tool extern instalat.

Rulare (din folderul backend):
    py -3.12 tools/inspect_db.py

Scriptul doar CITEȘTE baza. Nu modifică și nu șterge nimic.
Calea bazei poate fi suprascrisă cu variabila ACCESS_CONTROL_DB_PATH,
exact ca în aplicația FastAPI.
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
    print(f"Bază de date: {db_path}")

    if not db_path.exists():
        print("Fișierul nu există încă. Pornește backendul o dată ca să fie creat:")
        print("  py -3.12 -m uvicorn main:app --reload --port 8000")
        return

    print(f"Dimensiune: {db_path.stat().st_size} bytes\n")

    # mode=ro -> deschidere strict read-only, ca să nu putem strica datele din greșeală
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row

    tables = [
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
        )
    ]
    print(f"Tabele: {', '.join(tables) or '(niciuna)'}\n")

    for table in tables:
        count = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        columns = [row["name"] for row in connection.execute(f"PRAGMA table_info({table})")]
        print(f"--- {table}: {count} rânduri ---")
        print(f"Coloane: {', '.join(columns)}")

        for row in connection.execute(f"SELECT * FROM {table} LIMIT 5"):
            print("  ", dict(row))
        if count > 5:
            print(f"   ... și încă {count - 5} rânduri")
        print()

    connection.close()


if __name__ == "__main__":
    main()
