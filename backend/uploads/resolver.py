"""Decides whether an identifier names an uploaded project or a Maximo RFQ.

The analysis endpoints take one path identifier. Rather than duplicate
every route for uploads, the identifier is looked up here first: a hit
in the upload store means an uploaded project, a miss means Maximo. An
uploaded project's id is therefore used wherever an RFQNUM would be,
including as the key for the correction, disqualification and
partial-bid overlay tables, so analyst entries work the same way on both
kinds of project.
"""

from __future__ import annotations

from fastapi import HTTPException

from backend.uploads.source import UploadedSource
from backend.uploads.store import get_store


def resolve_source(identifier: str) -> UploadedSource | None:
    """UploadedSource for a confirmed uploaded project, None for a
    Maximo RFQ. Raises if the project exists but is still being edited,
    because a half-reviewed BOQ must not drive an evaluation."""
    boq = get_store().get(identifier)
    if boq is None:
        return None
    if not boq.confirmed:
        raise HTTPException(
            status_code=409,
            detail="This uploaded BOQ has not been confirmed yet. Review and confirm it first.",
        )
    return UploadedSource(boq)
