"""Detection evaluation -- the core of the surveillance system (decision D3).

This is the service the recognition loop on the Raspberry Pi will call
**directly, in-process**. That is why it never raises ``HTTPException`` and
knows nothing about HTTP: a loop processing camera frames has no request, no
response and no status code. The HTTP route ``POST /api/detection/evaluate``
is merely a second caller of the same function, used for testing and for the
demonstration.

The fail-loud principle -- and why it inverted
----------------------------------------------
Until decision D3 the system drove an electric lock, and the correct
behaviour on failure was **fail-closed**: if the database, the camera or the
model did not respond, the door stayed shut. Silence was the safe option.

D3 removed the lock. In a surveillance system **silence is the dangerous
option**: if the pipeline dies and nobody is notified, an intruder passes
unobserved. The correct behaviour becomes **fail-loud** -- on failure, raise
an alert.

``evaluate()`` therefore keeps the property of never raising (an exception
escaping into the frame loop would stop surveillance altogether), but the
default result on failure changed from "deny" to ``FAULT`` with reason
``DEGRADED``. The fault alert is intentionally DISTINCT from the intruder
alert: they have different recipients, and merging them would let a broken
camera produce notifications that look like break-in attempts.

The order of the checks is deliberate: camera first, identity second. A frame
from an unknown or disabled camera is classified before any comparison runs,
so no CPU is spent for nothing -- which matters on the Pi, where the loop runs
continuously.
"""

from __future__ import annotations

from typing import Any, Optional

from app.repositories.camera_repo import CameraRepository
from app.repositories.log_repo import LogRepository
from app.schemas.detection_schema import (
    OUTCOME_BY_REASON,
    REASONS_KEEPING_SNAPSHOT,
    REASONS_WITH_UNIDENTIFIED_PERSON,
    DetectionReason,
    DetectionRequest,
    DetectionResult,
)
from app.services.matching import find_best_match, get_match_threshold
from app.services.whitelist_cache import whitelist_cache

UNKNOWN_PERSON_NAME = "Unknown Person"


class DetectionService:
    def __init__(self) -> None:
        self.camera_repo = CameraRepository()
        self.log_repo = LogRepository()
        self.cache = whitelist_cache

    def evaluate(self, request: DetectionRequest, hub_id: str) -> DetectionResult:
        """Classify one detection and record the event.

        Always returns a result. Never raises.
        """
        threshold = get_match_threshold()
        try:
            return self._evaluate(request, hub_id, threshold)
        except Exception:  # noqa: BLE001 -- fail-loud is intentionally total
            # Not re-raised: the frame loop must keep running. But not silent
            # either -- a surveillance system that fails quietly is more
            # dangerous than one that is absent, because the user believes it
            # is still working.
            return self._build(request, hub_id, "DEGRADED", threshold)

    # -- actual implementation ---------------------------------------------
    def _evaluate(
        self,
        request: DetectionRequest,
        hub_id: str,
        threshold: float,
    ) -> DetectionResult:
        camera = self.camera_repo.get(hub_id, request.camera_id)

        if camera is None:
            return self._build(request, hub_id, "CAMERA_UNKNOWN", threshold)
        if not camera["enabled"]:
            return self._build(request, hub_id, "CAMERA_DISABLED", threshold)

        enrolled = self.cache.get_enrolled(hub_id)
        if not enrolled:
            # Nobody enrolled: every face is unknown. An alert, not a fault.
            return self._build(request, hub_id, "EMPTY_WHITELIST", threshold)

        matched, score = find_best_match(request.embedding, enrolled)

        if matched is None or score < threshold:
            # Not recognised. Together with EMPTY_WHITELIST, the only case in
            # which decision D2 allows the snapshot to be retained.
            return self._build(
                request,
                hub_id,
                "INTRUDER",
                threshold,
                score=score if matched is not None else None,
                candidates_compared=len(enrolled),
            )

        if request.camera_id not in (matched.get("allowed_cameras") or []):
            # The person IS known but appears in a zone where they are not
            # expected. This stays an alert, recorded WITH their identity: an
            # anonymous alert would make it impossible to tell who was where,
            # which is precisely the question the journal exists to answer.
            return self._build(
                request,
                hub_id,
                "UNEXPECTED_ZONE",
                threshold,
                score=score,
                candidates_compared=len(enrolled),
                user=matched,
            )

        return self._build(
            request,
            hub_id,
            "KNOWN",
            threshold,
            score=score,
            candidates_compared=len(enrolled),
            user=matched,
        )

    def _build(
        self,
        request: DetectionRequest,
        hub_id: str,
        reason: DetectionReason,
        threshold: float,
        score: Optional[float] = None,
        candidates_compared: int = 0,
        user: Optional[dict[str, Any]] = None,
    ) -> DetectionResult:
        """Build the result and record it in the journal.

        A single constructor for all seven reasons: the reason -> action
        mapping comes from ``OUTCOME_BY_REASON``, so there is no second source
        of truth and a reason added to the schema cannot silently end up
        without a classification.

        Decision D2 is enforced here, in one place: the snapshot is retained
        only when the person was not identified.
        """
        outcome = OUTCOME_BY_REASON[reason]

        is_unidentified = user is None and reason in REASONS_WITH_UNIDENTIFIED_PERSON
        snapshot_path = (
            request.snapshot_path
            if (reason in REASONS_KEEPING_SNAPSHOT and user is None)
            else None
        )

        user_id = user["id"] if user else None
        user_name = (
            user["name"] if user else (UNKNOWN_PERSON_NAME if is_unidentified else None)
        )

        log_id = self._try_log(
            hub_id=hub_id,
            camera_id=request.camera_id,
            user_id=user_id,
            user_name=user_name,
            status=reason,
            snapshot_path=snapshot_path,
        )
        return DetectionResult(
            outcome=outcome,
            reason=reason,
            camera_id=request.camera_id,
            user_id=user_id,
            user_name=user_name,
            score=score,
            threshold=threshold,
            log_id=log_id,
            candidates_compared=candidates_compared,
        )

    def _try_log(
        self,
        hub_id: str,
        camera_id: str,
        user_id: Optional[str],
        user_name: Optional[str],
        status: str,
        snapshot_path: Optional[str],
    ) -> Optional[str]:
        """Write the event; return ``None`` if the write failed.

        An unavailable database must not turn an alert into an exception: the
        alert has to reach the user even when the journal could not be
        written. Losing one journal line is an auditing problem, not a reason
        to stop surveillance.
        """
        try:
            event = self.log_repo.create(
                {
                    "hub_id": hub_id,
                    "camera_id": camera_id,
                    "user_id": user_id,
                    "user_name": user_name,
                    "status": status,
                    "snapshot_path": snapshot_path,
                }
            )
            return event["id"]
        except Exception:  # noqa: BLE001
            return None
