import pytest
from aihawk.academic_outreach_workflow import next_actions, archive_and_sync


def message():
    return {
        "id": "abc123",
        "thread_id": "thread1",
        "labels": ["SENT"],
        "to": ["prof@example.edu"],
        "attachments": [{"filename": "CV.pdf", "mime_type": "application/pdf", "size_bytes": 200}],
    }


def test_routes_blockers_in_parallel():
    actions = next_actions(["Supervisor acceptance", "Research plan", "Legalization", "Portal", "TOEFL", "Funding"])
    assert len(actions) == 6


def test_archive_and_sync_idempotent(tmp_path):
    calls = []

    def sync(record):
        calls.append(record["message"]["id"])
        return {"message_id": "abc123", "readback_verified": True}

    assert archive_and_sync(tmp_path, message(), sync)["sync_verified"]
    assert archive_and_sync(tmp_path, message(), sync)["sync_verified"]
    assert calls == ["abc123"]


def test_failed_sync_retries_without_resending(tmp_path):
    def fail(record):
        raise RuntimeError("Unavailable")

    assert not archive_and_sync(tmp_path, message(), fail)["sync_verified"]
    assert archive_and_sync(tmp_path, message(), lambda r: {"message_id": "abc123", "readback_verified": True})["sync_verified"]


def test_reject_unsent(tmp_path):
    m = message()
    m["labels"] = ["DRAFT"]
    with pytest.raises(ValueError):
        archive_and_sync(tmp_path, m, lambda r: {})
    assert not list(tmp_path.iterdir())


def test_reject_missing_cv(tmp_path):
    m = message()
    m["attachments"] = []
    with pytest.raises(ValueError):
        archive_and_sync(tmp_path, m, lambda r: {})
