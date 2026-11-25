"""Prevent draft edits and duplicate uploads after an application is submitted.

The local marker is not proof of a university receipt. A user-reported
submission is recorded as such, never promoted to institution-verified.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from aihawk.academic_browser import PortalPreparationError
from aihawk.academic_outreach_workflow import atomic_json

MARKER = "Application_Submission_Status.json"
SCHEMA = "aihawk.application.submission.v1"
SOURCES = {"user_reported", "university_receipt"}


def submission_record(folder: Path) -> dict | None:
    """Read a private local case marker; fail closed if malformed or unsafe."""
    folder = Path(folder).resolve(strict=True)
    path = folder / MARKER
    if path.is_symlink():
        raise PortalPreparationError("Unsafe submission status marker")
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        raise PortalPreparationError("Submission status cannot be verified; draft blocked") from error
    if (
        not isinstance(data, dict)
        or data.get("schema") != SCHEMA
        or data.get("status") != "submitted"
        or data.get("source") not in SOURCES
    ):
        raise PortalPreparationError("Unexpected submission status; draft blocked")
    return data


def require_open_application(folder: Path) -> None:
    """Guard any potentially mutating draft or file-upload workflow."""
    if submission_record(folder) is not None:
        raise PortalPreparationError("Application already submitted; no draft edits or uploads permitted")


def record_user_submission(folder: Path) -> Path:
    """Mark the applicant's own confirmation without claiming portal verification."""
    folder = Path(folder).resolve(strict=True)
    if not (folder / "Execution_Case.json").is_file():
        raise PortalPreparationError("Submission marker requires a reviewed application case")
    existing = submission_record(folder)
    if existing is not None:
        return folder / MARKER
    path = folder / MARKER
    atomic_json(
        path,
        {
            "schema": SCHEMA,
            "status": "submitted",
            "source": "user_reported",
            "university_receipt_verified": False,
            "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
            "resubmission_allowed": False,
        },
    )
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Record an applicant-reported submission in its private case")
    parser.add_argument("case_folder", type=Path)
    parser.add_argument("--user-reported", action="store_true", required=True)
    arguments = parser.parse_args()
    path = record_user_submission(arguments.case_folder)
    print("SUBMISSION_LOCKED_USER_REPORTED:", path.name)


if __name__ == "__main__":
    main()
