"""Routes for cameras.

Reading is allowed to anyone who can authenticate: the application needs
camera names in order to render the journal in readable form ("Front
Entrance" instead of "cam_entrance"). Writing requires ADMIN -- a new camera
extends the monitored perimeter.
"""

from typing import List

from fastapi import APIRouter, Depends, status

from app.dependencies.auth import require_admin, require_app_access
from app.schemas.auth_schema import CurrentUser
from app.schemas.camera_schema import CameraCreate, CameraPublic, CameraUpdate
from app.services.camera_service import CameraService

router = APIRouter(prefix="/api/cameras", tags=["Cameras"])
service = CameraService()


@router.get("/", response_model=List[CameraPublic], summary="List the hub's cameras")
def list_cameras(current_user: CurrentUser = Depends(require_app_access)):
    return service.get_all(current_user.hub_id)


@router.get("/{camera_id}", response_model=CameraPublic, summary="One camera")
def get_camera(camera_id: str, current_user: CurrentUser = Depends(require_app_access)):
    return service.get_one(current_user.hub_id, camera_id)


@router.post(
    "/",
    response_model=CameraPublic,
    status_code=status.HTTP_201_CREATED,
    summary="Register a camera",
    responses={409: {"description": "camera_id already exists in this hub"}},
)
def create_camera(camera: CameraCreate, current_user: CurrentUser = Depends(require_admin)):
    return service.create(camera, hub_id=current_user.hub_id)


@router.put("/{camera_id}", response_model=CameraPublic, summary="Update a camera")
def update_camera(
    camera_id: str,
    camera: CameraUpdate,
    current_user: CurrentUser = Depends(require_admin),
):
    return service.update(current_user.hub_id, camera_id, camera)


@router.delete(
    "/{camera_id}",
    summary="Delete a camera",
    responses={409: {"description": "The camera is still listed for some people"}},
)
def delete_camera(camera_id: str, current_user: CurrentUser = Depends(require_admin)):
    return service.delete(current_user.hub_id, camera_id)
