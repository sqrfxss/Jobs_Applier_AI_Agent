"""Authentication barriers must never be mistaken for submitted applications."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from aihawk.academic_auth_gate import (
    AuthChallenge, UserActionRequired, _safe_url, detect_auth_challenge,
    require_human_if_needed, save_public_checkpoint,
)
from aihawk.academic_browser import PortalPreparationError
from aihawk.academic_background_journey import _allowlisted_stage_page

HOSTS = ("kuleuven.be",)
URL = "https://account.kuleuven.be/login?state=VERYSECRET"
class Page:
    def __init__(self, fields=(), *, captcha=False, buttons=(), url=URL):
        self.url = url
        self.result = {"fields": list(fields), "captcha": captcha, "buttons": list(buttons)}
    def evaluate(self, script):
        assert "value" not in script.lower().split("const fields =")[1].split("const captcha")[0]
        return self.result

def field(t="text", name="username", autocomplete=""):
    return {"type":t,"name":name,"id":name,"autocomplete":autocomplete}

def detect(page):
    return detect_auth_challenge(page, official_hosts=HOSTS)

def test_login_requires_user_not_agent_secret():
    a=detect(Page([field("text"),field("password","password")],buttons=["Sign in"]))
    assert a.kind=="sign_in"
    assert a.page_url=="https://account.kuleuven.be/login"
    assert "password" in a.instructions.lower()
    assert "VERYSECRET" not in str(a.public_record())

def test_registration_form_classification():
    a=detect(Page([field("email","email"),field("password","password")],buttons=["Create account"]))
    assert a.kind=="create_account"

def test_otp_precedes_password_login():
    a=detect(Page([field("text","otp"),field("password","password")]))
    assert a.kind=="verification_code"

def test_one_time_code_autocomplete():
    assert detect(Page([field("text","verify","one-time-code")])).kind=="verification_code"

def test_captcha_always_requires_human():
    a=detect(Page([field("password","password")],captcha=True))
    assert a.kind=="captcha"

def test_no_auth_controls_proceeds():
    assert detect(Page([field("text","program")],url="https://www.kuleuven.be/apply")) is None

def test_email_only_sign_in_preflight():
    a=detect(Page([field("email","email")],url="https://account.kuleuven.be/signin"))
    assert a.kind=="account_or_login"

def test_account_gate_stops_real_stages_before_field_fill():
    pg=Page([field("password","password")])
    stage=SimpleNamespace(expected_host="account.kuleuven.be",expected_path="/login")
    with pytest.raises(UserActionRequired) as e:
        _allowlisted_stage_page(pg,stage,HOSTS)
    assert e.value.challenge.kind=="sign_in"

def test_untrusted_host_refused_before_credentials():
    with pytest.raises(PortalPreparationError):
        detect(Page([field("password","password")],url="https://evil.example.com/login"))

def test_checkpoint_redacts_secrets_and_is_resumable(tmp_path):
    challenge=AuthChallenge("captcha",_safe_url(URL),"Solve on official site.")
    output=tmp_path/".aihawk-auth-checkpoint.json"
    save_public_checkpoint(output,challenge)
    data=json.loads(output.read_text(encoding="utf-8"))
    assert data["status"]=="needs_user_action"
    assert data["credentials_stored"] is False
    assert data["submission_confirmed"] is False
    assert "VERYSECRET" not in output.read_text(encoding="utf-8")

def test_real_chromium_login_captcha_and_otp_detection():
    playwright = pytest.importorskip("playwright.sync_api")
    origin = "https://account.kuleuven.be/login"
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context()
        page = context.new_page()
        context.route(origin, lambda route: route.fulfill(
            status=200, content_type="text/html",
            body='<html><body><input id="username" name="username" type="text">'
                 '<input id="pw" name="password" type="password">'
                 '<button>Sign in</button></body></html>'
        ))
        page.goto(origin)
        assert detect_auth_challenge(page, official_hosts=HOSTS).kind == "sign_in"
        page.set_content('<html><body><input autocomplete="one-time-code"></body></html>')
        assert detect_auth_challenge(page, official_hosts=HOSTS).kind == "verification_code"
        page.set_content('<html><body><div class="g-recaptcha">Human challenge</div></body></html>')
        assert detect_auth_challenge(page, official_hosts=HOSTS).kind == "captcha"
        context.close()
        browser.close()

def test_kuleuven_identity_first_username_page_needs_user_action():
    page=Page([field("text","input")],buttons=["Continue"],
              url="https://idp.kuleuven.be/idpx/profile/SAML2/Redirect/SSO?RelayState=secret")
    challenge=detect(page)
    assert challenge.kind=="account_or_login"
    assert challenge.page_url.endswith("/idpx/profile/SAML2/Redirect/SSO")
    assert "secret" not in str(challenge.public_record())
