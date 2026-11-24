"""Regression: Exeter can update sections through an authenticated XHR."""
from aihawk.academic_session_controls import navigate
from playwright.sync_api import sync_playwright

def test_forced_stage_readback_accepts_fresh_same_origin_xhr():
    with sync_playwright() as p:
        browser=p.chromium.launch(channel="chrome",headless=True)
        page=browser.new_page()
        def route(r):
            if r.request.url.endswith("/switch"):
                r.fulfill(status=200,content_type="application/json",body='{"ok":true}')
            else:
                r.fulfill(status=200,content_type="text/html",body="""<h1>Example project</h1>
                    <h2 id='heading'>About you</h2>
                    <button id='go' onclick="fetch('/switch').then(r=>r.json()).then(
                       ()=>document.getElementById('heading').innerText='Address')">Address</button>""")
        page.route("https://example.edu/**",route)
        page.goto("https://example.edu/apply")
        navigate(page,("example.edu",),"Example project","Address",
                 expected_heading="Address",force=True)
        assert page.locator("#heading").inner_text()=="Address"
        browser.close()
