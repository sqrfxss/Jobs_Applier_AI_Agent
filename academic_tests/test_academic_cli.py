import json
from datetime import date

from aihawk.academic_cli import evaluate_document, main


def _payload():
    return {
        "applicant": {"language_test": "TOEFL Home Edition", "language_score": 100, "documents_legalized": False},
        "opportunities": [
            {
                "institution": "Example University",
                "program": "MSc Example",
                "official_hosts": ["example.edu"],
                "requirements": {
                    "deadline": "2027-02-01",
                    "accepted_language_tests": ["TOEFL Home Edition"],
                    "minimum_language_score": 90,
                    "requires_legalization_at_application": False,
                },
                "sources": [
                    {
                        "url": "https://example.edu/admissions",
                        "retrieved_at": "2026-11-19T12:00:00+00:00",
                        "requirement": key,
                        "evidence": "Official institution document (placeholder for integration tests)",
                    }
                    for key in ("deadline", "accepted_language_tests", "minimum_language_score", "requires_legalization_at_application")
                ],
            }
        ],
    }


def test_sourced_eligible_evaluation():
    result = evaluate_document(_payload(), today=date(2026, 11, 20))
    assert result["results"][0]["verdict"] == "needs_review"
    assert result["results"][0]["preliminary_verdict"] == "eligible"
    assert result["results"][0]["source_content_verified"] is False
    assert result["submission_enabled"] is False


def test_unattributed_requirement_requires_review():
    payload = _payload()
    payload["opportunities"][0]["sources"] = []
    result = evaluate_document(payload, today=date(2026, 11, 20))
    assert result["results"][0]["verdict"] == "needs_review"
    assert result["results"][0]["unsourced_requirements"]


def test_bad_host_rejected():
    payload = _payload()
    payload["opportunities"][0]["sources"][0]["url"] = "https://example.edu.attacker.test/"
    result = evaluate_document(payload, today=date(2026, 11, 20))
    assert result["results"][0]["verdict"] == "needs_review"
    assert result["results"][0]["source_errors"]


def test_cli_writes_json_without_submitting(tmp_path):
    source, destination = tmp_path / "input.json", tmp_path / "out.json"
    source.write_text(json.dumps(_payload()), encoding="utf-8")
    assert main(["evaluate", str(source), str(destination), "--date", "2026-11-20"]) == 0
    assert json.loads(destination.read_text(encoding="utf-8"))["submission_enabled"] is False
