"""Queue-to-letter automation: synthetic CV/source; no applicant information or API calls."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

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
    import aihawk.academic_motivation_auto as auto
    monkeypatch.setattr(auto, "_cv_facts", lambda path: [
        "MSc in Sports Biomechanics with experimental signal processing",
        "Research Programmer using MATLAB and Python",
    ])
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
    _, letter_path = prepare_position(tmp_path, "Example Researcher", tmp_path/"synthetic.pdf", spec, fetcher=official)
    old = letter_path.parent / "position-brief.json"
    content = json.loads(old.read_text())
    content["applicant_facts"] = ["Human-reviewed claim"]
    old.write_text(json.dumps(content))
    with pytest.raises(MotivationError, match="Review the prior"):
        prepare_position(tmp_path, "Example Researcher", tmp_path/"synthetic.pdf", spec, fetcher=official)


def test_cli_batch_handles_partial_errors_without_claiming_success(tmp_path, monkeypatch):
    import aihawk.academic_motivation_auto as auto
    from aihawk.academic_ops import main
    monkeypatch.setattr(auto, "process_queue", lambda *a, **kw: {
        "results": [{"status": "error"}, {"status": "drafted_review_required"}],
    })
    assert main(["motivation-batch", str(tmp_path/"queue.json"), "--model", "test-model"]) == 1
