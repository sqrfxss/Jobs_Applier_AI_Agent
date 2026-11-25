import json

import pytest

from aihawk.academic_background_queue import _approved_entries, run_approved_queue
from aihawk.academic_browser import PortalPreparationError


def _manifest(root, rel, content):
    dest = root / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(content), encoding="utf-8")


def test_queue_never_runs_unapproved_items_and_skips_submitted(tmp_path, monkeypatch):
    _manifest(tmp_path, "new/app.json", {"portal_bindings": [{"selector": "#name"}]})
    _manifest(tmp_path, "old/app.json", {"submitted": True})
    _manifest(tmp_path, "unapproved/app.json", {"portal_bindings": []})
    q = {
        "schema_version": "aihawk.academic.approved-draft-queue.v1",
        "applications": [
            {"manifest": "new/app.json", "approved_for_draft": True},
            {"manifest": "old/app.json", "approved_for_draft": True},
            {"manifest": "unapproved/app.json", "approved_for_draft": False},
        ],
    }
    (tmp_path / "queue.json").write_text(json.dumps(q), encoding="utf-8")
    calls = []

    def run(file, out):
        calls.append(file)
        return {"result": "server_saved_verified"}

    monkeypatch.setattr("aihawk.academic_background_queue.run_background_draft", run)
    out = run_approved_queue(tmp_path / "queue.json", tmp_path / "status.json")
    assert out["result"] == "queue_draft_work_complete"
    assert len(calls) == 1
    assert calls[0].name == "app.json" and calls[0].parent.name == "new"
    assert [e["state"] for e in out["items"]] == [
        "server_saved_verified",
        "skipped_already_final_submitted",
    ]
    assert out["final_submissions"] == 0
    assert out["emails_sent"] is False
    assert json.loads((tmp_path / "status.json").read_text())["result"] == "queue_draft_work_complete"


def test_queue_unavailable_portal_does_not_abort_other_apps(tmp_path, monkeypatch):
    _manifest(tmp_path, "one.json", {"portal_stages": []})
    _manifest(tmp_path, "two.json", {"portal_bindings": []})
    q = {
        "schema_version": "aihawk.academic.approved-draft-queue.v1",
        "applications": [
            {"manifest": "one.json", "approved_for_draft": True},
            {"manifest": "two.json", "approved_for_draft": True},
        ],
    }
    (tmp_path / "queue.json").write_text(json.dumps(q), encoding="utf-8")
    monkeypatch.setattr("aihawk.academic_background_queue.run_background_journey", lambda *args: (_ for _ in ()).throw(RuntimeError("Portal login expired")))
    monkeypatch.setattr("aihawk.academic_background_queue.run_background_draft", lambda *args: {"result": "server_saved_verified"})
    out = run_approved_queue(tmp_path / "queue.json", tmp_path / "report.json")
    assert out["result"] == "completed_with_review_items"
    assert [x["state"] for x in out["items"]] == ["stopped_needs_review", "server_saved_verified"]


def test_queue_rejects_unreviewed_absolute_path_and_parent_escape(tmp_path):
    for relative in ("../outside.json", "C:\\Windows\\secret.json"):
        queue = {"schema_version": "aihawk.academic.approved-draft-queue.v1", "applications": [{"manifest": relative, "approved_for_draft": True}]}
        with pytest.raises(PortalPreparationError):
            _approved_entries(queue, tmp_path)


def test_queue_rejects_duplicate_and_wrong_schema(tmp_path):
    q = {
        "schema_version": "aihawk.academic.approved-draft-queue.v1",
        "applications": [{"manifest": "a.json", "approved_for_draft": True}, {"manifest": "a.json", "approved_for_draft": True}],
    }
    with pytest.raises(PortalPreparationError):
        _approved_entries(q, tmp_path)
    q["schema_version"] = "unknown"
    with pytest.raises(PortalPreparationError):
        _approved_entries(q, tmp_path)
