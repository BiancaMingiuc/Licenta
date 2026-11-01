"""HTTP route for the detection contract.

This route is NOT the main operating path. The recognition loop on the
Raspberry Pi will call ``DetectionService.evaluate()`` directly, in-process,
with no HTTP involved -- there is no request, response or status code there.

The route exists for three reasons: automated testing of the classification
through the same contract production code will use, demonstrating the system
without a live camera, and preparing for a separate camera node (a second
device that asks the hub).

KNOWN LIMITATION, to be resolved before a real camera node uses this: the
route requires the ADMIN role, i.e. a HUMAN identity. A device has no email
and no password. A separate camera node needs machine authentication -- a
device token, issued per camera and revocable independently of user accounts.
It was not invented now, to avoid a second authentication mechanism that is
unused and untested.
"""

from fastapi import APIRouter, Depends

from app.dependencies.auth import require_admin
from app.schemas.auth_schema import CurrentUser
from app.schemas.detection_schema import DetectionRequest, DetectionResult
from app.services.detection_service import DetectionService

router = APIRouter(prefix="/api/detection", tags=["Detection"])
service = DetectionService()


@router.post(
    "/evaluate",
    response_model=DetectionResult,
    summary="Classify one detected face (fail-loud)",
    description=(
        "Compares the supplied embedding against the hub whitelist, checks "
        "whether the person is expected on the given camera, records the event "
        "and returns the classification. Never raises: any unforeseen situation "
        "produces a FAULT outcome rather than silence."
    ),
)
def evaluate_detection(
    request: DetectionRequest,
    current_user: CurrentUser = Depends(require_admin),
) -> DetectionResult:
    # The response is always 200, including for alerts: an alert is a valid
    # result of the operation, not a failure of the request. A 403 would
    # conflate "you, the caller, are not allowed" with "the person in front of
    # the camera is not expected here".
    return service.evaluate(request, hub_id=current_user.hub_id)
