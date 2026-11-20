from datetime import date

from aihawk.academic import AcademicOpportunity, ApplicantEvidence, Verdict, assess

TODAY = date(2026, 11, 20)


def test_unknown_requirements_are_not_accepted():
    result = assess(AcademicOpportunity("Example"), ApplicantEvidence(), today=TODAY)
    assert result.verdict is Verdict.NEEDS_REVIEW


def test_deadline_in_past_blocks():
    result = assess(
        AcademicOpportunity("Example", deadline=date(2026, 11, 19), requires_legalization_at_application=False),
        ApplicantEvidence(), today=TODAY,
    )
    assert result.verdict is Verdict.INELIGIBLE


def test_unaccepted_language_test_blocks():
    result = assess(
        AcademicOpportunity("Example", deadline=date(2027, 1, 1), accepted_language_tests=("IELTS",), requires_legalization_at_application=False),
        ApplicantEvidence(language_test="TOEFL Home Edition"), today=TODAY,
    )
    assert result.verdict is Verdict.INELIGIBLE


def test_missing_legalization_blocks_if_required():
    result = assess(
        AcademicOpportunity("Example", deadline=date(2027, 1, 1), requires_legalization_at_application=True),
        ApplicantEvidence(documents_legalized=False), today=TODAY,
    )
    assert result.verdict is Verdict.INELIGIBLE


def test_explicitly_satisfied_requirements():
    result = assess(
        AcademicOpportunity(
            "Example", deadline=date(2027, 1, 1), minimum_language_score=90,
            accepted_language_tests=("TOEFL Home Edition",), requires_legalization_at_application=False,
        ),
        ApplicantEvidence(language_test="toefl home edition", language_score=95), today=TODAY,
    )
    assert result.verdict is Verdict.ELIGIBLE


def test_insufficient_score_blocks():
    result = assess(
        AcademicOpportunity("Example", deadline=date(2027, 1, 1), minimum_language_score=90, requires_legalization_at_application=False),
        ApplicantEvidence(language_score=89), today=TODAY,
    )
    assert result.verdict is Verdict.INELIGIBLE
