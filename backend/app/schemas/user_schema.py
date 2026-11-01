"""Schemas for monitored persons (the known-persons list).

Keeping INPUT models (``UserCreate``, ``UserUpdate``) separate from OUTPUT
models (``UserPublic``, ``UserDetail``) is not redundancy: the output model is
the filter that stops sensitive fields from leaking.

Two fields must never leave the backend:

- ``embedding`` -- the facial biometric vector. It is biometric data (special
  category, GDPR art. 9) and has no place in the response of a listing
  screen. The app needs to know WHETHER a person is enrolled, not what their
  vector is; that is what ``has_embedding`` is for.
- ``password_hash`` -- even as a bcrypt hash, exposing it enables an offline
  password-guessing attack with no rate limiting.

Role vocabulary (decision D3): the third role is ``MONITORED``. It used to be
called ``PHYSICAL_ONLY``, which described a person who could open the door but
not log in. D3 removed the lock, so the name no longer described anything: the
role now means a person who is known to the surveillance system and therefore
does not raise an intruder alert, but who has no application access.
"""

from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator

from app.config.security import MAX_PASSWORD_BYTES, MIN_PASSWORD_LENGTH
from app.schemas.log_schema import LogEntity

UserRole = Literal["ADMIN", "APP_USER", "MONITORED"]

DEFAULT_CAMERA_ID = "cam_entrance"


def _validate_password(value: Optional[str]) -> Optional[str]:
    """Shared validation for the ``password`` field in create/update."""
    if value is None:
        return None
    if len(value) < MIN_PASSWORD_LENGTH:
        raise ValueError(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters long."
        )
    if len(value.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise ValueError(
            f"Password exceeds {MAX_PASSWORD_BYTES} bytes, the bcrypt algorithm limit."
        )
    return value


class UserCreate(BaseModel):
    """Data submitted when enrolling a person.

    ``hub_id`` is NOT accepted from the client: it is taken from the token of
    the administrator making the request, otherwise an admin of one hub could
    create users in someone else's hub and multi-tenant isolation would be
    decorative only.

    ``has_app_access`` is not accepted either: it is derived from the role in
    the service layer, so there is no second source of truth.
    """

    name: str = Field(min_length=1, max_length=120)
    role: UserRole = "MONITORED"
    email: Optional[str] = Field(default=None, max_length=320)
    allowed_cameras: List[str] = Field(default_factory=lambda: [DEFAULT_CAMERA_ID])
    embedding: Optional[List[float]] = None
    # Required for ADMIN/APP_USER, forbidden for MONITORED. The rule lives in
    # `UserService`, not here: it depends on the role, which makes it business
    # logic rather than shape validation.
    password: Optional[str] = None

    _check_password = field_validator("password")(_validate_password)


class UserUpdate(BaseModel):
    """Partial update.

    Used with ``model_dump(exclude_unset=True)`` in the service layer rather
    than filtering on ``is not None``. The difference is significant:
    ``exclude_unset`` distinguishes "the field was not sent" from "the field
    was sent as null", so ``email`` can be cleared deliberately and
    ``embedding`` can be reset. Filtering on ``None`` made both impossible.
    """

    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    role: Optional[UserRole] = None
    email: Optional[str] = Field(default=None, max_length=320)
    allowed_cameras: Optional[List[str]] = None
    embedding: Optional[List[float]] = None
    password: Optional[str] = None

    _check_password = field_validator("password")(_validate_password)


class UserPublic(BaseModel):
    """The safe representation of a person, for API responses."""

    id: str
    hub_id: str
    name: str
    role: UserRole
    has_app_access: bool
    email: Optional[str] = None
    allowed_cameras: List[str] = Field(default_factory=list)
    # Replaces exposing the vector: the UI only needs the "has an enrolled
    # face / does not" state.
    has_embedding: bool = False

    @classmethod
    def from_row(cls, user: dict[str, Any]) -> "UserPublic":
        return cls(
            id=user["id"],
            hub_id=user["hub_id"],
            name=user["name"],
            role=user["role"],
            has_app_access=bool(user["has_app_access"]),
            email=user.get("email"),
            allowed_cameras=user.get("allowed_cameras") or [],
            has_embedding=user.get("embedding") is not None,
        )


class UserDetail(UserPublic):
    """A person together with their surveillance history."""

    logs: List[LogEntity] = Field(default_factory=list)

    @classmethod
    def from_row(cls, user: dict[str, Any]) -> "UserDetail":
        base = UserPublic.from_row(user)
        return cls(
            **base.model_dump(),
            logs=[LogEntity.from_row(row) for row in (user.get("logs") or [])],
        )
