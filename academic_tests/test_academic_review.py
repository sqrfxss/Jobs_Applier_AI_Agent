import json
from datetime import UTC, datetime

import pytest

from aihawk.academic_approval import ApplicationPreview
from aihawk.academic_review import AcademicReview, WorkflowState, export_review

NOW = datetime(2026, 11, 20, tzinfo=UTC)


def sample():
    return ApplicationPreview(
        "https://uni.example.edu/apply",
        "private-candidate-id",
        (("email", "private@example.com"), ("programme", "PhD")),
        ("sha256:1234",),
    )


def test_review_requires_named_person():
    r = AcademicReview(sample())
    with pytest.raises(ValueError):
        r.mark_reviewed(reviewer="", now=NOW)
    r.mark_reviewed(reviewer="owner", now=NOW)
    with pytest.raises(PermissionError):
        r.approve(reviewer="other", now=NOW)


def test_approval_one_use_and_no_automatic_submission():
    r = AcademicReview(sample())
    with pytest.raises(PermissionError):
        r.prepare_manual_submission(reviewer="owner", now=NOW)
    r.mark_reviewed(reviewer="owner", now=NOW)
    r.approve(reviewer="owner", now=NOW)
    r.prepare_manual_submission(reviewer="owner", now=NOW)
    assert r.state is WorkflowState.AWAITING_MANUAL_SUBMISSION
    assert r.export_redacted()["submission_enabled"] is False
    with pytest.raises(PermissionError):
        r.prepare_manual_submission(reviewer="owner", now=NOW)


def test_edit_invalidates_approval():
    r = AcademicReview(sample())
    r.mark_reviewed(reviewer="owner", now=NOW)
    r.approve(reviewer="owner", now=NOW)
    p = ApplicationPreview("https://uni.example.edu/apply", "private-candidate-id", (("programme", "MSc"),))
    r.replace_application(p, now=NOW)
    assert r.state is WorkflowState.DRAFT
    with pytest.raises(PermissionError):
        r.prepare_manual_submission(reviewer="owner", now=NOW)


def test_audit_is_redacted(tmp_path):
    r = AcademicReview(sample())
    r.mark_reviewed(reviewer="owner", now=NOW)
    target = tmp_path / "audit.json"
    export_review(r, target)
    text = target.read_text(encoding="utf-8")
    assert "private@example.com" not in text
    assert "private-candidate-id" not in text
    assert json.loads(text)["schema"] == "aihawk.academic.review.v1"
