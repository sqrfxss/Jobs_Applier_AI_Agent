"""Real headless Chrome multi-step draft automation; synthetic institutional pages."""
import pytest

from aihawk.academic_browser import PortalPreparationError
from aihawk.academic_background_journey import _verified_save_action, run_stage
from aihawk.academic_stages import journey_from_manifest

pytestmark = pytest.mark.browser

ORIGIN = "https://admissions.uni.example.edu"
SAVES = {"selector": "#save", "label": "Save",
         "receipt_selector": "#saved", "receipt_text": "Saved draft"}


def _journey(tmp_path):
    data = {
        "title": "Synthetic academic application",
        "official_application_url": ORIGIN + "/apply",
        "official_hosts": ["uni.example.edu"],
        "applicant_id": "synthetic",
        "attachments": [],
        "fields": {"name": "Casey Sample", "degree": "MSc"},
        "portal_stages": [
            {"name": "Identity", "expected_host": "admissions.uni.example.edu",
             "expected_path": "/apply",
             "bindings": [{"field": "name", "selector": "#name", "kind": "text"}],
             "draft_save": SAVES},
            {"name": "Degree", "expected_host": "admissions.uni.example.edu",
             "expected_path": "/apply/education",
             "bindings": [{"field": "degree", "selector": "#degree", "kind": "select"}],
             "draft_save": SAVES},
        ],
    }
    return journey_from_manifest(data, manifest_dir=tmp_path), data


def _html(key, *, persist=True):
    controls = (
        '<input id="name" type="text">' if key == "name" else
        '<select id="degree"><option value="">Select</option><option value="MSc">MSc</option></select>'
    )
    write = f"sessionStorage.setItem('{key}',document.querySelector('#{key}').value);" if persist else ""
    return f"""<!doctype html><html><body>
    {controls}
    <button type="button" id="save" onclick="{write}document.querySelector('#saved').textContent='Saved draft'">Save</button>
    <div id="saved"></div>
    <button id="final" type="button" onclick="document.body.dataset.final='submitted'">Submit application</button>
    <script>
       const old=sessionStorage.getItem('{key}');
       if(old)document.querySelector('#{key}').value=old;
    </script>
    </body></html>"""


def test_fast_headless_two_stages_save_and_resume(tmp_path):
    sync = pytest.importorskip("playwright.sync_api")
    journey, data = _journey(tmp_path)
    endpoints = {
        ORIGIN + "/apply": _html("name"),
        ORIGIN + "/apply/education": _html("degree"),
    }
    with sync.sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(service_workers="block")
        traffic = []
        def serve(route):
            traffic.append((route.request.method, route.request.url))
            if route.request.url in endpoints:
                route.fulfill(status=200, content_type="text/html", body=endpoints[route.request.url])
            else:
                route.abort()
        context.route("**/*", serve)
        page = context.new_page()
        events = []
        page.on("dialog", lambda d: events.append(d.message))
        for stage, stage_data in zip(journey.stages, data["portal_stages"]):
            page.goto(ORIGIN + stage.expected_path, wait_until="domcontentloaded")
            result = run_stage(page, context, stage, journey.hosts, stage_data)
            assert result["state"] == "server_saved_verified"
            assert result["field_count"] == 1
            assert page.locator("body").get_attribute("data-final") is None
            second = run_stage(page, context, stage, journey.hosts, stage_data, already_confirmed=True)
            assert second["state"] == "reverified_no_change"
        assert events == []
        assert not any("/submit" in url for _, url in traffic)
        assert not any(method == "POST" for method, _ in traffic)
        context.close()
        browser.close()


def test_draft_receipt_without_saved_server_values_is_rejected(tmp_path):
    sync = pytest.importorskip("playwright.sync_api")
    journey, data = _journey(tmp_path)
    url = ORIGIN + "/apply"
    with sync.sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(service_workers="block")
        context.route(url, lambda route: route.fulfill(
            status=200, content_type="text/html", body=_html("name", persist=False)
        ))
        page = context.new_page()
        page.goto(url)
        with pytest.raises(PortalPreparationError, match="did not persist"):
            run_stage(page, context, journey.stages[0], journey.hosts, data["portal_stages"][0])
        assert page.locator("body").get_attribute("data-final") is None
        context.close()
        browser.close()


