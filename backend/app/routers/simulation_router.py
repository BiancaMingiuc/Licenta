from fastapi import APIRouter, HTTPException

from app.schemas.log_schema import LogCreate, SimulatedDetection
from app.services.log_service import LogService
from app.services.user_service import UserService

router = APIRouter(prefix="/api/simulation", tags=["Development Simulation"])
log_service = LogService()
user_service = UserService()


@router.post("/detection")
def simulate_detection(detection: SimulatedDetection):
    if detection.authorized:
        if detection.user_id is None:
            raise HTTPException(status_code=422, detail="Pentru o detecție autorizată este necesar user_id.")
        user = user_service.repo.get_by_id(detection.user_id)
        if user is None:
            raise HTTPException(status_code=404, detail="Utilizatorul autorizat nu a fost găsit.")
        log = LogCreate(
            hub_id=detection.hub_id,
            camera_id=detection.camera_id,
            user_id=user["id"],
            user_name=user["name"],
            status="GRANTED",
        )
    else:
        log = LogCreate(
            hub_id=detection.hub_id,
            camera_id=detection.camera_id,
            user_name="Persoană Necunoscută",
            status="DENIED",
        )

    event = log_service.create_log(log)
    return {"simulated": True, "decision": event["status"], "event": event}
