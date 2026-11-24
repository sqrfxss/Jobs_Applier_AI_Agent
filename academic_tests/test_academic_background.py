"""Background mode: no native GUI, manual prompts, emails, or final submission."""
import pytest

from aihawk.academic_background import background_prepare_page, exclusive_session
from aihawk.academic_browser import PortalPreparationError, plan_from_manifest


def test_exclusive_profile_lock_rejects_parallel_job(tmp_path):
    with exclusive_session(tmp_path):
        with pytest.raises(PortalPreparationError, match="using this private browser profile"):
            with exclusive_session(tmp_path):
                pass
    assert (tmp_path / ".aihawk-background.lock").is_file()
    with exclusive_session(tmp_path):
        pass  # The prior OS lock is released, even though the lock file remains.


def test_background_prepare_rejects_unapproved_page(tmp_path):
    manifest = {
        "title": "Synthetic", "applicant_id": "test",
        "official_application_url": "https://admissions.uni.example.edu/apply",
        "official_hosts": ["uni.example.edu"], "attachments": [],
        "fields": {"name": "Example"},
        "portal_bindings": [{"field": "name", "selector": "#name", "kind": "text"}],
    }
    plan = plan_from_manifest(manifest, manifest_dir=tmp_path)
    class Page:
        url = "https://admissions.uni.example.edu/login"
    with pytest.raises(PortalPreparationError, match="one-time interactive university login"):
        background_prepare_page(None, Page(), plan)


@pytest.mark.browser
def test_real_headless_chrome_prepares_no_gui_or_submit(tmp_path):
    p = pytest.importorskip("playwright.sync_api")
    url = "https://admissions.uni.example.edu/apply"
    manifest = {
        "title": "Headless synthetic test", "applicant_id": "test",
        "official_application_url": url, "official_hosts": ["uni.example.edu"],
        "attachments": [], "fields": {"name": "Test Applicant", "country": "Iran"},
        "portal_bindings": [
            {"field": "name", "selector": "#name", "kind": "text"},
            {"field": "country", "selector": "#country", "kind": "select"},
        ],
    }
    plan = plan_from_manifest(manifest, manifest_dir=tmp_path)
    html = """
    <input type='text' id='name'>
    <select id='country'><option value=''>Choose</option><option value='Iran'>Iran</option></select>
    <button id='submit' onclick="document.body.dataset.submitted='yes'">Submit</button>
    <script>document.getElementById('name').addEventListener('input',
       ()=>fetch('/unsafe',{method:'POST',body:'not-approved'}).catch(()=>{}));</script>
    """
    requested = []
    with p.sync_playwright() as play:
        browser = play.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(service_workers="block")
        def serve(route):
            requested.append(route.request.url)
            if route.request.url == url:
                route.fulfill(status=200, content_type="text/html", body=html)
            else:
                route.abort()
        context.route("**/*", serve)
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded")
        original = page.evaluate("document.body.dataset.submitted || ''")
        result = background_prepare_page(context, page, plan)
        assert result["result"] == "prepared_not_saved_or_submitted"
        assert result["field_count"] == 2
        assert result["browser_mode"] == "isolated_headless"
        assert page.locator("#name").input_value() == "Test Applicant"
        assert page.locator("#country").input_value() == "Iran"
        assert page.evaluate("document.body.dataset.submitted || ''") == original
        assert not any(item.endswith("/submit") for item in requested)
        context.close()
        browser.close()


@pytest.mark.browser
def test_real_headless_inspect_does_not_modify_fields(tmp_path):
    p = pytest.importorskip("playwright.sync_api")
    url = "https://admissions.uni.example.edu/apply"
    manifest = {
        "title": "Synthetic", "applicant_id": "test",
        "official_application_url": url, "official_hosts": ["uni.example.edu"],
        "attachments": [], "fields": {"name": "Changed"},
        "portal_bindings": [{"field": "name", "selector": "#name", "kind": "text"}],
    }
    plan = plan_from_manifest(manifest, manifest_dir=tmp_path)
    with p.sync_playwright() as play:
        browser = play.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(service_workers="block")
        context.route(url, lambda route: route.fulfill(
            content_type="text/html",
            body='<input id="name" type="text" value="Preserved"><button type="submit">Submit</button>',
        ))
        page = context.new_page()
        page.goto(url)
        result = background_prepare_page(context, page, plan, inspect_only=True)
        assert result["result"] == "inspected_no_changes"
        assert result["controls"] == 1
        assert page.locator("#name").input_value() == "Preserved"
        context.close()
        browser.close()
