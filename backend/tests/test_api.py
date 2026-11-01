"""Tests for CRUD, simulation, pagination and bulk deletion of the journal."""

import unittest

from tests.base import DEFAULT_CAMERA_ID, AuthenticatedApiTestCase


class LocalApiTests(AuthenticatedApiTestCase):
    async def test_user_crud_and_role_access(self):
        user = await self.create_user(
            name="Monitored Person",
            role="MONITORED",
        )
        self.assertFalse(user["has_app_access"])
        # The biometric vector must never appear in a response.
        self.assertNotIn("embedding", user)
        self.assertNotIn("password_hash", user)
        self.assertFalse(user["has_embedding"])

        listed = (await self.client.get("/api/whitelist/", headers=self.admin_auth)).json()
        self.assertIn(user["id"], [entry["id"] for entry in listed])

        # Promotion to APP_USER requires an email and a password.
        promoted = await self.client.put(
            f"/api/whitelist/{user['id']}",
            json={
                "role": "APP_USER",
                "email": "promoted@example.com",
                "password": "new-password-1",
            },
            headers=self.admin_auth,
        )
        self.assertEqual(promoted.status_code, 200, promoted.text)
        self.assertTrue(promoted.json()["has_app_access"])

        # Demotion withdraws application access.
        demoted = await self.client.put(
            f"/api/whitelist/{user['id']}",
            json={"role": "MONITORED"},
            headers=self.admin_auth,
        )
        self.assertEqual(demoted.status_code, 200, demoted.text)
        self.assertFalse(demoted.json()["has_app_access"])

    async def test_simulated_detection_and_deletion_keep_history(self):
        user = await self.create_user(
            name="Expected Person",
            role="APP_USER",
            email="expected@example.com",
            password="user-password-123",
        )
        detection = await self.client.post(
            "/api/simulation/detection",
            json={"expected": True, "user_id": user["id"]},
            headers=self.admin_auth,
        )
        self.assertEqual(detection.status_code, 201, detection.text)
        self.assertEqual(detection.json()["reason"], "KNOWN")

        deletion = await self.client.delete(
            f"/api/whitelist/{user['id']}",
            headers=self.admin_auth,
        )
        self.assertEqual(deletion.status_code, 200, deletion.text)

        # The journal keeps the event and the name, but loses the link: an
        # audit record must survive the removal of its subject.
        page = (await self.client.get("/api/logs/", headers=self.admin_auth)).json()
        self.assertEqual(page["total"], 1)
        self.assertIsNone(page["items"][0]["user_id"])
        self.assertEqual(page["items"][0]["user_name"], "Expected Person")

    async def test_simulated_intruder_detection_is_saved(self):
        detection = await self.client.post(
            "/api/simulation/detection",
            json={"expected": False},
            headers=self.admin_auth,
        )
        self.assertEqual(detection.status_code, 201, detection.text)
        event = detection.json()["event"]
        self.assertEqual(event["status"], "INTRUDER")
        self.assertIsNone(event["user_id"])

        page = (
            await self.client.get(
                f"/api/logs/?camera_id={DEFAULT_CAMERA_ID}", headers=self.admin_auth
            )
        ).json()
        self.assertEqual(page["total"], 1)
        self.assertEqual(page["items"][0]["id"], event["id"])

    async def test_logs_are_paginated(self):
        for _ in range(3):
            await self.client.post(
                "/api/simulation/detection",
                json={"expected": False},
                headers=self.admin_auth,
            )

        first_page = (
            await self.client.get("/api/logs/?limit=2&offset=0", headers=self.admin_auth)
        ).json()
        self.assertEqual(first_page["total"], 3)
        self.assertEqual(len(first_page["items"]), 2)

        second_page = (
            await self.client.get("/api/logs/?limit=2&offset=2", headers=self.admin_auth)
        ).json()
        self.assertEqual(len(second_page["items"]), 1)

        # The pages must not overlap.
        first_ids = {entry["id"] for entry in first_page["items"]}
        second_ids = {entry["id"] for entry in second_page["items"]}
        self.assertEqual(first_ids & second_ids, set())

    async def test_email_must_be_unique(self):
        await self.create_user(
            name="First",
            role="APP_USER",
            email="duplicate@example.com",
            password="first-password-123",
        )
        conflict = await self.client.post(
            "/api/whitelist/",
            json={
                "name": "Second",
                "role": "APP_USER",
                "email": "duplicate@example.com",
                "password": "second-password-123",
            },
            headers=self.admin_auth,
        )
        self.assertEqual(conflict.status_code, 409, conflict.text)

    async def test_update_can_clear_optional_field(self):
        """`exclude_unset` makes clearing a field on purpose possible."""
        user = await self.create_user(
            name="With Email", role="MONITORED", email="to@delete.com"
        )
        cleared = await self.client.put(
            f"/api/whitelist/{user['id']}",
            json={"email": None},
            headers=self.admin_auth,
        )
        self.assertEqual(cleared.status_code, 200, cleared.text)
        self.assertIsNone(cleared.json()["email"])

    async def test_last_admin_cannot_be_deleted(self):
        response = await self.client.delete(
            f"/api/whitelist/{self.admin['id']}",
            headers=self.admin_auth,
        )
        self.assertEqual(response.status_code, 409, response.text)


