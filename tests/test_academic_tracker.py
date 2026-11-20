"""Local database, duplicate-submission and evidence-isolation tests."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from aihawk.academic_approval import ApplicationPreview
from aihawk.academic_tracker import (
    DuplicateApplicationError,
    LocalApplicationRegistry,
    application_reference,
)

NOW = datetime(2026, 11, 20, tzinfo=UTC)


def preview(value="MSc"):
    return ApplicationPreview(
        "https://admissions.uni.example.edu/apply?session=private",
        "private-person-id", (("programme", value), ("email", "private@invalid.test")),
    )


def record(db, value="MSc"):
    return db.record_prepared(
        preview(value), title="Human Movement Studies",
        hosts=("uni.example.edu",), now=NOW,
    )


def test_prepared_is_persistent_and_redacted(tmp_path):
    dbpath = tmp_path / "private" / "records.sqlite"
    with LocalApplicationRegistry(dbpath) as db:
        a = record(db)
        assert a.state == "prepared"
        assert a.institutional_host == "admissions.uni.example.edu"
        ref = a.reference
    with LocalApplicationRegistry(dbpath) as db:
        assert db.state_for(ref).state == "prepared"
        assert len(db.audit(ref)) == 1
    stored = dbpath.read_bytes()
    assert b"private-person-id" not in stored
    assert b"private@invalid.test" not in stored
    assert b"session=private" not in stored


def test_human_attestation_required(tmp_path):
    with LocalApplicationRegistry(tmp_path / "records.sqlite") as db:
        record(db)
        with pytest.raises(PermissionError):
            db.record_manual_submission(preview(), title="Human Movement Studies", now=NOW, human_attested=False)


def test_cannot_report_submission_twice(tmp_path):
    with LocalApplicationRegistry(tmp_path / "records.sqlite") as db:
        first = record(db)
        sent = db.record_manual_submission(preview(), title="Human Movement Studies", now=NOW, human_attested=True)
        assert sent.state == "reported_submitted"
        with pytest.raises(DuplicateApplicationError):
            db.record_manual_submission(preview(), title="Human Movement Studies", now=NOW, human_attested=True)
        with pytest.raises(DuplicateApplicationError):
            record(db)
        assert len(db.audit(first.reference)) == 2


def test_edit_invalidates_prepared_fingerprint(tmp_path):
    with LocalApplicationRegistry(tmp_path / "records.sqlite") as db:
        record(db)
        with pytest.raises(PermissionError, match="changed"):
            db.record_manual_submission(preview("PhD"), title="Human Movement Studies", now=NOW, human_attested=True)


def test_evidence_is_hashed_not_retained(tmp_path):
    proof = tmp_path / "receipt.txt"
    proof.write_text("private confirmation number ABC", encoding="utf-8")
    with LocalApplicationRegistry(tmp_path / "records.sqlite") as db:
        item = record(db)
        outcome = db.record_manual_submission(
            preview(), title="Human Movement Studies", now=NOW, human_attested=True,
            proof_path=proof, private_root=tmp_path,
        )
        assert outcome.state == "proof_attached"
        events = db.audit(item.reference)
        assert len(events[-1][-1]) == 64
    assert b"ABC" not in (tmp_path / "records.sqlite").read_bytes()


def test_disallow_external_evidence_file(tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_bytes(b"test")
    private = tmp_path / "private"
    private.mkdir()
    with LocalApplicationRegistry(private / "records.sqlite") as db:
        record(db)
        with pytest.raises(ValueError, match="private"):
            db.record_manual_submission(
                preview(), title="Human Movement Studies", now=NOW, human_attested=True,
                proof_path=outside, private_root=private,
            )


def test_reference_ignores_private_url_query_and_form_edits():
    a = application_reference(preview(), "Human Movement Studies")
    b = application_reference(preview("PhD"), "Human Movement Studies")
    assert a == b
