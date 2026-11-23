"""Routes for the surveillance journal.

The RBAC rule enforced here is the one from the project specification:

- **ADMIN** sees every event of their own hub.
- **APP_USER** sees only their own events. The restriction is not optional and
  does not depend on what the client sends: ``restrict_to_user_id`` is imposed
  by the server from the role in the token.
- **MONITORED** never reaches this point, because they cannot authenticate.

Route order note: ``/filter-options`` is declared BEFORE ``/{doc_id}``. FastAPI
matches in declaration order, so the reverse order would make the literal path
be read as an entry id.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query, status

from app.dependencies.auth import require_admin, require_app_access
from app.schemas.auth_schema import CurrentUser
from app.schemas.detection_schema import DetectionReason
from app.schemas.log_schema import JournalFilterOptions, LogCreate, LogEntity, LogPage
from app.services.log_service import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, LogService

router = APIRouter(prefix="/api/logs", tags=["Surveillance Journal"])
service = LogService()


@router.get(
    "/",
    response_model=LogPage,
    summary="List surveillance events (paginated, filterable)",
    responses={
        422: {"description": "Unknown status, unparseable date, or an inverted range"},
    },
    description=(
        "Returns one page of this hub's journal, newest first. All filters are "
        "applied in the database, so `total` counts the FILTERED set and the "
        "client can page through exactly what it is showing. `since` is "
        "inclusive, `before` is exclusive, so two adjacent ranges neither "
        "overlap nor leave a gap."
    ),
)
def get_logs(
    camera_id: Optional[str] = Query(default=None, description="Filter by a single camera"),
    status_filter: Optional[DetectionReason] = Query(
        default=None,
        alias="status",
        description="Filter by one detection reason, e.g. INTRUDER",
    ),
    since: Optional[str] = Query(
        default=None,
        description="Only entries at or after this date / ISO-8601 timestamp (inclusive)",
    ),
    before: Optional[str] = Query(
        default=None,
        description="Only entries strictly before this date / ISO-8601 timestamp",
    ),
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
    current_user: CurrentUser = Depends(require_app_access),
) -> LogPage:
    page = service.get_logs(
        hub_id=current_user.hub_id,
        camera_id=camera_id,
        restrict_to_user_id=None if current_user.is_admin else current_user.id,
        status=status_filter,
        since=since,
        before=before,
        limit=limit,
        offset=offset,
    )
    # The explicit conversion through `from_row` is required: `has_snapshot` is
    # derived from `snapshot_path`, which is NOT exposed to the client.
    return LogPage(
        items=[LogEntity.from_row(row) for row in page["items"]],
        total=page["total"],
        limit=page["limit"],
        offset=page["offset"],
    )


@router.get(
    "/filter-options",
    response_model=JournalFilterOptions,
    summary="Values worth offering in the journal filter",
    description=(
        "The camera ids that actually occur in this hub's journal. Taken from "
        "the journal rather than the camera registry, because a camera that "
        "was deleted keeps its recorded events: offering only registered "
        "cameras would leave those events unreachable by filter."
    ),
)
def get_filter_options(
    current_user: CurrentUser = Depends(require_app_access),
) -> JournalFilterOptions:
    return JournalFilterOptions(
        cameras=service.get_journal_cameras(current_user.hub_id),
        statuses=list(DetectionReason.__args__),
    )


@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    summary="Create an event manually (administration/development)",
    responses={
        422: {
            "description": (
                "The status and the identity contradict each other: KNOWN and "
                "UNEXPECTED_ZONE require a user_id, every other status "
                "requires none."
            )
        },
    },
)
def add_log(log: LogCreate, current_user: CurrentUser = Depends(require_admin)):
    """Writing to the journal by hand is reserved for ADMIN.

    In phase 3 the recognition loop on the Raspberry Pi will write events by
    calling ``LogService`` directly, in-process, not through this HTTP route.

    ``user_name`` sent by the client is ignored: it is derived from the
    referenced person, so the journal cannot name someone other than the
    person it points at.
    """
    return service.create_log(log, hub_id=current_user.hub_id)


@router.delete(
    "/",
    summary="Delete many events at once (ADMIN, irreversible)",
    responses={
        400: {"description": "Missing explicit confirmation"},
        422: {"description": "Invalid status or 'before' filter"},
    },
    description=(
        "Deletes journal entries belonging to the caller's hub. With no "
        "filter it deletes the hub's entire journal, so `confirm=true` is "
        "mandatory. Use `before` to apply a retention policy, `camera_id` to "
        "clear one camera, and `status` to drop a single category (for "
        "example DEGRADED entries produced while debugging). The response "
        "reports how many deleted entries referenced a snapshot file, because "
        "the file itself is not removed.\n\n"
        "The filters are interpreted by the same code the listing uses, so "
        "listing with these filters previews exactly what will be deleted."
    ),
)
def purge_logs(
    confirm: bool = Query(
        description="Must be true. Without it the request is refused.",
    ),
    camera_id: Optional[str] = Query(default=None, description="Only this camera"),
    status_filter: Optional[str] = Query(
        default=None,
        alias="status",
        description="Only this detection reason, e.g. DEGRADED",
    ),
    before: Optional[str] = Query(
        default=None,
        description="Only entries older than this date or ISO-8601 timestamp",
    ),
    current_user: CurrentUser = Depends(require_admin),
) -> dict:
    return service.purge_logs(
        hub_id=current_user.hub_id,
        confirm=confirm,
        camera_id=camera_id,
        status=status_filter,
        before=before,
    )


@router.get(
    "/{doc_id}",
    response_model=LogEntity,
    summary="One surveillance event",
    responses={404: {"description": "Not found, another hub's, or another person's"}},
    description=(
        "Lets an event detail view load from its own address, so reloading "
        "the page or opening a shared link still works. An APP_USER reading "
        "someone else's event receives 404 rather than 403: a 403 would "
        "confirm that the id exists, which is itself information."
    ),
)
def get_log(doc_id: str, current_user: CurrentUser = Depends(require_app_access)) -> LogEntity:
    entry = service.get_log(
        doc_id,
        hub_id=current_user.hub_id,
        restrict_to_user_id=None if current_user.is_admin else current_user.id,
    )
    return LogEntity.from_row(entry)


@router.delete("/{doc_id}", summary="Delete an event")
def delete_log(doc_id: str, current_user: CurrentUser = Depends(require_admin)) -> dict[str, str]:
    return service.delete_log(doc_id, hub_id=current_user.hub_id)
