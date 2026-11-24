import pytest
from aihawk.academic_oracle_auth import verify_oracle_email_challenge
from aihawk.academic_browser import PortalPreparationError
URL='https://oracle.example.edu/hcmUI/CandidateExperience/en/sites/CX_2001/job/8538/apply/email'
HOSTS=('oracle.example.edu',)
@pytest.fixture
def fake_page():
 from playwright.sync_api import sync_playwright
 with sync_playwright() as p:
  try:b=p.chromium.launch(channel='chrome',headless=True)
  except Exception as e:pytest.skip(str(e))
  c=b.new_context()
  page=c.new_page()
  page.route('**/*',lambda r:r.fulfill(status=200,content_type='text/html',body='<html></html>'))
  page.goto(URL)
  yield page
  b.close()
def html(extra=''):
 return '<form onsubmit="event.preventDefault();window.verified=(window.verified||0)+1;">'+''.join(f'<input id="pin-code-{i}" required maxlength="1">' for i in range(1,7))+'<button type="submit">Verify</button>'+extra+'<button type="button" onclick="window.resent=true">Send New Code</button><button type="submit" onclick="window.final=true">Submit</button></form>'
def test_exact_verify_once(fake_page):
 fake_page.set_content(html())
 out=verify_oracle_email_challenge(fake_page,'123456',official_hosts=HOSTS)
 assert fake_page.evaluate('window.verified')==1
 assert fake_page.evaluate('Boolean(window.final||window.resent)') is False
 assert out['identity_verified'] is False and out['final_submission'] is False
def test_ambiguous_button_stops_before_code(fake_page):
 fake_page.set_content(html('<button type="submit">Verify</button>'))
 with pytest.raises(PortalPreparationError,match='exactly one'):
  verify_oracle_email_challenge(fake_page,'123456',official_hosts=HOSTS)
 assert all(fake_page.locator(f'#pin-code-{i}').input_value()=='' for i in range(1,7))
 assert fake_page.evaluate('Boolean(window.verified||window.final||window.resent)') is False

def test_request_budget_and_no_final_click(fake_page):
 from aihawk.academic_oracle_auth import request_oracle_email_challenge
 from aihawk.academic_portal_limits import PortalAccessHold
 fake_page.set_content('<input id="primary-email-0" type="email"><input id="legal-disclaimer-checkbox" type="checkbox" checked><button class="apply-flow-pagination__button" aria-label="Next" onclick="window.requests=(window.requests||0)+1">Next</button><button onclick="window.final=true">Submit</button>')
 request_oracle_email_challenge(fake_page,'candidate@example.edu',official_hosts=HOSTS)
 assert fake_page.evaluate('window.requests')==1
 with pytest.raises(PortalAccessHold):request_oracle_email_challenge(fake_page,'candidate@example.edu',official_hosts=HOSTS)
 assert fake_page.evaluate('window.requests')==1
 assert fake_page.evaluate('Boolean(window.final)') is False
def test_no_consent_no_request(fake_page):
 from aihawk.academic_oracle_auth import request_oracle_email_challenge
 fake_page.set_content('<input id="primary-email-0" type="email"><input id="legal-disclaimer-checkbox" type="checkbox"><button class="apply-flow-pagination__button" aria-label="Next" onclick="window.requests=1">Next</button>')
 with pytest.raises(PortalPreparationError,match='review and accept'):
  request_oracle_email_challenge(fake_page,'candidate@example.edu',official_hosts=HOSTS)
 assert fake_page.evaluate('Boolean(window.requests)') is False
