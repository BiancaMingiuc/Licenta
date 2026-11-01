"""Business logic for cameras.

The central rule: a camera is a real entity, not free text. Previously
``allowed_cameras`` accepted any string the client sent, which made
"multi-camera" a persistence feature rather than an access rule. From here on,
any ``camera_id`` used in a permission or in a detection must exist in this
hub.
"""

from typing import Any

from fastapi import HTTPException

from app.repositories.camera_repo import CameraRepository, DuplicateCameraError
from app.schemas.camera_schema import CameraCreate, CameraUpdate


class CameraService:
    def __init__(self) -> None:
        self.repo = CameraRepository()

    def get_all(self, hub_id: str) -> list[dict[str, Any]]:
        return self.repo.get_all_by_hub(hub_id)

    def get_one(self, hub_id: str, camera_id: str) -> dict[str, Any]:
        camera = self.repo.get(hub_id, camera_id)
        if camera is None:
            raise HTTPException(status_code=404, detail="Camera not found.")
        return camera

    def create(self, camera: CameraCreate, hub_id: str) -> dict[str, Any]:
        try:
            return self.repo.create({**camera.model_dump(), "hub_id": hub_id})
        except DuplicateCameraError:
            raise HTTPException(
                status_code=409,
                detail=f"A camera with id '{camera.camera_id}' already exists in this hub.",
            ) from None

    def update(self, hub_id: str, camera_id: str, camera: CameraUpdate) -> dict[str, Any]:
        update_data = camera.model_dump(exclude_unset=True)
        if not update_data:
            raise HTTPException(status_code=400, detail="No fields supplied for update.")
        updated = self.repo.update(hub_id, camera_id, update_data)
        if updated is None:
            raise HTTPException(status_code=404, detail="Camera not found.")
        return updated

    def delete(self, hub_id: str, camera_id: str) -> dict[str, str]:
        """Deletion is REFUSED while the camera is still granted to someone.

        The alternative -- deleting the camera and silently removing it from
        every ``allowed_cameras`` list -- would change who is expected where
        without the administrator asking for it. In a surveillance system a
        silent change to expectations is worse than a clear error: the
        administrator must see who is affected.
        """
        if self.repo.get(hub_id, camera_id) is None:
            raise HTTPException(status_code=404, detail="Camera not found.")

        granted_to = self.repo.count_users_granting(hub_id, camera_id)
        if granted_to:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"The camera is still listed for {granted_to} person(s). "
                    "Remove it from their permissions before deleting it."
                ),
            )

        self.repo.delete(hub_id, camera_id)
        return {"message": "Camera deleted."}

    # -- used by UserService -----------------------------------------------
    def validate_allowed_cameras(self, hub_id: str, camera_ids: list[str]) -> list[str]:
        """Validate a permission list and return its normalised form.

        Duplicates are removed and the order is stabilised. An unknown
        ``camera_id`` produces a 422 -- otherwise a typo would create a
        permission that never matches, and the person would keep triggering
        alerts with no error message anywhere.
        """
        existing = self.repo.existing_ids(hub_id)
        unknown = sorted(set(camera_ids) - existing)
        if unknown:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Cameras not registered in this hub: "
                    + ", ".join(unknown)
                    + ". Register them first via /api/cameras/."
                ),
            )
        return sorted(set(camera_ids))
