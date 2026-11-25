"""Reviewed same-session authentication for an explicitly approved draft journey."""

from __future__ import annotations
import base64
import re
import time
from email.utils import parseaddr
from urllib.parse import urlsplit
from aihawk.academic_browser import PortalPreparationError, verified_portal_host
from aihawk.academic_session_flow import oracle_identity_flow
from aihawk.academic_portal_limits import check_access


def _body(payload):
    if payload.get("mimeType") == "text/plain" and payload.get("body", {}).get("data"):
        value = payload["body"]["data"]
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)).decode("utf8", errors="replace")
    return "\n".join(_body(p) for p in payload.get("parts", []))


def fresh_oracle_code(gmail, *, sender, recipient, started, timeout=90):
    """Read only an exact fresh message; no retries of portal requests."""
    cutoff = time.monotonic() + timeout
    while time.monotonic() < cutoff:
        q = f'from:{sender} to:{recipient} subject:"Confirm your identity" after:{int(started) - 2}'
        rows = gmail.users().messages().list(userId="me", q=q, maxResults=10).execute(num_retries=0).get("messages", [])
        matches = []
        for item in rows:
            m = gmail.users().messages().get(userId="me", id=item["id"], format="full").execute(num_retries=0)
            if int(m.get("internalDate", "0")) / 1000 < started - 2:
                continue
            headers = {h["name"].lower(): h["value"] for h in m["payload"].get("headers", [])}
            if parseaddr(headers.get("from", ""))[1].casefold() != sender.casefold():
                continue
            if parseaddr(headers.get("to", ""))[1].casefold() != recipient.casefold():
                continue
            if headers.get("subject", "").casefold() != "confirm your identity":
                continue
            text = _body(m["payload"])
            code = re.search(r"one-time pass\s*code\s*:\s*(\d{6})\b", text, re.I)
            if code:
                matches.append(code[1])
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise PortalPreparationError("Multiple fresh codes; stop rather than guessing")
        time.sleep(5)
    return None


def reviewed_auth_callback(config, journey):
    if config.get("reviewed") is not True:
        raise PortalPreparationError("Oracle authentication configuration not reviewed")
    email = config.get("email", "")
    sender = config.get("verified_sender", "")
    for address in (email, sender):
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", address):
            raise PortalPreparationError("Exact applicant and verified sender email required")
    first = journey.stages[0]
    login = config["login_url"]
    if verified_portal_host(login, journey.hosts) != first.expected_host:
        raise PortalPreparationError("Login host mismatch")
    form_selector = config["form_selector"]
    if not isinstance(form_selector, str) or not form_selector.strip():
        raise PortalPreparationError("Exact form selector required")
    # Verify service access before creating any portal challenge.
    from aihawk.academic_google_bridge import services

    gmail, _ = services()

    def callback(page):
        from aihawk.academic_auth_gate import detect_auth_challenge

        check_access(journey.hosts)
        if urlsplit(page.url).path == first.expected_path:
            return
        if detect_auth_challenge(page, official_hosts=journey.hosts):
            raise PortalPreparationError("Existing challenge; no new request")
        if urlsplit(page.url).path != urlsplit(login).path:
            from aihawk.academic_action_budget import ActionBudget

            ActionBudget().reserve_url(login, "portal_entry", journey.hosts)
            page.goto(login, wait_until="domcontentloaded", timeout=25000)
        page.locator("#primary-email-0").wait_for(state="visible", timeout=15000)
        terms = page.locator("#legal-disclaimer-checkbox")
        if not terms.is_checked():
            raise PortalPreparationError("Privacy terms need review in dedicated browser; no code requested")
        r = oracle_identity_flow(
            page,
            email=email,
            hosts=journey.hosts,
            code_provider=lambda start: fresh_oracle_code(gmail, sender=sender, recipient=email, started=start),
            form_selector=form_selector,
            form_path=first.expected_path,
        )
        if not r.get("identity_verified"):
            raise PortalPreparationError("Identity not verified; no retry")

    return callback
