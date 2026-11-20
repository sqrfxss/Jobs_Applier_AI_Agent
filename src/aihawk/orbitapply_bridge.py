"""Versioned, privacy-minimizing exchange records for an OrbitApply adapter.

An exchange record represents a reviewed academic eligibility result, not an
application submitted to a university. This module performs no networking.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any
from urllib.parse import urlsplit

from aihawk.academic import Assessment, Verdict


SCHEMA_VERSION = "aihawk.orbitapply.academic.v1"
VALID_LEVELS = frozenset(("master", "phd"))
VALID_VERDICTS = frozenset(x.value for x in Verdict)


@dataclass(frozen=True)
class OpportunityExchange:
    university: str
    programme: str
    level: str
    official_url: str
    assessment: Assessment
    evaluated_on: date
    source_urls: tuple[str, ...] = ()

    def to_record(self) -> dict[str, Any]:
        if not self.university.strip() or not self.programme.strip():
            raise ValueError("University and programme names are required.")
        if self.level not in VALID_LEVELS:
            raise ValueError("Level must be master or phd.")
        parsed = urlsplit(self.official_url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Official URL must use HTTPS and contain no credentials.")
        return {
            "schema_version": SCHEMA_VERSION,
            "university": self.university.strip(),
            "programme": self.programme.strip(),
            "level": self.level,
            "official_url": self.official_url,
            "eligibility": self.assessment.verdict.value,
            "eligibility_reasons": list(self.assessment.reasons),
            "evaluated_on": self.evaluated_on.isoformat(),
            "source_urls": list(self.source_urls),
            "application_status": "not_submitted",
            "submission_enabled": False,
        }


def validate_exchange(record: dict[str, Any]) -> dict[str, Any]:
    """Validate incoming values; intentionally refuse claims of submission."""
    if record.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Unsupported academic exchange schema version.")
    if record.get("eligibility") not in VALID_VERDICTS:
        raise ValueError("Unknown eligibility verdict.")
    if record.get("application_status") != "not_submitted" or record.get("submission_enabled") is not False:
        raise ValueError("Offline exchange must not imply that a form was submitted.")
    if record.get("level") not in VALID_LEVELS:
        raise ValueError("Unsupported academic level.")
    if not isinstance(record.get("source_urls"), list) or not isinstance(record.get("eligibility_reasons"), list):
        raise ValueError("Sources and reasons must be arrays.")
    date.fromisoformat(record["evaluated_on"])
    if not record.get("university") or not record.get("programme"):
        raise ValueError("University and programme are required.")
    url = urlsplit(record["official_url"])
    if url.scheme != "https" or not url.hostname or url.username or url.password:
        raise ValueError("Official URL must be HTTPS without credentials.")
    return record


def serialize_exchange(exchange: OpportunityExchange) -> str:
    record = validate_exchange(exchange.to_record())
    return json.dumps(record, ensure_ascii=False, indent=2) + "\n"
