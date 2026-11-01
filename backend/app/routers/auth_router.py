"""Authentication routes."""

from fastapi import APIRouter, Depends, Response, status

from app.config.security import LOGIN_WINDOW_SECONDS
from app.dependencies.auth import get_client_key, get_current_user
from app.schemas.auth_schema import CurrentUser, LoginRequest, TokenResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/api/auth", tags=["Authentication"])
service = AuthService()


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Obtain an access token",
    responses={
        401: {"description": "Invalid credentials, or an account without application access"},
        429: {"description": "Too many authentication attempts"},
    },
)
def login(
    credentials: LoginRequest,
    response: Response,
    client_key: str = Depends(get_client_key),
) -> TokenResponse:
    """Authenticate with email and password.

    ``MONITORED`` persons have no password, so they receive 401: they are
    known to the surveillance system but have no application access, by
    construction.
    """
    token = service.login(credentials, client_key)
    # The response carries a bearer token, so it must never be stored by a
    # browser cache or an intermediate proxy.
    response.headers["Cache-Control"] = "no-store"
    return token


@router.get(
    "/me",
    response_model=CurrentUser,
    summary="Identity of the authenticated account",
)
def read_current_user(current_user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """Used by the application at start-up to learn its role and zones.

    The response contains neither the facial embedding nor the password hash.
    """
    return current_user


@router.get(
    "/policy",
    summary="Public authentication parameters",
    description=(
        "Non-confidential information the login screen needs: the length of "
        "the attempt rate-limiting window."
    ),
)
def read_auth_policy() -> dict[str, int]:
    return {"login_window_seconds": LOGIN_WINDOW_SECONDS}
