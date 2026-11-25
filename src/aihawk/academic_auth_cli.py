"""Launch a dedicated, reusable university login browser on the applicant's PC.

Passwords and CAPTCHA responses are entered directly at the university site.
The agent never asks for them in chat, scrapes their values, or logs them.
Usage: python -m aihawk.academic_auth_cli <manifest.json> [--timeout 900]
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from aihawk.academic_auth_gate import (
    detect_auth_challenge,
    save_public_checkpoint,
)
from aihawk.academic_background import exclusive_session
from aihawk.academic_browser import PortalPreparationError, verified_portal_host
from aihawk.academic_browser_session import launch_academic_context


def run_visible_auth_session(manifest: Path, *, timeout: int = 900) -> dict:
    """Keep the official browser open so a human can solve login, OTP or CAPTCHA."""
    manifest = manifest.resolve(strict=True)
    root = manifest.parent
    data = json.loads(manifest.read_text(encoding="utf-8"))
    url = data["official_application_url"]
    hosts = tuple(data["official_hosts"])
    verified_portal_host(url, hosts)
    checkpoint = root / ".aihawk-auth-checkpoint.json"

    from playwright.sync_api import sync_playwright

    with exclusive_session(root):
        with sync_playwright() as playwright:
            context = launch_academic_context(playwright, manifest_dir=root, headless=False)
            try:
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(url, wait_until="commit", timeout=45000)
                verified_portal_host(page.url, hosts)
                page.wait_for_timeout(1500)
                print("OFFICIAL_BROWSER_OPENED", flush=True)
                print("Enter account credentials and verification codes directly in the browser.", flush=True)
                print("Do not type passwords or one-time codes into the agent chat.", flush=True)

                # Dynamic SAP UI5 can render its entry button long AFTER the
                # first navigation commits. Retry locating the exact button,
                # never blindly click coordinates or an unreviewed action.
                entry_opened = False
                username_prefilled = False
                last_action = None
                observed_challenge = False
                challenge_absent_since = None
                end = time.monotonic() + timeout
                while time.monotonic() < end:
                    pages = [p for p in context.pages if not p.is_closed()]
                    if not pages:
                        return {"status": "browser_closed", "login_verified": False}
                    page = pages[-1]
                    verified_portal_host(page.url, hosts)
                    if not entry_opened and data.get("start_application_button") == "Apply now":
                        begin = page.get_by_role("button", name="Apply now", exact=True)
                        if begin.count() == 1 and begin.is_visible() and begin.is_enabled():
                            begin.click(timeout=12000)
                            entry_opened = True
                            print("OFFICIAL_APPLICATION_ENTRY_OPENED", flush=True)
                            time.sleep(1)
                            continue
                    try:
                        challenge = detect_auth_challenge(page, official_hosts=hosts)
                    except Exception as exc:
                        if isinstance(exc, PortalPreparationError):
                            raise
                        time.sleep(1)
                        continue

                    if challenge is not None:
                        observed_challenge = True
                        challenge_absent_since = None
                        # Prefill only an existing, nonsecret account identifier.
                        # Password and OTP are always entered by the applicant.
                        hint = data.get("existing_university_account_identifier")
                        if hint and not username_prefilled and challenge.kind in ("sign_in", "account_or_login"):
                            on_kuleuven_idp = page.url.startswith("https://idp.kuleuven.be/idpx/profile/")
                            selector = (
                                'input#input[name="input"]'
                                if on_kuleuven_idp
                                else 'input[autocomplete="username"],input[name="username"],input[id="username"],input[name="userId"],input[id="userId"]'
                            )
                            identifier = page.locator(selector)
                            if identifier.count() == 1 and identifier.is_visible():
                                if not identifier.input_value():
                                    identifier.fill(str(hint))
                                username_prefilled = True
                                print("ACCOUNT_IDENTIFIER_PREFILLED", flush=True)
                                if on_kuleuven_idp:
                                    advance = page.get_by_role("button", name="Continue", exact=True)
                                    if advance.count() == 1 and advance.is_enabled():
                                        advance.click(timeout=12000)
                                        print("OFFICIAL_USERNAME_STEP_COMPLETED", flush=True)
                                        time.sleep(1)
                                        continue
                        if challenge.kind != last_action:
                            save_public_checkpoint(checkpoint, challenge)
                            print(
                                f"USER_ACTION_REQUIRED {challenge.kind}: {challenge.instructions}",
                                flush=True,
                            )
                            last_action = challenge.kind
                    elif observed_challenge:
                        # Dynamic SSO can briefly remove a form while loading
                        # the next (password, OTP or CAPTCHA) step. Wait for
                        # the page to remain challenge-free for 12 seconds.
                        now = time.monotonic()
                        if challenge_absent_since is None:
                            challenge_absent_since = now
                            time.sleep(1.5)
                            continue
                        if now - challenge_absent_since < 12:
                            time.sleep(1.5)
                            continue
                        # Keep the browser open; dynamic SSO often briefly
                        # removes authentication controls between stages.
                        # An absent password input is NEVER a login receipt.
                        if last_action != "verification_pending":
                            record = {
                                "status": "verification_pending",
                                "login_verified": False,
                                "submission_confirmed": False,
                                "credentials_stored": False,
                            }
                            checkpoint.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
                            print("LOGIN_VERIFICATION_PENDING;BROWSER_REMAINS_OPEN", flush=True)
                            last_action = "verification_pending"
                    time.sleep(1.5)
                return {
                    "status": "user_action_timed_out",
                    "login_verified": False,
                    "submission_confirmed": False,
                }
            finally:
                context.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Official-site interactive university authentication")
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args(argv)
    if args.timeout < 30 or args.timeout > 3600:
        parser.error("timeout must be between 30 and 3600 seconds")
    result = run_visible_auth_session(args.manifest, timeout=args.timeout)
    print("AUTH_SESSION_RESULT", json.dumps(result, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
