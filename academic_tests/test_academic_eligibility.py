from datetime import date
from aihawk.academic_eligibility import evaluate_language, evaluate_credits, evaluate_degree, evaluate_credentials


def lang():
    return dict(
        reviewed=True,
        source="https://example.edu/language",
        accepted_delivery_modes=["home"],
        test="TOEFL iBT",
        scale="0-120",
        valid_months=24,
        minimum_total=90,
        minimum_sections={"speaking": 20},
    )


def cert():
    return dict(verified=True, delivery_mode="home", test="TOEFL iBT", scale="0-120", test_date="2025-01-14", total=93, sections={"speaking": 20})


def test_language_expiry_and_home_exclusion():
    assert evaluate_language(lang(), cert(), on=date(2026, 11, 24))["status"] == "verified_eligible"
    assert evaluate_language(lang(), cert(), on=date(2027, 1, 15))["status"] == "ineligible"
    assert evaluate_language({**lang(), "accepted_delivery_modes": ["center"]}, cert(), on=date(2026, 11, 24))["status"] == "ineligible"


def test_unknown_test_type_and_scale():
    assert evaluate_language(lang(), {**cert(), "delivery_mode": None}, on=date(2026, 11, 24))["status"] == "unknown"
    assert evaluate_language(lang(), {**cert(), "scale": "1-6"}, on=date(2026, 11, 24))["status"] == "unknown"


def test_section_shortfall():
    assert evaluate_language(lang(), {**cert(), "sections": {"speaking": 19}}, on=date(2026, 11, 24))["status"] == "ineligible"


def test_credit_no_conversion_no_double_count():
    rule = dict(reviewed=True, source="https://example.edu/credits", category="math", credit_unit="ECTS", minimum=6)
    course = dict(id="c1", verified=True, reviewed_categories=["math", "statistics"], credit_unit="ECTS", credits=6)
    r = evaluate_credits([rule, {**rule, "category": "statistics"}], [course])
    assert [x["status"] for x in r] == ["verified_eligible", "unknown"]
    assert evaluate_credits([rule], [{**course, "credit_unit": "local"}])[0]["status"] == "unknown"


def test_individual_equivalence():
    rule = dict(reviewed=True, source="https://example.edu", foreign_equivalence_individual=True, accepted_levels=["MSc"])
    assert evaluate_degree(rule, dict(verified=True, level="MSc"))["status"] == "pending_institutional_assessment"


def test_credential_timing():
    rule = dict(reviewed=True, source="https://example.edu", required_at_application=["translation"], legalization_timing="enrolment")
    assert evaluate_credentials(rule, {"translation": {"verified": True}})["status"] == "verified_eligible"
    assert evaluate_credentials({**rule, "legalization_timing": "application"}, {"translation": {"verified": True}})["status"] == "missing_document"
