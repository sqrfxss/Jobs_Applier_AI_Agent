"""Deterministic eligibility checks for academic opportunities.

This module does not scrape sites, infer credentials or submit applications.
Unknown information is never treated as satisfying a requirement.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import Enum


class Verdict(str, Enum):
    ELIGIBLE = "eligible"
    INELIGIBLE = "ineligible"
    NEEDS_REVIEW = "needs_review"


@dataclass(frozen=True)
class AcademicOpportunity:
    title: str
    deadline: date | None = None
    minimum_language_score: float | None = None
    accepted_language_tests: tuple[str, ...] = ()
    requires_legalization_at_application: bool | None = None


@dataclass(frozen=True)
class ApplicantEvidence:
    language_test: str | None = None
    language_score: float | None = None
    documents_legalized: bool | None = None


@dataclass(frozen=True)
class Assessment:
    verdict: Verdict
    reasons: tuple[str, ...]


def assess(
    opportunity: AcademicOpportunity,
    evidence: ApplicantEvidence,
    *,
    today: date,
) -> Assessment:
    """Check only explicit facts, preserving uncertainty for manual verification."""
    blocked: list[str] = []
    unknown: list[str] = []

    if opportunity.deadline is None:
        unknown.append("Application deadline has not been verified.")
    elif opportunity.deadline < today:
        blocked.append("Application deadline has passed.")

    accepted = tuple(test.casefold().strip() for test in opportunity.accepted_language_tests)
    if accepted:
        if not evidence.language_test:
            unknown.append("Language test type is unknown.")
        elif evidence.language_test.casefold().strip() not in accepted:
            blocked.append("Language test type is not listed as accepted.")

    if opportunity.minimum_language_score is not None:
        if evidence.language_score is None:
            unknown.append("Language score is unknown.")
        elif evidence.language_score < opportunity.minimum_language_score:
            blocked.append("Language score is below the stated minimum.")

    if opportunity.requires_legalization_at_application is True:
        if evidence.documents_legalized is False:
            blocked.append("Required document legalization is incomplete.")
        elif evidence.documents_legalized is None:
            unknown.append("Document legalization status is unknown.")
    elif opportunity.requires_legalization_at_application is None:
        unknown.append("Legalization requirement at application is unverified.")

    if blocked:
        return Assessment(Verdict.INELIGIBLE, tuple(blocked + unknown))
    if unknown:
        return Assessment(Verdict.NEEDS_REVIEW, tuple(unknown))
    return Assessment(Verdict.ELIGIBLE, ("All explicitly modeled requirements are satisfied.",))
