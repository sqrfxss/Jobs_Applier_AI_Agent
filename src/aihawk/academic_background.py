"""Non-interactive, isolated academic form preparation.

No personal Chrome tab switching, keyboard injection, form submission,
referee invitations, emails or consent decisions. A separately authenticated,
per-application Playwright browser profile is required for private portals.
"""
from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from typing import Any

from aihawk.academic_browser import (
    PortalPreparationError,
    PreparationNetworkGuard,
    plan_from_manifest,
    prepare_fields,
    verified_portal_host,
)
from aihawk.academic_browser_session import launch_academic_context, official_session_page


@contextmanager
def exclusive_session(manifest_dir: Path):
    """OS-managed, cross-process lock; process death releases it automatically.

    Keep the lock file permanently so file-unlink races cannot create two owners.
    """
    lock = manifest_dir / ".aihawk-background.lock"
    fd = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
    acquired = False
    try:
        if os.fstat(fd).st_size == 0:
            os.write(fd, b" ")
        os.lseek(fd, 0, os.SEEK_SET)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
        except (OSError, BlockingIOError) as exc:
            raise PortalPreparationError(
                "Another academic background job is using this private browser profile."
            ) from exc
        os.ftruncate(fd, 0)
        os.lseek(fd, 0, os.SEEK_SET)
        os.write(fd, str(os.getpid()).encode("ascii"))
        os.fsync(fd)
        yield
    finally:
        if acquired:
            os.lseek(fd, 0, os.SEEK_SET)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def background_prepare_page(context: Any, page: Any, plan: Any, *, inspect_only: bool = False) -> dict:
    """Prepare reviewed fields without operating-system GUI interaction.

    This function never clicks buttons or saves/submits university forms.
    """
    expected = urlsplit(plan.preview.opportunity_url)
    verified_portal_host(page.url, plan.hosts)
    actual = urlsplit(page.url)
    if actual.path != expected.path:
        raise PortalPreparationError(
            "Not on the reviewed form path. The isolated browser may need one-time "
            "interactive university login; no personal Chrome cookies are used."
        )
    start = time.perf_counter()
    if inspect_only:
        from aihawk.academic_inspect import inspect_controls

        data = inspect_controls(page, official_hosts=plan.hosts)
        return {
            "result": "inspected_no_changes",
            "controls": len(data["controls"]),
            "elapsed_seconds": round(time.perf_counter() - start, 3),
            "browser_mode": "isolated_headless",
        }
    guard = PreparationNetworkGuard(plan.hosts)
    context.route("**/*", guard)
    try:
        prepared = prepare_fields(page, plan)
        return {
            "result": "prepared_not_saved_or_submitted",
            "prepared_fields": list(prepared),
            "field_count": len(prepared),
            "blocked_network_requests": guard.blocked_requests,
            "elapsed_seconds": round(time.perf_counter() - start, 3),
            "browser_mode": "isolated_headless",
        }
    finally:
        context.unroute("**/*", guard)


def run_background(manifest: Path, output: Path, *, inspect_only: bool = False) -> dict:
    """Use a distinct persistent profile; never attach to the user's Chrome."""
    manifest = manifest.resolve(strict=True)
    output = output.resolve()
    if output.parent != manifest.parent:
        raise PortalPreparationError("Background report must stay beside the private manifest.")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if inspect_only and data.get("portal_bindings") == []:
        # Safe public read-only inspection without pretending to have an approved
        # applicant field mapping. Normal preparation still requires bindings.
        from types import SimpleNamespace

        url = data.get("official_application_url")
        hosts = data.get("official_hosts")
        if (
            not isinstance(url, str)
            or not isinstance(hosts, list)
            or not hosts
            or any(not isinstance(host, str) or not host for host in hosts)
            or not url.startswith("https://")
        ):
            raise PortalPreparationError("Inspect-only page needs an exact HTTPS URL and approved hosts.")
        verified_portal_host(url, tuple(hosts))
        plan = SimpleNamespace(
            preview=SimpleNamespace(opportunity_url=url), hosts=tuple(hosts)
        )
    else:
        plan = plan_from_manifest(data, manifest_dir=manifest.parent)
    from playwright.sync_api import sync_playwright

    with exclusive_session(manifest.parent):
        with sync_playwright() as playwright:
            context = launch_academic_context(
                playwright, manifest_dir=manifest.parent, headless=True
            )
            try:
                page = official_session_page(
                    context, url=plan.preview.opportunity_url, official_hosts=plan.hosts
                )
                report = background_prepare_page(
                    context, page, plan, inspect_only=inspect_only
                )
            finally:
                context.close()
        report["recorded_utc"] = datetime.now(timezone.utc).isoformat()
        report["approved_host"] = verified_portal_host(plan.preview.opportunity_url, plan.hosts)
        report["final_submission"] = False
        report["emails_sent"] = False
        report["personal_chrome_controlled"] = False
        tmp = output.with_name(output.name + ".tmp")
        try:
            tmp.write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            os.replace(tmp, output)
        finally:
            if tmp.exists():
                tmp.unlink()
        return report
