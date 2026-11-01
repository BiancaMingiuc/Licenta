"""Business logic for the surveillance journal."""

from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException

from app.repositories.log_repo import LogRepository
from app.repositories.user_repo import UserRepository
from app.schemas.detection_schema import (
    REASONS_WITH_UNIDENTIFIED_PERSON,
    DetectionReason,
    describe_identity_conflict,
)
from app.schemas.log_schema import UNKNOWN_PERSON_NAME, LogCreate

MAX_PAGE_SIZE = 500
DEFAULT_PAGE_SIZE = 100


class LogService:
    def __init__(self) -> None:
        self.repo = LogRepository()
        self.user_repo = UserRepository()

    def get_logs(
        self,
        hub_id: str,
        camera_id: Optional[str] = None,
        restrict_to_user_id: Optional[str] = None,
        limit: int = DEFAULT_PAGE_SIZE,
        offset: int = 0,
    ) -> dict[str, Any]:
        """One page of journal entries plus the pagination metadata.

        ``restrict_to_user_id`` is the mechanism by which an APP_USER sees
        only their own events. The parameter is a primitive rather than an
        authentication object, so the service stays callable from the Edge AI
        loop on the Raspberry Pi, which speaks no HTTP and has no session.
        """
        limit = max(1, min(limit, MAX_PAGE_SIZE))
        offset = max(0, offset)

        items = self.repo.get_all_by_hub(
            hub_id=hub_id,
            camera_id=camera_id,
            user_id=restrict_to_user_id,
            limit=limit,
            offset=offset,
        )
        total = self.repo.count_by_hub(
            hub_id=hub_id,
            camera_id=camera_id,
            user_id=restrict_to_user_id,
        )
        return {
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def create_log(self, log: LogCreate, hub_id: Optional[str] = None) -> dict[str, Any]:
        """Write one journal entry, refusing a self-contradictory one.

        The coherence rule is enforced HERE rather than in the router so no
        other caller can bypass it, and it is expressed in
        ``describe_identity_conflict`` rather than inline so the detection
        service and this route cannot drift apart.
        """
        log_data = log.model_dump()
        if hub_id is not None:
            log_data["hub_id"] = hub_id

        if log_data["user_id"] == "UNKNOWN":
            log_data["user_id"] = None

        conflict = describe_identity_conflict(log_data["status"], log_data["user_id"])
        if conflict is not None:
            raise HTTPException(status_code=422, detail=conflict)

        user = None
        if log_data["user_id"]:
            user = self.user_repo.get_by_id(log_data["user_id"])
            if user is None:
                raise HTTPException(
                    status_code=404,
                    detail="The person referenced by this event was not found.",
                )
            if user["hub_id"] != log_data["hub_id"]:
                # Without this check, an event referencing a person from
                # another hub could be written into this hub's journal.
                raise HTTPException(
                    status_code=422,
                    detail="The person does not belong to this event's hub.",
                )

        # The displayed name is DERIVED, never trusted from the client: a row
        # saying "KNOWN" while naming someone other than the referenced person
        # would be worse than a missing row, because it reads as evidence.
        if user is not None:
            log_data["user_name"] = user["name"]
        elif log_data["status"] in REASONS_WITH_UNIDENTIFIED_PERSON:
            log_data["user_name"] = UNKNOWN_PERSON_NAME
        else:
            # A fault involves no person at all, so naming one is misleading.
            log_data["user_name"] = None

        return self.repo.create(log_data)

    def delete_log(self, doc_id: str, hub_id: str) -> dict[str, str]:
        existing = self.repo.get_by_id(doc_id)
        if not existing or existing["hub_id"] != hub_id:
            raise HTTPException(status_code=404, detail="Journal entry not found.")
        if not self.repo.delete(doc_id):
            raise HTTPException(status_code=404, detail="Journal entry not found.")
        return {"message": "Journal entry deleted successfully."}

    def purge_logs(
        self,
        hub_id: str,
        confirm: bool,
        camera_id: Optional[str] = None,
        status: Optional[str] = None,
        before: Optional[str] = None,
    ) -> dict[str, Any]:
        """Delete many journal entries at once, within one hub.

        ``confirm`` must be explicitly true. The guard lives here rather than
        in the router so it cannot be bypassed by another caller: this is the
        only operation in the system that destroys evidence in bulk, and a
        mistyped URL must not be enough to trigger it.

        Passing no filter deletes the hub's entire journal. That is allowed
        because it is what an operator sometimes needs after a test run, but
        it is never the default: without ``confirm`` the request is refused.

        With ``before``, this is also the mechanism behind the retention
        policy required by decision D2 (automatic removal after 7-30 days). A
        scheduled job on the Pi calls exactly this method.
        """
        if not confirm:
            raise HTTPException(
                status_code=400,
                detail=(
                    "This deletes journal entries in bulk and cannot be undone. "
                    "Repeat the request with confirm=true."
                ),
            )

        if status is not None and status not in DetectionReason.__args__:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Unknown status filter. Allowed values: "
                    + ", ".join(DetectionReason.__args__)
                ),
            )

        normalised_before = self._normalise_before(before)

        result = self.repo.delete_many_by_hub(
            hub_id=hub_id,
            camera_id=camera_id,
            status=status,
            before=normalised_before,
        )
        return {
            "deleted": result["deleted"],
            "with_snapshot": result["with_snapshot"],
            "filters": {
                "camera_id": camera_id,
                "status": status,
                "before": normalised_before,
            },
        }

    @staticmethod
    def _normalise_before(before: Optional[str]) -> Optional[str]:
        """Validate the ``before`` bound and return it in the stored format.

        Accepts a plain date ("2026-10-20") or a full ISO-8601 timestamp. A
        plain date is treated as midnight UTC, so "before 2026-10-20" excludes
        that whole day rather than part of it.

        Validating here matters: an unparseable value compared as a string
        would silently match nothing, or everything, and the operator would
        believe the purge had run correctly.
        """
        if not before:
            return None
        try:
            parsed = datetime.fromisoformat(before.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Invalid 'before' value. Use a date (2026-10-20) or an "
                    "ISO-8601 timestamp (2026-10-20T14:30:00Z)."
                ),
            ) from None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
