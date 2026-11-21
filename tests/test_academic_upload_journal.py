"""Crash-safe upload journal: atomic state, stale lock refusal and no secret storage."""
from __future__ import annotations

import json

import pytest

from aihawk.academic_browser import PortalPreparationError
from aihawk.academic_upload_journal import UploadJournal


FP = "a" * 64


def test_journal_is_atomic_and_survives_restart(tmp_path):
    journal = UploadJournal(tmp_path, FP)
    with journal:
        journal.record("proof.pdf", "attempting")
        journal.record("proof.pdf", "uploaded")
        assert journal.last_status("proof.pdf") == "uploaded"
        persisted = json.loads(journal.filename.read_text(encoding="utf-8"))
        assert persisted["plan_fingerprint"] == FP
        assert persisted["records"]["proof.pdf"]["status"] == "uploaded"
        assert "applicant_id" not in persisted
    assert not journal.lock_path.exists()
    assert UploadJournal(tmp_path, FP).last_status("proof.pdf") == "uploaded"


def test_prevents_parallel_upload_attempts(tmp_path):
    first = UploadJournal(tmp_path, FP)
    second = UploadJournal(tmp_path, FP)
    with first:
        with pytest.raises(PortalPreparationError, match="Another upload"):
            with second:
                pass
    with second:
        second.record("proof.pdf", "unverified")


def test_rejects_unreviewed_status(tmp_path):
    with UploadJournal(tmp_path, FP) as journal:
        with pytest.raises(PortalPreparationError, match="Invalid"):
            journal.record("proof.pdf", "submitted")


def test_rejects_writing_without_exclusive_lock(tmp_path):
    journal = UploadJournal(tmp_path, FP)
    with pytest.raises(PortalPreparationError, match="exclusive lock"):
        journal.record("proof.pdf", "uploaded")


def test_rejects_git_checkout_for_private_state(tmp_path):
    (tmp_path / ".git").mkdir()
    with pytest.raises(PortalPreparationError, match="source repository"):
        UploadJournal(tmp_path, FP)


def test_fingerprint_is_scoped_to_each_reviewed_batch(tmp_path):
    with UploadJournal(tmp_path, FP) as journal:
        journal.record("proof.pdf", "attempting")
    other = UploadJournal(tmp_path, "b" * 64)
    assert other.filename != journal.filename
    assert other.last_status("proof.pdf") is None
