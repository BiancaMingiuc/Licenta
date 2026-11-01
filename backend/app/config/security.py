"""Security primitives: password hashing, JWT tokens, login rate limiting.

This module contains NO business logic. It decides only *how* a cryptographic
operation is performed, not *when* it is allowed -- that is the job of
``app/services/auth_service.py``.

Why it is needed
----------------
Firebase Authentication provided login, tokens and access rules as a service.
After the move to SQLite, the database knows nothing about an authenticated
user, so authentication becomes the application's responsibility.

Technical choices and their reasons
-----------------------------------
- **bcrypt**, not ``hashlib.sha256``. A password is not hashed with a fast
  function: speed is exactly what helps the attacker. bcrypt is deliberately
  slow and includes a unique *salt* per password, so two people with the same
  password get different hashes and a precomputed table does not help.
- **PyJWT**, not ``python-jose``. Fewer dependencies, and it is the reference
  JWT library for Python.
- **HS256** (a symmetric secret), not RS256. The same application both issues
  and verifies the token, so there is no reason for a key pair.
"""

from __future__ import annotations

import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
import jwt

from app.config.database import get_database_path

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
JWT_SECRET_ENV = "ACCESS_CONTROL_JWT_SECRET"
JWT_ALGORITHM = "HS256"

# RFC 7518 section 3.2: for HS256 the HMAC key must be at least as long as the
# hash output -- 32 bytes. A shorter secret reduces the effort needed to forge
# a signature, so accepting one would turn a signed token into a guessable
# token.
MIN_JWT_SECRET_BYTES = 32

# The short lifetime is required by decision D1 (remote access over VPN): if
# the phone is stolen, the window in which the token still works is small.
ACCESS_TOKEN_TTL_MINUTES = 15

# bcrypt refuses passwords longer than 72 BYTES (not characters -- a character
# with a diacritic takes 2). The limit is validated explicitly so the user gets
# a clear 422 rather than an exception from the library.
MAX_PASSWORD_BYTES = 72
MIN_PASSWORD_LENGTH = 8

# Login rate limiting: without it, someone can try passwords indefinitely.
LOGIN_MAX_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 60

# The bcrypt cost: the iteration count is 2**rounds. Higher = slower to crack,
# but also slower on every legitimate login. 12 is the current reference value
# and remains the default.
#
# The environment variable exists for ONE purpose: the automated tests. At 12
# rounds each hash takes nearly half a second, and a suite that creates people
# in every setUp becomes needlessly slow. The tests set it to the minimum;
# production never touches it.
BCRYPT_ROUNDS_ENV = "ACCESS_CONTROL_BCRYPT_ROUNDS"
DEFAULT_BCRYPT_ROUNDS = 12
MIN_BCRYPT_ROUNDS = 4
MAX_BCRYPT_ROUNDS = 16


def get_bcrypt_rounds() -> int:
    """The configured bcrypt cost, clamped to a valid range."""
    configured = os.getenv(BCRYPT_ROUNDS_ENV)
    if not configured:
        return DEFAULT_BCRYPT_ROUNDS
    try:
        rounds = int(configured)
    except ValueError:
        return DEFAULT_BCRYPT_ROUNDS
    return max(MIN_BCRYPT_ROUNDS, min(rounds, MAX_BCRYPT_ROUNDS))


class WeakPasswordError(ValueError):
    """The password does not meet the minimum requirements."""


class InsecureSecretError(RuntimeError):
    """The configured signing secret is too short for HS256."""


# ---------------------------------------------------------------------------
# The signing secret
# ---------------------------------------------------------------------------
def get_jwt_secret() -> str:
    """The secret used to sign tokens.

    Priority: the ACCESS_CONTROL_JWT_SECRET environment variable. On the
    Raspberry Pi this MUST be set -- it is the production configuration.

    For local development, when the variable is absent, a random secret is
    generated once and kept next to the database (a directory excluded from
    Git). The alternative -- a default secret written into the code -- would
    mean anyone who reads the repository can issue valid tokens.

    A configured secret shorter than 32 bytes is REFUSED rather than accepted
    with a warning: a weak password compromises one account, a weak signing
    secret allows issuing tokens for any account, including ADMIN.

    The secret is never returned in responses, logs or error messages.
    """
    configured = os.getenv(JWT_SECRET_ENV)
    if configured:
        if len(configured.encode("utf-8")) < MIN_JWT_SECRET_BYTES:
            raise InsecureSecretError(
                f"{JWT_SECRET_ENV} is shorter than {MIN_JWT_SECRET_BYTES} bytes. "
                'Generate one with: python -c "import secrets; '
                'print(secrets.token_urlsafe(48))"'
            )
        return configured

    secret_file = get_database_path().parent / "jwt_secret.key"
    if secret_file.exists():
        existing = secret_file.read_text(encoding="utf-8").strip()
        if len(existing.encode("utf-8")) >= MIN_JWT_SECRET_BYTES:
            return existing
        # An old or truncated file: regenerate rather than use it weak.

    generated = secrets.token_urlsafe(48)
    secret_file.parent.mkdir(parents=True, exist_ok=True)
    secret_file.write_text(generated, encoding="utf-8")
    return generated


