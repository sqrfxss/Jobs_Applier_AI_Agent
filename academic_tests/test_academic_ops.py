import hashlib
import json
from datetime import UTC, datetime

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
    preview, _, _, _ = application_from_manifest(manifest(), manifest_dir=tmp_path)
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
        "https://uni.example.edu/req",
        "https://uni.example.edu/req",
        datetime(2026, 11, 20, tzinfo=UTC),
        "0" * 64,
        "text/html",
        "TOEFL Home Edition is accepted here.",
    )
    monkeypatch.setattr(ops, "fetch_official_page", lambda *a, **kw: page)
    evidence = evidence_capture(
        "https://uni.example.edu/req",
        official_hosts=("uni.example.edu",),
        exact_phrase="TOEFL Home Edition",
        requirement="accepted_language_tests",
    )
    assert evidence["exact_phrase_found"] is True
    assert evidence["interpretation_reviewed"] is False


def test_evidence_unmatched_phrase_fails(monkeypatch):
    import aihawk.academic_ops as ops

    page = PageSnapshot("a", "b", datetime.now(UTC), "0" * 64, "text/html", "IELTS only.")
    monkeypatch.setattr(ops, "fetch_official_page", lambda *a, **kw: page)
    with pytest.raises(ValueError):
        evidence_capture("https://uni.example.edu", official_hosts=("uni.example.edu",), exact_phrase="TOEFL", requirement="accepted_language_tests")


def test_attachment_cannot_escape_manifest_directory(tmp_path):
    payload = manifest()
    payload["attachments"] = ["../private.txt"]
    with pytest.raises(ValueError, match="inside the private"):
        application_from_manifest(payload, manifest_dir=tmp_path)


def test_preview_displays_exact_mappings_and_digest(tmp_path):
    payload = manifest()
    payload["portal_bindings"] = [
        {"field": "first_name", "selector": "input[name='first_name']", "kind": "text"},
        {"field": "cv.pdf", "selector": "input[type='file']", "kind": "upload"},
    ]
    (tmp_path / "cv.pdf").write_bytes(b"test CV")
    original = tmp_path / "manifest.json"
    destination = tmp_path / "review.html"
    original.write_text(json.dumps(payload), encoding="utf-8")
    assert main(["preview", str(original), str(destination)]) == 0
    markup = destination.read_text(encoding="utf-8")
    assert "Exact browser field mapping" in markup
    assert "input[name=&#x27;first_name&#x27;]" in markup
    assert "Preparation fingerprint" in markup
    assert "nothing has been submitted" in markup


@pytest.mark.parametrize("action", ["autofill", "autofill-stages", "inspect"])
def test_cli_passes_private_persistent_profile_option(monkeypatch, tmp_path, action):
    import aihawk.academic_browser as browser
    import aihawk.academic_inspect as inspector
    import aihawk.academic_stages as stages

    calls = []
    monkeypatch.setattr(browser, "run_interactive", lambda *a, **kw: calls.append(("autofill", kw)) or 0)
    monkeypatch.setattr(stages, "run_interactive_journey", lambda *a, **kw: calls.append(("autofill-stages", kw)) or 0)
    monkeypatch.setattr(inspector, "run_interactive_inspection", lambda *a, **kw: calls.append(("inspect", kw)) or 0)

    args = [action, str(tmp_path / "private.json")]
    if action == "inspect":
        args.append(str(tmp_path / "inventory.json"))
    args.append("--persistent")
    assert main(args) == 0
    assert calls == [(action, {"persistent": True})]


def test_redacted_snapshot_cli_does_not_open_browser(tmp_path):
    snapshot = tmp_path / "snapshot.txt"
    destination = tmp_path / "historical-status.json"
    snapshot.write_text(
        "Verified host: admissions.uni.example.edu\n001|Text|Email|\n002|Edit|Email *|[BLANK]\n",
        encoding="utf-8",
    )
    assert (
        main(
            [
                "audit-snapshot",
                str(snapshot),
                str(destination),
                "--host",
                "admissions.uni.example.edu",
            ]
        )
        == 0
    )
    data = json.loads(destination.read_text(encoding="utf-8"))
    assert data["live_portal_verified"] is False
    assert data["counts"]["required_blank"] == 1
    assert data["submission_ready"] is False


def test_motivation_letter_pdf_flag_uses_reviewed_applicant_and_institution(tmp_path, monkeypatch):
    import aihawk.academic_motivation as motivation
    import aihawk.academic_motivation_pdf as pdf_module

    brief = tmp_path / "position.json"
    brief.write_text("{}", encoding="utf-8")
    docx = tmp_path / "letter.docx"
    docx.write_bytes(b"synthetic review source")
    observed = []

    def deliver_fake(*args, **kwargs):
        observed.append(("draft", args[0], args[1]))
        return docx

    def export_fake(source, destination, *, expected_name, expected_institution):
        observed.append(("pdf", source, destination, expected_name, expected_institution))
        destination.write_bytes(b"%PDF-1.4 fake")
        return destination

    monkeypatch.setattr(motivation, "deliver", deliver_fake)
    monkeypatch.setattr(
        motivation,
        "load_brief",
        lambda path: type(
            "Brief",
            (),
            {
                "applicant_name": "Example Person",
                "institution": "Example University",
            },
        )(),
    )
    monkeypatch.setattr(pdf_module, "export_letter_pdf", export_fake)
    assert main(["motivation-letter", str(brief), str(docx), "--pdf"]) == 0
    assert observed[0][0] == "draft"
    assert observed[1] == (
        "pdf",
        docx,
        docx.with_suffix(".pdf"),
        "Example Person",
        "Example University",
    )
    assert docx.with_suffix(".pdf").exists()


def test_motivation_letter_does_not_export_pdf_without_explicit_flag(tmp_path, monkeypatch):
    import aihawk.academic_motivation as motivation
    import aihawk.academic_motivation_pdf as pdf_module

    docx = tmp_path / "letter.docx"
    monkeypatch.setattr(motivation, "deliver", lambda *a, **kw: docx)
    monkeypatch.setattr(pdf_module, "export_letter_pdf", lambda *a, **kw: pytest.fail("Unexpected PDF export"))
    assert main(["motivation-letter", str(tmp_path / "position.json"), str(docx)]) == 0
