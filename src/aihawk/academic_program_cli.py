"""Evaluate stated admission, cost, and documentation conditions from local JSON.

Does not retrieve sources, verify fact interpretations, or submit applications.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from aihawk.academic_programs import (
    CandidateConditions,
    DocumentTiming,
    LanguageRule,
    Money,
    ProgrammeConditions,
    assess_conditions,
)


def _money(value):
    if value is None:
        return None
    if not isinstance(value, dict) or "amount" not in value or "currency" not in value:
        raise TypeError("Money must be an object with amount and currency or null.")
    return Money(Decimal(str(value["amount"])), str(value["currency"]))


def evaluate_programme(payload: dict, *, today: date) -> dict:
    p, a = payload["programme"], payload["applicant"]
    lang = p.get("accepted_languages")
    rules = None if lang is None else tuple(
        LanguageRule(str(r["test_name"]), r.get("minimum_score")) for r in lang
    )
    programme = ProgrammeConditions(
        institution=p["institution"],
        programme=p["name"],
        deadline=date.fromisoformat(p["deadline"]) if p.get("deadline") else None,
        admissions_open_from=date.fromisoformat(p["admissions_open_from"]) if p.get("admissions_open_from") else None,
        accepted_languages=rules,
        legalization=DocumentTiming(p.get("legalization", "unknown")),
        certified_translation=DocumentTiming(p.get("certified_translation", "unknown")),
        application_fee=_money(p.get("application_fee")),
        seat_deposit=_money(p.get("seat_deposit")),
        tuition_per_year=_money(p.get("tuition_per_year")),
        spouse_visa_policy_verified=p.get("spouse_visa_policy_verified") is True,
    )
    applicant = CandidateConditions(
        language_test=a.get("language_test"),
        language_score=a.get("language_score"),
        legalized=a.get("legalized"),
        certified_translations=a.get("certified_translations"),
        spouse_accompanying=a.get("spouse_accompanying") is True,
    )
    report = assess_conditions(programme, applicant, today=today)
    return {
        "schema": "aihawk.academic.programme.v1",
        "institution": p["institution"],
        "programme": p["name"],
        "evaluated_on": today.isoformat(),
        "preliminary_verdict": report.verdict.value,
        "blockers": list(report.blockers),
        "checks_needed": list(report.checks_needed),
        "financial_summary": {
            key: None if value is None else {"amount": str(value.amount), "currency": value.currency.upper()}
            for key, value in report.financial_summary
        },
        "family_visa_requires_separate_review": report.family_visa_requires_separate_review,
        "source_content_verified": False,
        "human_requirement_reviewed": False,
        "submission_enabled": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Review explicit university admission requirements without submitting forms.")
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--date", type=date.fromisoformat, default=date.today())
    args = parser.parse_args(argv)
    result = evaluate_programme(json.loads(args.input.read_text(encoding="utf-8")), today=args.date)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved preliminary review: {args.output}. No form submitted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
