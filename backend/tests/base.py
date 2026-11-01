"""Shared test infrastructure: a temporary database and authenticated clients.

Every test runs against its own SQLite file, created in a temporary directory
and removed afterwards. The real database under `backend/data` is never
touched.

The initial administrator is created through the repository rather than the
API, which is exactly the *bootstrap* problem `tools/create_admin.py` solves:
there is no ADMIN available to create the first ADMIN through the protected
routes.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from httpx import ASGITransport, AsyncClient

from app.config.database import initialize_database
from app.config.security import hash_password, login_rate_limiter
from app.repositories.camera_repo import CameraRepository
from app.repositories.user_repo import UserRepository
from app.services.whitelist_cache import whitelist_cache
from main import app

ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "admin-password-123"
HUB_ID = "HUB_001"
DEFAULT_CAMERA_ID = "cam_entrance"


class AuthenticatedApiTestCase(unittest.IsolatedAsyncioTestCase):
    """Test base with an existing ADMIN and an already authenticated client."""

    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "test.sqlite3"
        self.environment = patch.dict(
            os.environ,
            {
                "ACCESS_CONTROL_DB_PATH": str(self.database_path),
                # Fixed secret for the duration of the test: otherwise the
                # module would generate a secret file next to the temporary
                # database on every run. At least 32 bytes, as in production.
                "ACCESS_CONTROL_JWT_SECRET": "test-secret-long-enough-for-hs256-signing",
                # Minimum bcrypt cost: with the production value (12 rounds)
                # the suite takes tens of seconds without testing anything
                # extra.
                "ACCESS_CONTROL_BCRYPT_ROUNDS": "4",
            },
        )
        self.environment.start()
        initialize_database()

        # The rate limiter's state lives in process memory and is shared
        # between tests; without clearing it, a test that hits the limit would
        # break the next test's setUp for an unrelated reason.
        login_rate_limiter.clear()
        # The whitelist cache is a single instance shared by the whole
        # process. Without invalidation a test would see faces enrolled by the
        # previous test, in a database that no longer contains them.
        whitelist_cache.invalidate_all()

        self.repository = UserRepository()
        self.camera_repository = CameraRepository()
        # The default camera must exist before any person: `allowed_cameras`
        # is validated against the `cameras` table.
        self.camera_repository.create(
            {
                "hub_id": HUB_ID,
                "camera_id": DEFAULT_CAMERA_ID,
                "name": "Front Entrance",
                "kind": "USB",
                "source": None,
                "enabled": True,
            }
        )
        self.admin = self.repository.create(
            {
                "hub_id": HUB_ID,
                "name": "Test Administrator",
                "role": "ADMIN",
                "has_app_access": True,
                "email": ADMIN_EMAIL,
                "allowed_cameras": [DEFAULT_CAMERA_ID],
                "embedding": None,
                "password_hash": hash_password(ADMIN_PASSWORD),
            }
        )

        self.client = AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        )
        self.admin_token = await self.login(ADMIN_EMAIL, ADMIN_PASSWORD)

    async def asyncTearDown(self) -> None:
        await self.client.aclose()
        self.environment.stop()
        self.temp_dir.cleanup()

    # -- helpers -----------------------------------------------------------
    async def login(self, email: str, password: str) -> str:
        response = await self.client.post(
            "/api/auth/login",
            json={"email": email, "password": password},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["access_token"]

    @staticmethod
    def auth(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    @property
    def admin_auth(self) -> dict[str, str]:
        return self.auth(self.admin_token)

    async def create_user(self, **payload) -> dict:
        """Create a person through the API, as ADMIN."""
        response = await self.client.post(
            "/api/whitelist/",
            json=payload,
            headers=self.admin_auth,
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    async def create_camera(self, camera_id: str, **payload) -> dict:
        """Register a camera through the API, as ADMIN."""
        response = await self.client.post(
            "/api/cameras/",
            json={"camera_id": camera_id, "name": camera_id, **payload},
            headers=self.admin_auth,
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    async def enroll_face(self, name: str, embedding: list[float], **payload) -> dict:
        """Enrol a person with a face, for the detection tests.

        The vectors used in the tests are hand-built and deliberately simple:
        what is under test is the decision logic (threshold, zone
        expectations, cache), not the quality of a recognition model.
        """
        return await self.create_user(name=name, embedding=embedding, **payload)
