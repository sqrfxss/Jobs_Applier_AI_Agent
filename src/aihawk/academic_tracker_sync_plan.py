"""Build evidence-backed, idempotent status proposals; connector must re-read before writing."""

import argparse
import json
import hashlib
from datetime import datetime, date, timezone
from pathlib import Path
from aihawk.academic_discovery import canonical


def plan(state, rows, position_url):
    final = state.get("final_submission", {})
    if (
        state.get("status") != "FINAL_SUBMITTED"
        or final.get("read_only_application_view_verified") is not True
        or final.get("button_invoked_once") is not True
        or final.get("final_confirmation_ok_invoked_once") is not True
    ):
        return {"action": "review_required", "reason": "No verified final submission evidence"}
    try:
        submitted_date = date.fromisoformat(final["date"]).isoformat()
    except (KeyError, TypeError, ValueError):
        return {"action": "review_required", "reason": "Missing valid date"}
    candidates = [r for r in rows if r.get("url") and canonical(r["url"]) == canonical(position_url)]
    if len(candidates) != 1:
        return {"action": "review_required", "reason": "Missing or ambiguous position URL"}
    row = candidates[0]
    if str(row.get("status", "")).strip().casefold() not in {"submitted", "researching", "in progress", "application in progress", "draft", "draft saved"}:
        return {"action": "review_required", "reason": "Existing status must not be overwritten without review"}
    return {
        "action": "reconcile_existing_row",
        "row_hint": row["row"],
        "position_url": position_url,
        "expected_status": row["status"],
        "target_status": "Submitted",
        "submitted_date": submitted_date,
        "application_reference": str(final.get("application_reference", "")),
        "append_allowed": False,
        "requires_live_readback": True,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("state", type=Path)
    p.add_argument("index", type=Path)
    p.add_argument("position_url")
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    raw = a.state.read_bytes()
    index = json.loads(a.index.read_text(encoding="utf8"))
    r = plan(json.loads(raw), index["rows"], a.position_url)
    r.update(
        evidence_sha256=hashlib.sha256(raw).hexdigest(),
        created_at=datetime.now(timezone.utc).isoformat(),
        spreadsheet_id=index["spreadsheet_id"],
        tab=index["tab"],
        connector_write_performed=False,
    )
    with a.out.open("x", encoding="utf8") as f:
        json.dump(r, f, ensure_ascii=False, indent=2)
    print(json.dumps({k: r[k] for k in ("action", "connector_write_performed")}))


if __name__ == "__main__":
    main()
