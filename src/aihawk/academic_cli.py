"""Offline, non-submitting university application eligibility command.

Usage: python -m aihawk.academic_cli evaluate input.json output.json

No browsing, credential use, model inference, or form submission occurs.
All accepted university requirements must be entered and sourced by the user.
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime
from pathlib import Path

from aihawk.academic import AcademicOpportunity, ApplicantEvidence, assess
from aihawk.academic_sources import RequirementSource, validate_source


def evaluate_document(payload: dict, *, today: date) -> dict:
    """Evaluate explicitly provided, source-attributed opportunity records."""
    evidence_data = payload["applicant"]
    evidence = ApplicantEvidence(
        language_test=evidence_data.get("language_test"),
        language_score=evidence_data.get("language_score"),
        documents_legalized=evidence_data.get("documents_legalized"),
    )
    results = []
    for entry in payload["opportunities"]:
        requirement = entry["requirements"]
        allowed_hosts = tuple(entry.get("official_hosts", ()))
        metadata_valid_sources = []
        source_errors = []
        for raw in entry.get("sources", []):
            try:
                source = RequirementSource(
                    institution=entry["institution"],
                    source_url=raw["url"],
                    retrieved_at=datetime.fromisoformat(raw["retrieved_at"]),
                    requirement=raw["requirement"],
                    evidence=raw["evidence"],
                )
                validate_source(source, official_hosts=allowed_hosts, now=datetime.now().astimezone())
                metadata_valid_sources.append({
                    "url": source.source_url,
                    "retrieved_at": source.retrieved_at.isoformat(),
                    "requirement": source.requirement,
                    "evidence": source.evidence,
                })
            except (ValueError, KeyError, TypeError) as error:
                source_errors.append(str(error))
        # Missing or invalid provenance cannot be silently treated as verified.
        requirement_keys = set(requirement)
        sourced_keys = {item["requirement"] for item in metadata_valid_sources}
        missing = sorted(requirement_keys - sourced_keys)
        application = AcademicOpportunity(
            title=entry["program"],
            deadline=date.fromisoformat(requirement["deadline"]) if requirement.get("deadline") else None,
            minimum_language_score=requirement.get("minimum_language_score"),
            accepted_language_tests=tuple(requirement.get("accepted_language_tests", ())),
            requires_legalization_at_application=requirement.get("requires_legalization_at_application"),
        )
        assessment = assess(application, evidence, today=today)
        reasons = list(assessment.reasons)
        verdict = assessment.verdict.value
        if missing or source_errors:
            reasons.append("Some requirements lack even valid source metadata.")
        # Source URL + timestamp + user-provided quote are not independently verified
        # page contents, nor can they establish that an interpretation is correct.
        # Never declare confirmed eligibility from unverified metadata alone.
        if verdict == "eligible":
            verdict = "needs_review"
            reasons.append("Preliminary eligibility only: independent page verification and human interpretation are still required.")
        results.append({
            "institution": entry["institution"],
            "program": entry["program"],
            "verdict": verdict,
            "reasons": reasons,
            "source_records": metadata_valid_sources,
            "source_content_verified": False,
            "human_requirement_reviewed": False,
            "preliminary_verdict": assessment.verdict.value,
            "unsourced_requirements": missing,
            "source_errors": source_errors,
            "submission_enabled": False,
        })
    return {"evaluated_on": today.isoformat(), "results": results, "submission_enabled": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evidence-based academic eligibility checks; never submits forms.")
    parser.add_argument("command", choices=["evaluate"])
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--date", type=date.fromisoformat, default=date.today(), help="Evaluation date YYYY-MM-DD")
    args = parser.parse_args(argv)
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    result = evaluate_document(payload, today=args.date)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Evaluated {len(result['results'])} programmes; saved {args.output}. No forms were submitted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
