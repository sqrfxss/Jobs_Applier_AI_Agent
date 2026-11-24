"""Case-isolated, resumable operator session. Never import personal browser state."""

from __future__ import annotations
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime, timezone
from urllib.parse import urlsplit
import json
import os
import queue
import threading
from aihawk.academic_browser import PortalPreparationError, verified_portal_host
from aihawk.academic_browser_session import launch_academic_context, official_session_page, private_profile_dir
from aihawk.academic_outreach_workflow import atomic_json
from aihawk.academic_portal_limits import check_access


@contextmanager
def case_lock(folder):
    """OS lock released automatically if the process exits or crashes."""
    folder = folder.resolve(strict=True)
    private_profile_dir(folder, create=True)
    lock = folder / ".aihawk-session.lock"
    if lock.is_symlink():
        raise PortalPreparationError("Unsafe session lock")
    f = lock.open("a+b")
    acquired = False
    try:
        f.seek(0, 2)
        if f.tell() == 0:
            f.write(b"0")
            f.flush()
        f.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except OSError as exc:
            raise PortalPreparationError("Case already has an active session; do not open another browser.") from exc
        yield
    finally:
        if acquired:
            f.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        f.close()


def read_case(folder):
    p = folder / "Execution_Case.json"
    config = json.loads(p.read_text(encoding="utf8"))
    url = config["official_application_url"]
    hosts = tuple(config["official_hosts"])
    verified_portal_host(url, hosts)
    title = config.get("portal_project_title")
    if not isinstance(title, str) or not title.strip():
        raise PortalPreparationError("Reviewed exact project title required")
    return config, url, hosts, title


def inspect_page(page, hosts, title):
    verified_portal_host(page.url, hosts)
    check_access(hosts)
    # Only read exact, visible project marker and section controls; never form values.
    project = page.get_by_text(title, exact=True)
    matched = project.count() == 1 and project.is_visible()
    sections = []
    for name in ("About You", "Address", "Qualifications", "Employment", "References", "Additional Information", "Declaration and Submission"):
        item = page.get_by_role("button", name=name, exact=True)
        if matched and item.count() == 1 and item.is_visible():
            sections.append(name)
    login = page.locator('input[type="password"]:visible').count() > 0
    return {
        "status": "project_session_verified" if matched and sections else "manual_sign_in_required" if login else "unverified_page",
        "host": urlsplit(page.url).hostname,
        "path": urlsplit(page.url).path,
        "project_marker_verified": matched,
        "visible_section_controls": sections,
        "server_saved_fields_verified": False,
        "final_submission": False,
    }


def checkpoint(folder, report):
    atomic_json(folder / "Session_Checkpoint.json", {"schema": "aihawk.session.checkpoint.v1", "checked_at": datetime.now(timezone.utc).isoformat(), **report})


def wait_command(page, *, read=input, interval_ms=200):
    """Keep Playwright's event loop servicing intercepted requests during manual login."""
    from playwright.sync_api import Error as PlaywrightError

    result = queue.Queue(maxsize=1)

    def reader():
        try:
            result.put(read("SESSION [inspect / inventory / section NAME / apply / save / batch / scan / resume / diagnose_dates / recover / close]: ").strip())
        except (EOFError, KeyboardInterrupt):
            result.put("close")

    threading.Thread(target=reader, daemon=True).start()
    while True:
        if page.is_closed():
            return "browser_closed"
        try:
            return result.get_nowait()
        except queue.Empty:
            pass
        try:
            page.wait_for_timeout(interval_ms)
        except PlaywrightError:
            if page.is_closed():
                return "browser_closed"
            raise


def wait_for_project(page, hosts, title, timeout_seconds=None):
    from time import monotonic

    end = monotonic() + timeout_seconds if timeout_seconds is not None else None
    while not page.is_closed() and (end is None or monotonic() < end):
        if inspect_page(page, hosts, title)["status"] == "project_session_verified":
            return True
        page.wait_for_timeout(500)
    return False


def capture_session_error(page, folder, exc):
    """Best-effort private screenshot and diagnostic; never print form content."""
    from datetime import datetime, timezone

    artifact = {"type": type(exc).__name__, "detail": str(exc)[:700], "timestamp": datetime.now(timezone.utc).isoformat(), "final_submission": False}
    try:
        artifact["page_title"] = page.title()
        artifact["path"] = urlsplit(page.url).path
        artifact["browser_page_closed"] = page.is_closed()
    except Exception:
        pass
    try:
        page.screenshot(path=str(folder / "Session_Failure.png"), timeout=3500)
        artifact["screenshot"] = "Session_Failure.png"
    except Exception:
        pass
    checkpoint(folder, {"status": "recoverable_portal_error", **artifact})
    return artifact


