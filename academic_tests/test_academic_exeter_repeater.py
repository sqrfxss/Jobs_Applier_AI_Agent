import pytest
from aihawk.academic_session_controls import navigate,apply_plan
from aihawk.academic_browser import PortalPreparationError

@pytest.fixture
def page():
 from playwright.sync_api import sync_playwright
 with sync_playwright() as p:
  try:b=p.chromium.launch(channel="chrome",headless=True)
  except Exception as e:pytest.skip(str(e))
  c=b.new_context()
  pg=c.new_page()
  yield pg
  b.close()

def test_exact_visible_nav_ignores_accessible_completion_suffix(page):
 page.route("https://example.edu/**",lambda r:r.fulfill(status=200,content_type="text/html",body='''<h1>Example project</h1><h2>Work experience</h2><button aria-label="Qualifications stage complete" onclick="document.querySelector('h2').textContent='Qualifications'">Qualifications</button>'''))
 page.goto("https://example.edu/apply")
 navigate(page,("example.edu",),"Example project","Qualifications",expected_heading="Qualifications")
 assert page.get_by_role("heading",name="Qualifications",exact=True).is_visible()

def test_academic_repeater_clicks_once_then_is_idempotent(page,tmp_path):
 page.route("https://example.edu/**",lambda r:r.fulfill(status=200,content_type="text/html",body='''<h1>Example project</h1><h2>Qualifications</h2>
<input type="button" id="q1_add" value="Add another qualification" onclick="document.getElementById('second').style.display='block';document.getElementById('counter').textContent=String(+document.getElementById('counter').textContent+1)"><select id="IPQ_QUAL_TYPE2" style="display:none"></select><span id="counter">0</span>
<script>document.getElementById('IPQ_QUAL_TYPE2').parentElement.appendChild(document.getElementById('second')||Object.assign(document.createElement('span'),{id:'second'}));document.getElementById('second').style.display='none';document.getElementById('q1_add').onclick=()=>{document.getElementById('IPQ_QUAL_TYPE2').style.display='block';document.getElementById('counter').textContent=String(+document.getElementById('counter').textContent+1)}</script>'''))
 page.goto("https://example.edu/apply")
 item={"type":"repeater_add","button_selector":"#q1_add",
       "target_selector":"#IPQ_QUAL_TYPE2","source_evidence":"Official MSc diploma and transcript"}
 plan={"schema":"aihawk.session.draft.v1","project_title":"Example project",
       "section":"Qualifications","visible_heading":"Qualifications","actions":[item]}
 assert apply_plan(page,tmp_path,("example.edu",),"Example project",plan)[0]["second_degree_panel_visible"]
 assert page.locator("#counter").inner_text()=="1"
 apply_plan(page,tmp_path,("example.edu",),"Example project",plan)
 assert page.locator("#counter").inner_text()=="1"

def test_repeater_refuses_unreviewed_click(page,tmp_path):
 page.set_content('<h1>Example project</h1><h2>Qualifications</h2><input id="q1_add" type="button" value="Add another qualification"><select id="IPQ_QUAL_TYPE2" hidden></select>')
 plan={"schema":"aihawk.session.draft.v1","project_title":"Example project",
       "section":"Qualifications","visible_heading":"Qualifications",
       "actions":[{"type":"repeater_add","button_selector":"#q1_add",
        "target_selector":"#IPQ_QUAL_TYPE2","source_evidence":"Unapproved"}]}
 with pytest.raises(PortalPreparationError):
  apply_plan(page,tmp_path,("example.edu",),"Example project",plan)
