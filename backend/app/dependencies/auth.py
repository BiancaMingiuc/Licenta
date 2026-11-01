"""FastAPI dependencies that enforce authentication and RBAC.

Why here and not in every route
-------------------------------
A check written by hand inside every route function gets forgotten by the
twentieth route. A dependency declared in the decorator cannot be forgotten:
the route does not even execute if the dependency raises.

``require_roles`` is a dependency *factory*: you call it with the allowed
roles and get a ready-to-use dependency. That way the authorisation rule is
declared next to the route but implemented in a single place.
"""

from typing import Callable

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config.security import decode_access_token
from app.schemas.auth_schema import CurrentUser, UserRole
from app.services.auth_service import AuthService

# auto_error=False: we handle the missing header ourselves, so we can return a
# consistent message and the correct WWW-Authenticate header.
bearer_scheme = HTTPBearer(
    auto_error=False, description="JWT token obtained from /api/auth/login"
)

auth_service = AuthService()

_UNAUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Authentication required.",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> CurrentUser:
    """The caller's identity, validated from the token AND from the database."""
    if credentials is None or not credentials.credentials:
        raise _UNAUTHENTICATED

    try:
        payload = decode_access_token(credentials.credentials)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired. Please sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None
    except jwt.PyJWTError:
        # Invalid signature, malformed token, unsupported algorithm.
        raise _UNAUTHENTICATED from None

    user_id = payload.get("sub")
    if not user_id:
        raise _UNAUTHENTICATED

    user = auth_service.get_principal(user_id)
    if user is None or not user["has_app_access"]:
        # The account was deleted, or its access was withdrawn after the token
        # was issued. Revocation takes effect immediately.
        raise _UNAUTHENTICATED

    if user["role"] != payload.get("role"):
        # The role changed in the meantime. We neither silently escalate
        # privileges nor keep the old ones: a re-authentication is required so
        # the token reflects the real role.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account role changed. Please sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return CurrentUser(
        id=user["id"],
        hub_id=user["hub_id"],
        role=user["role"],
        name=user["name"],
        email=user.get("email"),
        allowed_cameras=user.get("allowed_cameras") or [],
    )


def require_roles(*allowed_roles: UserRole) -> Callable[[CurrentUser], CurrentUser]:
    """Build a dependency that requires one of the given roles."""

    def dependency(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This operation requires one of the roles: "
                + ", ".join(allowed_roles),
            )
        return current_user

    return dependency


# The dependencies used by the routers. ADMIN is listed explicitly for read
# access as well: an administrator can do everything an APP_USER can, but the
# hierarchy is declared rather than assumed.
require_admin = require_roles("ADMIN")
require_app_access = require_roles("ADMIN", "APP_USER")


def get_client_key(request: Request) -> str:
    """The key used for rate-limiting authentication attempts.

    Known limitation: behind a reverse proxy, ``request.client.host`` is the
    proxy's address rather than the real client's, and every client would
    share one quota. In this project's architecture (VPN access straight to
    the Raspberry Pi, no proxy) the address is the real one. If a proxy is
    ever added, the ``X-Forwarded-For`` header must be read -- but ONLY if the
    proxy is trusted, otherwise a client can forge its own identity.
    """
    if request.client is None:
        return "unknown"
    return request.client.host
