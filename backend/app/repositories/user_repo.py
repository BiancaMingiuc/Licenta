import json
from typing import Any, Optional
from uuid import uuid4

from app.config.database import get_connection

class UserRepository:
    @staticmethod
    def _serialize(user_data: dict[str, Any]) -> dict[str, Any]:
        serialized = dict(user_data)
        serialized["allowed_cameras"] = json.dumps(serialized["allowed_cameras"])
        serialized["embedding"] = (
            json.dumps(serialized["embedding"])
            if serialized.get("embedding") is not None
            else None
        )
        serialized["has_app_access"] = int(serialized["has_app_access"])
        return serialized

    @staticmethod
    def _deserialize(row: Any) -> dict[str, Any]:
        user = dict(row)
        user["has_app_access"] = bool(user["has_app_access"])
        user["allowed_cameras"] = json.loads(user["allowed_cameras"])
        user["embedding"] = json.loads(user["embedding"]) if user["embedding"] else None
        return user

    def get_all_by_hub(self, hub_id: str):
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

    def exists(self, doc_id: str) -> bool:
        with get_connection() as connection:
            row = connection.execute(
                "SELECT 1 FROM users WHERE id = ?",
                (doc_id,),
            ).fetchone()
        return row is not None

    def create(self, user_data: dict[str, Any]) -> dict[str, Any]:
        user = {"id": str(uuid4()), **user_data}
        serialized = self._serialize(user)
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO users (
                    id, hub_id, name, role, has_app_access, email, allowed_cameras, embedding
                ) VALUES (
                    :id, :hub_id, :name, :role, :has_app_access, :email, :allowed_cameras, :embedding
                )
                """,
                serialized,
            )
        return user

    def update(self, doc_id: str, update_data: dict[str, Any]) -> Optional[dict[str, Any]]:
        existing = self.get_by_id(doc_id)
        if existing is None:
            return None

        updated_user = {**existing, **update_data}
        serialized = self._serialize(updated_user)
        with get_connection() as connection:
            connection.execute(
                """
                UPDATE users
                SET hub_id = :hub_id,
                    name = :name,
                    role = :role,
                    has_app_access = :has_app_access,
                    email = :email,
                    allowed_cameras = :allowed_cameras,
                    embedding = :embedding
                WHERE id = :id
                """,
                serialized,
            )
        return updated_user

    def delete(self, doc_id: str):
        with get_connection() as connection:
            cursor = connection.execute("DELETE FROM users WHERE id = ?", (doc_id,))
        return cursor.rowcount > 0