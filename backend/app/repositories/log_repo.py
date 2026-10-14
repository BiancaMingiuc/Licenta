from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from app.config.database import get_connection

class LogRepository:
    def get_all_by_hub(self, hub_id: str, camera_id: Optional[str] = None):
        query = "SELECT * FROM logs WHERE hub_id = ?"
        parameters: list[Any] = [hub_id]
        if camera_id:
            query += " AND camera_id = ?"
            parameters.append(camera_id)
        query += " ORDER BY timestamp DESC"

        with get_connection() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [dict(row) for row in rows]

    def get_by_user_id(self, user_id: str):
        with get_connection() as connection:
            rows = connection.execute(
                "SELECT * FROM logs WHERE user_id = ? ORDER BY timestamp DESC",
                (user_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def create(self, log_data: dict[str, Any]) -> dict[str, Any]:
        log = {
            "id": str(uuid4()),
            **log_data,
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO logs (id, hub_id, camera_id, user_id, user_name, status, timestamp)
                VALUES (:id, :hub_id, :camera_id, :user_id, :user_name, :status, :timestamp)
                """,
                log,
            )
        return log

    def delete(self, doc_id: str):
        with get_connection() as connection:
            cursor = connection.execute("DELETE FROM logs WHERE id = ?", (doc_id,))
        return cursor.rowcount > 0