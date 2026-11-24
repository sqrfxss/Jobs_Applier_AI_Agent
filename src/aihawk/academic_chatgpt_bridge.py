"""Private handoff to ChatGPT's connected Gmail and Sheets.

Local OAuth is optional, not required. This module is an outbox/inbox,
not a remote API client. A connected ChatGPT session must process requests.
No access tokens, passwords, OTPs or outgoing messages in this queue.
"""

from __future__ import annotations
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone
from aihawk.academic_outreach_workflow import atomic_json


def _now():
    return datetime.now(timezone.utc).isoformat()


def _load(path):
    return json.loads(path.read_text(encoding="utf8")) if path.exists() else {}


def _key(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _private(folder):
    folder = folder.resolve(strict=True)
    if any((p / ".git").exists() for p in (folder, *folder.parents)):
        raise ValueError("Private bridge outside Git")
    return folder


def request_sync(folder, state):
    folder = _private(folder)
    sup = state.get("supervisor", {})
    payload = {
        "institution": state.get("institution"),
        "position_id": state.get("position_id") or state.get("job_id"),
        "thread_id": sup.get("thread_id"),
        "sent_message_id": sup.get("message_id"),
        "position_url": state.get("official_application_url"),
        "requested_operation": "reconcile_existing_tracker_and_gmail",
        "allow_send": False,
        "allow_submit": False,
    }
    if not payload["institution"] or not payload["position_id"]:
        return {"status": "not_configured"}
    key = _key(payload)
    path = folder / "ChatGPT_Sync_Request.json"
    prior = _load(path)
    if prior.get("request_id") == key and prior.get("status") == "pending":
        return prior
    req = {"schema": "aihawk.chatgpt.sync.v1", "request_id": key, "status": "pending", "requested_at": _now(), "payload": payload}
    atomic_json(path, req)
    return req


def accept_receipt(folder, receipt):
    folder = _private(folder)
    path = folder / "ChatGPT_Sync_Request.json"
    req = _load(path)
    if req.get("status") != "pending" or req.get("request_id") != receipt.get("request_id"):
        raise ValueError("Receipt does not match pending request")
    if receipt.get("connector_readback_verified") is not True:
        raise ValueError("Live connector readback required")
    if receipt.get("email_sent") is not False or receipt.get("application_submitted") is not False:
        raise ValueError("Sync must not send or submit")
    payload = req["payload"]
    tracker = receipt.get("tracker", {})
    if (
        not tracker.get("spreadsheet_id")
        or not tracker.get("sheet")
        or not tracker.get("row")
        or tracker.get("institution") != payload["institution"]
        or tracker.get("position_id") != payload["position_id"]
    ):
        raise ValueError("Tracker identity mismatch")
    if payload.get("thread_id"):
        thread = receipt.get("gmail", {})
        if thread.get("thread_id") != payload["thread_id"] or thread.get("sent_message_id") != payload["sent_message_id"]:
            raise ValueError("Gmail identity mismatch")
    result = {**receipt, "status": "verified", "received_at": _now()}
    atomic_json(folder / "ChatGPT_Sync_Receipt.json", result)
    req["status"] = "verified"
    atomic_json(path, req)
    return result


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("folder", type=Path)
    p.add_argument("--receipt", type=Path)
    a = p.parse_args()
    if a.receipt:
        print(json.dumps(accept_receipt(a.folder, _load(a.receipt)), ensure_ascii=True))
    else:
        print(json.dumps(_load(a.folder / "ChatGPT_Sync_Request.json"), ensure_ascii=True))
