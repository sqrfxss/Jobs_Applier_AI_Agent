import pytest
from aihawk.academic_session_flow import oracle_identity_flow

HOSTS = ("oracle.example.edu",)
PATH = "/hcmUI/CandidateExperience/en/sites/CX/job/123/apply/email"
FORM = "/hcmUI/CandidateExperience/en/sites/CX/job/123/apply/section/1"
BASE = "https://oracle.example.edu"
EMAIL = '<input id="primary-email-0" type="email"><input id="legal-disclaimer-checkbox" type="checkbox" checked><button class="apply-flow-pagination__button" aria-label="Next" onclick="showChallenge()">Next</button>'
PIN = "".join(f'<input id="pin-code-{i}" maxlength="1" required>' for i in range(1, 7))
PAGE = (
    """<html><body>"""
    + EMAIL
    + """<script>
function showChallenge(){window.requests=(window.requests||0)+1;document.body.innerHTML='"""
    + PIN
    + """<button type="submit" onclick="finish()">Verify</button>'}
function finish(){window.verifies=(window.verifies||0)+1;history.pushState({},'', '"""
    + FORM
    + """');document.body.innerHTML='<input name="firstName"><button onclick="window.submitted=true">Submit</button>'}
</script></body></html>"""
)


def test_same_session_auth_and_no_submit():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        try:
            b = p.chromium.launch(channel="chrome", headless=True)
        except Exception as e:
            pytest.skip(str(e))
        c = b.new_context()
        page = c.new_page()
        page.route("**/*", lambda r: r.fulfill(status=200, content_type="text/html", body=PAGE))
        page.goto(BASE + PATH)
        r = oracle_identity_flow(
            page, email="test@example.edu", hosts=HOSTS, code_provider=lambda _: "123456", form_selector='input[name="firstName"]', form_path=FORM
        )
        assert r["identity_verified"]
        assert page.evaluate("window.requests===1 && window.verifies===1 && !window.submitted")
        b.close()
