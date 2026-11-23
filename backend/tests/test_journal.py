"""Journal listing: filters, pagination and reading a single event.

What these tests actually protect is one property that is easy to break and
impossible to notice by clicking around: **the filters and the total must
describe the same set**. A listing that filters the rows but counts the whole
journal looks correct on the first page and lies about how many pages exist.

The second property is the RBAC boundary on a single event. An APP_USER sees
only their own events in the listing; if the detail route forgot that rule,
the restriction would be one guessed id away from being pointless.
"""

from uuid import uuid4

from app.config.database import get_connection
from tests.base import DEFAULT_CAMERA_ID, HUB_ID, AuthenticatedApiTestCase

OTHER_HUB_ID = "HUB_999"


class JournalFilterTests(AuthenticatedApiTestCase):
    """Filtering, counting and paging over the journal."""

    def insert_event(self, **overrides) -> dict:
        """Write one event straight into the table, with a chosen timestamp.

        Deliberately bypasses the service: the repository generates the
        timestamp itself, precisely so a client cannot backdate an audit
        entry. Testing a date range therefore needs rows whose timestamps were
        placed on purpose, and this is the only way to produce them.
        """
        row = {
            "id": str(uuid4()),
            "hub_id": HUB_ID,
            "camera_id": DEFAULT_CAMERA_ID,
            "user_id": None,
            "user_name": "Unknown Person",
            "status": "INTRUDER",
            "timestamp": "2026-06-15T12:00:00Z",
            "snapshot_path": None,
            **overrides,
        }
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO logs (
                    id, hub_id, camera_id, user_id, user_name, status, timestamp,
                    snapshot_path
                ) VALUES (
                    :id, :hub_id, :camera_id, :user_id, :user_name, :status,
                    :timestamp, :snapshot_path
                )
                """,
                row,
            )
        return row

    async def list_journal(self, query: str = "") -> dict:
        response = await self.client.get(
            f"/api/logs/{query}",
            headers=self.admin_auth,
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    async def test_status_filter_narrows_the_items_and_the_total_together(self):
        """The core invariant: `total` counts the FILTERED set.

        If `total` were the journal's full size, the client would page past
        the end of a filtered result and show empty pages it was told exist.
        """
        for _ in range(3):
            self.insert_event(status="INTRUDER")
        for _ in range(2):
            self.insert_event(status="DEGRADED", user_name=None)

        everything = await self.list_journal()
        self.assertEqual(everything["total"], 5)

        intruders = await self.list_journal("?status=INTRUDER")
        self.assertEqual(intruders["total"], 3)
        self.assertEqual(len(intruders["items"]), 3)
        self.assertTrue(all(item["status"] == "INTRUDER" for item in intruders["items"]))

        faults = await self.list_journal("?status=DEGRADED")
        self.assertEqual(faults["total"], 2)

    async def test_unknown_status_filter_is_refused(self):
        """A misspelled filter must fail loudly, not return an empty page.

        An empty page is indistinguishable from a quiet period, and on a
        surveillance journal that is the difference between "no intruders
        were recorded" and "your filter never matched anything".
        """
        self.insert_event()
        response = await self.client.get(
            "/api/logs/?status=GRANTED",
            headers=self.admin_auth,
        )
        self.assertEqual(response.status_code, 422, response.text)

    async def test_date_range_selects_exactly_the_period(self):
        """`since` is inclusive, `before` is exclusive.

        The boundary rows are the whole point: with both bounds treated the
        same way, two adjacent ranges would either double-count the boundary
        event or lose it entirely.
        """
        self.insert_event(timestamp="2026-06-01T00:00:00Z")
        self.insert_event(timestamp="2026-06-10T08:00:00Z")
        self.insert_event(timestamp="2026-06-20T08:00:00Z")

        window = await self.list_journal("?since=2026-06-10&before=2026-06-20")
        self.assertEqual(window["total"], 1)
        self.assertEqual(window["items"][0]["timestamp"].startswith("2026-06-10"), True)

        # The upper bound is exclusive, so the 20th is reachable only by
        # moving the bound past it.
        including = await self.list_journal("?since=2026-06-10&before=2026-06-21")
        self.assertEqual(including["total"], 2)

    async def test_plain_date_is_treated_as_midnight_utc(self):
        """A date bound must land on a day boundary, not part-way through it."""
        self.insert_event(timestamp="2026-06-15T00:00:00Z")
        self.insert_event(timestamp="2026-06-15T23:59:59Z")

        whole_day = await self.list_journal("?since=2026-06-15&before=2026-06-16")
        self.assertEqual(whole_day["total"], 2)

    async def test_unparseable_date_is_refused(self):
        self.insert_event()
        response = await self.client.get(
            "/api/logs/?since=yesterday",
            headers=self.admin_auth,
        )
        self.assertEqual(response.status_code, 422, response.text)

    async def test_inverted_range_is_refused(self):
        """An inverted range can only ever return nothing.

        Returning an empty page would read as "no events in this period",
        which is a false statement about the journal rather than about the
        query.
        """
        self.insert_event()
        response = await self.client.get(
            "/api/logs/?since=2026-06-20&before=2026-06-10",
            headers=self.admin_auth,
        )
        self.assertEqual(response.status_code, 422, response.text)

    async def test_filters_combine(self):
        await self.create_camera("cam_garage", name="Garage")
        self.insert_event(status="INTRUDER", camera_id=DEFAULT_CAMERA_ID)
        self.insert_event(status="INTRUDER", camera_id="cam_garage")
        self.insert_event(status="DEGRADED", camera_id="cam_garage", user_name=None)

        combined = await self.list_journal("?status=INTRUDER&camera_id=cam_garage")
        self.assertEqual(combined["total"], 1)
        self.assertEqual(combined["items"][0]["camera_id"], "cam_garage")

    async def test_pagination_neither_repeats_nor_skips_under_a_filter(self):
        """Paging a filtered set must still cover it exactly once.

        Ten events share a single timestamp here on purpose: that is the case
        in which the ordering is undefined unless a tie-breaker is applied,
        and the symptom is a row appearing on two pages while another is never
        returned at all.
        """
        for _ in range(10):
            self.insert_event(status="INTRUDER", timestamp="2026-06-15T12:00:00Z")

        seen: list[str] = []
        for offset in (0, 4, 8):
            page = await self.list_journal(f"?status=INTRUDER&limit=4&offset={offset}")
            self.assertEqual(page["total"], 10)
            seen.extend(item["id"] for item in page["items"])

        self.assertEqual(len(seen), 10)
        self.assertEqual(len(set(seen)), 10)

    async def test_filter_options_report_cameras_present_in_the_journal(self):
        """Including cameras no longer in the registry.

        A deleted camera keeps its recorded events. If the filter offered only
        registered cameras, those events could not be narrowed to -- the
        filter would hide evidence instead of selecting it.
        """
        await self.create_camera("cam_garage", name="Garage")
        self.insert_event(camera_id="cam_garage")
        self.insert_event(camera_id="cam_removed")

        response = await self.client.get(
            "/api/logs/filter-options",
            headers=self.admin_auth,
        )
        self.assertEqual(response.status_code, 200, response.text)
        options = response.json()
        self.assertIn("cam_garage", options["cameras"])
        self.assertIn("cam_removed", options["cameras"])
        self.assertIn("INTRUDER", options["statuses"])

    async def test_filter_options_is_not_read_as_an_entry_id(self):
        """Route ordering: the literal path must win over `/{doc_id}`.

        Declared the other way round, this request would look up an event
        called "filter-options" and answer 404.
        """
        response = await self.client.get(
            "/api/logs/filter-options",
            headers=self.admin_auth,
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("cameras", response.json())


class JournalEntryAccessTests(AuthenticatedApiTestCase):
    """Reading one event, and the role boundary around it."""

    async def asyncSetUp(self) -> None:
        await super().asyncSetUp()
        self.app_user = await self.create_user(
            name="Journal Reader",
            role="APP_USER",
            email="reader@example.com",
            password="reader-password-123",
            allowed_cameras=[DEFAULT_CAMERA_ID],
        )
        self.app_user_token = await self.login("reader@example.com", "reader-password-123")
        self.app_user_auth = self.auth(self.app_user_token)

    async def create_event_for(self, user_id: str) -> str:
        response = await self.client.post(
            "/api/logs/",
            json={"camera_id": DEFAULT_CAMERA_ID, "user_id": user_id, "status": "KNOWN"},
            headers=self.admin_auth,
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["id"]

    async def test_admin_reads_any_event_of_the_hub(self):
        event_id = await self.create_event_for(self.app_user["id"])
        response = await self.client.get(f"/api/logs/{event_id}", headers=self.admin_auth)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["id"], event_id)
        self.assertEqual(body["status"], "KNOWN")
        # The photo path is never exposed, only whether one exists.
        self.assertNotIn("snapshot_path", body)
        self.assertIn("has_snapshot", body)

    async def test_app_user_reads_their_own_event(self):
        event_id = await self.create_event_for(self.app_user["id"])
        response = await self.client.get(f"/api/logs/{event_id}", headers=self.app_user_auth)
        self.assertEqual(response.status_code, 200, response.text)

    async def test_app_user_cannot_read_someone_elses_event(self):
        """404, not 403.

        A 403 would confirm the id exists, which is itself information: an
        APP_USER could enumerate ids and learn how many events the hub holds
        without ever being allowed to read one.
        """
        event_id = await self.create_event_for(self.admin["id"])
        response = await self.client.get(f"/api/logs/{event_id}", headers=self.app_user_auth)
        self.assertEqual(response.status_code, 404, response.text)

    async def test_app_user_listing_and_total_are_both_restricted(self):
        """The restriction must reach the count as well as the rows.

        A total covering the whole hub would leak the hub's activity volume to
        a user allowed to see only their own events.
        """
        await self.create_event_for(self.app_user["id"])
        await self.create_event_for(self.admin["id"])
        await self.create_event_for(self.admin["id"])

        as_admin = (await self.client.get("/api/logs/", headers=self.admin_auth)).json()
        self.assertEqual(as_admin["total"], 3)

        as_user = (await self.client.get("/api/logs/", headers=self.app_user_auth)).json()
        self.assertEqual(as_user["total"], 1)
        self.assertEqual(len(as_user["items"]), 1)
        self.assertEqual(as_user["items"][0]["user_id"], self.app_user["id"])

    async def test_event_of_another_hub_is_not_found(self):
        """Tenant isolation on the detail route.

        The id is valid and the row exists; it simply belongs to another
        hub, and nothing about it may be readable from this one.
        """
        foreign_id = str(uuid4())
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO logs (
                    id, hub_id, camera_id, user_id, user_name, status, timestamp,
                    snapshot_path
                ) VALUES (?, ?, ?, NULL, 'Unknown Person', 'INTRUDER',
                          '2026-06-15T12:00:00Z', NULL)
                """,
                (foreign_id, OTHER_HUB_ID, DEFAULT_CAMERA_ID),
            )

        response = await self.client.get(f"/api/logs/{foreign_id}", headers=self.admin_auth)
        self.assertEqual(response.status_code, 404, response.text)

    async def test_unknown_id_is_not_found(self):
        response = await self.client.get(
            f"/api/logs/{uuid4()}",
            headers=self.admin_auth,
        )
        self.assertEqual(response.status_code, 404, response.text)
