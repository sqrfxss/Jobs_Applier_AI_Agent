"""Regression: programmatic fill of a date can be discarded by portal blur handlers."""
import pytest
from playwright.sync_api import sync_playwright
from aihawk.academic_session_controls import apply_plan
from aihawk.academic_browser import PortalPreparationError

def test_date_falls_back_to_key_events_once(tmp_path):
    with sync_playwright() as p:
        b=p.chromium.launch(channel="chrome",headless=True)
        page=b.new_page()
        page.route("https://example.edu/**",lambda r:r.fulfill(
            status=200,content_type="text/html",body="""<h1>Example project</h1>
            <h2>Qualifications</h2><label for="ELQUAL_DATE">Date of test</label>
            <input id="ELQUAL_DATE" onkeydown="this.dataset.typed='yes'"
                onblur="if(this.dataset.typed!=='yes')this.value='';">"""))
        page.goto("https://example.edu/apply")
        plan={"schema":"aihawk.session.draft.v1","project_title":"Example project",
              "section":"Qualifications","visible_heading":"Qualifications",
              "actions":[{"type":"fill","selector":"#ELQUAL_DATE","value":"14/Jan/2025"}]}
        results=apply_plan(page,tmp_path,("example.edu",),"Example project",plan)
        assert results[0]["local_readback"]
        assert page.locator("#ELQUAL_DATE").input_value()=="14/Jan/2025"
        b.close()

def test_invalid_date_does_not_get_accepted(tmp_path):
    with sync_playwright() as p:
        b=p.chromium.launch(channel="chrome",headless=True)
        page=b.new_page()
        page.route("https://example.edu/**",lambda r:r.fulfill(
            status=200,content_type="text/html",body="""<h1>Example project</h1>
            <h2>Qualifications</h2><input id="ELQUAL_DATE" onblur="this.value='';">"""))
        page.goto("https://example.edu/apply")
        plan={"schema":"aihawk.session.draft.v1","project_title":"Example project",
              "section":"Qualifications","visible_heading":"Qualifications",
              "actions":[{"type":"fill","selector":"#ELQUAL_DATE","value":"14/Jan/2025"}]}
        with pytest.raises(PortalPreparationError,match="#ELQUAL_DATE"):
            apply_plan(page,tmp_path,("example.edu",),"Example project",plan)
        b.close()
