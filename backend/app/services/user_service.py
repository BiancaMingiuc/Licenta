"""Business logic for monitored persons (the known-persons list).

This layer is the only one that decides rules. Routers merely translate HTTP;
repositories merely read and write. The rules implemented here:

1. **The role determines application access.** ``has_app_access`` is not
   accepted from the client; it is derived from the role, so there is no
   second source of truth.
2. **A password is required exactly for the roles that can authenticate.**
   ``MONITORED`` never gets a password, so it can never log in by
   construction -- the third RBAC tier follows from the schema rather than
   from special-case checks.
3. **Email is mandatory for roles with login**, because it is the
   authentication identity.
4. **The last ADMIN of a hub cannot be deleted or demoted.** Otherwise the
   system would be left with no administrator and the only recovery path
   would be physical access to the database file.
"""

from typing import Any, Optional

from fastapi import HTTPException

from app.config.security import WeakPasswordError, hash_password
from app.repositories.log_repo import LogRepository
from app.repositories.user_repo import DuplicateEmailError, UserRepository
from app.schemas.user_schema import UserCreate, UserUpdate
from app.services.camera_service import CameraService
from app.services.whitelist_cache import whitelist_cache

ROLES_WITH_LOGIN = ("ADMIN", "APP_USER")


class UserService:
    def __init__(self) -> None:
        self.repo = UserRepository()
        self.log_repo = LogRepository()
        self.cameras = CameraService()

    # -- reads -------------------------------------------------------------
    def get_all_users(self, hub_id: str) -> list[dict[str, Any]]:
        return self.repo.get_all_by_hub(hub_id)

    def get_user(self, doc_id: str, hub_id: Optional[str] = None) -> dict[str, Any]:
        """Return the person together with their surveillance history.

        ``hub_id`` is checked when supplied: an admin of hub A must not be
        able to read a person from hub B just because they know the id.
        Without this check, multi-tenant isolation would only exist in the
        listing queries.
        """
        user = self.repo.get_by_id(doc_id)
        if not user or (hub_id is not None and user["hub_id"] != hub_id):
            # The same 404 in both cases: a distinct 403 would confirm that
            # the id exists in another hub.
            #
            # The message names the expected input because the most common
            # cause is a caller passing a name or an email instead of the id.
            # It reveals nothing: it is identical whether the person exists in
            # another hub or does not exist at all.
            raise HTTPException(
                status_code=404,
                detail=(
                    "Person not found. This endpoint expects the person's id "
                    "(a UUID from GET /api/whitelist/), not their name or email."
                ),
            )

        user["logs"] = self.log_repo.get_by_user_id(doc_id)
        return user

    # -- writes ------------------------------------------------------------
    def create_user(self, user: UserCreate, hub_id: str) -> dict[str, Any]:
        """Enrol a person into the hub of the requesting administrator.

        ``hub_id`` comes from the token, not from the request body.
        """
        user_data = user.model_dump()
        password = user_data.pop("password", None)
        role = user_data["role"]

        user_data["hub_id"] = hub_id
        user_data["has_app_access"] = role in ROLES_WITH_LOGIN
        # Every allowed camera must exist in this hub. Without this check a
        # typo would create a permission that never matches, and the person
        # would keep raising alerts in a zone they were supposed to be
        # expected in, with no error message anywhere.
        user_data["allowed_cameras"] = self.cameras.validate_allowed_cameras(
            hub_id, user_data.get("allowed_cameras") or []
        )

        if role in ROLES_WITH_LOGIN:
            if not user_data.get("email"):
                raise HTTPException(
                    status_code=422,
                    detail=f"Role {role} authenticates by email, so email is required.",
                )
            if not password:
                raise HTTPException(
                    status_code=422,
                    detail=f"Role {role} has application access, so a password is required.",
                )
            user_data["password_hash"] = self._hash(password)
        else:
            if password:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "A MONITORED person has no application access, so they "
                        "cannot have a password. Promote them to APP_USER if login "
                        "is needed."
                    ),
                )
            user_data["password_hash"] = None

        self._ensure_email_available(user_data.get("email"), exclude_id=None)

        try:
            created = self.repo.create(user_data)
        except DuplicateEmailError:
            raise HTTPException(status_code=409, detail="Email is already in use.") from None

        # The whitelist cache must see the newly enrolled face immediately.
        whitelist_cache.invalidate(hub_id)
        return created

    def update_user(self, doc_id: str, user_update: UserUpdate, hub_id: str) -> dict[str, Any]:
        """Partial update, recomputing the consequences of a role change."""
        existing = self.repo.get_by_id(doc_id)
        if not existing or existing["hub_id"] != hub_id:
            raise HTTPException(status_code=404, detail="Person not found.")

        # exclude_unset=True distinguishes "not supplied" from "sent as null",
        # so email can be cleared and the embedding reset deliberately.
        update_data = user_update.model_dump(exclude_unset=True)
        password = update_data.pop("password", None)

        if not update_data and password is None:
            raise HTTPException(status_code=400, detail="No fields supplied for update.")

        resulting_role = update_data.get("role", existing["role"])
        resulting_email = update_data.get("email", existing["email"])

        if "role" in update_data and update_data["role"] != existing["role"]:
            self._guard_last_admin(existing, new_role=update_data["role"])

        update_data["has_app_access"] = resulting_role in ROLES_WITH_LOGIN

        if resulting_role in ROLES_WITH_LOGIN:
            if not resulting_email:
                raise HTTPException(
                    status_code=422,
                    detail=f"Role {resulting_role} requires an email to authenticate.",
                )
            if password is not None:
                update_data["password_hash"] = self._hash(password)
            elif not existing.get("password_hash"):
                # Promotion from MONITORED: there is no password to keep.
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"Promoting to {resulting_role} requires a password, "
                        "because the person had no application access."
                    ),
                )
        else:
            if password is not None:
                raise HTTPException(
                    status_code=422,
                    detail="A MONITORED person cannot have a password.",
                )
            # Demotion invalidates the credentials: otherwise a former
            # APP_USER would keep a valid hash and could be re-promoted
            # without the administrator setting a new password.
            update_data["password_hash"] = None

        if "email" in update_data:
            self._ensure_email_available(update_data["email"], exclude_id=doc_id)

        if "allowed_cameras" in update_data:
            update_data["allowed_cameras"] = self.cameras.validate_allowed_cameras(
                hub_id, update_data["allowed_cameras"] or []
            )

        try:
            updated = self.repo.update(doc_id, update_data)
        except DuplicateEmailError:
            raise HTTPException(status_code=409, detail="Email is already in use.") from None

        if not updated:
            raise HTTPException(status_code=404, detail="Person not found.")

        # Invalidate after ANY change, not just after an embedding change: a
        # change to `allowed_cameras` alters the detection result just as
        # directly as a change of face.
        whitelist_cache.invalidate(hub_id)
        return updated

    def delete_user(self, doc_id: str, hub_id: str) -> dict[str, str]:
        existing = self.repo.get_by_id(doc_id)
        if not existing or existing["hub_id"] != hub_id:
            raise HTTPException(status_code=404, detail="Person not found.")

        self._guard_last_admin(existing, new_role=None)

        if not self.repo.delete(doc_id):
            raise HTTPException(status_code=404, detail="Person not found.")

        # Removal must take effect on the next frame, not when some cache
        # expires: a deleted person stops being recognised immediately.
        whitelist_cache.invalidate(hub_id)
        return {"message": "Person deleted successfully."}

    # -- internal helpers --------------------------------------------------
    @staticmethod
    def _hash(password: str) -> str:
        try:
            return hash_password(password)
        except WeakPasswordError as error:
            raise HTTPException(status_code=422, detail=str(error)) from None

    def _ensure_email_available(self, email: Optional[str], exclude_id: Optional[str]) -> None:
        """Pre-flight check, for a clear conflict message.

        The real uniqueness guarantee is the unique index in the database;
        here we only turn the common case into an explicit 409 instead of an
        integrity error.
        """
        if not email:
            return
        other = self.repo.get_by_email(email)
        if other and other["id"] != exclude_id:
            raise HTTPException(status_code=409, detail="Email is already in use.")

    def _guard_last_admin(self, user: dict[str, Any], new_role: Optional[str]) -> None:
        """Prevent a hub from being left without an administrator.

        ``new_role=None`` means deletion. Recovering a hub with no ADMIN would
        require physical access to the database file and running the bootstrap
        tool, so blocking it here is preferable.
        """
        if user["role"] != "ADMIN" or new_role == "ADMIN":
            return
        if self.repo.count_by_role("ADMIN", user["hub_id"]) <= 1:
            raise HTTPException(
                status_code=409,
                detail=(
                    "This is the only ADMIN of the system. "
                    "Create another administrator first."
                ),
            )
