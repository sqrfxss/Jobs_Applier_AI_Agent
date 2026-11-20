"""Real Chromium integration on a synthetic, fully intercepted university form.

No real university endpoint is contacted and no application is sent.
"""
from __future__ import annotations

import pytest
from aihawk.academic_browser import PreparationNetworkGuard, plan_from_manifest, prepare_fields

pytestmark = pytest.mark.browser


def test_real_browser_autofill_does_not_submit(tmp_path):
    sync_api = pytest.importorskip("playwright.sync_api")
    (tmp_path / "cv.pdf").write_bytes(b"%PDF-1.4 example test file only")
    url = "https://admissions.uni.example.edu/apply"
    manifest = {
        "title": "Test MSc",
        "official_application_url": url,
        "official_hosts": ["uni.example.edu"],
        "applicant_id": "testing-only",
        "fields": {"full_name": "Testing Applicant", "programme": "MSc"},
        "attachments": ["cv.pdf"],
        "portal_bindings": [
            {"field": "full_name", "selector": "#name", "kind": "text"},
            {"field": "programme", "selector": "#programme", "kind": "select"},
            {"field": "cv.pdf", "selector": "#cv", "kind": "upload"},
        ],
    }
    plan = plan_from_manifest(manifest, manifest_dir=tmp_path)
    document = """<!doctype html><html><body>
<form id="application" method="POST" action="/submission">
<input id="name" name="name" type="text">
<select id="programme"><option value="">Select</option><option value="MSc">MSc</option></select>
<input id="cv" type="file"><button id="submit" type="submit">Submit</button>
</form>
<span id="sent">not submitted</span>
<script>
document.querySelector("#name").addEventListener("input", () => {
    fetch("/implicit-submit", {method: "POST", body: "test"})
        .catch(() => {});
});
</script></body></html>"""
    with sync_api.sync_playwright() as play:
        browser = play.chromium.launch(headless=True)
        context = browser.new_context(service_workers="block")
        context.route(url, lambda route: route.fulfill(status=200, content_type="text/html", body=document))
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded")
        guard = PreparationNetworkGuard(("uni.example.edu",))
        context.route("**/*", guard)
        assert prepare_fields(page, plan) == ("full_name", "programme", "cv.pdf")
        page.wait_for_timeout(200)
        assert guard.blocked_requests >= 1
        assert page.locator("#name").input_value() == "Testing Applicant"
        assert page.locator("#programme").input_value() == "MSc"
        assert page.locator("#sent").text_content() == "not submitted"
        assert page.locator("#submit").count() == 1
        context.close()
        browser.close()
