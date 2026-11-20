import hashlib
import json
from datetime import datetime, timezone

import pytest

from aihawk.academic_ops import application_from_manifest, evidence_capture, main
from aihawk.official_fetch import PageSnapshot


def manifest():
    return {
        "title": "Example MSc application",
        "official_application_url": "https://admissions.uni.example.edu/form",
        "official_hosts": ["uni.example.edu"],
        "applicant_id": "local-candidate",
        "fields": {"first_name": "A", "programme": "MSc"},
        "attachments": ["cv.pdf"],
        "source_urls": ["https://uni.example.edu/requirements"],
    }


def test_attachment_hash_derived_from_file_contents(tmp_path):
    (tmp_path / "cv.pdf").write_bytes(b"my actual CV file")
    preview, title, hosts, sources = application_from_manifest(manifest(), manifest_dir=tmp_path)
    assert preview.attachment_hashes == ("sha256:" + hashlib.sha256(b"my actual CV file").hexdigest(),)
    assert preview.opportunity_url.endswith("/form")


def test_missing_attachment_refused(tmp_path):
    with pytest.raises(ValueError, match="Attachment"):
        application_from_manifest(manifest(), manifest_dir=tmp_path)


def test_preview_command(tmp_path):
    (tmp_path / "cv.pdf").write_bytes(b"private CV bytes")
    m, out = tmp_path / "manifest.json", tmp_path / "review.html"
    m.write_text(json.dumps(manifest()), encoding="utf-8")
    assert main(["preview", str(m), str(out)]) == 0
    rendered = out.read_text(encoding="utf-8")
    assert "nothing has been submitted" in rendered
    assert "private CV bytes" not in rendered


def test_capture_requires_real_matching_phrase(monkeypatch):
    import aihawk.academic_ops as ops
    page = PageSnapshot(
        "https://uni.example.edu/req", "https://uni.example.edu/req",
        datetime(2026, 11, 20, tzinfo=timezone.utc), "0" * 64,
        "text/html", "TOEFL Home Edition is accepted here."
    )
    monkeypatch.setattr(ops, "fetch_official_page", lambda *a, **kw: page)
    evidence = evidence_capture(
        "https://uni.example.edu/req", official_hosts=("uni.example.edu",),
        exact_phrase="TOEFL Home Edition", requirement="accepted_language_tests",
    )
    assert evidence["exact_phrase_found"] is True
    assert evidence["interpretation_reviewed"] is False


def test_evidence_unmatched_phrase_fails(monkeypatch):
    import aihawk.academic_ops as ops
    page = PageSnapshot("a", "b", datetime.now(timezone.utc), "0" * 64, "text/html", "IELTS only.")
    monkeypatch.setattr(ops, "fetch_official_page", lambda *a, **kw: page)
    with pytest.raises(ValueError):
        evidence_capture("https://uni.example.edu", official_hosts=("uni.example.edu",),
            exact_phrase="TOEFL", requirement="accepted_language_tests")