def _write_runtime(folder, status, **extra):
    """Expose whether the agent is executing or waiting for human commands."""
    atomic_json(
        folder / "Agent_Runtime_Status.json",
        {"schema": "aihawk.agent.runtime.v1", "checked_at": datetime.now(timezone.utc).isoformat(), "status": status, "final_submission": False, **extra},
    )


def run(folder, *, auto=False):
    folder = folder.resolve(strict=True)
    config, url, hosts, title = read_case(folder)
    if auto and not (folder / "Session_Batch_Plan.json").is_file():
        raise PortalPreparationError("Reviewed batch mapping missing; no browser opened.")
    if auto:
        batch = json.loads((folder / "Session_Batch_Plan.json").read_text(encoding="utf-8-sig"))
        if batch.get("schema") != "aihawk.session.batch.v1" or batch.get("project_title") != title:
            raise PortalPreparationError("Invalid batch plan; no browser opened")
        if batch.get("final_submission") is not False or batch.get("continue_on_stage_error") is not True:
            raise PortalPreparationError("Final submission must be disabled; stop-after-error decisions must be explicit")
    last_batch_status = None
    last_command = None
    last_error = None
    attempted_blank_recovery = False
    with case_lock(folder):
        from playwright.sync_api import sync_playwright, Error as PlaywrightError

        with sync_playwright() as p:
            c = launch_academic_context(p, manifest_dir=folder, headless=False)
            try:
                page = official_session_page(c, url=url, official_hosts=hosts)
                if auto:
                    plan_path = folder / "Session_Batch_Plan.json"
                    if not plan_path.is_file():
                        raise PortalPreparationError("Reviewed batch mapping missing; do not request login before preparation.")
                    from aihawk.academic_session_supervisor import supervise

                    try:
                        report = supervise(page, folder, hosts, title, plan_path)
                        last_batch_status = report.get("status", "unknown")
                        _write_runtime(
                            folder,
                            "automatic_batch_stopped",
                            batch_status=last_batch_status,
                            all_sections_verified=report.get("all_sections_verified", False),
                            awaiting_manual_commands=True,
                        )
                        print(json.dumps(report, ensure_ascii=False), flush=True)
                    except Exception as exc:
                        last_batch_status = "batch_interrupted"
                        last_error = type(exc).__name__
                        _write_runtime(folder, "automatic_batch_interrupted", batch_status=last_batch_status, last_error=last_error)
                        print(json.dumps({"status": "batch_interrupted", "error": type(exc).__name__, "final_submission": False}), flush=True)
                        capture_session_error(page, folder, exc)
                    # Automatically resume once after a later manual sign-in.
                    # No password, MFA or CAPTCHA is solved by the agent.
                    if last_batch_status in ("authentication_required", "awaiting_manual_login"):
                        from time import monotonic

                        next_report = 0
                        while not page.is_closed():
                            state = inspect_page(page, hosts, title)["status"]
                            if state == "project_session_verified":
                                _write_runtime(folder, "authenticated_resuming_draft", awaiting_manual_commands=False)
                                refreshed = supervise(page, folder, hosts, title, plan_path)
                                last_batch_status = refreshed.get("status", "unknown")
                                _write_runtime(
                                    folder,
                                    "automatic_batch_stopped",
                                    batch_status=last_batch_status,
                                    all_sections_verified=refreshed.get("all_sections_verified", False),
                                    awaiting_manual_commands=True,
                                )
                                print(json.dumps(refreshed, ensure_ascii=False), flush=True)
                                break
                            if monotonic() >= next_report:
                                _write_runtime(
                                    folder,
                                    "waiting_for_manual_login",
                                    authenticated=False,
                                    awaiting_manual_commands=False,
                                    batch_status="authentication_required",
                                    automatic_resume_after_login=True,
                                )
                                next_report = monotonic() + 10
                            page.wait_for_timeout(1000)
                    # Retain the same authenticated window for review.
                while True:
                    if page.is_closed():
                        checkpoint(folder, {"status": "browser_closed", "final_submission": False})
                        break
                    try:
                        report = inspect_page(page, hosts, title)
                    except PlaywrightError as exc:
                        capture_session_error(page, folder, exc)
                        report = {"status": "page_inspection_failed", "final_submission": False}
                    checkpoint(folder, report)
                    print(json.dumps(report), flush=True)
                    if auto and report.get("status") == "unverified_page" and not attempted_blank_recovery:
                        from aihawk.academic_blank_recovery import recover_once

                        recovery = recover_once(page, folder, hosts, title, url)
                        attempted_blank_recovery = True
                        print(json.dumps({"recovery": recovery["status"], "final_submission": False}), flush=True)
                        if recovery["status"] == "project_restored":
                            continue
                    _write_runtime(
                        folder,
                        ("idle_waiting_for_command" if report.get("status") == "project_session_verified" else "waiting_for_manual_login"),
                        batch_status=last_batch_status,
                        last_command=last_command,
                        last_error=last_error,
                        authenticated=(report.get("status") == "project_session_verified"),
                        awaiting_manual_commands=True,
                    )
                    try:
                        cmd = wait_command(page)
                    except PlaywrightError as exc:
                        capture_session_error(page, folder, exc)
                        if page.is_closed():
                            break
                        continue
                    if cmd in ("close", "browser_closed"):
                        if cmd == "browser_closed":
                            checkpoint(folder, {"status": "browser_closed", "final_submission": False})
                        break
                    last_command = cmd.split(" ", 1)[0] if cmd else None
                    last_error = None
                    _write_runtime(folder, "executing_command", batch_status=last_batch_status, last_command=last_command, awaiting_manual_commands=False)
                    try:
                        from aihawk.academic_session_controls import inventory, navigate, apply_plan, save_draft

                        if cmd == "inventory":
                            controls = inventory(page, hosts, title)
                            atomic_json(folder / "Session_Inventory.json", controls)
                            print(json.dumps(controls), flush=True)
                        elif cmd.startswith("section "):
                            navigate(page, hosts, title, cmd[8:])
                            controls = inventory(page, hosts, title)
                            atomic_json(folder / "Session_Inventory.json", controls)
                            print(json.dumps(controls), flush=True)
                        elif cmd == "apply":
                            plan = json.loads((folder / "Session_Draft_Plan.json").read_text(encoding="utf8"))
                            print(json.dumps(apply_plan(page, folder, hosts, title, plan)), flush=True)
                        elif cmd == "scan":
                            from aihawk.academic_session_scan import scan_all

                            print(json.dumps(scan_all(page, folder, hosts, title)), flush=True)
                        elif cmd in ("batch", "resume"):
                            from aihawk.academic_session_supervisor import supervise

                            print(json.dumps(supervise(page, folder, hosts, title, folder / "Session_Batch_Plan.json")), flush=True)
                        elif cmd == "save":
                            print(json.dumps(save_draft(page, hosts, title, folder=folder)), flush=True)
                        elif cmd == "diagnose_dates":
                            from aihawk.academic_date_probe import probe

                            print(json.dumps(probe(page, folder, hosts, title)), flush=True)
                        elif cmd == "recover":
                            from aihawk.academic_blank_recovery import recover_once

                            print(json.dumps(recover_once(page, folder, hosts, title, url)), flush=True)
                        elif cmd != "inspect":
                            print("No action; unsupported command.", flush=True)
                    except (PortalPreparationError, ValueError, KeyError, OSError, PlaywrightError) as exc:
                        last_error = type(exc).__name__ + ": " + str(exc)[:140]
                        capture_session_error(page, folder, exc)
                        print("Draft action blocked: " + type(exc).__name__ + ": " + str(exc)[:220], flush=True)
                        # Preserve the authenticated browser/context after a recoverable
                        # navigation, DOM, or validation exception. Do not exit to finally.
            except PlaywrightError as exc:
                # Preserve the reason: a blank response, renderer crash, closed
                # page or timeout must not collapse to a generic "interrupted".
                import re

                detail = re.sub(r"https?://\S+", "[portal_url]", str(exc))
                detail = re.sub(r"[\w.+-]+@[\w.-]+", "[email]", detail)[:500]
                diagnostic = {
                    "schema": "aihawk.browser.error.v1",
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                    "status": "browser_interrupted",
                    "error_type": type(exc).__name__,
                    "details": detail,
                    "final_submission": False,
                }
                atomic_json(folder / "Agent_Browser_Error.json", diagnostic)
                checkpoint(folder, {"status": "browser_interrupted", "error_type": type(exc).__name__, "final_submission": False})
                _write_runtime(folder, "browser_interrupted", error_type=type(exc).__name__, awaiting_manual_commands=False)
                print(json.dumps({"browser": "interrupted", "error_type": type(exc).__name__, "final_submission": False}), flush=True)
            finally:
                try:
                    c.close()
                except PlaywrightError:
                    pass


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    parser.add_argument("--auto", action="store_true")
    args = parser.parse_args()
    run(args.folder, auto=args.auto)
