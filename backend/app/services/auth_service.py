"""Authentication logic: credential verification and token issuance.

Kept separate from ``UserService`` because it answers a different question:
``UserService`` administers people, ``AuthService`` establishes who the caller
is.

Security decisions implemented here
-----------------------------------
- **A single failure message.** A non-existent email, a wrong password and an
  account without application access all produce the same 401 with the same
  text. A different message would tell an attacker which addresses exist in
  the system.
- **Equalised timing.** When the email does not exist, the time of a bcrypt
  verification is burned anyway. Without that, the difference between an
  instant response and a computed one would allow account enumeration.
- **Rate limiting before any verification**, so repeated attempts do not burn
  CPU on a device with 2 GB of RAM.
"""

from typing import Any

from fastapi import HTTPException

from app.config.security import (
    create_access_token,
    login_rate_limiter,
    verify_password,
    waste_password_verification_time,
)
from app.repositories.user_repo import UserRepository
from app.schemas.auth_schema import LoginRequest, TokenResponse

GENERIC_LOGIN_ERROR = "Incorrect email or password."


class AuthService:
    def __init__(self) -> None:
        self.repo = UserRepository()

    def login(self, credentials: LoginRequest, client_key: str) -> TokenResponse:
        """Authenticate a user and issue an access token.

        ``client_key`` identifies the source of the request for rate
        limiting; in practice it is the client's IP address.
        """
        try:
            login_rate_limiter.check(client_key)
        except PermissionError as error:
            # 429 Too Many Requests.
            raise HTTPException(status_code=429, detail=str(error)) from None

        user = self.repo.get_by_email(credentials.email)

        if user is None:
            waste_password_verification_time()
            raise HTTPException(status_code=401, detail=GENERIC_LOGIN_ERROR)

        password_hash = user.get("password_hash")
        if not password_hash:
            # The MONITORED case: no hash, so authentication is impossible.
            # This is not a misconfiguration, it is the designed behaviour.
            waste_password_verification_time()
            raise HTTPException(status_code=401, detail=GENERIC_LOGIN_ERROR)

        if not verify_password(credentials.password, password_hash):
            raise HTTPException(status_code=401, detail=GENERIC_LOGIN_ERROR)

        if not user["has_app_access"]:
            raise HTTPException(status_code=401, detail=GENERIC_LOGIN_ERROR)

        login_rate_limiter.reset(client_key)

        token, expires_in = create_access_token(
            user_id=user["id"],
            hub_id=user["hub_id"],
            role=user["role"],
        )
        return TokenResponse(
            access_token=token,
            expires_in=expires_in,
            user_id=user["id"],
            hub_id=user["hub_id"],
            role=user["role"],
        )

    def get_principal(self, user_id: str) -> dict[str, Any] | None:
        """Reload the user from the database on every request.

        This costs one extra SQLite read per request, but it is necessary: a
        token valid for 15 minutes would keep working after the administrator
        deleted the account or withdrew its access. For a system that guards a
        perimeter, revocation must take effect immediately rather than when
        the token expires.
        """
        return self.repo.get_by_id(user_id)
