"""Configurarea bazei SQLite locale și mecanismul de migrare a schemei.

De ce există migrări
--------------------
Schema bazei este definită în cod, nu într-o consolă web (vezi discuția
Firestore vs SQLite). Asta înseamnă că orice schimbare de schemă trebuie
aplicată de noi, explicit, și pe bazele care EXISTĂ deja.

`CREATE TABLE IF NOT EXISTS` nu este suficient: dacă tabela există deja,
instrucțiunea este ignorată complet, deci o coloană nouă adăugată acolo nu
apare niciodată pe o bază veche. Rezultatul ar fi eroarea `no such column`
în producție, pe Raspberry Pi, după un update aparent inofensiv.

Soluția folosită aici este versionarea schemei prin `PRAGMA user_version`,
un număr întreg stocat în header-ul fișierului SQLite. La pornire comparăm
versiunea din fișier cu versiunea din cod și aplicăm doar pașii lipsă.

Cum adaugi o migrare nouă
-------------------------
1. Adaugi un tuplu nou la finalul `MIGRATIONS`, cu versiunea următoare.
2. Scrii instrucțiunile SQL ca pași mici și idempotenți dacă e posibil.
3. NU modifici niciodată o migrare deja livrată — bazele existente au
   aplicat-o deja și nu o vor mai rula. Orice corecție devine o migrare nouă.

Exemplu, pentru autentificare:

    (
        2,
        "Adaugă password_hash pentru autentificare",
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
# Definiția migrărilor
# ---------------------------------------------------------------------------
# Fiecare intrare: (versiune, descriere, instrucțiuni SQL executate în ordine).
#
# Migrarea 1 este o migrare "de bază" (baseline): folosește IF NOT EXISTS
# pentru că trebuie să funcționeze în DOUĂ situații diferite:
#   - bază nouă, complet goală  -> creează tot
#   - bază existentă creată înainte de introducerea migrărilor (user_version=0,
#     dar tabelele există deja) -> nu strică nimic, doar marchează versiunea 1
MIGRATIONS: tuple[tuple[int, str, tuple[str, ...]], ...] = (
    (
        1,
        "Schema inițială: users, logs și indecșii aferenți",
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
)

# Versiunea pe care o așteaptă codul curent. Calculată automat din MIGRATIONS,
# ca să nu existe riscul de a uita actualizarea unei constante separate.
LATEST_SCHEMA_VERSION = max(version for version, _, _ in MIGRATIONS)


def get_database_path() -> Path:
    """Calea fișierului SQLite.

    Variabila de mediu ACCESS_CONTROL_DB_PATH are prioritate, ca să putem
    rula testele pe o bază temporară și să putem muta baza într-o locație
    persistentă pe Raspberry Pi, fără modificări de cod.
    """
    configured_path = os.getenv(DATABASE_PATH_ENV)
    if configured_path:
        return Path(configured_path).expanduser().resolve()
    return DEFAULT_DATABASE_PATH


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    """Conexiune pentru operațiile normale ale aplicației (repositories).

    Comite la ieșirea normală din bloc și face rollback dacă apare o
    excepție, deci o operație nu poate rămâne scrisă pe jumătate.
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
    """Conexiune separată, folosită EXCLUSIV pentru migrări.

    Diferența față de `get_connection`: `isolation_level=None` pune driverul
    în autocommit, ca să putem controla noi tranzacțiile cu BEGIN/COMMIT
    explicit. Este necesar pentru că:
      - `PRAGMA journal_mode = WAL` nu poate rula în interiorul unei tranzacții;
      - fiecare migrare trebuie să fie atomică: ori se aplică integral
        împreună cu incrementarea versiunii, ori deloc.
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
    """Versiunea schemei înregistrată în fișierul bazei.

    O bază nouă sau una creată înainte de introducerea migrărilor
    raportează 0.
    """
    return int(connection.execute("PRAGMA user_version").fetchone()[0])


def apply_migrations(connection: sqlite3.Connection) -> list[int]:
    """Aplică migrările lipsă, în ordine crescătoare.

    Returnează lista versiunilor aplicate efectiv (goală dacă baza era deja
    la zi), ca apelantul să poată loga sau testa ce s-a întâmplat.

    Ridică RuntimeError dacă fișierul are o versiune mai NOUĂ decât codul:
    situația apare când rulezi o versiune veche a aplicației pe o bază deja
    migrată, iar continuarea ar scrie date într-o schemă pe care codul nu o
    înțelege. Oprirea imediată este preferabilă coruperii datelor.
    """
    current_version = get_schema_version(connection)

    if current_version > LATEST_SCHEMA_VERSION:
        raise RuntimeError(
            f"Baza de date este la versiunea {current_version}, dar codul "
            f"cunoaște doar până la {LATEST_SCHEMA_VERSION}. "
            "Actualizează aplicația sau folosește o bază compatibilă."
        )

    applied: list[int] = []

    for version, description, statements in MIGRATIONS:
        if version <= current_version:
            continue

        # Tranzacție explicită: instrucțiunile SQL și incrementarea versiunii
        # trebuie să reușească sau să eșueze împreună. Altfel baza ar putea
        # rămâne cu o schemă pe jumătate aplicată, dar marcată ca migrată.
        connection.execute("BEGIN")
        try:
            for statement in statements:
                connection.execute(statement)
            # PRAGMA user_version nu acceptă parametri legați (?), deci
            # interpolăm. Valoarea provine din constanta MIGRATIONS din acest
            # fișier și este convertită la int, deci nu există input extern.
            connection.execute(f"PRAGMA user_version = {int(version)}")
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise RuntimeError(
                f"Migrarea {version} ({description}) a eșuat. "
                "Baza a fost readusă la starea anterioară."
            ) from None

        applied.append(version)

    return applied


def initialize_database() -> list[int]:
    """Pregătește baza la pornirea aplicației.

    Apelată din `lifespan` în main.py. Este idempotentă: la a doua pornire nu
    se aplică nimic, pentru că versiunea din fișier este deja la zi.
    """
    with _get_migration_connection() as connection:
        # WAL (Write-Ahead Logging) permite citiri concurente cu o scriere.
        # Necesar pe Pi: bucla camerei scrie loguri în timp ce aplicația
        # mobilă le citește. Se setează în afara oricărei tranzacții.
        connection.execute("PRAGMA journal_mode = WAL")
        return apply_migrations(connection)
