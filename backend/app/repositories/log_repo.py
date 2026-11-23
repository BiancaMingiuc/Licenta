from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from app.config.database import get_connection


def _build_filters(
    hub_id: str,
    camera_id: Optional[str] = None,
    user_id: Optional[str] = None,
    status: Optional[str] = None,
    since: Optional[str] = None,
    before: Optional[str] = None,
) -> tuple[str, list[Any]]:
    """Assemble the WHERE clause shared by listing, counting and bulk delete.

    Extracted on purpose rather than repeated per method. Listing and counting
    MUST agree on the filters: if they drifted apart, the page would show rows
    the total does not account for, and pagination would report a number of
    pages that does not exist. With five filters, keeping two hand-written
    copies in step is a defect waiting to happen.

    ``hub_id`` is a required positional argument, not an optional filter: a
    journal query without it would cross tenants, and that must not be
    expressible at the data-access layer at all.

    The clause is built from FIXED fragments only; every value is bound as a
    parameter, so this is not string-interpolated SQL.

    Timestamp bounds are compared as strings. That is sound because every
    timestamp is stored in the same zero-padded ISO-8601 UTC format, where
    lexicographic and chronological order coincide. ``since`` is inclusive and
    ``before`` is exclusive, so two adjacent ranges can neither overlap nor
    leave a gap.
    """
    conditions = ["hub_id = ?"]
    parameters: list[Any] = [hub_id]
    if camera_id:
        conditions.append("camera_id = ?")
        parameters.append(camera_id)
    if user_id:
        conditions.append("user_id = ?")
        parameters.append(user_id)
    if status:
        conditions.append("status = ?")
        parameters.append(status)
    if since:
        conditions.append("timestamp >= ?")
        parameters.append(since)
    if before:
        conditions.append("timestamp < ?")
        parameters.append(before)
    return " AND ".join(conditions), parameters


class LogRepository:
    def get_all_by_hub(
        self,
        hub_id: str,
        camera_id: Optional[str] = None,
        user_id: Optional[str] = None,
        status: Optional[str] = None,
        since: Optional[str] = None,
        before: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Journal entries, filtered and PAGINATED.

        Pagination is not a luxury: a camera running 24/7 writes
        continuously, and an unbounded listing would return the whole table on
        every request -- on a device with 2 GB of RAM that becomes a way to
        take the service down.

        The ``user_id`` filter serves role isolation: an APP_USER sees only
        their own events, not the whole hub's.

        ``status``, ``since`` and ``before`` are applied HERE, in SQL, rather
        than by the client over an already-paginated page. Filtering a loaded
        page would describe only those rows while the total still counted the
        rest, so the screen would claim "3 events" out of hundreds.
        """
        where, parameters = _build_filters(
            hub_id=hub_id,
            camera_id=camera_id,
            user_id=user_id,
            status=status,
            since=since,
            before=before,
        )
        # The ordering includes `id` as a second criterion: two events written
        # in the same millisecond would otherwise have an undefined order, and
        # pagination could repeat or skip a row between two pages.
        query = (
            f"SELECT * FROM logs WHERE {where} "
            "ORDER BY timestamp DESC, id DESC LIMIT ? OFFSET ?"
        )
        parameters.extend([limit, offset])

        with get_connection() as connection:
            rows = connection.execute(query, parameters).fetchall()
        return [dict(row) for row in rows]

    def count_by_hub(
        self,
        hub_id: str,
        camera_id: Optional[str] = None,
        user_id: Optional[str] = None,
        status: Optional[str] = None,
        since: Optional[str] = None,
        before: Optional[str] = None,
    ) -> int:
        """Total number of records matching the filters, for pagination."""
        where, parameters = _build_filters(
            hub_id=hub_id,
            camera_id=camera_id,
            user_id=user_id,
            status=status,
            since=since,
            before=before,
        )
        with get_connection() as connection:
            row = connection.execute(
                f"SELECT COUNT(*) AS total FROM logs WHERE {where}",
                parameters,
            ).fetchone()
        return int(row["total"])

    def get_by_user_id(self, user_id: str, limit: int = 100) -> list[dict[str, Any]]:
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT * FROM logs WHERE user_id = ?
                ORDER BY timestamp DESC, id DESC LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_by_id(self, doc_id: str) -> Optional[dict[str, Any]]:
        with get_connection() as connection:
            row = connection.execute(
                "SELECT * FROM logs WHERE id = ?",
                (doc_id,),
            ).fetchone()
        return dict(row) if row else None

    def distinct_cameras(self, hub_id: str) -> list[str]:
        """Camera ids that actually appear in this hub's journal.

        Needed because the camera filter must be able to offer a camera that
        has since been deleted from the registry: its events remain in the
        journal, and a filter that could not reach them would hide evidence
        rather than narrow it.
        """
        with get_connection() as connection:
            rows = connection.execute(
                "SELECT DISTINCT camera_id FROM logs WHERE hub_id = ? ORDER BY camera_id",
                (hub_id,),
            ).fetchall()
        return [str(row["camera_id"]) for row in rows]

    def create(self, log_data: dict[str, Any]) -> dict[str, Any]:
        log = {
            "id": str(uuid4()),
            # The snapshot is optional and, per decision D2, present only for
            # events involving an unidentified person. `setdefault` keeps it
            # absent by default, so callers that know nothing about it
            # (manual creation by an ADMIN) do not have to send it.
            "snapshot_path": None,
            **log_data,
            # Timestamp generated by the server, not the client: a client must
            # not be able to write backdated events into an audit journal.
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO logs (
                    id, hub_id, camera_id, user_id, user_name, status, timestamp, snapshot_path
                ) VALUES (
                    :id, :hub_id, :camera_id, :user_id, :user_name, :status, :timestamp,
                    :snapshot_path
                )
                """,
                log,
            )
        return log

    def delete(self, doc_id: str) -> bool:
        with get_connection() as connection:
            cursor = connection.execute("DELETE FROM logs WHERE id = ?", (doc_id,))
        return cursor.rowcount > 0

    def delete_many_by_hub(
        self,
        hub_id: str,
        camera_id: Optional[str] = None,
        status: Optional[str] = None,
        before: Optional[str] = None,
    ) -> dict[str, int]:
        """Bulk delete, always scoped to one hub.

        Returns the number of rows removed and, separately, how many of them
        referenced a snapshot file. The second figure matters from phase 3
        onwards: deleting the row does not delete the JPEG on disk, so the
        caller needs to know that orphaned files were produced.

        This shares ``_build_filters`` with the listing deliberately: an
        operator previews what a purge would remove by listing it with the
        same filters, so the two must interpret those filters identically.
        """
        where, parameters = _build_filters(
            hub_id=hub_id,
            camera_id=camera_id,
            status=status,
            before=before,
        )

        with get_connection() as connection:
            # Counted before the delete, in the same transaction, so the figure
            # cannot drift from what was actually removed.
            with_snapshot = connection.execute(
                f"SELECT COUNT(*) AS total FROM logs WHERE {where} "
                "AND snapshot_path IS NOT NULL",
                parameters,
            ).fetchone()["total"]
            cursor = connection.execute(f"DELETE FROM logs WHERE {where}", parameters)
            deleted = cursor.rowcount

        return {"deleted": int(deleted), "with_snapshot": int(with_snapshot)}
