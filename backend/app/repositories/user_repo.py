import json
import sqlite3
from typing import Any, Optional
from uuid import uuid4

from app.config.database import get_connection


class DuplicateEmailError(Exception):
    """The email is already used by another person.

    Raised by the repository because this is the only layer that sees the
    uniqueness error coming out of SQLite. The service translates it into a
    409 Conflict.
    """


class UserRepository:
    # The columns written and read. Kept in one place so a future migration
    # cannot leave INSERT and UPDATE out of sync.
    COLUMNS = (
        "id",
        "hub_id",
        "name",
        "role",
        "has_app_access",
        "email",
        "allowed_cameras",
        "embedding",
        "password_hash",
    )

    @staticmethod
    def _serialize(user_data: dict[str, Any]) -> dict[str, Any]:
        """Convert Python types into types SQLite accepts.

        SQLite knows neither lists nor booleans: lists become JSON text and a
        boolean becomes 0/1.
        """
        serialized = dict(user_data)
        serialized["allowed_cameras"] = json.dumps(serialized.get("allowed_cameras") or [])
        serialized["embedding"] = (
            json.dumps(serialized["embedding"])
            if serialized.get("embedding") is not None
            else None
        )
        serialized["has_app_access"] = int(bool(serialized.get("has_app_access")))
        serialized["password_hash"] = serialized.get("password_hash")
        serialized["email"] = serialized.get("email")
        return serialized

    @staticmethod
    def _deserialize(row: Any) -> dict[str, Any]:
        """Convert an SQLite row into the dictionary the application uses.

        ``password_hash`` IS kept here, because the authentication service
        needs it. Filtering for API responses happens through ``UserPublic``,
        not by hiding data in the repository: the data-access layer must not
        decide what the client gets to see.
        """
        user = dict(row)
        user["has_app_access"] = bool(user["has_app_access"])
        user["allowed_cameras"] = json.loads(user["allowed_cameras"])
        user["embedding"] = json.loads(user["embedding"]) if user["embedding"] else None
        return user

    def get_all_by_hub(self, hub_id: str) -> list[dict[str, Any]]:
        with get_connection() as connection:
            rows = connection.execute(
                "SELECT * FROM users WHERE hub_id = ? ORDER BY name COLLATE NOCASE",
                (hub_id,),
            ).fetchall()
        return [self._deserialize(row) for row in rows]

    def get_by_id(self, doc_id: str) -> Optional[dict[str, Any]]:
        with get_connection() as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE id = ?",
                (doc_id,),
            ).fetchone()
        return self._deserialize(row) if row else None

    def get_by_email(self, email: str) -> Optional[dict[str, Any]]:
        """Lookup used for authentication.

        The comparison is case-insensitive (``COLLATE NOCASE``) so that
        "Bianca@example.com" and "bianca@example.com" are the same account.
        """
        with get_connection() as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE email = ? COLLATE NOCASE",
                (email,),
            ).fetchone()
        return self._deserialize(row) if row else None

    def count_by_role(self, role: str, hub_id: str) -> int:
        """How many people hold a role, within one hub.

        Scoping to the hub is essential: "the last ADMIN" is a per-hub notion,
        not a global one. Without it, a second hub could leave the first
        without an administrator.
        """
        with get_connection() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS total FROM users WHERE role = ? AND hub_id = ?",
                (role, hub_id),
            ).fetchone()
        return int(row["total"])

    def exists(self, doc_id: str) -> bool:
        with get_connection() as connection:
            row = connection.execute(
                "SELECT 1 FROM users WHERE id = ?",
                (doc_id,),
            ).fetchone()
        return row is not None

    def create(self, user_data: dict[str, Any]) -> dict[str, Any]:
        user = {"id": str(uuid4()), **user_data}
        user.setdefault("password_hash", None)
        serialized = self._serialize(user)
        placeholders = ", ".join(f":{column}" for column in self.COLUMNS)
        try:
            with get_connection() as connection:
                connection.execute(
                    f"INSERT INTO users ({', '.join(self.COLUMNS)}) VALUES ({placeholders})",
                    serialized,
                )
        except sqlite3.IntegrityError as error:
            # The partial unique index on email (migration 2) is the real
            # uniqueness guarantee. The pre-flight check in the service
            # reduces the cases but does not eliminate them: two concurrent
            # requests can both pass the check, and one will fail here.
            if "email" in str(error):
                raise DuplicateEmailError(user.get("email") or "") from error
            raise
        return user

    def update(self, doc_id: str, update_data: dict[str, Any]) -> Optional[dict[str, Any]]:
        existing = self.get_by_id(doc_id)
        if existing is None:
            return None

        updated_user = {**existing, **update_data}
        serialized = self._serialize(updated_user)
        assignments = ", ".join(
            f"{column} = :{column}" for column in self.COLUMNS if column != "id"
        )
        try:
            with get_connection() as connection:
                connection.execute(
                    f"UPDATE users SET {assignments} WHERE id = :id",
                    serialized,
                )
        except sqlite3.IntegrityError as error:
            if "email" in str(error):
                raise DuplicateEmailError(updated_user.get("email") or "") from error
            raise
        return updated_user

    def delete(self, doc_id: str) -> bool:
        with get_connection() as connection:
            cursor = connection.execute("DELETE FROM users WHERE id = ?", (doc_id,))
        return cursor.rowcount > 0
