"""Batch motivation writing for multiple independent academic positions."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from aihawk.academic_motivation import MotivationError
from aihawk.academic_motivation_batch import batch_from_queue, run_batch


def make_queue(tmp_path, *, duplicate_outputs=False):
    (tmp_path / "resume.pdf").write_bytes(b"%PDF-1.4 synthetic CV")
    for index, university in enumerate(("Example University", "Independent University")):
        brief = {
            "applicant_name": "Example Applicant",
            "institution": university,
            "programme": "Biomedical AI" if index == 0 else "Human Movement Science",
            "degree": "PhD" if index == 0 else "MSc",
            "cv_file": "resume.pdf",
            "official_source_hosts": ["uni.example.edu"],
            "applicant_facts": ["MSc thesis in biomechanical measurements"],
            "programme_evidence": [{
                "url": "https://uni.example.edu/programme",
                "excerpt": "An interdisciplinary degree with supervised research.",
            }],
            "research_fit": ["Independent validation of physiological data"],
            "career_goal": "Reliable biomedical research",
        }
        (tmp_path / f"brief-{index}.json").write_text(json.dumps(brief), encoding="utf-8")
    destinations = ["A.docx", "A.docx" if duplicate_outputs else "B.docx"]
    queue = {
        "positions": [
            {"brief": f"brief-{i}.json", "output": destinations[i]} for i in range(2)
        ]
    }
    q = tmp_path / "private-queue.json"
    q.write_text(json.dumps(queue), encoding="utf-8")
    return q


def test_review_only_plans_multiple_distinct_letters_without_writing(tmp_path):
    queue = make_queue(tmp_path)
    result = run_batch(queue)
    assert [r["status"] for r in result] == ["ready_for_generation"] * 2
    assert result[0]["institution"] != result[1]["institution"]
    assert not (tmp_path / "A.docx").exists()
    assert not (tmp_path / ".aihawk-motivation-batch.json").exists()


def test_sequential_generation_creates_distinct_review_drafts(tmp_path):
    queue = make_queue(tmp_path)
    calls = []

    def fake_generator(brief, destination, **kwargs):
        calls.append((Path(brief).name, Path(destination).name, kwargs))
        Path(destination).write_bytes(b"synthetic Word file")
        return Path(destination)

    result = run_batch(queue, generate=True, model="test", generator=fake_generator)
    assert len(calls) == 2
    assert {r["output"] for r in result} == {"A.docx", "B.docx"}
    assert all(r["status"] == "draft_requires_applicant_approval" for r in result)
    audit = json.loads((tmp_path / ".aihawk-motivation-batch.json").read_text(encoding="utf-8"))
    assert audit["university_submitted"] is False
    assert "Example Applicant" not in json.dumps(audit)


def test_duplicate_output_is_rejected_before_any_generation(tmp_path):
    queue = make_queue(tmp_path, duplicate_outputs=True)
    with pytest.raises(MotivationError, match="same motivation"):
        batch_from_queue(queue)


def test_unapproved_external_path_is_refused(tmp_path):
    queue = make_queue(tmp_path)
    data = json.loads(queue.read_text(encoding="utf-8"))
    data["positions"][1]["output"] = "../external.docx"
    queue.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(MotivationError, match="private queue"):
        batch_from_queue(queue)


def test_partial_failure_records_review_required_without_pii(tmp_path):
    queue = make_queue(tmp_path)
    calls = 0

    def fake_generator(_, destination, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("synthetic service failure with private message")
        Path(destination).write_bytes(b"synthetic")
        return Path(destination)

    with pytest.raises(RuntimeError, match="synthetic service"):
        run_batch(queue, generate=True, generator=fake_generator)
    audit = json.loads((tmp_path / ".aihawk-motivation-batch.json").read_text(encoding="utf-8"))
    assert [x["status"] for x in audit["records"]] == [
        "draft_requires_applicant_approval", "failed_review_required",
    ]
    assert "private message" not in json.dumps(audit)
