"""Simulation endpoint, for development without a camera and without a model.

WARNING, deliberately kept in the code: this endpoint is **not face
recognition**. It receives ``expected`` as a boolean from the client and
believes it. It checks no ``allowed_cameras`` and compares no embedding.

It remains useful so the frontend can be built and tested before any hardware
exists, but it is restricted to the ADMIN role: on a working system, any
client able to call it could forge the audit journal.

The real detection contract -- ``POST /api/detection/evaluate``, with camera
validation and fail-loud behaviour -- already exists and does NOT have this
shape.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies.auth import require_admin
from app.schemas.auth_schema import CurrentUser
from app.schemas.log_schema import UNKNOWN_PERSON_NAME, LogCreate, SimulatedDetection
from app.services.log_service import LogService
from app.services.user_service import UserService

router = APIRouter(prefix="/api/simulation", tags=["Development Simulation"])
log_service = LogService()
user_service = UserService()


@router.post(
    "/detection",
    status_code=status.HTTP_201_CREATED,
    summary="Generate a simulated event (ADMIN, development only)",
)
def simulate_detection(
    detection: SimulatedDetection,
    current_user: CurrentUser = Depends(require_admin),
):
    if detection.expected:
        if detection.user_id is None:
            raise HTTPException(
                status_code=422,
                detail="user_id is required for a simulated known person.",
            )
        user = user_service.repo.get_by_id(detection.user_id)
        if user is None or user["hub_id"] != current_user.hub_id:
            raise HTTPException(status_code=404, detail="Known user not found.")
        log = LogCreate(
            hub_id=current_user.hub_id,
            camera_id=detection.camera_id,
            user_id=user["id"],
            user_name=user["name"],
            status="KNOWN",
        )
    else:
        log = LogCreate(
            hub_id=current_user.hub_id,
            camera_id=detection.camera_id,
            user_name=UNKNOWN_PERSON_NAME,
            status="INTRUDER",
        )

    event = log_service.create_log(log, hub_id=current_user.hub_id)
    return {"simulated": True, "reason": event["status"], "event": event}
