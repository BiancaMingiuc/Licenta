"""Detection contract schemas (decision D3).

Vocabulary
----------
Before decision D3 the system granted physical access, so the contract spoke
in terms of ``GRANTED``/``DENIED``. D3 removed the lock: the camera now
observes and alerts. A result is therefore no longer a permission but a
classification of what was detected.

There are two deliberately separate levels:

- ``DetectionReason`` -- the precise, fine-grained reason. This is what gets
  written to the journal and what the thesis evaluation chapter counts ("how
  many alerts were unknown persons rather than known persons in a zone they
  are not expected in").
- ``DetectionOutcome`` -- what the system must DO: nothing, raise a security
  alert, or raise a fault alert. The mobile app and the buzzer react to this
  level, not to the reason.

The split matters because an intruder alert and a fault alert have different
recipients: the first is a security signal, the second is maintenance. If they
were merged, a broken camera would produce notifications that look like
break-in attempts, and the user would learn to ignore them -- exactly the
behaviour that makes an alerting system useless.
"""

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

DetectionReason = Literal[
    # Expected person, in a zone where they are expected.
    "KNOWN",
    # Face not recognised. Together with EMPTY_WHITELIST, the only case in
    # which decision D2 allows the snapshot to be retained.
    "INTRUDER",
    # Person IDENTIFIED, but seen on a camera where they are not expected.
    # This stays a valid surveillance signal rather than an error:
    # `allowed_cameras` describes a person's normal zones, and a deviation is
    # worth reporting.
    "UNEXPECTED_ZONE",
    # Nobody enrolled in this hub. Any detected face is unknown by definition,
    # so the result is an ALERT, not a fault -- see the note on
    # OUTCOME_BY_REASON.
    "EMPTY_WHITELIST",
    # Frame received from an unregistered camera: a configuration error.
    "CAMERA_UNKNOWN",
    # Camera is registered but was disabled by an administrator.
    "CAMERA_DISABLED",
    # The system could not evaluate (database unavailable, model down, invalid
    # vector). A fault alert: staying silent would be the dangerous option.
    "DEGRADED",
]

DetectionOutcome = Literal["KNOWN", "ALERT", "FAULT"]

# Reason -> action mapping, kept in a single place so the service does not
# duplicate it.
#
# EMPTY_WHITELIST is classified as ALERT rather than FAULT, and that is a
# deliberate fail-loud choice: a fresh install guarding an empty house must
# alert on ANYONE who shows up, not stay silent because nobody has been
# enrolled yet. Silence would be the dangerous behaviour.
#
# CAMERA_DISABLED is FAULT rather than ALERT: the administrator turned that
# camera off on purpose, so an intruder alert would be a false positive. It is
# still reported, because a loop pushing frames from a disabled camera means
# the configuration is inconsistent.
OUTCOME_BY_REASON: Dict[str, DetectionOutcome] = {
    "KNOWN": "KNOWN",
    "INTRUDER": "ALERT",
    "UNEXPECTED_ZONE": "ALERT",
    "EMPTY_WHITELIST": "ALERT",
    "CAMERA_UNKNOWN": "FAULT",
    "CAMERA_DISABLED": "FAULT",
    "DEGRADED": "FAULT",
}

# Reasons for which the snapshot may be retained (decision D2): UNIDENTIFIED
# persons only. For a known person the identity is already in the journal, so
# an extra image would be biometric data without a purpose.
REASONS_KEEPING_SNAPSHOT: frozenset[str] = frozenset({"INTRUDER", "EMPTY_WHITELIST"})

# ---------------------------------------------------------------------------
# Journal coherence invariant
# ---------------------------------------------------------------------------
# A reason either names a specific person or it cannot name one at all. The
# rule lives here, beside the vocabulary, so every writer of the journal obeys
# the same one.
#
# ``DetectionService`` is coherent by construction: it fills the identity only
# when a candidate actually matched. The manual route ``POST /api/logs/``
# accepts whatever the client sends, and that is how the row
# "status=INTRUDER, user_name=Bianca" appeared during development. That row is
# self-contradictory -- INTRUDER means BY DEFINITION a person who was not
# identified -- and it corrupts the evaluation chapter of the thesis: counting
# intruder alerts would include an event that had a known subject.
REASONS_WITH_IDENTITY: frozenset[str] = frozenset({"KNOWN", "UNEXPECTED_ZONE"})

# Reasons that describe a person who WAS present but was not identified. The
# journal stores a placeholder name for these, so a listing never shows a row
# with no subject at all. Fault reasons involve no person, so the name is NULL.
REASONS_WITH_UNIDENTIFIED_PERSON: frozenset[str] = frozenset(
    {"INTRUDER", "EMPTY_WHITELIST"}
)


def describe_identity_conflict(reason: str, user_id: Optional[str]) -> Optional[str]:
    """Return why ``reason`` and ``user_id`` contradict each other, or ``None``.

    A plain function returning a message rather than a Pydantic validator or
    an exception, for one reason: the recognition loop on the Raspberry Pi
    writes journal rows in-process and must never receive an ``HTTPException``
    from a layer below it. The HTTP layer turns the message into a 422; the
    loop can log it and carry on.
    """
    if reason in REASONS_WITH_IDENTITY and not user_id:
        return (
            f"Status '{reason}' describes an identified person, so user_id is "
            "required. Use INTRUDER for a face that was not recognised."
        )
    if reason not in REASONS_WITH_IDENTITY and user_id:
        return (
            f"Status '{reason}' describes an event with no identified person, "
            "so user_id must be empty. Use KNOWN, or UNEXPECTED_ZONE if the "
            "person was seen on a camera where they are not expected."
        )
    return None


class DetectionRequest(BaseModel):
    """One evaluated frame, submitted by the local surveillance loop.

    ``hub_id`` is absent on purpose: it is derived from the caller's identity.

    ``embedding`` is the vector extracted from the live frame. Its length is
    not pinned in the schema because it depends on the model in use;
    compatibility is checked per candidate at comparison time.

    ``snapshot_path`` is the path of the photo captured by the local loop. Per
    decision D2 it is retained ONLY for unidentified persons; in every other
    case it is discarded even when supplied.
    """

    camera_id: str = Field(min_length=1, max_length=40)
    embedding: List[float] = Field(min_length=1)
    snapshot_path: Optional[str] = Field(default=None, max_length=500)


class DetectionResult(BaseModel):
    """The evaluation result together with the evidence that produced it.

    ``score`` and ``threshold`` are returned deliberately: without them an
    alert cannot be diagnosed ("was not recognised" versus "was recognised at
    0.48, below the 0.5 threshold"), and the threshold calibration planned for
    phase 3 would be blind.
    """

    outcome: DetectionOutcome
    reason: DetectionReason
    camera_id: str
    user_id: Optional[str] = None
    user_name: Optional[str] = None
    score: Optional[float] = None
    threshold: float
    # Absent only when even the journal write failed -- in that case the alert
    # was still raised, but the event could not be recorded.
    log_id: Optional[str] = None
    candidates_compared: int = 0
