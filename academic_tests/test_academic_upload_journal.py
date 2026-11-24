"""Crash-safe upload journal: atomic state, stale lock refusal and no secret storage."""

from __future__ import annotations

import json
import subprocess
import sys

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
    assert journal.lock_path.exists()  # stable inode prevents Unix lock-file split brain
    assert UploadJournal(tmp_path, FP).last_status("proof.pdf") == "uploaded"


def test_prevents_parallel_upload_attempts(tmp_path):
    first = UploadJournal(tmp_path, FP)
    second = UploadJournal(tmp_path, FP)
    with first, pytest.raises(PortalPreparationError, match="Another upload"), second:
        pass
    with second:
        second.record("proof.pdf", "unverified")


def test_rejects_unreviewed_status(tmp_path):
    with UploadJournal(tmp_path, FP) as journal, pytest.raises(PortalPreparationError, match="Invalid"):
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


def test_lock_is_released_after_abrupt_process_exit(tmp_path):
    # A genuine crashed process cannot execute UploadJournal.__exit__.
    # OS locks must be released without someone manually deleting lock files.
    code = (
        "import os,sys\n"
        "from pathlib import Path\n"
        "from aihawk.academic_upload_journal import UploadJournal\n"
        "with UploadJournal(Path(sys.argv[1]), 'a'*64) as journal:\n"
        "    journal.record('proof.pdf', 'attempting')\n"
        "    os._exit(9)\n"
    )
    run = subprocess.run([sys.executable, "-c", code, str(tmp_path)], check=False)
    assert run.returncode == 9
    with UploadJournal(tmp_path, FP) as recovered:
        assert recovered.last_status("proof.pdf") == "attempting"
        recovered.record("proof.pdf", "unverified")
    assert UploadJournal(tmp_path, FP).last_status("proof.pdf") == "unverified"
