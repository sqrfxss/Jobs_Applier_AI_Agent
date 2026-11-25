"""Headless, resumable, draft-only academic application workflow.

Single isolated browser context; no personal Chrome focus, OS file picker,
referee invitations, emails, legal consents, or final application Submit.
All navigation and Save actions must match the operator-reviewed manifest.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from aihawk.academic_background import exclusive_session
from aihawk.academic_account_verification import require_verified_account
from aihawk.academic_auth_gate import UserActionRequired, require_human_if_needed, save_public_checkpoint
from aihawk.academic_browser import PortalPreparationError, PreparationNetworkGuard, verified_portal_host
from aihawk.academic_browser_session import launch_academic_context, official_session_page
from aihawk.academic_stages import journey_from_manifest, prepare_stage, verify_stage_location
from aihawk.academic_uploads import receipt_present, upload_one, upload_plan_from_manifest

SAFE_DRAFT_BUTTONS = frozenset({"save", "save draft", "save changes"})


def _atomic_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def _verified_save_action(data: Any) -> dict:
    if not isinstance(data, dict):
        raise PortalPreparationError("Every autonomous stage requires an explicitly mapped draft_save action.")
    allowed = {"selector", "label", "receipt_selector", "receipt_text", "post_save_path"}
    if set(data) - allowed or not all(k in data for k in ("selector", "label", "receipt_selector", "receipt_text")):
        raise PortalPreparationError("Unknown or missing draft save review metadata.")
    for key in ("selector", "label", "receipt_selector", "receipt_text"):
        value = data[key]
        if not isinstance(value, str) or not value.strip() or len(value) > 300 or "\n" in value:
            raise PortalPreparationError("Invalid draft-save selector or confirmation.")
    if " ".join(data["label"].casefold().split()) not in SAFE_DRAFT_BUTTONS:
        raise PortalPreparationError("This action is not explicitly recognized as Save Draft.")
    path = data.get("post_save_path")
    if path is not None and (not isinstance(path, str) or not path.startswith("/") or path.startswith("//") or any(x in path for x in ("?", "#", "\r", "\n"))):
        raise PortalPreparationError("Invalid post-save path.")
    return dict(data)


def _activate_stage_tab(page: Any, stage: Any, stage_data: dict, hosts: tuple[str, ...]) -> None:
    """Open only a reviewed navigation tab, not an action or Submit control."""
    tab = stage_data.get("activate_tab")
    if tab is None:
        return
    if not isinstance(tab, dict) or set(tab) != {"selector", "label"} or any(not isinstance(v, str) or not v.strip() or len(v) > 250 for v in tab.values()):
        raise PortalPreparationError("A tab activation requires an exact reviewed selector and caption.")
    forbidden = ("submit", "send", "invite", "referee", "consent", "agree", "pay", "purchase", "delete")
    if any(word in tab["label"].casefold() for word in forbidden):
        raise PortalPreparationError("A stage tab cannot perform an irreversible application action.")
    node = page.locator(tab["selector"])
    if node.count() != 1 or not node.is_visible() or not node.is_enabled():
        raise PortalPreparationError("Expected university navigation tab missing or ambiguous.")
    info = node.evaluate(r"""e => ({
        tag:e.tagName.toLowerCase(),
        label:(e.textContent||'').trim().replace(/\s+/g,' '),
        type:(e.getAttribute('type')||'').toLowerCase()
    })""")
    if info["tag"] not in ("a", "button") or info["type"] == "submit":
        raise PortalPreparationError("Mapped stage navigation is not a safe tab.")
    if " ".join(info["label"].split()) != " ".join(tab["label"].split()):
        raise PortalPreparationError("University tab label changed from reviewed manifest.")
    node.click(timeout=5000)
    _allowlisted_stage_page(page, stage, hosts)


def _field_equals_review(page: Any, stage: Any) -> bool:
    """Readback on a NEW server-loaded page, never accept a local journal alone."""
    fields = dict(stage.form.preview.fields)
    for b in stage.form.bindings:
        node = page.locator(b.selector)
        if node.count() != 1:
            return False
        if b.kind in ("text", "select"):
            if node.input_value(timeout=3000) != fields[b.field]:
                return False
        elif b.kind == "choice":
            tag = node.evaluate("(e) => e.tagName.toLowerCase()")
            current = node.input_value(timeout=3000) if tag == "input" else node.inner_text(timeout=3000).strip()
            if current != fields[b.field].strip():
                return False
        else:
            # Local file-input state cannot verify a completed upload.
            raise PortalPreparationError("Use reviewed portal_uploads, not bare file input bindings.")
    return True


def _allowlisted_stage_page(page: Any, stage: Any, hosts: tuple[str, ...]) -> None:
    from aihawk.academic_portal_limits import check_access

    check_access(hosts)
    require_human_if_needed(page, official_hosts=hosts)
    try:
        verify_stage_location(page.url, stage, hosts)
    except PortalPreparationError as exc:
        raise PortalPreparationError("Stage unavailable or authentication expired; stop without submitting.") from exc


def _verify_server_persistence(page: Any, stage: Any, hosts: tuple[str, ...], stage_data: dict) -> None:
    from aihawk.academic_portal_limits import check_access

    check_access(hosts)
    page.goto(f"https://{stage.expected_host}{stage.expected_path}", wait_until="domcontentloaded", timeout=25000)
    _allowlisted_stage_page(page, stage, hosts)
    _activate_stage_tab(page, stage, stage_data, hosts)
    if not _field_equals_review(page, stage):
        raise PortalPreparationError("Draft Save did not persist all reviewed values after a new page load.")


def run_stage(
    page: Any,
    context: Any,
    stage: Any,
    hosts: tuple[str, ...],
    stage_data: dict,
    *,
    upload_plan: Any | None = None,
    already_confirmed: bool = False,
) -> dict:
    """Run one exact stage; server readback is mandatory before checkpoint."""
    started = time.perf_counter()
    _allowlisted_stage_page(page, stage, hosts)
    _activate_stage_tab(page, stage, stage_data, hosts)
    save = _verified_save_action(stage_data.get("draft_save"))
    for binding in stage.form.bindings:
        if binding.kind == "upload":
            raise PortalPreparationError("Bare upload binding is not a server receipt. Use portal_uploads.")
    uploads = []
    if upload_plan is not None:
        uploads = [mapping for mapping in upload_plan.bindings if mapping.expected_path == stage.expected_path]
    if already_confirmed:
        if not _field_equals_review(page, stage):
            raise PortalPreparationError("Previously saved stage no longer matches; refusing silent overwrite.")
        for mapping in uploads:
            container = page.locator(mapping.container_selector)
            if container.count() != 1 or not receipt_present(container, mapping, upload_plan.file_for(mapping.field)[0].name):
                raise PortalPreparationError("Previously confirmed file receipt is no longer visible.")
        return {
            "state": "reverified_no_change",
            "field_count": len(stage.form.bindings),
            "uploads": len(uploads),
            "elapsed_seconds": round(time.perf_counter() - started, 3),
        }

    # Use constrained locators; never touch desktop focus or activate personal Chrome.
    guard = PreparationNetworkGuard(hosts)
    context.route("**/*", guard)
    try:
        filled = prepare_stage(page, stage, hosts=hosts)
    finally:
        context.unroute("**/*", guard)
    # Exact file mappings are independently verified by a successful server response
    # plus an expected document link and removal control, without a native chooser.
    file_status = {}
    from aihawk.academic_portal_limits import check_access

    for mapping in uploads:
        check_access(hosts)
        from aihawk.academic_action_budget import ActionBudget

        ActionBudget().reserve_url(page.url, "upload", hosts)
        file_status[mapping.field] = upload_one(page, context, upload_plan, mapping)
    action = page.locator(save["selector"])
    if action.count() != 1 or not action.is_visible() or not action.is_enabled():
        raise PortalPreparationError("Reviewed draft Save control not visible and unique.")
    meta = action.evaluate("""e => ({
        tag: e.tagName.toLowerCase(),
        label: (e.value || e.textContent || '').replace(/\\s+/g, ' ').trim()
    })""")
    if meta["tag"] not in ("button", "input"):
        raise PortalPreparationError("Draft Save mapping must point to button/input.")
    if " ".join(meta["label"].casefold().split()) != " ".join(save["label"].casefold().split()):
        raise PortalPreparationError("The button caption changed; refusing possible final Submit.")
    if " ".join(meta["label"].casefold().split()) not in SAFE_DRAFT_BUTTONS:
        raise PortalPreparationError("Refusing non-draft form action.")
    check_access(hosts)
    from aihawk.academic_action_budget import ActionBudget

    ActionBudget().reserve_url(page.url, "draft_save", hosts)
    action.click(timeout=6000)
    expected_post = save.get("post_save_path", stage.expected_path)
    page.locator(save["receipt_selector"]).wait_for(state="visible", timeout=12000)
    label = page.locator(save["receipt_selector"])
    if label.count() != 1 or save["receipt_text"] not in label.inner_text(timeout=4000):
        raise PortalPreparationError("University did not display reviewed draft-save acknowledgement.")
    verified_portal_host(page.url, hosts)
    if urlsplit(page.url).path != expected_post:
        raise PortalPreparationError("Draft Save navigated somewhere unexpected.")
    _verify_server_persistence(page, stage, hosts, stage_data)
    for mapping in uploads:
        container = page.locator(mapping.container_selector)
        if container.count() != 1 or not receipt_present(container, mapping, upload_plan.file_for(mapping.field)[0].name):
            raise PortalPreparationError("Uploaded document has no server receipt after saving and reloading.")
    return {
        "state": "server_saved_verified",
        "field_count": len(filled),
        "uploads": file_status,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "blocked_during_field_prep": guard.blocked_requests,
    }


def run_background_journey(manifest: Path, report_path: Path) -> dict:
    """Prepare reviewed stages using one fast headless browser/profile.

    Resuming uses both a stable fingerprint and a fresh server-side readback.
    This never submits, invites, consents, or sends email.
    """
    manifest = manifest.resolve(strict=True)
    report_path = report_path.resolve()
    if manifest.parent != report_path.parent:
        raise PortalPreparationError("Private report must remain beside private manifest.")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    require_verified_account(data, manifest_dir=manifest.parent)
    journey = journey_from_manifest(data, manifest_dir=manifest.parent)
    stages_data = data["portal_stages"]
    auth_callback = None
    if data.get("oracle_auth"):
        from aihawk.academic_live_auth import reviewed_auth_callback

        auth_callback = reviewed_auth_callback(data["oracle_auth"], journey)
    for s in stages_data:
        _verified_save_action(s.get("draft_save"))
    upload_plan = None
    if data.get("portal_uploads"):
        upload_plan = upload_plan_from_manifest(data, manifest_dir=manifest.parent)
        known_paths = {stage.expected_path for stage in journey.stages}
        if any(u.expected_path not in known_paths for u in upload_plan.bindings):
            raise PortalPreparationError("An upload references a page not present in the reviewed journey.")
    reviewed_actions = {
        "journey": journey.fingerprint(),
        "saves": [_verified_save_action(item["draft_save"]) for item in stages_data],
        "tabs": [item.get("activate_tab") for item in stages_data],
        "uploads": upload_plan.fingerprint() if upload_plan is not None else None,
    }
    fingerprint = hashlib.sha256(json.dumps(reviewed_actions, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    previous = {}
    if report_path.exists():
        previous = json.loads(report_path.read_text(encoding="utf-8"))
    prior = previous.get("stages", {}) if previous.get("fingerprint") == fingerprint else {}
    report = {
        "schema_version": "aihawk.academic.headless-draft.v1",
        "fingerprint": fingerprint,
        "result": "running",
        "browser": "isolated_headless",
        "emails_sent": False,
        "final_submission": False,
        "personal_chrome_controlled": False,
        "stages": dict(prior),
    }
    started = time.perf_counter()
    _atomic_json(report_path, report)
    with exclusive_session(manifest.parent):
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            context = launch_academic_context(playwright, manifest_dir=manifest.parent, headless=auth_callback is None)
            try:
                page = official_session_page(context, url=journey.starting_url, official_hosts=journey.hosts)
                if auth_callback is not None:
                    auth_callback(page)
                for stage, stage_data in zip(journey.stages, stages_data, strict=True):
                    stage_url = f"https://{stage.expected_host}{stage.expected_path}"
                    from aihawk.academic_portal_limits import check_access

                    check_access(journey.hosts)
                    if page.url != stage_url:
                        require_human_if_needed(page, official_hosts=journey.hosts)
                        page.goto(stage_url, wait_until="domcontentloaded", timeout=25000)
                    try:
                        outcome = run_stage(
                            page,
                            context,
                            stage,
                            journey.hosts,
                            stage_data,
                            upload_plan=upload_plan,
                            already_confirmed=report["stages"].get(stage.name, {}).get("state")
                            in (
                                "server_saved_verified",
                                "reverified_no_change",
                            ),
                        )
                        report["stages"][stage.name] = outcome
                        _atomic_json(report_path, report)
                    except UserActionRequired as error:
                        report["result"] = "needs_user_action"
                        report["stopped_at"] = stage.name
                        report["user_action"] = error.challenge.public_record()
                        report["elapsed_seconds"] = round(time.perf_counter() - started, 3)
                        save_public_checkpoint(manifest.parent / ".aihawk-auth-checkpoint.json", error.challenge)
                        _atomic_json(report_path, report)
                        return report
                    except Exception as error:
                        report["result"] = "stopped_needs_review"
                        report["stopped_at"] = stage.name
                        report["error"] = str(error)[:400]
                        report["elapsed_seconds"] = round(time.perf_counter() - started, 3)
                        _atomic_json(report_path, report)
                        return report
            finally:
                context.close()
    report["result"] = "all_draft_stages_saved_verified"
    report["elapsed_seconds"] = round(time.perf_counter() - started, 3)
    report["recorded_utc"] = datetime.now(timezone.utc).isoformat()
    _atomic_json(report_path, report)
    return report


def run_background_journey_reported(manifest: Path, report_path: Path) -> dict:
    """Never leave a 'running' checkpoint after an expected portal/login failure."""
    try:
        return run_background_journey(manifest, report_path)
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
