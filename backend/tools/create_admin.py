"""Create the first administrator directly in the local database.

The problem this solves
-----------------------
Every administration route requires the ADMIN role. But a fresh database has
no ADMIN, so nobody can create one through the API. This is the classic
circular dependency at system start-up (*bootstrap*).

The chosen solution: the first administrator is created by a tool that runs on
the machine itself, not over the network. The root of trust becomes **physical
access to the device**: anyone who can run this script could read and modify
the SQLite file directly anyway.

Rejected alternatives:

- *An HTTP bootstrap route, active until the first ADMIN exists* -- that would
  be a window during which anyone on the network could take over the system.
- *A default administrator password* -- the single most common way IoT devices
  get compromised.

Usage, from the ``backend`` folder:

    python tools\\create_admin.py --name "Bianca" --email bianca@example.com

The password is NOT passed as an argument: it would stay in the shell history.
The script asks for it interactively and does not echo the characters.

For automation and for testing the script there is ``--password-stdin``, which
reads the password from standard input. The reason this option exists:
``getpass`` reads directly from the console on Windows rather than from stdin,
so a non-interactive run would hang forever waiting for a keyboard. Standard
input does not appear in the process list and does not enter the shell
history, so it does not have the problem of a command-line argument.

    "secret" | python tools\\create_admin.py --name "Bianca" ^
        --email bianca@example.com --password-stdin
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

# Allows running as a script from the `backend` folder, without installing the
# project as a package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config.database import get_database_path, initialize_database  # noqa: E402
from app.config.security import WeakPasswordError, hash_password  # noqa: E402
from app.repositories.camera_repo import CameraRepository  # noqa: E402
from app.repositories.user_repo import DuplicateEmailError, UserRepository  # noqa: E402

DEFAULT_CAMERA_ID = "cam_entrance"
DEFAULT_CAMERA_NAME = "Front Entrance"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create an administrator in the local database.",
    )
    parser.add_argument("--name", required=True, help="Display name of the administrator")
    parser.add_argument("--email", required=True, help="Email used to authenticate")
    parser.add_argument(
        "--hub-id", default="HUB_001", help="Hub identifier (default HUB_001)"
    )
    parser.add_argument(
        "--allow-additional",
        action="store_true",
        help="Allow creating an ADMIN even when the hub already has one",
    )
    parser.add_argument(
        "--password-stdin",
        action="store_true",
        help=(
            "Read the password from standard input, without confirmation. "
            "For automation and tests; interactively, use the default mode."
        ),
    )
    arguments = parser.parse_args()

    applied = initialize_database()
    print(f"Database: {get_database_path()}")
    if applied:
        print(f"Migrations applied now: {applied}")

    repository = UserRepository()

    existing_admins = repository.count_by_role("ADMIN", arguments.hub_id)
    if existing_admins and not arguments.allow_additional:
        print(
            f"Hub {arguments.hub_id} already has {existing_admins} administrator(s). "
            "Create new users from the application, or pass --allow-additional.",
            file=sys.stderr,
        )
        return 1

    if repository.get_by_email(arguments.email):
        print(f"Email {arguments.email} is already in use.", file=sys.stderr)
        return 1

    if arguments.password_stdin:
        # No confirmation: a password arriving through a pipe cannot be
        # mistyped twice differently, and a second read would hang the script.
        password = sys.stdin.readline().rstrip("\n").rstrip("\r")
        if not password:
            print("No password received on standard input.", file=sys.stderr)
            return 1
    else:
        password = getpass.getpass("Password (at least 8 characters): ")
        confirmation = getpass.getpass("Confirm password: ")
        if password != confirmation:
            print("Passwords do not match.", file=sys.stderr)
            return 1

    try:
        password_hash = hash_password(password)
    except WeakPasswordError as error:
        print(str(error), file=sys.stderr)
        return 1

    try:
        user = repository.create(
            {
                "hub_id": arguments.hub_id,
                "name": arguments.name,
                "role": "ADMIN",
                "has_app_access": True,
                "email": arguments.email,
                "allowed_cameras": [DEFAULT_CAMERA_ID],
                "embedding": None,
                "password_hash": password_hash,
            }
        )
    except DuplicateEmailError:
        print(f"Email {arguments.email} is already in use.", file=sys.stderr)
        return 1

    # The password hash is never printed.
    print(f"Administrator created: {user['name']} <{user['email']}>, id={user['id']}")

    # A hub with no registered camera is unusable: person permissions are
    # validated against the `cameras` table, so the first enrolment from the
    # app would fail with "cameras not registered". The bootstrap tool must
    # leave a working system behind, not just an account.
    camera_repository = CameraRepository()
    if not camera_repository.get(arguments.hub_id, DEFAULT_CAMERA_ID):
        camera_repository.create(
            {
                "hub_id": arguments.hub_id,
                "camera_id": DEFAULT_CAMERA_ID,
                "name": DEFAULT_CAMERA_NAME,
                "kind": "CSI",
                "source": None,
                "enabled": True,
            }
        )
        print(f"Default camera created: {DEFAULT_CAMERA_ID}")

    print("Log in with: POST /api/auth/login using the email and password above.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
