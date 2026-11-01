"""Tests for the `cameras` entity and for permission validation.

Their purpose: `allowed_cameras` used to accept any text, which made
"multi-camera" a persistence feature rather than real scoping. These tests
demonstrate that a `camera_id` is a validated reference.

Since decision D3 the list no longer grants physical access; it states the
zones in which a person is EXPECTED. Validation matters just as much: a typo
would silently make someone unexpected everywhere, turning every normal
appearance into an alert.
"""

import unittest

from tests.base import DEFAULT_CAMERA_ID, AuthenticatedApiTestCase


class CameraCrudTests(AuthenticatedApiTestCase):
    async def test_seeded_default_camera_is_listed(self):
        cameras = (await self.client.get("/api/cameras/", headers=self.admin_auth)).json()
        self.assertEqual([c["camera_id"] for c in cameras], [DEFAULT_CAMERA_ID])

    async def test_create_and_update_camera(self):
        created = await self.create_camera(
            "cam_garage", name="Garage", kind="RTSP", source="rtsp://x"
        )
        self.assertEqual(created["kind"], "RTSP")
        self.assertTrue(created["enabled"])

        updated = await self.client.put(
            "/api/cameras/cam_garage",
            json={"enabled": False, "name": "Garage (off)"},
            headers=self.admin_auth,
        )
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertFalse(updated.json()["enabled"])
        self.assertEqual(updated.json()["name"], "Garage (off)")

    async def test_duplicate_camera_id_is_rejected(self):
        response = await self.client.post(
            "/api/cameras/",
            json={"camera_id": DEFAULT_CAMERA_ID, "name": "Duplicate"},
            headers=self.admin_auth,
        )
        self.assertEqual(response.status_code, 409, response.text)

    async def test_invalid_camera_id_format_is_rejected(self):
        # A camera id ends up in file paths and in URLs, so it is restricted
        # to lowercase ASCII, digits and underscores.
        for invalid in ("Cam Entrance", "cam-entrance", "cam_entrançe", "x"):
            response = await self.client.post(
                "/api/cameras/",
                json={"camera_id": invalid, "name": "Invalid"},
                headers=self.admin_auth,
            )
            self.assertEqual(response.status_code, 422, f"{invalid}: {response.text}")

    async def test_camera_still_referenced_cannot_be_deleted(self):
        """Deletion must not silently change who is expected where."""
        await self.create_user(name="Expected Person", role="MONITORED")
        response = await self.client.delete(
            f"/api/cameras/{DEFAULT_CAMERA_ID}",
            headers=self.admin_auth,
        )
        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn("still listed", response.json()["detail"])

    async def test_unused_camera_can_be_deleted(self):
        await self.create_camera("cam_yard", name="Yard")
        response = await self.client.delete("/api/cameras/cam_yard", headers=self.admin_auth)
        self.assertEqual(response.status_code, 200, response.text)

    async def test_app_user_can_read_but_not_write_cameras(self):
        await self.create_user(
            name="Application User",
            role="APP_USER",
            email="cameras@example.com",
            password="cameras-pass-1234",
        )
        token = await self.login("cameras@example.com", "cameras-pass-1234")

        read = await self.client.get("/api/cameras/", headers=self.auth(token))
        self.assertEqual(read.status_code, 200, read.text)

        write = await self.client.post(
            "/api/cameras/",
            json={"camera_id": "cam_intruder", "name": "Intruder"},
            headers=self.auth(token),
        )
        self.assertEqual(write.status_code, 403, write.text)


class AllowedCamerasValidationTests(AuthenticatedApiTestCase):
    async def test_unknown_camera_in_permissions_is_rejected(self):
        response = await self.client.post(
            "/api/whitelist/",
            json={
                "name": "Typo",
                "role": "MONITORED",
                "allowed_cameras": ["cam_entrnce"],
            },
            headers=self.admin_auth,
        )
        self.assertEqual(response.status_code, 422, response.text)
        self.assertIn("cam_entrnce", response.json()["detail"])

    async def test_permissions_are_deduplicated_and_sorted(self):
        await self.create_camera("cam_back", name="Back")
        user = await self.create_user(
            name="Several Zones",
            role="MONITORED",
            allowed_cameras=["cam_back", DEFAULT_CAMERA_ID, "cam_back"],
        )
        # Sorted alphabetically, so the stored order does not depend on the
        # order the administrator happened to type them in.
        self.assertEqual(user["allowed_cameras"], ["cam_back", DEFAULT_CAMERA_ID])

    async def test_update_validates_permissions_too(self):
        user = await self.create_user(name="To Be Updated", role="MONITORED")
        response = await self.client.put(
            f"/api/whitelist/{user['id']}",
            json={"allowed_cameras": ["cam_missing"]},
            headers=self.admin_auth,
        )
        self.assertEqual(response.status_code, 422, response.text)


if __name__ == "__main__":
    unittest.main()
