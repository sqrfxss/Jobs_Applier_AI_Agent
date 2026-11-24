import json
from datetime import date

from aihawk.academic_program_cli import evaluate_programme, main


def sample():
    return {
        "programme": {
            "institution": "Example University",
            "name": "MSc Example",
            "deadline": "2027-01-01",
            "accepted_languages": [{"test_name": "TOEFL iBT Home Edition", "minimum_score": 90}],
            "legalization": "at_enrolment",
            "certified_translation": "not_required",
            "application_fee": {"amount": "0", "currency": "EUR"},
            "seat_deposit": None,
            "tuition_per_year": {"amount": "12000", "currency": "EUR"},
        },
        "applicant": {
            "language_test": "TOEFL iBT Home Edition",
            "language_score": 100,
            "legalized": False,
            "spouse_accompanying": True,
        },
    }


def test_preserves_unknown_deposit_and_family_visa():
    result = evaluate_programme(sample(), today=date(2026, 11, 20))
    assert result["preliminary_verdict"] == "needs_review"
    assert result["financial_summary"]["seat_deposit"] is None
    assert result["family_visa_requires_separate_review"] is True
    assert result["submission_enabled"] is False


def test_cli_generates_json(tmp_path):
    source, target = tmp_path / "input.json", tmp_path / "review.json"
    source.write_text(json.dumps(sample()), encoding="utf-8")
    assert main([str(source), str(target), "--date", "2026-11-20"]) == 0
    assert json.loads(target.read_text(encoding="utf-8"))["source_content_verified"] is False
