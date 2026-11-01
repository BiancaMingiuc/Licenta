"""Tests for the detection decision: threshold, expected zone, fail-loud.

The vectors are hand-built rather than produced by a model: what is under
test here is the DECISION logic, not recognition quality. A real model
arrives in phase 3.

These tests also pin the semantics of decision D3. Before D3 the system drove
a lock and failure meant "deny"; now it observes and alerts, so failure means
"raise a fault alert". The two alert levels are kept apart on purpose: a
security ALERT and a maintenance FAULT have different recipients.
"""

import unittest

from app.schemas.detection_schema import DetectionRequest
from app.services.detection_service import DetectionService
from app.services.matching import cosine_similarity
from tests.base import DEFAULT_CAMERA_ID, AuthenticatedApiTestCase

# Two orthogonal vectors: similarity 0, so they can never be confused.
FACE_A = [1.0, 0.0, 0.0, 0.0]
FACE_B = [0.0, 1.0, 0.0, 0.0]
# Same direction as FACE_A, different magnitude: the cosine is 1, because
# cosine similarity ignores vector length.
FACE_A_SCALED = [3.0, 0.0, 0.0, 0.0]


class CosineSimilarityTests(unittest.TestCase):
    def test_identical_direction_scores_one(self):
        self.assertAlmostEqual(cosine_similarity(FACE_A, FACE_A_SCALED), 1.0)

    def test_orthogonal_vectors_score_zero(self):
        self.assertAlmostEqual(cosine_similarity(FACE_A, FACE_B), 0.0)

    def test_opposite_direction_scores_minus_one(self):
        self.assertAlmostEqual(cosine_similarity([1.0, 0.0], [-1.0, 0.0]), -1.0)

    def test_zero_vector_is_similar_to_nothing(self):
        """A null vector has no direction, so it cannot resemble anything."""
        self.assertEqual(cosine_similarity([0.0, 0.0], FACE_A[:2]), 0.0)

    def test_incompatible_dimensions_raise(self):
        """Comparing vectors from different models must not produce a number."""
        with self.assertRaises(ValueError):
            cosine_similarity([1.0, 0.0], [1.0, 0.0, 0.0])


class DetectionDecisionTests(AuthenticatedApiTestCase):
    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.service = DetectionService()
        self.enrolled = await self.enroll_face(
            "Enrolled Person",
            FACE_A,
            role="MONITORED",
            allowed_cameras=[DEFAULT_CAMERA_ID],
        )

    def evaluate(self, embedding, camera_id=DEFAULT_CAMERA_ID, snapshot_path=None):
        return self.service.evaluate(
            DetectionRequest(
                camera_id=camera_id,
                embedding=embedding,
                snapshot_path=snapshot_path,
            ),
            hub_id=self.admin["hub_id"],
        )

    async def test_expected_person_in_expected_zone_raises_nothing(self):
        result = self.evaluate(FACE_A_SCALED)
        self.assertEqual(result.outcome, "KNOWN")
        self.assertEqual(result.reason, "KNOWN")
        self.assertEqual(result.user_id, self.enrolled["id"])
        self.assertAlmostEqual(result.score, 1.0)
        self.assertIsNotNone(result.log_id)

    async def test_unrecognised_face_raises_an_intruder_alert(self):
        result = self.evaluate(FACE_B)
        self.assertEqual(result.outcome, "ALERT")
        self.assertEqual(result.reason, "INTRUDER")
        self.assertIsNone(result.user_id)

    async def test_known_person_in_unexpected_zone_keeps_their_identity(self):
        """The alert keeps the identity: otherwise who was where is unknowable."""
        await self.create_camera("cam_server", name="Server Room")
        result = self.evaluate(FACE_A, camera_id="cam_server")
        self.assertEqual(result.outcome, "ALERT")
        self.assertEqual(result.reason, "UNEXPECTED_ZONE")
        self.assertEqual(result.user_id, self.enrolled["id"])
        self.assertAlmostEqual(result.score, 1.0)

    async def test_unknown_camera_is_a_fault_and_compares_nothing(self):
        """A misconfigured camera is maintenance, not a break-in attempt."""
        result = self.evaluate(FACE_A, camera_id="cam_missing")
        self.assertEqual(result.outcome, "FAULT")
        self.assertEqual(result.reason, "CAMERA_UNKNOWN")
        # The camera is checked before identity, so nothing was compared.
        self.assertEqual(result.candidates_compared, 0)

    async def test_disabled_camera_is_a_fault_not_an_alert(self):
        """The administrator disabled it on purpose: an alert would be a false positive."""
        await self.client.put(
            f"/api/cameras/{DEFAULT_CAMERA_ID}",
            json={"enabled": False},
            headers=self.admin_auth,
        )
        result = self.evaluate(FACE_A)
        self.assertEqual(result.outcome, "FAULT")
        self.assertEqual(result.reason, "CAMERA_DISABLED")

    async def test_incompatible_embedding_alerts_instead_of_crashing(self):
        """Fail-loud: a vector of another size neither crashes nor stays silent."""
        result = self.evaluate([1.0, 0.0])
        self.assertEqual(result.outcome, "ALERT")
        self.assertEqual(result.reason, "INTRUDER")

    async def test_evaluate_never_raises(self):
        """The frame loop must survive any internal failure.

        The repository is replaced with one that always raises, which is the
        closest stand-in for a database that has become unavailable on the Pi.
        The call must still return a result, and that result must be a FAULT
        rather than silence.
        """

        class BrokenRepository:
            def get(self, *args, **kwargs):
                raise RuntimeError("database unavailable")

        self.service.camera_repo = BrokenRepository()
        result = self.evaluate(FACE_A)
        self.assertEqual(result.outcome, "FAULT")
        self.assertEqual(result.reason, "DEGRADED")

    async def test_deleting_person_takes_effect_on_the_next_frame(self):
        """Cache invalidation: a removal applies to the very next frame."""
        self.assertEqual(self.evaluate(FACE_A).reason, "KNOWN")

        await self.client.delete(
            f"/api/whitelist/{self.enrolled['id']}",
            headers=self.admin_auth,
        )
        after = self.evaluate(FACE_A)
        self.assertEqual(after.outcome, "ALERT")
        self.assertEqual(after.reason, "EMPTY_WHITELIST")

    async def test_changing_expected_zones_takes_effect_immediately(self):
        await self.create_camera("cam_side", name="Side")
        await self.client.put(
            f"/api/whitelist/{self.enrolled['id']}",
            json={"allowed_cameras": ["cam_side"]},
            headers=self.admin_auth,
        )
        result = self.evaluate(FACE_A)
        self.assertEqual(result.reason, "UNEXPECTED_ZONE")

    async def test_every_detection_is_recorded(self):
        self.evaluate(FACE_A)
        self.evaluate(FACE_B)
        page = (await self.client.get("/api/logs/", headers=self.admin_auth)).json()
        self.assertEqual(page["total"], 2)
        self.assertEqual(
            {entry["status"] for entry in page["items"]}, {"KNOWN", "INTRUDER"}
        )


