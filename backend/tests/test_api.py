import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from httpx import ASGITransport, AsyncClient

from app.config.database import initialize_database
from main import app


class LocalApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "test.sqlite3"
        self.database_override = patch.dict(
            os.environ,
            {"ACCESS_CONTROL_DB_PATH": str(self.database_path)},
        )
        self.database_override.start()
        initialize_database()
        self.client = AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        )

    async def asyncTearDown(self):
        await self.client.aclose()
        self.database_override.stop()
        self.temp_dir.cleanup()

    async def test_user_crud_and_role_access(self):
        response = await self.client.post(
            "/api/whitelist/",
            json={"name": "Administrator", "role": "ADMIN"},
        )
        self.assertEqual(response.status_code, 200)
        user = response.json()
        self.assertTrue(user["has_app_access"])

        listed = (await self.client.get("/api/whitelist/")).json()
        self.assertEqual([entry["id"] for entry in listed], [user["id"]])

        updated = await self.client.put(
            f"/api/whitelist/{user['id']}",
            json={"role": "PHYSICAL_ONLY"},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertFalse(updated.json()["has_app_access"])

    async def test_simulated_detection_and_user_deletion_keep_history(self):
        user = (await self.client.post(
            "/api/whitelist/",
            json={"name": "Authorized Person", "role": "APP_USER"},
        )).json()
        detection = await self.client.post(
            "/api/simulation/detection",
            json={"authorized": True, "user_id": user["id"]},
        )
        self.assertEqual(detection.status_code, 200)
        self.assertEqual(detection.json()["decision"], "GRANTED")

        deletion = await self.client.delete(f"/api/whitelist/{user['id']}")
        self.assertEqual(deletion.status_code, 200)

        logs = (await self.client.get("/api/logs/")).json()
        self.assertEqual(len(logs), 1)
        self.assertIsNone(logs[0]["user_id"])
        self.assertEqual(logs[0]["user_name"], "Authorized Person")

    async def test_unauthorized_simulated_detection_is_saved(self):
        detection = await self.client.post(
            "/api/simulation/detection",
            json={"authorized": False},
        )
        self.assertEqual(detection.status_code, 200)
        event = detection.json()["event"]
        self.assertEqual(event["status"], "DENIED")
        self.assertIsNone(event["user_id"])

        logs = (await self.client.get("/api/logs/?camera_id=cam_intrare")).json()
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["id"], event["id"])


if __name__ == "__main__":
    unittest.main()
