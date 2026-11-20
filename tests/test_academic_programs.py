from datetime import date
from decimal import Decimal

import pytest

from aihawk.academic import Verdict
from aihawk.academic_programs import (
    CandidateConditions, DocumentTiming, LanguageRule, Money, ProgrammeConditions, assess_conditions,
)


TODAY = date(2026, 11, 20)


def base():
    return ProgrammeConditions(
        institution="Example University", programme="MSc",
        deadline=date(2027, 3, 1),
        accepted_languages=(LanguageRule("TOEFL iBT Home Edition", 90),),
        legalization=DocumentTiming.ENROLMENT,
        certified_translation=DocumentTiming.NOT_REQUIRED,
        application_fee=Money(Decimal("0"), "EUR"),
        seat_deposit=Money(Decimal("0"), "EUR"),
        tuition_per_year=Money(Decimal("14000"), "EUR"),
        spouse_visa_policy_verified=True,
    )


def test_exact_test_format_is_required():
    result = assess_conditions(base(), CandidateConditions(language_test="TOEFL iBT", language_score=100), today=TODAY)
    assert result.verdict is Verdict.INELIGIBLE


def test_home_edition_accepted_when_explicit():
    result = assess_conditions(
        base(), CandidateConditions(language_test="TOEFL iBT Home Edition", language_score=95, certified_translations=True, legalized=True),
        today=TODAY,
    )
    assert result.verdict is Verdict.ELIGIBLE


def test_legalization_at_enrolment_not_an_application_failure():
    result = assess_conditions(
        base(), CandidateConditions(language_test="TOEFL iBT Home Edition", language_score=95, legalized=False),
        today=TODAY,
    )
    assert result.verdict is Verdict.NEEDS_REVIEW
    assert any("deferred" in line for line in result.checks_needed)


def test_legalization_due_at_application_requires_check():
    from dataclasses import replace
    program = replace(base(), legalization=DocumentTiming.APPLICATION)
    result = assess_conditions(program, CandidateConditions(language_test="TOEFL iBT Home Edition", language_score=99, legalized=False), today=TODAY)
    assert result.verdict is Verdict.NEEDS_REVIEW
    assert any("before submitting" in line for line in result.checks_needed)


def test_unknown_deposit_not_assumed_free():
    from dataclasses import replace
    report = assess_conditions(
        replace(base(), seat_deposit=None),
        CandidateConditions(language_test="TOEFL iBT Home Edition", language_score=99, legalized=True),
        today=TODAY,
    )
    assert report.verdict is Verdict.NEEDS_REVIEW
    assert any("seat_deposit" in x for x in report.checks_needed)


def test_family_visa_is_independent_review():
    from dataclasses import replace
    result = assess_conditions(
        replace(base(), spouse_visa_policy_verified=False),
        CandidateConditions(language_test="TOEFL iBT Home Edition", language_score=99, legalized=True, spouse_accompanying=True),
        today=TODAY,
    )
    assert result.family_visa_requires_separate_review is True


def test_expired_deadline_is_ineligible():
    from dataclasses import replace
    result = assess_conditions(
        replace(base(), deadline=date(2026, 11, 19)),
        CandidateConditions(language_test="TOEFL iBT Home Edition", language_score=99, legalized=True),
        today=TODAY,
    )
    assert result.verdict is Verdict.INELIGIBLE


@pytest.mark.parametrize("amount,currency", [("-1", "EUR"), ("0", "EURO"), ("NaN", "EUR")])
def test_bad_currency_input_rejected(amount, currency):
    with pytest.raises(ValueError):
        Money(Decimal(amount), currency)
