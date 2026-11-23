"""Role transitions, biometric erasure, and the person detail payload.

These are the rules the people administration screens depend on, and none of
them was covered before. The gap mattered in one direction specifically: the
form mirrors each rule so the administrator sees a required field instead of
discovering it as a 422, and a mirror is only safe while the thing it mirrors
is pinned by a test. If the backend's rule changed, the form would quietly
start asking for the wrong thing.

What is tested elsewhere and deliberately not repeated here: a MONITORED
person cannot receive a password and cannot log in (`test_auth.py`), an
ADMIN/APP_USER requires an email and a password (`test_auth.py`), the last
administrator cannot be DELETED (`test_api.py`), email uniqueness and clearing
an optional field (`test_api.py`), and permission validation against the
camera registry (`test_cameras.py`).
"""

from tests.base import DEFAULT_CAMERA_ID, AuthenticatedApiTestCase


class RoleTransitionTests(AuthenticatedApiTestCase):
    """Promotion and demotion, which are where credentials appear and vanish."""

    async def test_promoting_a_monitored_person_requires_a_new_password(self):
        """A promotion cannot inherit a password, because there was none.

        The person was created without a hash, so there is nothing for the
        backend to keep. Refusing here rather than creating a login with no
        password is what the form's mandatory password field reflects.
        """
        person = await self.create_user(name="Monitored Person", role="MONITORED")

        response = await self.client.put(
            f"/api/whitelist/{person['id']}",
            json={"role": "APP_USER", "email": "promoted@example.com"},
            headers=self.admin_auth,
        )

        self.assertEqual(response.status_code, 422, response.text)
        self.assertIn("password", response.json()["detail"].lower())

    async def test_promotion_succeeds_when_a_password_is_supplied(self):
        """The same request with a password produces a working login."""
        person = await self.create_user(name="Monitored Person", role="MONITORED")

        response = await self.client.put(
            f"/api/whitelist/{person['id']}",
            json={
                "role": "APP_USER",
                "email": "promoted@example.com",
                "password": "promoted-password-123",
            },
            headers=self.admin_auth,
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["has_app_access"])
        # The decisive check is not the flag but an actual authentication:
        # `has_app_access` could be true while no usable hash was stored.
        await self.login("promoted@example.com", "promoted-password-123")

    async def test_demotion_destroys_the_password(self):
        """A demoted person's old password stops working permanently.

        This is why the form warns BEFORE the change rather than after:
        promoting the person again later needs a new password, and the old one
        cannot be recovered.
        """
        person = await self.create_user(
            name="Application User",
            role="APP_USER",
            email="appuser@example.com",
            password="app-user-password-123",
        )
        await self.login("appuser@example.com", "app-user-password-123")

        demote = await self.client.put(
            f"/api/whitelist/{person['id']}",
            json={"role": "MONITORED"},
            headers=self.admin_auth,
        )
        self.assertEqual(demote.status_code, 200, demote.text)
        self.assertFalse(demote.json()["has_app_access"])

        refused = await self.client.post(
            "/api/auth/login",
            json={"email": "appuser@example.com", "password": "app-user-password-123"},
        )
        self.assertEqual(refused.status_code, 401, refused.text)

        # And promoting them back is treated as a fresh promotion, not as a
        # restoration: the hash is gone, so a password is required again.
        repromote = await self.client.put(
            f"/api/whitelist/{person['id']}",
            json={"role": "APP_USER"},
            headers=self.admin_auth,
        )
        self.assertEqual(repromote.status_code, 422, repromote.text)

    async def test_the_last_admin_cannot_be_demoted(self):
        """Demotion is the other way to leave a hub with no administrator.

        Deletion is already blocked and tested. Without this, the same
        lockout would be reachable by changing a role, and recovery would
        require the bootstrap tool and access to the database file.
        """
        response = await self.client.put(
            f"/api/whitelist/{self.admin['id']}",
            json={"role": "MONITORED"},
            headers=self.admin_auth,
        )

        self.assertEqual(response.status_code, 409, response.text)
        self.assertIn("only ADMIN", response.json()["detail"])

    async def test_an_admin_can_be_demoted_once_another_one_exists(self):
        """The guard protects the LAST administrator, not the role itself."""
        await self.create_user(
            name="Second Administrator",
            role="ADMIN",
            email="second-admin@example.com",
            password="second-admin-password-123",
        )

        response = await self.client.put(
            f"/api/whitelist/{self.admin['id']}",
            json={"role": "MONITORED"},
            headers=self.admin_auth,
        )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(response.json()["has_app_access"])

    async def test_an_update_with_no_fields_is_refused(self):
        """An empty update is a client mistake, not a no-op success.

        Reported as 400 so the screen can disable its save button instead of
        sending a request that changes nothing and answers 200.
        """
        person = await self.create_user(name="Monitored Person", role="MONITORED")

        response = await self.client.put(
            f"/api/whitelist/{person['id']}",
            json={},
            headers=self.admin_auth,
        )

        self.assertEqual(response.status_code, 400, response.text)


