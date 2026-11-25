"""Isolated persistent academic browser sessions (not the personal Chrome profile).

A single university application may reuse its own Playwright user-data directory.
This does NOT connect to an existing personal Chrome process through CDP and
does NOT import cookies, passwords or browser profiles from the user's Chrome.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from aihawk.academic_browser import PortalPreparationError, verified_portal_host

PROFILE_DIRNAME = ".aihawk-academic-session"


def private_profile_dir(manifest_dir: Path, *, create: bool = True) -> Path:
    """Constrain browser identity state to an untracked private application folder."""
    root = manifest_dir.resolve(strict=True)
    if not root.is_dir():
        raise PortalPreparationError("The private application directory is unavailable.")
    if any((ancestor / ".git").exists() for ancestor in (root, *root.parents)):
        raise PortalPreparationError("Browser session secrets must not reside inside a Git repository.")
    destination = root / PROFILE_DIRNAME
    if destination.is_symlink():
        raise PortalPreparationError("Refusing a symlinked browser-profile directory.")
    if create:
        destination.mkdir(mode=0o700, parents=False, exist_ok=True)
        try:
            if os.name != "nt":
                destination.chmod(0o700)
        except OSError:
            pass
    return destination


def launch_academic_context(playwright: Any, *, manifest_dir: Path, headless: bool = False) -> Any:
    """Launch exactly one persistent, locally managed Playwright browser context.

    Fallback to installed Chrome/Edge is allowed only if the Playwright
    browser executable is missing, not for launch crashes or access failures.
    """
    profile = private_profile_dir(manifest_dir)
    unavailable: list[str] = []
    for channel in (None, "chrome", "msedge"):
        options: dict[str, Any] = {
            "user_data_dir": str(profile),
            "headless": headless,
            "service_workers": "block",
            "accept_downloads": False,
        }
        if channel is not None:
            options["channel"] = channel
        try:
            return playwright.chromium.launch_persistent_context(**options)
        except Exception as error:
            if "executable doesn't exist" not in str(error).casefold():
                raise
            unavailable.append(channel or "playwright-chromium")
    raise PortalPreparationError("No supported local Chromium browser found. Tried: " + ", ".join(unavailable))


def official_session_page(context: Any, *, url: str, official_hosts: tuple[str, ...]) -> Any:
    """Reuse only the matching institutional tab; never inspect other tabs."""
    expected = verified_portal_host(url, official_hosts)
    from aihawk.academic_portal_limits import attach_limits

    attach_limits(context, official_hosts)
    other_pages = [page for page in context.pages if page.url != "about:blank"]
    selected = [page for page in other_pages if _matching_host(page.url, expected, official_hosts)]
    if len(selected) > 1:
        raise PortalPreparationError("Multiple institutional tabs: select one explicitly before proceeding.")
    if other_pages and len(selected) != len(other_pages):
        raise PortalPreparationError("Unexpected tabs in the dedicated profile; refuse ambiguous browser context.")
    if selected:
        return selected[0]
    page = context.pages[0] if context.pages else context.new_page()
    from aihawk.academic_action_budget import ActionBudget

    ActionBudget().reserve_url(url, "portal_entry", official_hosts)
    # Some e:Vision institutional pages deliver headers but stall before
    # DOMContentLoaded. Distinguish a server response from a fully rendered
    # application; the authenticated-project guard checks the latter later.
    page.goto(url, wait_until="commit", timeout=25_000)
    verified_portal_host(page.url, official_hosts)
    if hasattr(page, "wait_for_load_state"):
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

        try:
            page.wait_for_load_state("domcontentloaded", timeout=6_000)
        except PlaywrightTimeoutError:
            # The supervisor will classify the page as unavailable or
            # unauthenticated; don't treat a blank page as an application.
            pass
    return page


def _matching_host(url: str, expected_host: str, hosts: tuple[str, ...]) -> bool:
    try:
        return verified_portal_host(url, hosts) == expected_host
    except PortalPreparationError:
        return False


def workflow_context(playwright: Any, *, manifest_dir: Path, persistent: bool) -> tuple[Any, Any | None]:
    """Return (context, browser), using an isolated persistent profile on request."""
    if persistent:
        return launch_academic_context(playwright, manifest_dir=manifest_dir), None
    from aihawk.academic_browser_launch import launch_operator_browser

    browser = launch_operator_browser(playwright, headless=False)
    return browser.new_context(service_workers="block", accept_downloads=False), browser


def run_interactive_session(manifest: Path, *, prompt=input) -> int:
    """One-time manual sign-in using a profile isolated to this application."""
    if not sys.stdin.isatty():
        raise PortalPreparationError("Browser sign-in must take place in an interactive local terminal.")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    official_url = str(data["official_application_url"])
    official_hosts = tuple(data["official_hosts"])
    verified_portal_host(official_url, official_hosts)
    if prompt("Type OPEN SESSION to open the dedicated academic browser: ") != "OPEN SESSION":
        return 1
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise PortalPreparationError("Install the optional Playwright browser dependency.") from error
    with sync_playwright() as playwright:
        context = launch_academic_context(playwright, manifest_dir=manifest.parent, headless=False)
        try:
            page = official_session_page(context, url=official_url, official_hosts=official_hosts)
            print("Sign in manually in this isolated university browser. Do not copy personal Chrome cookies.")
            prompt("Press Enter after finishing or canceling the login session: ")
            verified_portal_host(page.url, official_hosts)
            print("Private browser closed. Persistent cookies may be retained; session-only login may expire.")
            return 0
        finally:
            context.close()
