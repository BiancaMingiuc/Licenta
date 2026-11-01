"""Tests for authentication and RBAC enforcement.

These are the tests that demonstrate the roles are ENFORCED, not merely
stored. Before they existed, `ADMIN` / `APP_USER` / `MONITORED` were just text
values in a column.
"""

import os
import unittest
from unittest.mock import patch

from app.config.security import (
    LOGIN_MAX_ATTEMPTS,
    MIN_JWT_SECRET_BYTES,
    InsecureSecretError,
    get_jwt_secret,
    hash_password,
    login_rate_limiter,
    validate_security_configuration,
    verify_password,
)
from tests.base import ADMIN_EMAIL, ADMIN_PASSWORD, AuthenticatedApiTestCase


class PasswordHashingTests(unittest.TestCase):
    def test_hash_is_salted_and_verifiable(self):
        first = hash_password("correct-password-1")
        second = hash_password("correct-password-1")

        # A fresh salt on every call: the same password produces different
        # hashes, so a precomputed table does not help an attacker.
        self.assertNotEqual(first, second)
        self.assertTrue(verify_password("correct-password-1", first))
        self.assertTrue(verify_password("correct-password-1", second))
        self.assertFalse(verify_password("wrong-password", first))

    def test_hash_is_not_the_plain_password(self):
        hashed = hash_password("correct-password-1")
        self.assertNotIn("correct-password-1", hashed)
        self.assertTrue(hashed.startswith("$2"))


class SecretConfigurationTests(unittest.TestCase):
    """A signing secret that is too short must be refused, not accepted quietly.

    A weak password compromises one account; a weak signing secret allows
    valid tokens to be issued for any account, including ADMIN.
    """

    def test_short_secret_is_rejected(self):
        with patch.dict(os.environ, {"ACCESS_CONTROL_JWT_SECRET": "too-short"}):
            with self.assertRaises(InsecureSecretError):
                validate_security_configuration()

    def test_sufficiently_long_secret_is_accepted(self):
        long_secret = "a" * MIN_JWT_SECRET_BYTES
        with patch.dict(os.environ, {"ACCESS_CONTROL_JWT_SECRET": long_secret}):
            validate_security_configuration()
            self.assertEqual(get_jwt_secret(), long_secret)


class AuthenticationTests(AuthenticatedApiTestCase):
    async def test_protected_route_requires_token(self):
        response = await self.client.get("/api/whitelist/")
        self.assertEqual(response.status_code, 401)

    async def test_invalid_token_is_rejected(self):
        response = await self.client.get(
            "/api/whitelist/",
            headers=self.auth("this.is.not-a-token"),
        )
        self.assertEqual(response.status_code, 401)

    async def test_login_returns_role_and_expiry(self):
        response = await self.client.post(
            "/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["role"], "ADMIN")
        self.assertEqual(body["token_type"], "bearer")
        self.assertGreater(body["expires_in"], 0)

    async def test_wrong_password_and_unknown_email_give_same_answer(self):
        """Identical messages: otherwise existing accounts can be enumerated."""
        wrong_password = await self.client.post(
            "/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": "something-entirely-else"},
        )
        unknown_email = await self.client.post(
            "/api/auth/login",
            json={"email": "nobody@example.com", "password": "something-entirely-else"},
        )
        self.assertEqual(wrong_password.status_code, 401)
        self.assertEqual(unknown_email.status_code, 401)
        self.assertEqual(wrong_password.json()["detail"], unknown_email.json()["detail"])

    async def test_monitored_person_cannot_log_in(self):
        """The third RBAC tier: no password, so no authentication is possible."""
        await self.create_user(
            name="Monitored Only", role="MONITORED", email="monitored@example.com"
        )
        response = await self.client.post(
            "/api/auth/login",
            json={"email": "monitored@example.com", "password": "any-password-123"},
        )
        self.assertEqual(response.status_code, 401)

    async def test_monitored_person_cannot_receive_a_password(self):
        response = await self.client.post(
            "/api/whitelist/",
            json={
                "name": "Invalid",
                "role": "MONITORED",
                "email": "invalid@example.com",
                "password": "some-password-1",
            },
            headers=self.admin_auth,
        )
        self.assertEqual(response.status_code, 422, response.text)

    async def test_app_user_role_requires_password_and_email(self):
        without_password = await self.client.post(
            "/api/whitelist/",
            json={"name": "No Password", "role": "APP_USER", "email": "nopass@example.com"},
            headers=self.admin_auth,
        )
        self.assertEqual(without_password.status_code, 422)

        without_email = await self.client.post(
            "/api/whitelist/",
            json={"name": "No Email", "role": "APP_USER", "password": "valid-password-1"},
            headers=self.admin_auth,
        )
        self.assertEqual(without_email.status_code, 422)

    async def test_login_is_rate_limited(self):
        login_rate_limiter.clear()

        statuses = []
        for _ in range(LOGIN_MAX_ATTEMPTS + 2):
            response = await self.client.post(
                "/api/auth/login",
                json={"email": ADMIN_EMAIL, "password": "wrong-password"},
            )
            statuses.append(response.status_code)

        self.assertIn(429, statuses)
        # The limit is reached only after the configured number of attempts.
        self.assertEqual(statuses[0], 401)