class JournalPurgeTests(AuthenticatedApiTestCase):
    """Bulk deletion: the only operation that destroys evidence at scale.

    The guards are the point of these tests. An audit journal that can be
    emptied by a mistyped URL is not an audit journal.
    """

    async def _simulate(self, count: int, camera_id: str = DEFAULT_CAMERA_ID) -> None:
        for _ in range(count):
            response = await self.client.post(
                "/api/simulation/detection",
                json={"expected": False, "camera_id": camera_id},
                headers=self.admin_auth,
            )
            self.assertEqual(response.status_code, 201, response.text)

    async def _total(self) -> int:
        page = (await self.client.get("/api/logs/", headers=self.admin_auth)).json()
        return page["total"]

    async def test_confirmation_is_mandatory(self):
        await self._simulate(2)
        response = await self.client.delete("/api/logs/", headers=self.admin_auth)
        # `confirm` is a required parameter, so its absence is a 422; supplying
        # it as false is a deliberate refusal, which is a 400.
        self.assertEqual(response.status_code, 422, response.text)

        refused = await self.client.delete(
            "/api/logs/?confirm=false", headers=self.admin_auth
        )
        self.assertEqual(refused.status_code, 400, refused.text)
        self.assertEqual(await self._total(), 2)

    async def test_invalid_filters_delete_nothing(self):
        await self._simulate(2)

        unknown_status = await self.client.delete(
            "/api/logs/?confirm=true&status=GRANTED", headers=self.admin_auth
        )
        self.assertEqual(unknown_status.status_code, 422, unknown_status.text)

        bad_date = await self.client.delete(
            "/api/logs/?confirm=true&before=yesterday", headers=self.admin_auth
        )
        self.assertEqual(bad_date.status_code, 422, bad_date.text)

        self.assertEqual(await self._total(), 2)

    async def test_purge_filtered_by_camera(self):
        await self.create_camera("cam_garage", name="Garage")
        await self._simulate(2, camera_id=DEFAULT_CAMERA_ID)
        await self._simulate(3, camera_id="cam_garage")

        response = await self.client.delete(
            "/api/logs/?confirm=true&camera_id=cam_garage", headers=self.admin_auth
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["deleted"], 3)
        self.assertEqual(await self._total(), 2)

    async def test_purge_everything_in_the_hub(self):
        await self._simulate(3)
        response = await self.client.delete("/api/logs/?confirm=true", headers=self.admin_auth)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["deleted"], 3)
        self.assertEqual(await self._total(), 0)

    async def test_purging_an_empty_journal_is_not_an_error(self):
        response = await self.client.delete("/api/logs/?confirm=true", headers=self.admin_auth)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["deleted"], 0)

    async def test_app_user_cannot_purge_the_journal(self):
        await self._simulate(2)
        await self.create_user(
            name="Application User",
            role="APP_USER",
            email="purge@example.com",
            password="purge-password-1",
        )
        token = await self.login("purge@example.com", "purge-password-1")

        response = await self.client.delete(
            "/api/logs/?confirm=true", headers=self.auth(token)
        )
        self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(await self._total(), 2)


