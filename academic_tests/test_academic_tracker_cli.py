"""Record operator-reported statuses through the public CLI, without network."""
from __future__ import annotations

import json

from aihawk.academic_ops import main
from aihawk.academic_tracker import LocalApplicationRegistry


def create_manifest(tmp_path):
    (tmp_path / "cv.pdf").write_bytes(b"test document")
    manifest = {
        "title": "Example Test MSc",
        "official_application_url": "https://admissions.uni.example.edu/apply",
        "official_hosts": ["uni.example.edu"],
        "applicant_id": "test-only",
        "fields": {"programme": "MSc"},
        "attachments": ["cv.pdf"],
    }
    path = tmp_path / "application.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def test_track_prepared_and_status(tmp_path, capsys):
    manifest = create_manifest(tmp_path)
    assert main(["track-prepared", str(manifest)]) == 0
    assert main(["track-status", str(manifest)]) == 0
    assert "Local status: prepared" in capsys.readouterr().out
    with LocalApplicationRegistry(tmp_path / "academic-private.sqlite") as registry:
        assert registry.db.execute("SELECT count(*) FROM applications").fetchone()[0] == 1


def test_track_submission_is_noninteractive_by_default(tmp_path, monkeypatch):
    manifest = create_manifest(tmp_path)
    assert main(["track-prepared", str(manifest)]) == 0
    import sys

    monkeypatch.setattr(sys, "stdin", type("BlockedTerminal", (), {"isatty": lambda self: False})())
    try:
        main(["track-submitted", str(manifest)])
    except PermissionError as error:
        assert "human terminal" in str(error)
    else:
        raise AssertionError("Expected submission reporting to require a real terminal.")
