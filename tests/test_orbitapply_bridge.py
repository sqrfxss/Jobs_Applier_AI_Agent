from datetime import date
import json

import pytest

from aihawk.academic import Assessment, Verdict
from aihawk.orbitapply_bridge import OpportunityExchange, serialize_exchange, validate_exchange


def sample():
    return OpportunityExchange(
        university="Example University",
        programme="Human Movement Science",
        level="master",
        official_url="https://example.edu/degree",
        assessment=Assessment(Verdict.NEEDS_REVIEW, ("Verify fee on university site.",)),
        evaluated_on=date(2026, 11, 20),
        source_urls=("https://example.edu/degree",),
    )


def test_export_has_explicit_unsubmitted_status():
    result = json.loads(serialize_exchange(sample()))
    assert result["schema_version"] == "aihawk.orbitapply.academic.v1"
    assert result["application_status"] == "not_submitted"
    assert result["submission_enabled"] is False


def test_invalid_level_rejected():
    item = sample()
    from dataclasses import replace
    with pytest.raises(ValueError):
        replace(item, level="bachelor").to_record()


def test_fake_submitted_status_rejected():
    record = sample().to_record()
    record["application_status"] = "submitted"
    with pytest.raises(ValueError):
        validate_exchange(record)


def test_invalid_source_field_rejected():
    record = sample().to_record()
    record["source_urls"] = None
    with pytest.raises(ValueError):
        validate_exchange(record)
