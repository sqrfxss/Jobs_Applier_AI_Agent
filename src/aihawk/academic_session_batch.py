"""Resumable draft-only application stages; every saved stage requires server readback."""

from __future__ import annotations
from pathlib import Path
from time import perf_counter
from datetime import datetime, timezone
from aihawk.academic_browser import PortalPreparationError
from aihawk.academic_field_journal import seed_plan, record as field_record
from aihawk.academic_outreach_workflow import atomic_json
from aihawk.academic_session_progress import (
    verify_stage,
    should_skip_verified_stage,
    update,
)

ALLOWED = ("About You", "Address", "Qualifications", "Employment", "References", "Additional Information")


def auth_expired(page, hosts, title):
    from aihawk.academic_browser import verified_portal_host

    try:
        verified_portal_host(page.url, hosts)
        if page.locator('input[type="password"]:visible').count():
            return True
        marker = page.get_by_text(title, exact=True)
        if marker.count() == 1 and marker.is_visible():
            return False
        path = page.url.lower()
        return "/siw_ipp_lgn." in path or "/login" in path
    except Exception:
        return True


def settle_project_identity(page, hosts, title, *, seconds=5):
    """Classify a delayed university redirect without replaying a POST.

    A blank/intermediate document is not evidence that the login is still
    valid. Stop the batch instead of trying subsequent sections on it.
    """
    from time import monotonic

    deadline = monotonic() + seconds
    while not page.is_closed():
        if auth_expired(page, hosts, title):
            return "authentication_required"
        try:
            identity = page.get_by_text(title, exact=True)
            if identity.count() == 1 and identity.is_visible():
                return "authenticated"
        except Exception:
            pass
        if monotonic() >= deadline:
            break
        page.wait_for_timeout(250)
    return "unverified_portal"


def _open_modal(page):
    dialogs = page.get_by_role("dialog")
    return any(dialogs.nth(i).is_visible() for i in range(dialogs.count()))


def run_batch(page, folder, hosts, title, plan):
    from aihawk.academic_session_controls import navigate, apply_plan, save_draft, inventory

    folder = Path(folder).resolve(strict=True)
    if plan.get("schema") != "aihawk.session.batch.v1" or plan.get("project_title") != title:
        raise PortalPreparationError("Reviewed batch plan required")
    if plan.get("final_submission", False) is not False:
        raise PortalPreparationError("Final submission must be disabled")
    stages = plan.get("stages")
    if not isinstance(stages, list) or not stages:
        raise PortalPreparationError("No reviewed application stages")
    names = [s.get("section") for s in stages]
    if len(set(names)) != len(names) or any(n not in ALLOWED for n in names):
        raise PortalPreparationError("Duplicate/unreviewed stage or final declaration")
    seed_plan(folder, plan)
    report = {"schema": "aihawk.batch.report.v2", "final_submission": False, "status": "running", "stages": [], "all_sections_verified": False}

    def record():
        report["checked_at"] = datetime.now(timezone.utc).isoformat()
        atomic_json(folder / "Session_Batch_Report.json", report)

    record()
    for stage in stages:
        began = perf_counter()
        section = stage["section"]
        row = {"section": section, "state": "started", "server_saved_verified": False}
        report["stages"].append(row)
        record()

        def stage_record(state, *, verified=False, reason=None):
            ms = round((perf_counter() - began) * 1000)
            row.update(state=state, server_saved_verified=verified, duration_ms=ms)
            if reason:
                row["reason"] = reason[:180]
            # Login expiry alone does not invalidate a previously server-
            # verified saved stage. Re-read it after reauthentication.
            if state != "awaiting_manual_login":
                update(folder, stage, state, verified=verified, duration_ms=ms, reason=reason)
            record()
            try:
                field_record(
                    folder,
                    stage=section,
                    field="_stage",
                    action="batch",
                    status=("server_verified" if verified else "stage_blocked"),
                    details=state,
                    error_type=reason and "StageProblem" or None,
                    elapsed_ms=ms,
                )
            except OSError:
                raise

        if auth_expired(page, hosts, title):
            stage_record("awaiting_manual_login", reason="Authenticated portal session expired")
            report["status"] = "awaiting_manual_login"
            record()
            return report
        if _open_modal(page):
            stage_record("blocked_modal_review_required", reason="Incomplete document dialog needs reconciliation")
            report["status"] = "blocked_modal_review_required"
            record()
            return report
        try:
            if should_skip_verified_stage(page, folder, stage, hosts, title):
                stage_record("server_readback_verified", verified=True)
                row["resume"] = "verified_saved_stage_skipped"
                record()
                continue
            if _open_modal(page):
                raise PortalPreparationError("Unresolved university upload dialog")
            heading = stage["visible_heading"]
            navigate(page, hosts, title, section, expected_heading=heading)
            h = page.get_by_role("heading", name=heading, exact=True)
            if h.count() != 1 or not h.is_visible():
                raise PortalPreparationError("Expected portal stage heading missing")
            if stage.get("reviewed_complete") is not True:
                atomic_json(folder / "Session_Inventory.json", inventory(page, hosts, title))
                stage_record("mapping_review_required")
                if plan.get("continue_on_stage_error") is True:
                    continue
                report["status"] = "blocked"
                record()
                return report
            draft = {
                "schema": "aihawk.session.draft.v1",
                "project_title": title,
                "section": section,
                "visible_heading": heading,
                "actions": stage.get("actions", []),
            }
            row["controls"] = apply_plan(page, folder, hosts, title, draft)
            if stage.get("save_after_actions") is False:
                stage_record("fields_prepared_not_server_saved")
                continue
            # Every save is one action. Confirmation comes from a new request,
            # not from the click itself or from the prior tab's local input value.
            next_heading = stage.get("next_visible_heading")
            if not next_heading:
                raise PortalPreparationError("No reviewed next-stage heading for save verification")
            row["save"] = save_draft(page, hosts, title, expected_next_heading=next_heading, folder=folder)
            verify_stage(page, stage, hosts, title, navigate_to=True, folder=folder)
            stage_record("server_readback_verified", verified=True)
        except Exception as exc:
            kind = type(exc).__name__
            reason = str(exc)[:180]
            row["error_type"] = kind
            # Section navigations may replace the DOM asynchronously. If the
            # project vanished, settle the redirect before touching any other
            # university form. No speculative request or login replay.
            identity = settle_project_identity(page, hosts, title)
            if identity == "authentication_required":
                stage_record("awaiting_manual_login", reason="Portal session returned to university login")
                report["status"] = "awaiting_manual_login"
                record()
                return report
            if identity == "unverified_portal":
                stage_record("portal_identity_unverified", reason="Project identity absent after university navigation")
                report["status"] = "portal_unverified"
                record()
                return report
            if auth_expired(page, hosts, title):
                stage_record("awaiting_manual_login", reason=reason)
                report["status"] = "awaiting_manual_login"
                record()
                return report
            if _open_modal(page):
                stage_record("blocked_modal_review_required", reason=reason)
                report["status"] = "blocked_modal_review_required"
                record()
                return report
            stage_record("blocked", reason=reason)
            if plan.get("continue_on_stage_error") is not True:
                report["status"] = "blocked"
                record()
                return report
    report["all_sections_verified"] = set(names) == set(ALLOWED) and all(x["server_saved_verified"] for x in report["stages"])
    report["status"] = "reviewed_stages_completed" if report["all_sections_verified"] else "partially_prepared_review_required"
    record()
    return report
