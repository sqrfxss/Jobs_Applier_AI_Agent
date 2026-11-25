from datetime import date
from aihawk.academic_execution import language_reference_date
from aihawk.academic_eligibility import evaluate_language


def test_never_use_deadline_for_start_anchored_english_validity():
    config = {"deadline": "2026-12-08"}
    rule = {"validity_reference": "programme_start"}
    assert language_reference_date(rule, {}, config) is None
    assert language_reference_date(rule, {"programme_start_date": "2027-09-01"}, config) == date(2027, 9, 1)
    assert language_reference_date({"validity_reference": "application_deadline"}, {}, config) == date(2026, 12, 8)
    assert language_reference_date({"validity_reference": "unsupported"}, {}, config) is None


def test_toefl_expiry_is_checked_at_programme_start():
    rule = {
        "reviewed": True,
        "source": "https://www.exeter.ac.uk/study/englishlanguagerequirements/",
        "accepted_delivery_modes": ["Home Edition"],
        "test": "TOEFL",
        "scale": "0-120",
        "valid_months": 24,
        "minimum_total": 87,
        "minimum_sections": {"Reading": 20, "Listening": 20, "Speaking": 20, "Writing": 20},
        "validity_reference": "programme_start",
    }
    cert = {
        "verified": True,
        "delivery_mode": "Home Edition",
        "test": "TOEFL",
        "scale": "0-120",
        "test_date": "2025-01-14",
        "total": 93,
        "sections": {"Reading": 25, "Listening": 27, "Speaking": 20, "Writing": 21},
    }
    on = language_reference_date(rule, {"programme_start_date": "2027-09-01"}, {"deadline": "2026-12-08"})
    assert evaluate_language(rule, cert, on=on)["status"] == "ineligible"
    assert evaluate_language(rule, cert, on=date(2026, 12, 8))["status"] == "verified_eligible"