def validate_security_configuration() -> None:
    """Check the security configuration at start-up.

    Called from ``lifespan`` so that a misconfiguration stops the application
    immediately rather than at the first authentication attempt -- on a device
    running 24/7, a late failure would only be discovered when someone needs
    the system to work.
    """
    get_jwt_secret()


# ---------------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------------
def validate_password_strength(plain_password: str) -> None:
    """Raise WeakPasswordError when the password cannot be accepted."""
    if len(plain_password) < MIN_PASSWORD_LENGTH:
        raise WeakPasswordError(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters long."
        )
    if len(plain_password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise WeakPasswordError(
            f"Password exceeds {MAX_PASSWORD_BYTES} bytes, the bcrypt algorithm limit."
        )


def hash_password(plain_password: str) -> str:
    """Turn a password into a bcrypt hash. The result embeds the salt."""
    validate_password_strength(plain_password)
    # gensalt() produces a fresh random salt on every call; it is stored
    # inside the resulting hash, so it does not have to be saved separately.
    salt = bcrypt.gensalt(rounds=get_bcrypt_rounds())
    return bcrypt.hashpw(plain_password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Compare a plaintext password against a stored hash.

    ``checkpw`` extracts the salt from the hash, recomputes and compares in
    constant time, so the password cannot be deduced by timing the call.
    """
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8")[:MAX_PASSWORD_BYTES],
            password_hash.encode("utf-8"),
        )
    except (ValueError, TypeError):
        # A corrupt hash, or one in another format: treated as a failure
        # rather than an exception.
        return False


# A fixed hash, used ONLY to equalise the duration of a failed login.
# Without it a non-existent email would answer instantly while an existing one
# with a wrong password would answer after a bcrypt computation -- and that
# timing difference allows enumerating which accounts exist.
#
# It is built lazily and memoised per round count: it must have exactly the
# configured cost, otherwise the "equaliser" would itself introduce a
# measurable timing difference.
_dummy_hashes: dict[int, bytes] = {}


def _get_dummy_hash() -> bytes:
    rounds = get_bcrypt_rounds()
    if rounds not in _dummy_hashes:
        _dummy_hashes[rounds] = bcrypt.hashpw(
            b"timing-equalizer", bcrypt.gensalt(rounds=rounds)
        )
    return _dummy_hashes[rounds]


def waste_password_verification_time() -> None:
    """Burn roughly the same time as a real password verification."""
    bcrypt.checkpw(b"timing-equalizer", _get_dummy_hash())


# ---------------------------------------------------------------------------
# JWT tokens
# ---------------------------------------------------------------------------
def create_access_token(user_id: str, hub_id: str, role: str) -> tuple[str, int]:
    """Issue an access token.

    Returns ``(token, lifetime_in_seconds)``.

    The payload holds strictly what authorisation needs: the subject (the
    person's id), the hub and the role. Name and email are NOT included -- a
    JWT is only signed, not encrypted, so its contents are readable by anyone
    who intercepts it.
    """
    issued_at = datetime.now(timezone.utc)
    expires_at = issued_at + timedelta(minutes=ACCESS_TOKEN_TTL_MINUTES)
    payload = {
        "sub": user_id,
        "hub_id": hub_id,
        "role": role,
        "iat": issued_at,
        "exp": expires_at,
    }
    token = jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)
    return token, ACCESS_TOKEN_TTL_MINUTES * 60


def decode_access_token(token: str) -> dict[str, Any]:
    """Validate the signature and the expiry, then return the payload.

    Raises ``jwt.PyJWTError`` (including ``ExpiredSignatureError``) when the
    token is invalid. The accepted algorithm is stated explicitly: the
    ``algorithms`` list prevents the attack where an attacker rewrites the
    header to ``alg: none`` and sends an unsigned token.
    """
    return jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])


# ---------------------------------------------------------------------------
# Login rate limiting
# ---------------------------------------------------------------------------
class LoginRateLimiter:
    """A simple sliding window, per key (in practice: per IP address).

    Accepted limitation: the state lives in the process memory, so it is lost
    on restart and is not shared between several worker processes. For a
    single uvicorn process on the Raspberry Pi -- this project's configuration
    -- that is sufficient. A distributed solution would require Redis, i.e.
    one more service on a device with 2 GB of RAM.
    """

    def __init__(
        self,
        max_attempts: int = LOGIN_MAX_ATTEMPTS,
        window_seconds: int = LOGIN_WINDOW_SECONDS,
    ) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._attempts: dict[str, list[float]] = {}

    def check(self, key: str) -> None:
        """Record an attempt. Raises ``PermissionError`` when over the limit."""
        now = time.monotonic()
        window_start = now - self.window_seconds
        recent = [stamp for stamp in self._attempts.get(key, []) if stamp > window_start]

        if len(recent) >= self.max_attempts:
            self._attempts[key] = recent
            raise PermissionError(
                "Too many authentication attempts. Try again in a minute."
            )

        recent.append(now)
        self._attempts[key] = recent

    def reset(self, key: str) -> None:
        """Clear the counter after a successful login."""
        self._attempts.pop(key, None)

    def clear(self) -> None:
        """Wipe the state entirely. Used by the tests so that one run does not
        influence the next -- the state is process-global."""
        self._attempts.clear()


login_rate_limiter = LoginRateLimiter()