class JournalCoherenceTests(AuthenticatedApiTestCase):
    """The status and the identity of an event must agree.

    These guard a real incident: a row reading "status=INTRUDER,
    user_name=Bianca" was written through POST /api/logs/ during development.
    An intruder is by definition a person who was NOT identified, so that row
    is self-contradictory -- and it silently corrupts any count of intruder
    alerts, which is a figure the thesis evaluation chapter reports.
    """

    async def test_intruder_cannot_carry_an_identity(self):
        response = await self.client.post(
            "/api/logs/",
            json={"status": "INTRUDER", "user_id": self.admin["id"]},
            headers=self.admin_auth,
        )
        self.assertEqual(response.status_code, 422, response.text)
        self.assertIn("user_id must be empty", response.json()["detail"])

    async def test_fault_cannot_carry_an_identity(self):
        response = await self.client.post(
            "/api/logs/",
            json={"status": "DEGRADED", "user_id": self.admin["id"]},
            headers=self.admin_auth,
        )
        self.assertEqual(response.status_code, 422, response.text)

    async def test_known_requires_an_identity(self):
        response = await self.client.post(
            "/api/logs/",
            json={"status": "KNOWN"},
            headers=self.admin_auth,
        )
        self.assertEqual(response.status_code, 422, response.text)
        self.assertIn("user_id is required", response.json()["detail"])

    async def test_unexpected_zone_requires_an_identity(self):
        response = await self.client.post(
            "/api/logs/",
            json={"status": "UNEXPECTED_ZONE"},
            headers=self.admin_auth,
        )
        self.assertEqual(response.status_code, 422, response.text)

    async def test_the_displayed_name_is_derived_not_trusted(self):
        """A client-supplied name must not be able to misattribute an event."""
        response = await self.client.post(
            "/api/logs/",
            json={
                "status": "KNOWN",
                "user_id": self.admin["id"],
                "user_name": "Somebody Else",
            },
            headers=self.admin_auth,
        )
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["user_name"], self.admin["name"])

    async def test_a_fault_names_nobody(self):
        response = await self.client.post(
            "/api/logs/",
            json={"status": "CAMERA_DISABLED", "user_name": "Unknown Person"},
            headers=self.admin_auth,
        )
        self.assertEqual(response.status_code, 201, response.text)
        # A fault involves no person, so naming one would be misleading.
        self.assertIsNone(response.json()["user_name"])

    async def test_an_unidentified_person_gets_the_placeholder_name(self):
        response = await self.client.post(
            "/api/logs/",
            json={"status": "EMPTY_WHITELIST", "user_name": ""},
            headers=self.admin_auth,
        )
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["user_name"], "Unknown Person")

    async def test_the_literal_unknown_sentinel_still_works(self):
        """`user_id: "UNKNOWN"` is accepted and normalised to no identity."""
        response = await self.client.post(
            "/api/logs/",
            json={"status": "INTRUDER", "user_id": "UNKNOWN"},
            headers=self.admin_auth,
        )
        self.assertEqual(response.status_code, 201, response.text)
        self.assertIsNone(response.json()["user_id"])

    async def test_the_detection_service_never_produces_an_incoherent_row(self):
        """Every reason the service can emit satisfies the same invariant."""
        from app.schemas.detection_schema import (
            OUTCOME_BY_REASON,
            REASONS_WITH_IDENTITY,
            describe_identity_conflict,
        )

        for reason in OUTCOME_BY_REASON:
            identity = "some-person-id" if reason in REASONS_WITH_IDENTITY else None
            self.assertIsNone(
                describe_identity_conflict(reason, identity),
                f"{reason} is not covered by the coherence rule",
            )


if __name__ == "__main__":
    unittest.main()
