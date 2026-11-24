from playwright.sync_api import sync_playwright
from aihawk.academic_blank_recovery import recover_once

def test_recovery_only_one_get_on_blank_page(tmp_path):
    with sync_playwright() as p:
        b=p.chromium.launch(channel="chrome",headless=True)
        page=b.new_page()
        observed=[]
        def handler(r):
            observed.append((r.request.method,r.request.url))
            if r.request.url.endswith("/blank"):
                r.fulfill(status=200,content_type="text/html",body="")
            else:
                r.fulfill(status=200,content_type="text/html",
                          body="<h1>Example project</h1><button>About You</button>")
        page.route("https://example.edu/**",handler)
        page.goto("https://example.edu/blank")
        r=recover_once(page,tmp_path,("example.edu",),
                       "Example project","https://example.edu/official")
        assert r["status"]=="project_restored"
        assert r["attempted"]
        assert observed==[("GET","https://example.edu/blank"),
                          ("GET","https://example.edu/official")]
        assert r["final_submission"] is False
        b.close()

def test_no_navigation_if_form_is_nonblank(tmp_path):
    with sync_playwright() as p:
        b=p.chromium.launch(channel="chrome",headless=True)
        page=b.new_page()
        seen=[]
        page.route("https://example.edu/**",lambda r:(
            seen.append(r.request.url),
            r.fulfill(status=200,content_type="text/html",
              body="<h1>Some other project</h1><input id='keep' value='x'>")))
        page.goto("https://example.edu/somewhere")
        r=recover_once(page,tmp_path,("example.edu",),
                       "Example project","https://example.edu/official")
        assert r["status"]=="nonblank_unverified_page_manual_review"
        assert seen==["https://example.edu/somewhere"]
        b.close()
