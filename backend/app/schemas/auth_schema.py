"""Authentication schemas (input/output DTOs)."""

from typing import Literal, Optional

from pydantic import BaseModel, Field

# Imported rather than redeclared. This file used to carry its own copy of the
# role list, which is how the `PHYSICAL_ONLY` -> `MONITORED` rename (decision
# D3) left one definition stale: the role vocabulary now has exactly one
# source of truth.
from app.schemas.user_schema import UserRole


class LoginRequest(BaseModel):
    """Body of the authentication request.

    Email is the login identity; it is unique in the database (migration 2).
    The type is ``str`` rather than ``EmailStr`` so as not to add the
    ``email-validator`` dependency on a resource-constrained device.
    Validating the shape of the address adds no security here -- a
    non-existent address fails to authenticate anyway.
    """

    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=256)


class TokenResponse(BaseModel):
    """Response to a successful authentication.

    ``role`` and ``user_id`` are included so the application can decide which
    screens to show without decoding the token on the client.
    """

    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    user_id: str
    hub_id: str
    role: UserRole


class CurrentUser(BaseModel):
    """The caller's identity, rebuilt from the token AND from the database.

    This is not a response DTO but the principal that routes receive through
    ``Depends``. It holds strictly what authorisation decisions need.

    In practice ``role`` is only ever ``ADMIN`` or ``APP_USER``: a
    ``MONITORED`` person has no password, so they can never reach this point.
    """

    id: str
    hub_id: str
    role: UserRole
    name: str
    email: Optional[str] = None
    allowed_cameras: list[str] = Field(default_factory=list)

    @property
    def is_admin(self) -> bool:
        return self.role == "ADMIN"
