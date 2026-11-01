"""Schemas for the ``cameras`` entity."""

import re
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

CameraKind = Literal["USB", "CSI", "RTSP"]

# `camera_id` ends up in `allowed_cameras`, in URLs and in the audit journal.
# The format is deliberately restricted to unambiguous characters: an
# identifier containing spaces or diacritics could be written in several ways
# for the same camera, and the permission comparison would fail silently.
CAMERA_ID_PATTERN = re.compile(r"^[a-z0-9_]{2,40}$")


def _validate_camera_id(value: str) -> str:
    if not CAMERA_ID_PATTERN.match(value):
        raise ValueError(
            "camera_id may contain only lowercase letters, digits and "
            "underscores (2 to 40 characters), for example 'cam_entrance'."
        )
    return value


class CameraCreate(BaseModel):
    """Data required to register a camera.

    ``hub_id`` is not accepted from the client: it comes from the
    administrator's token.

    ``source`` is how the stream is reached and depends on ``kind``: the
    device index for USB ("0"), the port for CSI, or the full URL for RTSP. It
    stays free text because the only real validation is trying to open the
    stream, which happens in phase 3.
    """

    camera_id: str = Field(description="Identifier within the hub, e.g. 'cam_entrance'")
    name: str = Field(min_length=1, max_length=120)
    kind: CameraKind = "USB"
    source: Optional[str] = Field(default=None, max_length=500)
    enabled: bool = True

    _check_camera_id = field_validator("camera_id")(_validate_camera_id)


class CameraUpdate(BaseModel):
    """Partial update.

    ``camera_id`` is deliberately absent: renaming it would silently
    invalidate every reference in ``allowed_cameras`` and in journal rows
    already written. A camera is "renamed" by changing ``name``, which is only
    the displayed label.
    """

    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    kind: Optional[CameraKind] = None
    source: Optional[str] = Field(default=None, max_length=500)
    enabled: Optional[bool] = None


class CameraPublic(BaseModel):
    hub_id: str
    camera_id: str
    name: str
    kind: CameraKind
    source: Optional[str] = None
    enabled: bool
    created_at: Optional[str] = None
