"""Sequential approved academic draft queue (headless, resumable and no email)."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from aihawk.academic_background_journey import _atomic_json, run_background_journey_reported as run_background_journey
from aihawk.academic_background_single import run_background_draft_reported as run_background_draft
from aihawk.academic_browser import PortalPreparationError


def _approved_entries(data: dict, root: Path) -> list[tuple[str, Path]]:
    if set(data) - {"schema_version", "applications"} or data.get("schema_version") != "aihawk.academic.approved-draft-queue.v1":
        raise PortalPreparationError("Queue schema mismatch or unsupported properties.")
    items = data.get("applications")
    if not isinstance(items, list) or not 1 <= len(items) <= 50:
        raise PortalPreparationError("Queue must contain between 1 and 50 reviewed entries.")
    results = []
    seen: set[Path] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict) or set(item) != {"manifest", "approved_for_draft"}:
            raise PortalPreparationError("Queue items must explicitly specify manifest and approved_for_draft.")
        relative = item["manifest"]
        if not isinstance(relative, str) or not relative.strip() or Path(relative).is_absolute():
            raise PortalPreparationError("Queue manifest path must be relative to queue folder.")
        file = (root / relative).resolve()
        if not file.is_relative_to(root) or file.suffix.lower() != ".json":
            raise PortalPreparationError("Manifest path escapes the approved queue root.")
        if file in seen:
            raise PortalPreparationError("The same application cannot appear twice in one queue.")
        seen.add(file)
        if item["approved_for_draft"] is not True:
            continue
        if not file.is_file():
            raise PortalPreparationError(f"Approved queue manifest {index + 1} is missing.")
        results.append((relative, file))
    return results


def _already_final_submitted(manifest: Path, data: dict) -> bool:
    if data.get("submitted") is True or data.get("status") in ("FINAL_SUBMITTED", "submitted"):
        return True
    # Support the previously generated Max Planck application status file.
    for status in manifest.parent.glob("*APPLICATION_VERIFIED_STATE_*.json"):
        try:
            body = json.loads(status.read_text(encoding="utf-8"))
            if body.get("status") == "FINAL_SUBMITTED":
                return True
        except (ValueError, OSError):
            continue
    return False


def run_approved_queue(queue_file: Path, report_file: Path) -> dict:
    """Runs only explicitly approved draft preparation. No autonomous final Submit."""
    queue_file = queue_file.resolve(strict=True)
    root = queue_file.parent
    report_file = report_file.resolve()
    if report_file.parent != root:
        raise PortalPreparationError("Queue progress must stay in its private folder.")
    manifest = json.loads(queue_file.read_text(encoding="utf-8"))
    entries = _approved_entries(manifest, root)
    out: dict = {
        "schema_version": "aihawk.academic.queue-progress.v1",
        "result": "running",
        "total_approved": len(entries),
        "items": [],
        "emails_sent": False,
        "final_submissions": 0,
        "personal_chrome_controlled": False,
    }
    _atomic_json(report_file, out)
    started = time.perf_counter()
    for relative, file in entries:
        label = {"manifest": relative}
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
            if _already_final_submitted(file, data):
                label["state"] = "skipped_already_final_submitted"
            elif "portal_stages" in data:
                result = run_background_journey(file, file.with_name(".aihawk-journey-status.json"))
                label["state"] = result["result"]
            else:
                result = run_background_draft(file, file.with_name(".aihawk-single-draft-status.json"))
                label["state"] = result["result"]
        except Exception as error:
            label["state"] = "stopped_needs_review"
            label["error"] = str(error)[:320]
        out["items"].append(label)
        _atomic_json(report_file, out)
        if label["state"] == "needs_user_action":
            out["result"] = "paused_needs_user_action"
            out["paused_manifest"] = relative
            out["elapsed_seconds"] = round(time.perf_counter() - started, 3)
            _atomic_json(report_file, out)
            return out
    out["result"] = "completed_with_review_items" if any(
        item["state"] == "stopped_needs_review" for item in out["items"]
    ) else "queue_draft_work_complete"
    out["elapsed_seconds"] = round(time.perf_counter() - started, 3)
    out["recorded_utc"] = datetime.now(timezone.utc).isoformat()
    _atomic_json(report_file, out)
    return out