def test_final_submit_mislabeled_as_save_is_refused():
    with pytest.raises(PortalPreparationError, match="Save Draft"):
        _verified_save_action({
            "selector": "#final", "label": "Submit application",
            "receipt_selector": "#receipt", "receipt_text": "Done",
        })


def test_save_review_rejects_unexpected_extra_actions():
    with pytest.raises(PortalPreparationError, match="metadata"):
        _verified_save_action({
            "selector": "#save", "label": "Save",
            "receipt_selector": "#receipt", "receipt_text": "Saved",
            "send_referee_emails": True,
        })


def test_headless_tabs_on_one_portal_page_do_not_steal_desktop_focus(tmp_path):
    sync = pytest.importorskip("playwright.sync_api")
    journey, data = _journey(tmp_path)
    stages = list(data["portal_stages"])
    for stage in stages:
        stage["expected_path"] = "/apply"
    stages[0]["activate_tab"] = {"selector": "#identity-tab", "label": "Identity"}
    stages[1]["activate_tab"] = {"selector": "#degree-tab", "label": "Degree"}
    stages[0]["draft_save"] = {**SAVES, "selector": "#save-identity"}
    stages[1]["draft_save"] = {**SAVES, "selector": "#save-degree"}
    journey = journey_from_manifest(data, manifest_dir=tmp_path)
    html = """<!doctype html><html><body>
    <button id='identity-tab' onclick="show('identity')">Identity</button>
    <button id='degree-tab' onclick="show('degree')">Degree</button>
    <section id='identity'>
      <input id='name' type='text'>
      <button id='save-identity' onclick="save('name')">Save</button>
    </section>
    <section id='degree-panel' hidden>
      <select id='degree'><option value=''>Choose</option><option value='MSc'>MSc</option></select>
      <button id='save-degree' onclick="save('degree')">Save</button>
    </section>
    <div id='saved'></div>
    <button id='final-submit' onclick="document.body.dataset.final='yes'">Submit</button>
    <script>
    function show(which) {
      document.querySelector('section#identity').hidden=which!=='identity';
      document.querySelector('section#degree-panel').hidden=which!=='degree';
    }
    function save(k) {
      sessionStorage.setItem(k,document.querySelector(k==='name'?'input#name':'select#degree').value);
      document.querySelector('#saved').textContent='Saved draft';
    }
    if(sessionStorage.getItem('name'))document.querySelector('input#name').value=sessionStorage.getItem('name');
    if(sessionStorage.getItem('degree'))document.querySelector('select#degree').value=sessionStorage.getItem('degree');
    </script></body></html>"""
    with sync.sync_playwright() as play:
        browser = play.chromium.launch(channel="chrome", headless=True)
        context = browser.new_context(service_workers="block")
        context.route(ORIGIN+"/apply", lambda route: route.fulfill(status=200,content_type="text/html",body=html))
        page = context.new_page()
        page.goto(ORIGIN+"/apply")
        for stage, info in zip(journey.stages, stages):
            result = run_stage(page, context, stage, journey.hosts, info)
            assert result["state"] == "server_saved_verified"
            assert page.locator("body").get_attribute("data-final") is None
        assert page.locator("input#name").input_value() == "Casey Sample"
        assert page.locator("select#degree").input_value() == "MSc"
        context.close()
        browser.close()


def test_save_and_continue_not_implicitly_authorized_as_draft_only():
    with pytest.raises(PortalPreparationError, match="Save Draft"):
        _verified_save_action({
            "selector": "#next", "label": "Save and Continue",
            "receipt_selector": "#saved", "receipt_text": "Saved",
        })
