"""Queue-to-letter automation: synthetic CV/source; no applicant information or API calls."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from aihawk.academic_motivation import MotivationError
from aihawk.academic_motivation_auto import _official_excerpt, prepare_position, process_queue
from aihawk.official_fetch import PageSnapshot


def queue(tmp_path: Path) -> Path:
    (tmp_path / "synthetic.pdf").write_bytes(b"%PDF-1.4 dummy synthetic test")
    spec = {
        "applicant_name": "Example Researcher",
        "cv_file": "synthetic.pdf",
        "positions": [
            {
                "institution": "University A",
                "programme": "Biomechanical Signal Processing",
                "degree": "PhD",
                "official_url": "https://a.example.edu/doctoral",
                "official_hosts": ["a.example.edu"],
            },
            {
                "institution": "University B",
                "programme": "Medical Data Analysis",
                "degree": "MSc",
                "official_url": "https://b.example.edu/masters",
                "official_hosts": ["b.example.edu"],
            },
        ],
    }
    p = tmp_path / "private-queue.json"
    p.write_text(json.dumps(spec), encoding="utf-8")
    return p


def official(url, *, official_hosts):
    assert official_hosts == [url.split("/")[2]] or tuple(official_hosts) == (url.split("/")[2],)
    text = (
        "The doctoral research programme supports work on biological and medical "
        "measurement systems and computational signal processing. Researchers "
        "develop predictive models while examining the limitations of complex "
        "observations, experimental variability and generalisation. Applicants "
        "undertake original research with interdisciplinary supervision and "
        "training in scientific methodology."
    )
    return PageSnapshot(url, url, datetime(2026, 11, 21, tzinfo=UTC), "a" * 64, "text/html", text)


def test_official_excerpt_is_bounded():
    snap = official("https://a.example.edu/doctoral", official_hosts=("a.example.edu",))
    out = _official_excerpt(snap, "Biomedical Signal Processing")
    assert "computational signal processing" in out
    assert len(out) < 1800


def test_queue_generates_individual_directories_without_submitting(tmp_path, monkeypatch):
    import aihawk.academic_document_gate as gate

    monkeypatch.setattr(gate, "require_writing_preflight", lambda path: path)
    import aihawk.academic_motivation_auto as auto

    monkeypatch.setattr(
        auto,
        "_cv_facts",
        lambda path: [
            "MSc in Sports Biomechanics with experimental signal processing",
            "Research Programmer using MATLAB and Python",
        ],
    )
    produced = []

    def mock_deliver(brief, output, **kwargs):
        obj = json.loads(brief.read_text(encoding="utf-8"))
        produced.append((obj["institution"], obj["programme"]))
        output.write_bytes(b"synthetic DOCX - test only")
        return output

    monkeypatch.setattr(auto, "deliver", mock_deliver)
    p = queue(tmp_path)
    result = process_queue(p, fetcher=official)
    assert result["university_submission"] is False
    assert result["human_review_required"] is True
    assert [r["status"] for r in result["results"]] == ["drafted_review_required"] * 2
    assert produced == [
        ("University A", "Biomechanical Signal Processing"),
        ("University B", "Medical Data Analysis"),
    ]
    assert result["results"][0]["path"] != result["results"][1]["path"]
    assert Path(result["results"][0]["path"]).parent != Path(result["results"][1]["path"]).parent
    assert Path(result["results"][0]["path"]).exists()
    again = process_queue(p, fetcher=official)
    assert [r["status"] for r in again["results"]] == ["already_drafted_review_required"] * 2
    assert produced == [
        ("University A", "Biomechanical Signal Processing"),
        ("University B", "Medical Data Analysis"),
    ]


def test_failed_official_evidence_does_not_generate_generic_letter(tmp_path, monkeypatch):
    import aihawk.academic_motivation_auto as auto

    monkeypatch.setattr(auto, "_cv_facts", lambda path: ["MSc biomechanics", "Research programmer"])
    invoked = []
    monkeypatch.setattr(auto, "deliver", lambda *a, **kw: invoked.append(a))
    p = queue(tmp_path)

    def bad_source(url, *, official_hosts):
        raise RuntimeError("Official page unavailable")

    result = process_queue(p, fetcher=bad_source)
    assert all(row["status"] == "error" for row in result["results"])
    assert not invoked


def test_position_fails_closed_on_unsupported_cv_reference(tmp_path):
    p = queue(tmp_path)
    data = json.loads(p.read_text())
    data["cv_file"] = "../another-person.pdf"
    p.write_text(json.dumps(data))
    with pytest.raises(MotivationError, match="inside"):
        process_queue(p, fetcher=official)


def test_prior_reviewed_brief_never_silently_overwritten(tmp_path, monkeypatch):
    import aihawk.academic_motivation_auto as auto

    monkeypatch.setattr(auto, "_cv_facts", lambda path: ["Degree", "Research"])
    p = queue(tmp_path)
    spec = json.loads(p.read_text())["positions"][0]
    _, letter_path = prepare_position(tmp_path, "Example Researcher", tmp_path / "synthetic.pdf", spec, fetcher=official)
    old = letter_path.parent / "position-brief.json"
    content = json.loads(old.read_text())
    content["applicant_facts"] = ["Human-reviewed claim"]
    old.write_text(json.dumps(content))
    with pytest.raises(MotivationError, match="Review the prior"):
        prepare_position(tmp_path, "Example Researcher", tmp_path / "synthetic.pdf", spec, fetcher=official)


def test_cli_batch_handles_partial_errors_without_claiming_success(tmp_path, monkeypatch):
    import aihawk.academic_motivation_auto as auto
    from aihawk.academic_ops import main

    monkeypatch.setattr(
        auto,
        "process_queue",
        lambda *a, **kw: {
            "results": [{"status": "error"}, {"status": "drafted_review_required"}],
        },
    )
    assert main(["motivation-auto", str(tmp_path / "queue.json"), "--model", "test-model"]) == 1


def test_pdf_only_position_exports_verified_format_without_rewriting_docx(tmp_path, monkeypatch):
    import aihawk.academic_document_gate as gate

    monkeypatch.setattr(gate, "require_writing_preflight", lambda path: path)
    import aihawk.academic_motivation_auto as auto
    import aihawk.academic_motivation_pdf as pdfmod

    monkeypatch.setattr(
        auto,
        "_cv_facts",
        lambda path: [
            "MSc in sports biomechanics with measurement models",
            "MATLAB and Python research programming",
        ],
    )
    source = queue(tmp_path)
    values = json.loads(source.read_text(encoding="utf-8"))
    values["positions"] = [values["positions"][0]]
    values["positions"][0]["portal_allowed_extensions"] = ["pdf", "doc", "txt"]
    source.write_text(json.dumps(values), encoding="utf-8")
    drafts = []
    exports = []

    def fake_deliver(brief, output, **kwargs):
        drafts.append(output)
        output.write_bytes(b"test DOCX stand-in")
        return output

    def fake_export(docx, pdf, *, expected_name, expected_institution):
        exports.append((docx, pdf, expected_name, expected_institution))
        pdf.write_bytes(b"%PDF-1.4 verified fake")
        return pdf

    monkeypatch.setattr(auto, "deliver", fake_deliver)
    monkeypatch.setattr(pdfmod, "export_letter_pdf", fake_export)
    first = process_queue(source, fetcher=official)
    assert first["results"][0]["status"] == "drafted_review_required"
    assert first["results"][0]["path"].endswith(".pdf")
    assert len(drafts) == 1
    assert len(exports) == 1
    assert drafts[0].exists()
    assert exports[0][2:] == ("Example Researcher", "University A")
    second = process_queue(source, fetcher=official)
    assert second["results"][0]["status"] == "already_drafted_review_required"
    assert len(drafts) == len(exports) == 1


def test_pdf_only_batch_recovers_from_existing_docx_without_rewriting(tmp_path, monkeypatch):
    import aihawk.academic_document_gate as gate

    monkeypatch.setattr(gate, "require_writing_preflight", lambda path: path)
    import aihawk.academic_motivation_auto as auto
    import aihawk.academic_motivation_pdf as pdfmod

    monkeypatch.setattr(
        auto,
        "_cv_facts",
        lambda path: [
            "MSc scientific computing",
            "Doctoral research in medical imaging",
        ],
    )
    q = queue(tmp_path)
    data = json.loads(q.read_text(encoding="utf-8"))
    data["positions"] = [data["positions"][0]]
    data["positions"][0]["portal_allowed_extensions"] = [".pdf"]
    q.write_text(json.dumps(data), encoding="utf-8")
    _, word = prepare_position(
        tmp_path,
        "Example Researcher",
        tmp_path / "synthetic.pdf",
        data["positions"][0],
        fetcher=official,
    )
    word.write_bytes(b"previously approved document")
    monkeypatch.setattr(auto, "deliver", lambda *a, **kw: pytest.fail("Should never regenerate existing Word"))
    monkeypatch.setattr(
        pdfmod,
        "export_letter_pdf",
        lambda docx, out, **kw: out.write_bytes(b"%PDF-1.4 synthetic approved"),
    )
    outcome = process_queue(q, fetcher=official)
    assert outcome["results"][0]["status"] == "pdf_exported_review_required"
    assert word.read_bytes() == b"previously approved document"


@pytest.mark.parametrize("allowed", [[], ["exe"], ["pdf;exe"], ["../pdf"], ["docx", 42]])
def test_unsupported_or_malformed_portal_formats_rejected_before_writing(tmp_path, monkeypatch, allowed):
    import aihawk.academic_motivation_auto as auto

    monkeypatch.setattr(auto, "_cv_facts", lambda path: ["Research programmer", "Thesis in biomechanics"])
    monkeypatch.setattr(auto, "deliver", lambda *a, **kw: pytest.fail("Do not draft for unsupported upload rules"))
    q = queue(tmp_path)
    data = json.loads(q.read_text())
    data["positions"] = [data["positions"][0]]
    data["positions"][0]["portal_allowed_extensions"] = allowed
    q.write_text(json.dumps(data))
    result = process_queue(q, fetcher=official)
    assert result["results"][0]["status"] == "error"
