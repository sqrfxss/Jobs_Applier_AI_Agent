"""Human-in-the-loop authentication checkpoints for academic portals.

The applicant enters credentials, verification codes and CAPTCHAs only
in an official visible browser. Neither secrets nor cookies enter reports.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from aihawk.academic_browser import PortalPreparationError, verified_portal_host


@dataclass(frozen=True)
class AuthChallenge:
    kind: str
    page_url: str
    instructions: str

    def public_record(self) -> dict:
        return {
            "status": "needs_user_action",
            "action": self.kind,
            "page_url": self.page_url,
            "instructions": self.instructions,
            "credentials_stored": False,
            "submission_confirmed": False,
        }


class UserActionRequired(PortalPreparationError):
    def __init__(self, challenge: AuthChallenge):
        super().__init__(f"User action required: {challenge.kind}. No application submitted.")
        self.challenge = challenge


def _safe_url(url: str) -> str:
    """Never persist query arguments (some login URLs embed sensitive tokens)."""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def detect_auth_challenge(page, *, official_hosts: tuple[str, ...]) -> AuthChallenge | None:
    """Inspect only element metadata; never read input values or cookies."""
    verified_portal_host(page.url, official_hosts)
    visible = page.evaluate("""() => {
      const shown = e => !!(e.getClientRects().length) &&
        getComputedStyle(e).visibility !== 'hidden';
      const fields = [...document.querySelectorAll('input')]
        .filter(shown).map(e => ({
          type:(e.type||'').toLowerCase(),
          name:(e.name||'').toLowerCase(),
          id:(e.id||'').toLowerCase(),
          autocomplete:(e.autocomplete||'').toLowerCase()
        }));
      const captcha = [...document.querySelectorAll(
        'iframe[src*="recaptcha"],iframe[src*="hcaptcha"],.g-recaptcha,' +
        '.h-captcha,.cf-turnstile,iframe[src*="challenges.cloudflare.com"],' +
        '[data-sitekey],input[name*="captcha" i],input[id*="captcha" i]'
      )].some(shown);
      const buttons = [...document.querySelectorAll('button,input[type="submit"],a[role="button"]')]
        .filter(shown).map(e => (e.textContent||e.value||'').trim().toLowerCase()).slice(0,35);
      return {fields,captcha,buttons};
    }""")
    fields = visible["fields"]
    keys = " ".join(f"{x['name']} {x['id']} {x['autocomplete']}" for x in fields)
    buttons = " ".join(visible["buttons"]).casefold()
    url = _safe_url(page.url)

    if visible["captcha"]:
        return AuthChallenge(
            "captcha", url,
            "Solve CAPTCHA in the official browser yourself. Do not share its token."
        )
    if any(x["autocomplete"] == "one-time-code" for x in fields) or re.search(
        r"\b(otp|totp|mfa|2fa|verification.?code|sms.?code|pin.?code)\b", keys
    ):
        return AuthChallenge(
            "verification_code", url,
            "Enter the one-time verification code in the official browser. Do not send it in chat."
        )
    if any(x["type"] == "password" for x in fields):
        kind = "create_account" if re.search(
            r"create (an? )?account|sign up|register|registration|activate account", buttons
        ) else "sign_in"
        return AuthChallenge(
            kind, url,
            "Enter your university username and password directly in the official browser. "
            "Do not send passwords in chat or store them in agent logs."
        )
    host = (urlsplit(page.url).hostname or "").casefold()
    kuleuven_identity = (
        host == "idp.kuleuven.be"
        and "/idpx/profile/" in urlsplit(page.url).path
        and "continue" in buttons
    )
    if kuleuven_identity or re.search(
        r"sign.?in|log.?in|register|create.?account|account/activate", page.url, re.I
    ):
        if any(x["type"] in ("email", "text") for x in fields):
            return AuthChallenge(
                "account_or_login", url,
                "Continue university sign-in/registration in the official browser."
            )
    return None


def require_human_if_needed(page, *, official_hosts: tuple[str, ...]) -> None:
    challenge = detect_auth_challenge(page, official_hosts=official_hosts)
    if challenge is not None:
        raise UserActionRequired(challenge)


def save_public_checkpoint(path: Path, challenge: AuthChallenge) -> None:
    """Store a minimal, non-secret continuation record."""
    record = challenge.public_record()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp.replace(path)
    finally:
        if tmp.exists():
            tmp.unlink()
