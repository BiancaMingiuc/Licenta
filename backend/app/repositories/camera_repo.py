"""Data access for the ``cameras`` entity.

``camera_id`` is the readable identifier ("cam_entrance"), unique within one
hub. The primary key is the composite ``(hub_id, camera_id)``, so every
operation receives both values -- there is no camera without a hub.
"""

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional

from app.config.database import get_connection


class DuplicateCameraError(Exception):
    """``camera_id`` already exists in this hub."""


class CameraRepository:
    COLUMNS = ("hub_id", "camera_id", "name", "kind", "source", "enabled", "created_at")

    @staticmethod
    def _deserialize(row: Any) -> dict[str, Any]:
        camera = dict(row)
        camera["enabled"] = bool(camera["enabled"])
        return camera

    def get_all_by_hub(self, hub_id: str) -> list[dict[str, Any]]:
        with get_connection() as connection:
            rows = connection.execute(
                "SELECT * FROM cameras WHERE hub_id = ? ORDER BY camera_id",
                (hub_id,),
            ).fetchall()
        return [self._deserialize(row) for row in rows]

    def get(self, hub_id: str, camera_id: str) -> Optional[dict[str, Any]]:
        with get_connection() as connection:
            row = connection.execute(
                "SELECT * FROM cameras WHERE hub_id = ? AND camera_id = ?",
                (hub_id, camera_id),
            ).fetchone()
        return self._deserialize(row) if row else None

    def existing_ids(self, hub_id: str) -> set[str]:
        """Every ``camera_id`` in the hub, to validate an ``allowed_cameras`` list.

        One query for the whole list instead of one per camera: validating a
        person with several allowed cameras must not produce N database round
        trips.
        """
        with get_connection() as connection:
            rows = connection.execute(
                "SELECT camera_id FROM cameras WHERE hub_id = ?",
                (hub_id,),
            ).fetchall()
        return {row["camera_id"] for row in rows}

    def create(self, camera_data: dict[str, Any]) -> dict[str, Any]:
        camera = {
            **camera_data,
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        serialized = {**camera, "enabled": int(bool(camera.get("enabled", True)))}
        placeholders = ", ".join(f":{column}" for column in self.COLUMNS)
        try:
            with get_connection() as connection:
                connection.execute(
                    f"INSERT INTO cameras ({', '.join(self.COLUMNS)}) VALUES ({placeholders})",
                    serialized,
                )
        except sqlite3.IntegrityError as error:
            raise DuplicateCameraError(camera["camera_id"]) from error
        camera["enabled"] = bool(camera.get("enabled", True))
        return camera

    def update(
        self, hub_id: str, camera_id: str, update_data: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        existing = self.get(hub_id, camera_id)
        if existing is None:
            return None

        # `camera_id` and `hub_id` are never changed: doing so would silently
        # invalidate every reference in `allowed_cameras` and in journal rows
        # already written.
        updated = {**existing, **update_data, "hub_id": hub_id, "camera_id": camera_id}
        serialized = {**updated, "enabled": int(bool(updated["enabled"]))}
        with get_connection() as connection:
            connection.execute(
                """
                UPDATE cameras
                SET name = :name, kind = :kind, source = :source, enabled = :enabled
                WHERE hub_id = :hub_id AND camera_id = :camera_id
                """,
                serialized,
            )
        return updated

    def delete(self, hub_id: str, camera_id: str) -> bool:
        with get_connection() as connection:
            cursor = connection.execute(
                "DELETE FROM cameras WHERE hub_id = ? AND camera_id = ?",
                (hub_id, camera_id),
            )
        return cursor.rowcount > 0

    def count_users_granting(self, hub_id: str, camera_id: str) -> int:
        """How many people list this camera in ``allowed_cameras``.

        ``allowed_cameras`` is JSON text, so there is no foreign key to
        protect the reference. The counting happens in Python over the hub's
        people: a text match (``LIKE '%cam_entrance%'``) would produce false
        positives for a camera named ``cam_entrance_2``.
        """
        with get_connection() as connection:
            rows = connection.execute(
                "SELECT allowed_cameras FROM users WHERE hub_id = ?",
                (hub_id,),
            ).fetchall()
        return sum(1 for row in rows if camera_id in json.loads(row["allowed_cameras"]))
