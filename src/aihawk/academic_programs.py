"""Detailed, conservative admissions review for programmes and applicants.

Financial obligations and family immigration are recorded separately from
admissions eligibility. No programme-specific facts are inferred automatically.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum

from aihawk.academic import Verdict


class DocumentTiming(str, Enum):
    APPLICATION = "at_application"
    ENROLMENT = "at_enrolment"
    NOT_REQUIRED = "not_required"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Money:
    amount: Decimal
    currency: str

    def __post_init__(self):
        if not self.amount.is_finite() or self.amount < 0:
            raise ValueError("Amount must be a finite non-negative value.")
        if len(self.currency) != 3 or not self.currency.isalpha():
            raise ValueError("Use a three-letter ISO currency code.")


@dataclass(frozen=True)
class LanguageRule:
    test_name: str
    minimum_score: float | None


@dataclass(frozen=True)
class ProgrammeConditions:
    institution: str
    programme: str
    deadline: date | None = None
    admissions_open_from: date | None = None
    accepted_languages: tuple[LanguageRule, ...] | None = None
    legalization: DocumentTiming = DocumentTiming.UNKNOWN
    certified_translation: DocumentTiming = DocumentTiming.UNKNOWN
    application_fee: Money | None = None
    seat_deposit: Money | None = None
    tuition_per_year: Money | None = None
    spouse_visa_policy_verified: bool = False


@dataclass(frozen=True)
class CandidateConditions:
    language_test: str | None = None
    language_score: float | None = None
    legalized: bool | None = None
    certified_translations: bool | None = None
    spouse_accompanying: bool = False


@dataclass(frozen=True)
class ConditionsReport:
    verdict: Verdict
    blockers: tuple[str, ...]
    checks_needed: tuple[str, ...]
    financial_summary: tuple[tuple[str, Money | None], ...]
    family_visa_requires_separate_review: bool


def assess_conditions(program: ProgrammeConditions, person: CandidateConditions, *, today: date) -> ConditionsReport:
    blocked: list[str] = []
    checks: list[str] = []

    if program.deadline is None:
        checks.append("The application deadline has not been independently confirmed.")
    elif today > program.deadline:
        blocked.append("Application deadline has passed.")
    if program.admissions_open_from is not None and today < program.admissions_open_from:
        checks.append("Application period has not opened yet.")

    if program.accepted_languages is None:
        checks.append("Accepted language examinations are unknown.")
    elif not program.accepted_languages:
        checks.append("The programme did not provide an explicit language requirement.")
    elif not person.language_test:
        checks.append("Applicant language examination has not been specified.")
    else:
        found = [r for r in program.accepted_languages if r.test_name.casefold().strip() == person.language_test.casefold().strip()]
        if not found:
            blocked.append("This exact examination format is not listed as accepted.")
        elif all(r.minimum_score is None for r in found):
            checks.append("The minimum score for this test format is unknown.")
        elif person.language_score is None:
            checks.append("Applicant language score is missing.")
        elif not any(r.minimum_score is not None and person.language_score >= r.minimum_score for r in found):
            blocked.append("Applicant language score is below the specified minimum.")

    for label, timing, complete in (
        ("Legalization", program.legalization, person.legalized),
        ("Certified translation", program.certified_translation, person.certified_translations),
    ):
        if timing is DocumentTiming.UNKNOWN:
            checks.append(f"{label} timing is unknown.")
        elif timing is DocumentTiming.APPLICATION and complete is not True:
            checks.append(f"{label} is required before submitting; completion must be verified.")
        elif timing is DocumentTiming.ENROLMENT and complete is not True:
            checks.append(f"{label} is deferred until enrolment; confirm deadlines after admission.")

    money = (
        ("application_fee", program.application_fee),
        ("seat_deposit", program.seat_deposit),
        ("tuition_per_year", program.tuition_per_year),
    )
    for label, value in money:
        if value is None:
            checks.append(f"{label} has not been verified; unknown is not zero.")
    family_review = person.spouse_accompanying and not program.spouse_visa_policy_verified
    if family_review:
        checks.append("Spouse residence/visa permissions require independent immigration-authority verification.")

    verdict = Verdict.INELIGIBLE if blocked else (Verdict.NEEDS_REVIEW if checks else Verdict.ELIGIBLE)
    return ConditionsReport(verdict, tuple(blocked), tuple(checks), money, family_review)
