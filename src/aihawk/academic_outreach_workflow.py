"""Post-outreach state machine. Connector actions are explicit dependencies, not simulated sends."""

import json
import os
from pathlib import Path
from datetime import datetime, timezone


def next_actions(blockers):
    text = " ".join(str(x) for x in blockers).lower()
    actions = []
    if "supervisor" in text:
        actions.append("research_supervisors_and_prepare_personalized_outreach")
    if any(x in text for x in ("authentication", "legalization", "legalisation", "apostille", "naric")):
        actions.append("prepare_admissions_authentication_enquiry")
    if "research plan" in text:
        actions.append("prepare_evidence_based_research_plan")
    if "portal" in text:
        actions.append("recheck_official_portal")
    if any(x in text for x in ("language", "toefl")):
        actions.append("verify_language_policy")
    if "funding" in text:
        actions.append("verify_funding_route")
    return actions


def atomic_json(path, data):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def archive_and_sync(folder, message, sync_connector):
    """Require a Gmail readback, persist first, then request idempotent tracker upsert.
    sync_connector must verify unique existing row, update both trackers and return
    readback confirmation keyed by message ID. No sending is performed here."""
    folder = Path(folder)
    mid = message.get("id", "")
    if not mid or not mid.isalnum() or "SENT" not in message.get("labels", []):
        raise ValueError("Verified Gmail SENT message required")
    if len(message.get("to", [])) != 1 or not message.get("thread_id"):
        raise ValueError("One verified recipient and thread required")
    if not any(
        a.get("mime_type") == "application/pdf" and a.get("size_bytes", 0) > 0 and "cv" in a.get("filename", "").lower() for a in message.get("attachments", [])
    ):
        raise ValueError("CV PDF attachment not verified")
    path = folder / ("outreach_" + mid + ".json")
    if path.exists():
        record = json.loads(path.read_text(encoding="utf-8"))
        if record["message"]["id"] != mid:
            raise ValueError("Archive identity mismatch")
        if record.get("sync_verified") is True:
            return record
    else:
        record = {"message": message, "status": "Awaiting Supervisor Approval", "sync_verified": False, "application_submitted": False}
        atomic_json(path, record)
    try:
        result = sync_connector(record)
        if not isinstance(result, dict) or result.get("message_id") != mid or result.get("readback_verified") is not True:
            raise ValueError("Tracker readback not verified")
        record["sync_verified"] = True
        record["sync_receipt"] = result
        record.pop("sync_error", None)
    except Exception as exc:
        record["sync_error"] = type(exc).__name__ + ": " + str(exc)[:300]
    record["updated_at"] = datetime.now(timezone.utc).isoformat()
    atomic_json(path, record)
    return record
