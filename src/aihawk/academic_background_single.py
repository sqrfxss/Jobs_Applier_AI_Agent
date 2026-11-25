"""Single-page headless draft Save with authoritative server readback.

Never invites referees, sends emails, changes consents, or final-submits.
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from aihawk.academic_background import exclusive_session
from aihawk.academic_auth_gate import UserActionRequired, save_public_checkpoint
from aihawk.academic_background_journey import _atomic_json, _verified_save_action, run_stage
from aihawk.academic_browser import PortalPreparationError, plan_from_manifest, verified_portal_host
from aihawk.academic_browser_session import launch_academic_context, official_session_page
from aihawk.academic_stages import PortalStage
from aihawk.academic_uploads import upload_plan_from_manifest


def run_background_draft(manifest: Path, report_path: Path) -> dict:
    manifest = manifest.resolve(strict=True)
    report_path = report_path.resolve()
    if report_path.parent != manifest.parent:
        raise PortalPreparationError("Report and manifest must be inside the same private application folder.")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if "portal_stages" in data:
        raise PortalPreparationError("Multi-page application requires background-journey.")
    form = plan_from_manifest(data, manifest_dir=manifest.parent)
    url = urlsplit(form.preview.opportunity_url)
    host = verified_portal_host(form.preview.opportunity_url, form.hosts)
    stage = PortalStage("Application draft", host, url.path or "/", form)
    save = _verified_save_action(data.get("draft_save"))
    upload_plan = None
    if data.get("portal_uploads"):
        upload_plan = upload_plan_from_manifest(data, manifest_dir=manifest.parent)
        if any(m.expected_path != stage.expected_path for m in upload_plan.bindings):
            raise PortalPreparationError("Single-page upload mapping references another route.")
    reviewed = {
        "form": form.fingerprint(),
        "save": save,
        "uploads": upload_plan.fingerprint() if upload_plan is not None else None,
    }
    signature = hashlib.sha256(json.dumps(reviewed, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    previous = {}
    if report_path.exists():
        previous = json.loads(report_path.read_text(encoding="utf-8"))
    already = previous.get("fingerprint") == signature and (previous.get("result") == "server_saved_verified" or previous.get("last_verified_saved") is True)
    report = {
        "schema_version": "aihawk.academic.headless-single-draft.v1",
        "fingerprint": signature,
        "last_verified_saved": already,
        "result": "running",
        "personal_chrome_controlled": False,
        "emails_sent": False,
        "final_submission": False,
    }
    _atomic_json(report_path, report)
    started = time.perf_counter()
    with exclusive_session(manifest.parent):
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            context = launch_academic_context(playwright, manifest_dir=manifest.parent, headless=True)
            try:
                page = official_session_page(context, url=form.preview.opportunity_url, official_hosts=form.hosts)
                try:
                    outcome = run_stage(
                        page,
                        context,
                        stage,
                        form.hosts,
                        data,
                        upload_plan=upload_plan,
                        already_confirmed=already,
                    )
                    report.update(outcome)
                    report["result"] = "server_saved_verified"
                    report["last_verified_saved"] = True
                except UserActionRequired as error:
                    report["result"] = "needs_user_action"
                    report["user_action"] = error.challenge.public_record()
                    save_public_checkpoint(manifest.parent / ".aihawk-auth-checkpoint.json", error.challenge)
                except Exception as error:
                    report["result"] = "stopped_needs_review"
                    report["error"] = str(error)[:400]
            finally:
                context.close()
    report["recorded_utc"] = datetime.now(timezone.utc).isoformat()
    report["elapsed_seconds_total"] = round(time.perf_counter() - started, 3)
    _atomic_json(report_path, report)
    return report


def run_background_draft_reported(manifest: Path, report_path: Path) -> dict:
    """Record authentication, browser, or portal failures without fake success."""
    try:
        return run_background_draft(manifest, report_path)
    except UserActionRequired as error:
        status = {}
        if report_path.exists():
            try:
                status = json.loads(report_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
        status.update(
            {
                "result": "needs_user_action",
                "user_action": error.challenge.public_record(),
                "emails_sent": False,
                "final_submission": False,
                "personal_chrome_controlled": False,
            }
        )
        save_public_checkpoint(manifest.parent / ".aihawk-auth-checkpoint.json", error.challenge)
        _atomic_json(report_path, status)
        return status
    except Exception as error:
        status = {}
        if report_path.exists():
            try:
                status = json.loads(report_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
        status.update(
            {
                "result": "stopped_needs_review",
                "error": str(error)[:400],
                "emails_sent": False,
                "final_submission": False,
                "personal_chrome_controlled": False,
            }
        )
        _atomic_json(report_path, status)
        return status