class BiometricErasureTests(AuthenticatedApiTestCase):
    """Deleting a face without deleting the person or the audit trail."""

    async def test_sending_a_null_embedding_erases_the_stored_face(self):
        """Erasure keeps the person and their history.

        This is the GDPR art. 17 path for biometric data: the special-category
        vector is destroyed on request, while the surveillance events stay,
        because deleting those would destroy the audit trail rather than
        protect the person.

        It works only because the backend uses
        ``model_dump(exclude_unset=True)``: an absent field is left alone, a
        field sent as null is cleared. Filtering on ``None`` would make
        erasure impossible to express.
        """
        person = await self.enroll_face("Enrolled Person", [1.0, 0.0, 0.0])
        self.assertTrue(person["has_embedding"])

        # Give them a recorded event, so the test proves the history survives.
        simulated = await self.client.post(
            "/api/simulation/detection",
            json={"expected": True, "user_id": person["id"], "camera_id": DEFAULT_CAMERA_ID},
            headers=self.admin_auth,
        )
        self.assertEqual(simulated.status_code, 201, simulated.text)

        erased = await self.client.put(
            f"/api/whitelist/{person['id']}",
            json={"embedding": None},
            headers=self.admin_auth,
        )
        self.assertEqual(erased.status_code, 200, erased.text)
        self.assertFalse(erased.json()["has_embedding"])

        detail = await self.client.get(
            f"/api/whitelist/{person['id']}",
            headers=self.admin_auth,
        )
        self.assertEqual(detail.status_code, 200, detail.text)
        body = detail.json()
        self.assertFalse(body["has_embedding"])
        self.assertEqual(len(body["logs"]), 1)

    async def test_an_omitted_embedding_is_not_an_erasure(self):
        """Renaming a person must not silently delete their face.

        The distinction this protects is the whole reason the erasure above
        works: if an absent field were treated as null, every edit of the name
        would wipe the biometric vector.
        """
        person = await self.enroll_face("Enrolled Person", [1.0, 0.0, 0.0])

        renamed = await self.client.put(
            f"/api/whitelist/{person['id']}",
            json={"name": "Renamed Person"},
            headers=self.admin_auth,
        )

        self.assertEqual(renamed.status_code, 200, renamed.text)
        self.assertEqual(renamed.json()["name"], "Renamed Person")
        self.assertTrue(renamed.json()["has_embedding"])


class PersonDetailPayloadTests(AuthenticatedApiTestCase):
    """What the detail route returns, which the detail screen renders directly."""

    async def test_the_detail_route_returns_the_surveillance_history(self):
        """The listing route does not carry logs; the detail route must.

        The screen renders `logs` without a second request, so an empty array
        here would read as a person who had never been seen.
        """
        person = await self.create_user(name="Monitored Person", role="MONITORED")
        for _ in range(3):
            response = await self.client.post(
                "/api/simulation/detection",
                json={
                    "expected": True,
                    "user_id": person["id"],
                    "camera_id": DEFAULT_CAMERA_ID,
                },
                headers=self.admin_auth,
            )
            self.assertEqual(response.status_code, 201, response.text)

        detail = await self.client.get(
            f"/api/whitelist/{person['id']}",
            headers=self.admin_auth,
        )

        self.assertEqual(detail.status_code, 200, detail.text)
        body = detail.json()
        self.assertEqual(len(body["logs"]), 3)
        self.assertTrue(all(entry["user_id"] == person["id"] for entry in body["logs"]))

    async def test_the_detail_route_never_exposes_the_vector(self):
        """A face is biometric data and must not leave the backend.

        Checked on the DETAIL route specifically: it is the one that composes
        two models (`UserDetail` extends `UserPublic`), which is exactly where
        a field can be reintroduced by accident.
        """
        person = await self.enroll_face("Enrolled Person", [0.6, 0.8, 0.0])

        detail = await self.client.get(
            f"/api/whitelist/{person['id']}",
            headers=self.admin_auth,
        )

        self.assertEqual(detail.status_code, 200, detail.text)
        body = detail.json()
        self.assertNotIn("embedding", body)
        self.assertNotIn("password_hash", body)
        self.assertTrue(body["has_embedding"])

    async def test_a_person_from_another_hub_is_not_found(self):
        """404 rather than 403: a 403 would confirm that the id exists."""
        other_hub = self.repository.create(
            {
                "hub_id": "HUB_OTHER",
                "name": "Other Hub Person",
                "role": "MONITORED",
                "has_app_access": False,
                "email": None,
                "allowed_cameras": [],
                "embedding": None,
                "password_hash": None,
            }
        )

        response = await self.client.get(
            f"/api/whitelist/{other_hub['id']}",
            headers=self.admin_auth,
        )

        self.assertEqual(response.status_code, 404, response.text)
