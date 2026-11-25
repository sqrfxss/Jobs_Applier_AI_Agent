"""Read-only, redaction-safe audit of a *saved* university form inventory.

A saved accessibility snapshot is not a live server check. A control labelled
BLANK may have been completed later; no account, cookies or browser are read.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aihawk.academic_browser import PortalPreparationError

CONTROL_LINE = re.compile(r"^(?P<index>\d{1,6})\|(?P<kind>Text|Edit|Hyperlink|Button|ListItem)\|(?P<label>[^|]*)\|(?P<state>[^|]*)$")
ALLOWED_EDIT_STATES = frozenset({"[BLANK]", "[HAS_VALUE; REDACTED]"})
INTERESTING_UNSET_FIELDS = frozenset(
    {
        "Country",
        "Country of birth",
        "Nationality or citizenship",
        "Second nationality",
        "First Preference",
        "Second Preference",
        "Third Preference",
        "Proof of Language Proficiency",
    }
)
# OpenCampus BMAI groups some tab sections without a "Hide ..." heading. These
# are exact observed textual landmarks, not predictions of current field values.
BMAI_SECTION_LANDMARKS = (
    ("Journal of Publication 1", "5 Publications"),
    ("Name your top three subject-relevant awards", "6 Awards/Extracurriculars"),
    ("Proof of Language Proficiency", "7 Language"),
    ("First Preference", "8 PhD preferences"),
    ("Further documents", "9 Additional Information"),
)


def audit_redacted_snapshot(source: str, *, expected_host: str) -> dict[str, Any]:
    """Parse labels/status markers only; reject unredacted applicant field values."""
    if len(source.encode("utf-8")) > 1_000_000:
        raise PortalPreparationError("Unreasonably large form inventory.")
    lines = source.lstrip("\ufeff").splitlines()
    if not lines or lines[0].strip() != "Verified host: " + expected_host:
        raise PortalPreparationError("Snapshot host differs from the reviewed institutional hostname.")
    entries: list[dict[str, str | int]] = []
    for line in lines[1:]:
        match = CONTROL_LINE.fullmatch(line.strip())
        if not match:
            continue
        entry: dict[str, str | int] = {
            "line": int(match["index"]),
            "kind": match["kind"],
            "label": match["label"].strip()[:180],
            "state": match["state"].strip(),
        }
        if entry["kind"] == "Edit" and entry["state"] not in ALLOWED_EDIT_STATES:
            raise PortalPreparationError("Form inventory contains unredacted or unknown input state.")
        entries.append(entry)
    if not entries or not any(item["kind"] == "Edit" for item in entries):
        raise PortalPreparationError("Snapshot has no inspectable form controls.")

    section = "General information"
    blank_required: list[dict[str, str | int]] = []
    blank_other: list[dict[str, str | int]] = []
    unset: list[dict[str, str | int]] = []
    pending_file_inputs: list[dict[str, str | int]] = []
    prev_label = ""
    prev_number = -100
    for item in entries:
        kind = item["kind"]
        label = str(item["label"])
        number = int(item["line"])
        if kind == "Hyperlink" and label.startswith("Hide "):
            section = label.removeprefix("Hide ").strip()
        if kind == "Text" and expected_host == "mps.cloud.opencampus.net":
            for label_prefix, section_name in BMAI_SECTION_LANDMARKS:
                if label.startswith(label_prefix):
                    section = section_name
                    break
        if kind == "Edit" and item["state"] == "[BLANK]":
            record = {"line": number, "label": label, "section": section}
            (blank_required if label.rstrip().endswith("*") else blank_other).append(record)
        if kind == "Hyperlink" and label == "- None -" and number - prev_number <= 4 and prev_label in INTERESTING_UNSET_FIELDS:
            unset.append({"line": number, "label": prev_label, "section": section})
        if kind == "Button" and label == "Choose File: No file chosen":
            pending_file_inputs.append({"line": number, "section": section})
        if kind == "Text" and label:
            prev_label = label
            prev_number = number

    return {
        "schema": "aihawk.academic.snapshot-readiness.v1",
        "source_kind": "previously_saved_redacted_accessibility_snapshot",
        "institutional_host": expected_host,
        "audited_at": datetime.now(UTC).isoformat(),
        "live_portal_verified": False,
        "snapshot_may_be_outdated": True,
        "required_blank_inputs_observed": blank_required,
        "other_blank_inputs_observed": blank_other,
        "unset_selects_requiring_review": unset,
        "empty_file_inputs_at_capture": pending_file_inputs,
        "counts": {
            "required_blank": len(blank_required),
            "other_blank": len(blank_other),
            "unset_selects": len(unset),
            "empty_file_inputs_at_capture": len(pending_file_inputs),
        },
        "submission_ready": False,
        "note": ("This is a historical, redacted snapshot only. It cannot establish which fields or documents are currently missing, nor a server receipt."),
    }


def write_readiness(source_path: Path, destination: Path, *, expected_host: str) -> dict[str, Any]:
    """Produce a private, redacted JSON report; no HTTP request or portal write."""
    source = source_path.read_text(encoding="utf-8-sig")
    report = audit_redacted_snapshot(source, expected_host=expected_host)
    if source_path.resolve() == destination.resolve():
        raise PortalPreparationError("Refusing to overwrite the source snapshot.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report
