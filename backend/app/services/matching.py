"""Facial embedding matching -- THE REFERENCE IMPLEMENTATION (baseline).

The role of this module in the thesis
-------------------------------------
This is the **unoptimised** pure-Python implementation of vector comparison.
It is NOT written for speed; it is written to be correct, readable and
measurable. In phase 4, exactly these two functions are the ones replaced by
the C/C++ kernel with ARM NEON intrinsics, and the measured difference between
them is part of the scientific contribution.

Therefore: do not optimise this module. The reference figures (per-frame
latency, FPS, RAM) must be collected with this version, otherwise the phase-4
comparison no longer has a valid basis.

numpy is deliberately not used. Two reasons: the dependencies on the Raspberry
Pi stay minimal, and the baseline reflects pure Python rather than the
optimised BLAS behind numpy -- which would mix two different optimisations into
the same measurement.

Threshold decisions
-------------------
The default threshold is NOT a validated security value. It is a starting
point. It must be calibrated in phase 3 on real data, reporting the false
rejection rate and the false acceptance rate, and the chosen value must be
documented in the thesis. An uncalibrated threshold on a system that decides
who counts as an intruder is a vulnerability, not a configuration detail.
"""

from __future__ import annotations

import math
import os
from typing import Any, Iterable, Optional

MATCH_THRESHOLD_ENV = "ACCESS_CONTROL_MATCH_THRESHOLD"
DEFAULT_MATCH_THRESHOLD = 0.5


def get_match_threshold() -> float:
    """The minimum similarity for two faces to be considered the same person."""
    configured = os.getenv(MATCH_THRESHOLD_ENV)
    if not configured:
        return DEFAULT_MATCH_THRESHOLD
    try:
        value = float(configured)
    except ValueError:
        return DEFAULT_MATCH_THRESHOLD
    # Cosine similarity lies in [-1, 1]; a threshold outside that range would
    # mean either "nobody is ever recognised" or "everybody is".
    return max(-1.0, min(value, 1.0))


def cosine_similarity(first: list[float], second: list[float]) -> float:
    """Cosine similarity between two vectors of the same length.

    The formula: the dot product divided by the product of the Euclidean
    norms. The result is 1 for vectors pointing the same way and 0 for
    perpendicular vectors.

    Raises ``ValueError`` on differing lengths: comparing vectors produced by
    different models would yield a meaningless number, and a meaningless
    number that clears the threshold marks a stranger as a known person.
    """
    if len(first) != len(second):
        raise ValueError(f"Incompatible dimensions: {len(first)} vs {len(second)}.")

    dot_product = 0.0
    first_norm = 0.0
    second_norm = 0.0
    # One pass for all three sums: the "readable" variant with three separate
    # comprehensions walks the vector three times, and at 24/7 on a
    # Cortex-A72 that difference shows up in the profile.
    for left, right in zip(first, second):
        dot_product += left * right
        first_norm += left * left
        second_norm += right * right

    if first_norm == 0.0 or second_norm == 0.0:
        # A zero vector has no direction, so it cannot be "similar" to
        # anything.
        return 0.0

    return dot_product / (math.sqrt(first_norm) * math.sqrt(second_norm))


def find_best_match(
    probe: list[float],
    candidates: Iterable[dict[str, Any]],
) -> tuple[Optional[dict[str, Any]], float]:
    """The closest candidate from the known-persons list, and its score.

    ``candidates`` are person dictionaries that have a non-empty
    ``embedding``. Returns ``(None, 0.0)`` when there is no comparable
    candidate.

    Candidates with an incompatible length are IGNORED rather than treated as
    an error: the list may temporarily hold vectors produced by an earlier
    version of the model, and raising would stall the whole recognition loop
    over a single stale row. Ignoring them means that person is not
    recognised, which under decision D3 produces an intruder ALERT -- a false
    alarm rather than silence. That is the safe direction for a surveillance
    system: a spurious notification is inspected and dismissed, whereas a
    missed intruder is never noticed at all.
    """
    best_candidate: Optional[dict[str, Any]] = None
    best_score = 0.0

    for candidate in candidates:
        embedding = candidate.get("embedding")
        if not embedding:
            continue
        try:
            score = cosine_similarity(probe, embedding)
        except ValueError:
            continue
        if score > best_score:
            best_candidate = candidate
            best_score = score

    return best_candidate, best_score
