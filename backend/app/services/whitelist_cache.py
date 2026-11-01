"""In-memory cache of the known-persons list.

Why it exists
-------------
The recognition loop on the Raspberry Pi processes frames continuously, 24/7.
If every frame read from SQLite and ran ``json.loads`` over each person's
embedding, the I/O and parsing cost would be added to every comparison -- a
cost that has nothing to do with the inference being measured in phases 3 and
4. The cache isolates the measurement: what remains in the loop is capture,
inference and comparison.

Invalidation strategy
---------------------
Explicit invalidation, not time-based expiry. A TTL cache would mean a deleted
person stays valid until expiry -- on a system that decides whether to raise
an intruder alert, a window in which a removed person is still treated as
expected is unacceptable, even if it lasts only seconds.

``UserService`` calls ``invalidate(hub_id)`` after any create, update or
delete. The cost is one full reload on the next detection, which is the right
trade: writes are rare (enrolments), reads are continuous.

Known limitation: the cache lives in the process memory. With several uvicorn
workers each would hold its own copy, and invalidating one would not reach the
others. This project's architecture runs a single process on the Pi, so the
situation does not arise; if workers are added, invalidation must become an
inter-process signal.
"""

from __future__ import annotations

from typing import Any

from app.repositories.user_repo import UserRepository


class WhitelistCache:
    def __init__(self) -> None:
        self._repo = UserRepository()
        self._by_hub: dict[str, list[dict[str, Any]]] = {}

    def get_enrolled(self, hub_id: str) -> list[dict[str, Any]]:
        """The hub's people who have an enrolled embedding.

        Only those can be recognised, so only those enter the cache: a person
        with no enrolled face has no business in the comparison loop.
        """
        cached = self._by_hub.get(hub_id)
        if cached is None:
            cached = [
                user
                for user in self._repo.get_all_by_hub(hub_id)
                if user.get("embedding")
            ]
            self._by_hub[hub_id] = cached
        return cached

    def invalidate(self, hub_id: str) -> None:
        self._by_hub.pop(hub_id, None)

    def invalidate_all(self) -> None:
        self._by_hub.clear()

    def size(self, hub_id: str) -> int:
        """How many faces are loaded -- useful for diagnostic reporting."""
        return len(self._by_hub.get(hub_id, []))


# A single instance shared by the whole process: the detection service and the
# person service must see the same cache, otherwise invalidation would have no
# effect.
whitelist_cache = WhitelistCache()
