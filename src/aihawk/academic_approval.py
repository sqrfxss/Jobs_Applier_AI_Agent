"""Explicit, one-use approval for a specific reviewed academic application.

This is a reusable gate for future academic adapters, not a blanket approval
to existing browser tools. The adapter must call consume() immediately before
submission and must enforce browser action restrictions separately.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class ApplicationPreview:
    opportunity_url: str
    applicant_id: str
    fields: tuple[tuple[str, str], ...]
    attachment_hashes: tuple[str, ...] = ()

    def fingerprint(self) -> str:
        payload = {
            "opportunity_url": self.opportunity_url,
            "applicant_id": self.applicant_id,
            "fields": sorted(self.fields),
            "attachment_hashes": sorted(self.attachment_hashes),
        }
        data = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(data.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Approval:
    fingerprint: str
    reviewer: str
    approved_at: datetime


class ApprovalGate:
    """In-memory one-time gate: no approval is created by the AI/model itself."""

    def __init__(self) -> None:
        self._approved: dict[str, Approval] = {}

    def approve(self, preview: ApplicationPreview, *, reviewer: str, now: datetime) -> Approval:
        if not reviewer.strip() or now.tzinfo is None:
            raise ValueError("Named reviewer and timezone-aware approval time are required.")
        approval = Approval(preview.fingerprint(), reviewer.strip(), now.astimezone(timezone.utc))
        self._approved[approval.fingerprint] = approval
        return approval

    def consume(self, preview: ApplicationPreview, *, reviewer: str) -> Approval:
        fingerprint = preview.fingerprint()
        approval = self._approved.get(fingerprint)
        if approval is None or approval.reviewer != reviewer:
            raise PermissionError("An explicit approval for this exact application is required.")
        del self._approved[fingerprint]
        return approval
