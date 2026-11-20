"""Academic application review session, deliberately separated from AIHawk's job bot.

State transitions: draft -> reviewed -> approved -> consumed. Submissions
cannot be performed here: there is no browser, network or submit method. A
future portal adapter must implement the verified approval boundary itself.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from urllib.parse import urlsplit

from aihawk.academic_approval import ApplicationPreview, ApprovalGate


class WorkflowState(str, Enum):
    DRAFT = "draft"
    REVIEWED = "reviewed"
    APPROVED = "approved"
    AWAITING_MANUAL_SUBMISSION = "awaiting_manual_submission"


@dataclass
class AcademicReview:
    application: ApplicationPreview
    state: WorkflowState = WorkflowState.DRAFT
    reviewer: str = ""
    history: list[dict[str, str]] = field(default_factory=list)
    _gate: ApprovalGate = field(default_factory=ApprovalGate, repr=False)

    def _record(self, action: str, now: datetime) -> None:
        if now.tzinfo is None:
            raise ValueError("Timestamp must be timezone-aware.")
        # No form contents or applicant secrets in audit events.
        self.history.append({
            "time": now.astimezone(timezone.utc).isoformat(),
            "action": action,
            "fingerprint": self.application.fingerprint(),
        })

    def mark_reviewed(self, *, reviewer: str, now: datetime) -> None:
        if self.state is not WorkflowState.DRAFT or not reviewer.strip():
            raise ValueError("Review requires a draft and a named human reviewer.")
        self.reviewer = reviewer.strip()
        self.state = WorkflowState.REVIEWED
        self._record("reviewed", now)

    def approve(self, *, reviewer: str, now: datetime) -> None:
        if self.state is not WorkflowState.REVIEWED or self.reviewer != reviewer:
            raise PermissionError("Only the recorded reviewer can approve reviewed content.")
        self._gate.approve(self.application, reviewer=reviewer, now=now)
        self.state = WorkflowState.APPROVED
        self._record("approved", now)

    def prepare_manual_submission(self, *, reviewer: str, now: datetime) -> None:
        """Consume approval; never send data to an external form."""
        if self.state is not WorkflowState.APPROVED:
            raise PermissionError("Application has not been explicitly approved.")
        self._gate.consume(self.application, reviewer=reviewer)
        self.state = WorkflowState.AWAITING_MANUAL_SUBMISSION
        self._record("approval_consumed_manual_submission_required", now)

    def replace_application(self, new: ApplicationPreview, *, now: datetime) -> None:
        """Any edit resets review and approval, preventing stale authorizations."""
        self.application = new
        self.state = WorkflowState.DRAFT
        self.reviewer = ""
        self._gate = ApprovalGate()
        self._record("draft_changed_review_required", now)

    def export_redacted(self) -> dict:
        return {
            "schema": "aihawk.academic.review.v1",
            "state": self.state.value,
            "fingerprint": self.application.fingerprint(),
            "opportunity_host": urlsplit(self.application.opportunity_url).hostname,
            "history": list(self.history),
            "submission_enabled": False,
        }


def export_review(review: AcademicReview, path: Path) -> None:
    """Write a redacted audit JSON; use an access-controlled destination."""
    path.write_text(json.dumps(review.export_redacted(), indent=2) + "\n", encoding="utf-8")