class AuthorizationTests(AuthenticatedApiTestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.app_user = await self.create_user(
            name="Application User",
            role="APP_USER",
            email="appuser@example.com",
            password="app-password-123",
        )
        self.app_user_token = await self.login("appuser@example.com", "app-password-123")

    async def test_app_user_cannot_list_monitored_people(self):
        response = await self.client.get("/api/whitelist/", headers=self.auth(self.app_user_token))
        self.assertEqual(response.status_code, 403, response.text)

    async def test_app_user_cannot_create_people(self):
        response = await self.client.post(
            "/api/whitelist/",
            json={
                "name": "Intruder",
                "role": "ADMIN",
                "email": "intruder@example.com",
                "password": "intruder-password-1",
            },
            headers=self.auth(self.app_user_token),
        )
        self.assertEqual(response.status_code, 403, response.text)

    async def test_app_user_sees_only_own_events(self):
        # One event for the APP_USER and one for an unidentified person.
        await self.client.post(
            "/api/simulation/detection",
            json={"expected": True, "user_id": self.app_user["id"]},
            headers=self.admin_auth,
        )
        await self.client.post(
            "/api/simulation/detection",
            json={"expected": False},
            headers=self.admin_auth,
        )

        admin_view = (await self.client.get("/api/logs/", headers=self.admin_auth)).json()
        self.assertEqual(admin_view["total"], 2)

        user_view = (
            await self.client.get("/api/logs/", headers=self.auth(self.app_user_token))
        ).json()
        self.assertEqual(user_view["total"], 1)
        self.assertEqual(user_view["items"][0]["user_id"], self.app_user["id"])

    async def test_app_user_cannot_run_the_simulation(self):
        response = await self.client.post(
            "/api/simulation/detection",
            json={"expected": False},
            headers=self.auth(self.app_user_token),
        )
        self.assertEqual(response.status_code, 403, response.text)

    async def test_me_returns_identity_without_sensitive_fields(self):
        response = await self.client.get(
            "/api/auth/me",
            headers=self.auth(self.app_user_token),
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["role"], "APP_USER")
        self.assertNotIn("password_hash", body)
        self.assertNotIn("embedding", body)

    async def test_revoked_access_invalidates_an_existing_token(self):
        """Demotion takes effect immediately, not when the token expires."""
        await self.client.put(
            f"/api/whitelist/{self.app_user['id']}",
            json={"role": "MONITORED"},
            headers=self.admin_auth,
        )
        response = await self.client.get(
            "/api/logs/",
            headers=self.auth(self.app_user_token),
        )
        self.assertEqual(response.status_code, 401, response.text)


if __name__ == "__main__":
    unittest.main()
