import json
import hashlib
from datetime import date
from aihawk.academic_execution import evaluate, execute


def test_missing_documents_never_contact_portal(tmp_path):
    c = {
        "schema": "aihawk.execution.v1",
        "official_application_url": "https://example.edu/apply",
        "official_hosts": ["example.edu"],
        "deadline": "2027-01-01",
        "required_roles": ["cv"],
        "documents": {},
    }
    p = tmp_path / "case.json"
    p.write_text(json.dumps(c))
    r = execute(p, run_draft=True, today=date(2026, 11, 24))
    assert r["network_actions"] is False and r["final_submission"] is False
    assert r["result"] == "blocked_preflight"
    assert "document:cv:missing_or_unverified" in r["blockers"]
    assert (tmp_path / "Execution_Report.json").is_file()


def test_integrity_and_terminal_guard(tmp_path):
    (tmp_path / "cv.pdf").write_bytes(b"test")
    c = {
        "schema": "aihawk.execution.v1",
        "official_application_url": "https://example.edu/apply",
        "official_hosts": ["example.edu"],
        "deadline": "2027-01-01",
        "required_roles": ["cv"],
        "documents": {"cv": {"file": "cv.pdf", "sha256": hashlib.sha256(b"test").hexdigest(), "verified": True}},
        "submission_previously_verified": True,
    }
    r = evaluate(c, tmp_path, date(2026, 11, 24))
    assert r["verified_documents"] == ["cv"] and "already_submitted" in r["blockers"]
    (tmp_path / "cv.pdf").write_bytes(b"changed")
    assert "document:cv:changed" in evaluate(c, tmp_path, date(2026, 11, 24))["blockers"]
