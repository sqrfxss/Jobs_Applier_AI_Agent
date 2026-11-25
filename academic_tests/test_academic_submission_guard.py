"""No repeat applications after the applicant reports a completed submission."""

import json

import pytest

from aihawk.academic_browser import PortalPreparationError
from aihawk.academic_session_batch import run_batch
from aihawk.academic_session_controls import apply_plan, save_draft
from aihawk.academic_submission_guard import (
    MARKER,
    record_user_submission,
    require_open_application,
    submission_record,
)


class MustNotTouchBrowser:
    def __getattr__(self, name):
        raise AssertionError("No browser operations allowed for a submitted case")


def make_case(tmp_path):
    (tmp_path / "Execution_Case.json").write_text('{"portal_project_title":"Example"}')
    return tmp_path


def test_user_reported_submission_is_idempotent_and_not_institution_verified(tmp_path):
    case = make_case(tmp_path)
    assert submission_record(case) is None
    require_open_application(case)
    first = record_user_submission(case)
    assert first.name == MARKER
    data = submission_record(case)
    assert data["status"] == "submitted"
    assert data["source"] == "user_reported"
    assert data["university_receipt_verified"] is False
    assert data["resubmission_allowed"] is False
    assert record_user_submission(case) == first
    with pytest.raises(PortalPreparationError, match="already submitted"):
        require_open_application(case)


def test_corrupt_or_ambiguous_marker_blocks_draft(tmp_path):
    case = make_case(tmp_path)
    marker = case / MARKER
    marker.write_text("{malformed")
    with pytest.raises(PortalPreparationError, match="Submission status"):
        require_open_application(case)
    marker.write_text(json.dumps({"schema": "aihawk.application.submission.v1", "status": "maybe"}))
    with pytest.raises(PortalPreparationError, match="Unexpected submission status"):
        require_open_application(case)


def test_submitted_case_blocks_every_mutating_path_before_dom_or_upload(tmp_path):
    case = make_case(tmp_path)
    record_user_submission(case)
    page = MustNotTouchBrowser()
    with pytest.raises(PortalPreparationError, match="already submitted"):
        apply_plan(page, case, ("example.edu",), "Example", {})
    with pytest.raises(PortalPreparationError, match="already submitted"):
        save_draft(page, ("example.edu",), "Example", folder=case)
    with pytest.raises(PortalPreparationError, match="already submitted"):
        run_batch(page, case, ("example.edu",), "Example", {})


def test_resuming_submitted_case_does_not_open_a_browser(tmp_path, monkeypatch):
    from aihawk import academic_resume_session

    case = make_case(tmp_path)
    record_user_submission(case)

    def fail(*args, **kwargs):
        raise AssertionError("A submitted application must not open its portal")

    monkeypatch.setattr(academic_resume_session, "read_case", fail)
    academic_resume_session.run(case, auto=True)
    result = json.loads((case / "Agent_Runtime_Status.json").read_text(encoding="utf-8"))
    assert result["status"] == "already_submitted"
    assert result["submission_source"] == "user_reported"
    assert result["final_submission"] is False
