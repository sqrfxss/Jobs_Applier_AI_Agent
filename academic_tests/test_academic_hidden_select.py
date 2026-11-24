import pytest
from aihawk.academic_session_controls import apply_plan
def test_hidden_select_by_exact_id(tmp_path):
 from playwright.sync_api import sync_playwright
 with sync_playwright() as p:
  try:b=p.chromium.launch(channel="chrome",headless=True)
  except Exception as e:pytest.skip(str(e))
  pg=b.new_page()
  pg.route("https://example.edu/**",lambda r:r.fulfill(status=200,content_type="text/html",body='<h1>Example project</h1><select style="display:none" id="choice"><option>Choose...</option><option value="a">Academic (Higher Education)</option></select>'))
  pg.goto("https://example.edu/apply")
  plan={"schema":"aihawk.session.draft.v1","project_title":"Example project","section":"References","visible_heading":"Example project","actions":[{"type":"select","selector":"#choice","label":"Academic (Higher Education)"}]}
  assert apply_plan(pg,tmp_path,("example.edu",),"Example project",plan)[0]["local_readback"]
  assert pg.locator("#choice").input_value()=="a"
  b.close()
