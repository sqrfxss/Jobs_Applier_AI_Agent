"""Same-session Oracle identity workflow. No automatic retries or consent."""

from __future__ import annotations
import time
from aihawk.academic_oracle_auth import request_oracle_email_challenge, verify_oracle_email_challenge
from aihawk.academic_auth_gate import detect_auth_challenge
from aihawk.academic_browser import PortalPreparationError, verified_portal_host
from aihawk.academic_portal_limits import check_access


def oracle_identity_flow(page, *, email, hosts, code_provider, form_selector, form_path, timeout_seconds=90):
    """Use the caller's already-open dedicated page; keep it open across all stages.
    The provider must supply only a fresh, verified code for this exact challenge.
    This function never navigates, resends, accepts terms, or closes the browser.
    """
    verified_portal_host(page.url, hosts)
    check_access(hosts)
    if page.locator(form_selector).count() == 1 and page.locator(form_selector).is_visible():
        from urllib.parse import urlsplit

        if urlsplit(page.url).path != form_path:
            raise PortalPreparationError("Unexpected authenticated form")
        return {"identity_verified": True, "request_count": 0, "verify_count": 0}
    challenge = detect_auth_challenge(page, official_hosts=hosts)
    if challenge is not None:
        # Existing challenge may predate this process. Never issue another code.
        return {"identity_verified": False, "request_count": 0, "verify_count": 0, "status": "existing_challenge_manual_review"}
    started = time.time()
    request_oracle_email_challenge(page, email, official_hosts=hosts)
    page.locator('input[id="pin-code-1"]:visible').wait_for(state="visible", timeout=timeout_seconds * 1000)
    check_access(hosts)
    if detect_auth_challenge(page, official_hosts=hosts) is None:
        raise PortalPreparationError("Challenge not verified")
    code = code_provider(started)
    if code is None:
        return {"identity_verified": False, "request_count": 1, "verify_count": 0, "status": "code_unavailable"}
    try:
        verify_oracle_email_challenge(page, code, official_hosts=hosts)
    finally:
        del code
    page.locator(form_selector).wait_for(state="visible", timeout=timeout_seconds * 1000)
    from urllib.parse import urlsplit

    verified_portal_host(page.url, hosts)
    check_access(hosts)
    if urlsplit(page.url).path != form_path or page.locator(form_selector).count() != 1:
        raise PortalPreparationError("Authenticated form not uniquely verified")
    return {"identity_verified": True, "request_count": 1, "verify_count": 1}
