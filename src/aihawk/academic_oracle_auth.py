"""Oracle email challenge adapter. One code entry; no resend, no final submit."""
from __future__ import annotations
import re
from urllib.parse import urlsplit
from aihawk.academic_browser import PortalPreparationError,verified_portal_host
from aihawk.academic_auth_gate import detect_auth_challenge
from aihawk.academic_portal_limits import check_access

def verify_oracle_email_challenge(page,code,*,official_hosts):
    verified_portal_host(page.url,official_hosts)
    if not re.fullmatch(r'/hcmUI/CandidateExperience/[^/]+/sites/[^/]+/job/\d+/apply/email/?',urlsplit(page.url).path):
        raise PortalPreparationError("Not a reviewed Oracle email challenge route")
    check_access(official_hosts)
    challenge=detect_auth_challenge(page,official_hosts=official_hosts)
    if not challenge or challenge.kind!="verification_code":
        raise PortalPreparationError("No active email verification challenge")
    if not isinstance(code,str) or not re.fullmatch(r'\d{6}',code):
        raise PortalPreparationError("Unexpected verification code format")
    pins=[page.locator(f'input[id="pin-code-{i}"]:visible') for i in range(1,7)]
    if any(x.count()!=1 or not x.is_enabled() or not x.is_editable() for x in pins):
        raise PortalPreparationError("Six exact PIN inputs not verified")
    # Determine unique action before entering the code. Never use a generic submit locator.
    buttons=page.locator('button[type="submit"]:visible')
    matches=[]
    for i in range(buttons.count()):
        node=buttons.nth(i)
        meta=node.evaluate("""x=>({text:(x.innerText||'').trim(),label:(x.getAttribute('aria-label')||'').trim()})""")
        if meta["text"].casefold()=="verify" and meta["label"].casefold() in ("","verify"):
            matches.append(i)
    if len(matches)!=1:raise PortalPreparationError("Expected exactly one Verify control; no code entered")
    from aihawk.academic_action_budget import ActionBudget
    ActionBudget().reserve_url(page.url, "auth_verify", official_hosts)
    for i,node in enumerate(pins):
        node.fill(code[i])
    if ''.join(node.input_value() for node in pins)!=code:
        raise PortalPreparationError("Code entry readback failed")
    del code
    check_access(official_hosts)
    action=buttons.nth(matches[0])
    if not action.is_enabled():raise PortalPreparationError("Verify control disabled; no retry")
    action.click(timeout=6000)
    # The caller must verify the new page and must not click Verify again on timeout.
    return {"verification_action":"clicked_once","identity_verified":False,"final_submission":False}

def request_oracle_email_challenge(page,email,*,official_hosts):
    """After the operator has accepted the portal's terms, request one code.
    Never attempts to defeat verification, retry delivery, or submit an application.
    """
    verified_portal_host(page.url,official_hosts)
    if not re.fullmatch(r'/hcmUI/CandidateExperience/[^/]+/sites/[^/]+/job/\d+/apply/email/?',urlsplit(page.url).path):
        raise PortalPreparationError("Not a reviewed Oracle email route")
    check_access(official_hosts)
    if not isinstance(email,str) or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email):
        raise PortalPreparationError("Verified email address required")
    if detect_auth_challenge(page,official_hosts=official_hosts):
        raise PortalPreparationError("Existing identity challenge; do not request a new code")
    inp=page.locator('input[id="primary-email-0"]:visible')
    terms=page.locator('input[id="legal-disclaimer-checkbox"]')
    button=page.locator('button.apply-flow-pagination__button[aria-label="Next"]:visible')
    if inp.count()!=1 or terms.count()!=1 or button.count()!=1:
        raise PortalPreparationError("Reviewed email/terms/Next controls unavailable")
    if not terms.is_checked():
        raise PortalPreparationError("Operator must review and accept privacy terms in official browser")
    if inp.input_value() not in ("",email):
        raise PortalPreparationError("Conflicting portal email; no request sent")
    inp.fill(email)
    inp.blur()
    if inp.input_value()!=email or not button.is_enabled():
        raise PortalPreparationError("Email field or Next control is not ready")
    from aihawk.academic_action_budget import ActionBudget
    ActionBudget().reserve_url(page.url,"auth_request",official_hosts)
    button.click(timeout=6000)
    return {"request_action":"clicked_once","identity_verified":False,"final_submission":False}