class SnapshotPolicyTests(AuthenticatedApiTestCase):
    """Decision D2: the photo is retained ONLY for unidentified persons."""

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.service = DetectionService()
        self.enrolled = await self.enroll_face(
            "Enrolled",
            FACE_A,
            role="MONITORED",
            allowed_cameras=[DEFAULT_CAMERA_ID],
        )

    def evaluate(self, embedding, camera_id=DEFAULT_CAMERA_ID):
        return self.service.evaluate(
            DetectionRequest(
                camera_id=camera_id,
                embedding=embedding,
                snapshot_path="snapshots/2026-10-19/test.jpg",
            ),
            hub_id=self.admin["hub_id"],
        )

    def _snapshot_of(self, log_id: str):
        return self.service.log_repo.get_by_id(log_id)["snapshot_path"]

    async def test_snapshot_kept_for_an_unidentified_person(self):
        result = self.evaluate(FACE_B)
        self.assertEqual(result.reason, "INTRUDER")
        self.assertIsNotNone(self._snapshot_of(result.log_id))

    async def test_snapshot_discarded_for_an_expected_person(self):
        result = self.evaluate(FACE_A)
        self.assertEqual(result.reason, "KNOWN")
        self.assertIsNone(self._snapshot_of(result.log_id))

    async def test_snapshot_discarded_once_the_person_is_identified(self):
        """Known person in an unexpected zone: the identity is in the journal already."""
        await self.create_camera("cam_restricted", name="Restricted")
        result = self.evaluate(FACE_A, camera_id="cam_restricted")
        self.assertEqual(result.reason, "UNEXPECTED_ZONE")
        self.assertIsNone(self._snapshot_of(result.log_id))

    async def test_snapshot_path_is_never_exposed_by_the_logs_api(self):
        result = self.evaluate(FACE_B)
        page = (await self.client.get("/api/logs/", headers=self.admin_auth)).json()
        entry = next(e for e in page["items"] if e["id"] == result.log_id)
        self.assertNotIn("snapshot_path", entry)
        self.assertTrue(entry["has_snapshot"])


class DetectionRouteTests(AuthenticatedApiTestCase):
    async def test_route_requires_admin(self):
        await self.create_user(
            name="Application User",
            role="APP_USER",
            email="detection@example.com",
            password="detection-pass-1",
        )
        token = await self.login("detection@example.com", "detection-pass-1")
        response = await self.client.post(
            "/api/detection/evaluate",
            json={"camera_id": DEFAULT_CAMERA_ID, "embedding": FACE_A},
            headers=self.auth(token),
        )
        self.assertEqual(response.status_code, 403, response.text)

    async def test_an_alert_still_returns_200(self):
        """An alert is a valid result of the operation, not a bad request."""
        response = await self.client.post(
            "/api/detection/evaluate",
            json={"camera_id": DEFAULT_CAMERA_ID, "embedding": FACE_A},
            headers=self.admin_auth,
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["outcome"], "ALERT")
        self.assertEqual(response.json()["reason"], "EMPTY_WHITELIST")

    async def test_empty_embedding_is_rejected_by_the_schema(self):
        response = await self.client.post(
            "/api/detection/evaluate",
            json={"camera_id": DEFAULT_CAMERA_ID, "embedding": []},
            headers=self.admin_auth,
        )
        self.assertEqual(response.status_code, 422, response.text)


if __name__ == "__main__":
    unittest.main()
