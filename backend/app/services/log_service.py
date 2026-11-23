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


def validate_status_filter(status: Optional[str]) -> Optional[str]:
    """Reject a status that is not part of the detection vocabulary.

    Shared by listing and purging rather than written twice. A value this
    layer does not recognise is refused instead of being passed to SQL, where
    it would match nothing: a filter that silently returns an empty page is
    indistinguishable from a quiet period, and on an audit journal that is the
    difference between "no intruders" and "your filter was misspelled".
    """
    if status is None:
        return None
    if status not in DetectionReason.__args__:
        raise HTTPException(
            status_code=422,
            detail=(
                "Unknown status filter. Allowed values: "
                + ", ".join(DetectionReason.__args__)
            ),
        )
    return status


def normalise_timestamp_bound(value: Optional[str], field: str) -> Optional[str]:
    """Validate a date bound and return it in the stored format.

    Accepts a plain date ("2026-10-20") or a full ISO-8601 timestamp. A plain
    date is treated as midnight UTC, so a bound expressed as a date always
    falls on a day boundary rather than part-way through a day.

    Validating here matters: an unparseable value compared as a string would
    silently match nothing, or everything, and the operator would believe the
    filter had been applied.
    """
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Invalid '{field}' value. Use a date (2026-10-20) or an "
                "ISO-8601 timestamp (2026-10-20T14:30:00Z)."
            ),
        ) from None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class LogService:
    def __init__(self) -> None:
        self.repo = LogRepository()
        self.user_repo = UserRepository()

    def get_logs(
        self,
        hub_id: str,
        camera_id: Optional[str] = None,
        restrict_to_user_id: Optional[str] = None,
        status: Optional[str] = None,
        since: Optional[str] = None,
        before: Optional[str] = None,
        limit: int = DEFAULT_PAGE_SIZE,
        offset: int = 0,
    ) -> dict[str, Any]:
        """One page of journal entries plus the pagination metadata.

        ``restrict_to_user_id`` is the mechanism by which an APP_USER sees
        only their own events. The parameter is a primitive rather than an
        authentication object, so the service stays callable from the Edge AI
        loop on the Raspberry Pi, which speaks no HTTP and has no session.

        The filters are validated and then applied in SQL. ``total`` therefore
        counts the FILTERED set, not the whole journal -- without that the UI
        would page through a total it is not showing.
        """
        limit = max(1, min(limit, MAX_PAGE_SIZE))
        offset = max(0, offset)

        status = validate_status_filter(status)
        normalised_since = normalise_timestamp_bound(since, "since")
        normalised_before = normalise_timestamp_bound(before, "before")

        if (
            normalised_since is not None
            and normalised_before is not None
            and normalised_since >= normalised_before
        ):
            # An inverted range always returns nothing. Refusing it names the
            # mistake instead of showing an empty journal, which the operator
            # would read as "no events in this period".
            raise HTTPException(
                status_code=422,
                detail="'since' must be earlier than 'before'; this range is empty.",
            )

        filters = {
            "hub_id": hub_id,
            "camera_id": camera_id,
            "user_id": restrict_to_user_id,
            "status": status,
            "since": normalised_since,
            "before": normalised_before,
        }

        items = self.repo.get_all_by_hub(**filters, limit=limit, offset=offset)
        total = self.repo.count_by_hub(**filters)
        return {
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def get_log(
        self,
        doc_id: str,
        hub_id: str,
        restrict_to_user_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """One journal entry, for the event detail screen.

        Needed so a detail view can load from its own URL. Without it the
        screen would only work when reached from the list, and reloading the
        page -- or opening a shared link -- would show nothing.

        An entry outside the caller's hub, or belonging to another person when
        the caller is an APP_USER, answers 404 rather than 403. A 403 would
        confirm that the id exists, which is itself information: an APP_USER
        could enumerate ids and learn how many events the hub recorded.
        """
        entry = self.repo.get_by_id(doc_id)
        if not entry or entry["hub_id"] != hub_id:
            raise HTTPException(status_code=404, detail="Journal entry not found.")
        if restrict_to_user_id is not None and entry.get("user_id") != restrict_to_user_id:
            raise HTTPException(status_code=404, detail="Journal entry not found.")
        return entry

    def get_journal_cameras(self, hub_id: str) -> list[str]:
        """Camera ids present in this hub's journal, for the filter control.

        Taken from the journal rather than from the camera registry because a
        deleted camera keeps its recorded events: offering only registered
        cameras would make those events unreachable by filter.
        """
        return self.repo.distinct_cameras(hub_id)

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

        The filters are validated by the SAME functions the listing uses, so
        an operator who previews a purge by listing it with those filters sees
        exactly the set that will be removed.
        """
        if not confirm:
            raise HTTPException(
                status_code=400,
                detail=(
                    "This deletes journal entries in bulk and cannot be undone. "
                    "Repeat the request with confirm=true."
                ),
            )

        status = validate_status_filter(status)
        normalised_before = normalise_timestamp_bound(before, "before")

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
