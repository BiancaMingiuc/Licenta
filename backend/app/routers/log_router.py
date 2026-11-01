"""Routes for the surveillance journal.

The RBAC rule enforced here is the one from the project specification:

- **ADMIN** sees every event of their own hub.
- **APP_USER** sees only their own events. The restriction is not optional and
  does not depend on what the client sends: ``restrict_to_user_id`` is imposed
  by the server from the role in the token.
- **MONITORED** never reaches this point, because they cannot authenticate.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query, status

from app.dependencies.auth import require_admin, require_app_access
from app.schemas.auth_schema import CurrentUser
from app.schemas.log_schema import LogCreate, LogEntity, LogPage
from app.services.log_service import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, LogService

router = APIRouter(prefix="/api/logs", tags=["Surveillance Journal"])
service = LogService()


@router.get(
    "/",
    response_model=LogPage,
    summary="List surveillance events (paginated)",
)
def get_logs(
    camera_id: Optional[str] = Query(default=None, description="Filter by a single camera"),
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
    current_user: CurrentUser = Depends(require_app_access),
) -> LogPage:
    page = service.get_logs(
        hub_id=current_user.hub_id,
        camera_id=camera_id,
        restrict_to_user_id=None if current_user.is_admin else current_user.id,
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


@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    summary="Create an event manually (administration/development)",
)
def add_log(log: LogCreate, current_user: CurrentUser = Depends(require_admin)):
    """Writing to the journal by hand is reserved for ADMIN.

    In phase 3 the recognition loop on the Raspberry Pi will write events by
    calling ``LogService`` directly, in-process, not through this HTTP route.
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
        "the file itself is not removed."
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


@router.delete("/{doc_id}", summary="Delete an event")
def delete_log(doc_id: str, current_user: CurrentUser = Depends(require_admin)) -> dict[str, str]:
    return service.delete_log(doc_id, hub_id=current_user.hub_id)
