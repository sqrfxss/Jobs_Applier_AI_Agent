"""Redacted historical UIA snapshot audits never contact an actual university."""

from __future__ import annotations

import json

import pytest

from aihawk.academic_browser import PortalPreparationError
from aihawk.academic_readiness import audit_redacted_snapshot, write_readiness

HOST = "admissions.uni.example.edu"
SNAPSHOT = """Verified host: admissions.uni.example.edu
UIA document nodes: 18
001|Hyperlink|Hide 1.1 Referee A|
002|Text|Family Name|
003|Edit|Family Name *|[BLANK]
004|Text|Email|
005|Edit|Email *|[BLANK]
006|Hyperlink|Hide 2.1 Personal Details|
007|Text|Country of birth|
008|Hyperlink|- None -|
009|Text|Current Address|
010|Edit|Current Address|[HAS_VALUE; REDACTED]
011|Text|Passport|
012|Button|Choose File: No file chosen|
013|Text|Grade|
014|Edit|Grade|[HAS_VALUE; REDACTED]
"""


def test_snapshot_audit_redacts_and_distinguishes_historical_status():
    report = audit_redacted_snapshot(SNAPSHOT, expected_host=HOST)
    assert report["submission_ready"] is False
    assert report["live_portal_verified"] is False
    assert report["counts"] == {
        "required_blank": 2,
        "other_blank": 0,
        "unset_selects": 1,
        "empty_file_inputs_at_capture": 1,
    }
    assert report["required_blank_inputs_observed"][0]["section"] == "1.1 Referee A"
    assert report["unset_selects_requiring_review"][0]["label"] == "Country of birth"
    assert "[HAS_VALUE; REDACTED]" not in json.dumps(report)


def test_refuses_snapshot_from_other_university():
    with pytest.raises(PortalPreparationError, match="host differs"):
        audit_redacted_snapshot(SNAPSHOT, expected_host="other.uni.example.edu")


def test_refuses_unredacted_personal_input_values():
    leaked = SNAPSHOT.replace(
        "Edit|Current Address|[HAS_VALUE; REDACTED]",
        "Edit|Current Address|private home address",
    )
    with pytest.raises(PortalPreparationError, match="unredacted"):
        audit_redacted_snapshot(leaked, expected_host=HOST)


def test_writes_json_without_changing_source(tmp_path):
    src = tmp_path / "snapshot.txt"
    out = tmp_path / "report.json"
    src.write_text(SNAPSHOT, encoding="utf-8")
    result = write_readiness(src, out, expected_host=HOST)
    assert json.loads(out.read_text(encoding="utf-8"))["counts"] == result["counts"]
    assert src.read_text(encoding="utf-8") == SNAPSHOT
    with pytest.raises(PortalPreparationError, match="source"):
        write_readiness(src, src, expected_host=HOST)


def test_empty_or_invalid_inventory_is_rejected():
    with pytest.raises(PortalPreparationError, match="inspectable"):
        audit_redacted_snapshot("Verified host: " + HOST + "\nNo valid fields", expected_host=HOST)


def test_bmai_unheaded_language_and_fellow_sections_are_not_misattributed():
    snapshot = """Verified host: mps.cloud.opencampus.net
001|Hyperlink|Hide 4.3 Additional Research Project|
002|Text|Proof of Language Proficiency|
003|Hyperlink|- None -|
004|Text|First Preference|
005|Hyperlink|- None -|
006|Text|Second Preference|
007|Hyperlink|- None -|
008|Text|Third Preference|
009|Hyperlink|- None -|
010|Edit|Other notes|[HAS_VALUE; REDACTED]
"""
    report = audit_redacted_snapshot(snapshot, expected_host="mps.cloud.opencampus.net")
    sections = [(x["label"], x["section"]) for x in report["unset_selects_requiring_review"]]
    assert sections == [
        ("Proof of Language Proficiency", "7 Language"),
        ("First Preference", "8 PhD preferences"),
        ("Second Preference", "8 PhD preferences"),
        ("Third Preference", "8 PhD preferences"),
    ]
