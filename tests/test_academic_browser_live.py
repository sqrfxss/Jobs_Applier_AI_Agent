"""Real Chromium integration on a synthetic, fully intercepted university form.

No real university endpoint is contacted and no application is sent.
"""
from __future__ import annotations

import pytest

from aihawk.academic_browser import PreparationNetworkGuard, plan_from_manifest, prepare_fields
from aihawk.academic_inspect import inspect_controls
from aihawk.academic_stages import journey_from_manifest, prepare_stage

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
        inventory = inspect_controls(page, official_hosts=("uni.example.edu",))
        assert {control["kind"] for control in inventory["controls"]} == {"text", "select", "upload"}
        assert inventory["values_captured"] is False
        assert not any(control["selector_candidate"] == "#submit" for control in inventory["controls"])
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


def test_two_page_chromium_prepares_separate_fields_without_any_submit(tmp_path):
    sync_api = pytest.importorskip("playwright.sync_api")
    base = "https://admissions.uni.example.edu"
    first, second = base + "/apply", base + "/apply/degree"
    manifest = {
        "title": "Synthetic multi-page MSc",
        "official_application_url": first,
        "official_hosts": ["uni.example.edu"],
        "applicant_id": "test-only",
        "fields": {"legal_name": "Casey Sample", "degree": "MSc"},
        "attachments": [],
        "portal_stages": [
            {"name": "Identity", "expected_host": "admissions.uni.example.edu",
             "expected_path": "/apply",
             "bindings": [{"field": "legal_name", "selector": "#legal", "kind": "text"}]},
            {"name": "Degree", "expected_host": "admissions.uni.example.edu",
             "expected_path": "/apply/degree",
             "bindings": [{"field": "degree", "selector": "#degree", "kind": "select"}]},
        ],
    }
    journey = journey_from_manifest(manifest, manifest_dir=tmp_path)
    pages = {
        first: (
            "<form method='POST' action='/submit'><input id='legal' type='text'>"
            "<button type='submit'>Send</button></form><script>"
            "document.querySelector('#legal').addEventListener('input', () => "
            "fetch('/implicit-submit', {method:'POST', body:'x'}).catch(() => {}));"
            "</script>"
        ),
        second: (
            "<form method='POST' action='/submit'><select id='degree'>"
            "<option value=''>Select</option><option value='MSc'>MSc</option></select>"
            "<button type='submit'>Send</button></form>"
        ),
    }
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(service_workers="block")
        context.route("**/*", lambda route: route.fulfill(
            status=200, content_type="text/html",
            body=pages.get(route.request.url, "<h1>Unexpected navigation</h1>"),
        ))
        page = context.new_page()
        page.goto(first)
        guard = PreparationNetworkGuard(journey.hosts)
        context.route("**/*", guard)
        assert prepare_stage(page, journey.stages[0], hosts=journey.hosts) == ("legal_name",)
        page.wait_for_timeout(150)
        assert guard.blocked_requests >= 1
        assert page.locator("#legal").input_value() == "Casey Sample"
        context.unroute("**/*", guard)
        # This navigation represents the test operator's manual Next action;
        # the production journey never navigates between stages itself.
        page.goto(second)
        guard = PreparationNetworkGuard(journey.hosts)
        context.route("**/*", guard)
        assert prepare_stage(page, journey.stages[1], hosts=journey.hosts) == ("degree",)
        assert page.locator("#degree").input_value() == "MSc"
        assert page.locator("button[type='submit']").count() == 1
        context.close()
        browser.close()


def test_hidden_file_input_directly_attached_without_native_file_chooser(tmp_path):
    sync_api = pytest.importorskip("playwright.sync_api")
    (tmp_path / "proof.pdf").write_bytes(b"%PDF-1.4 synthetic evidence")
    url = "https://admissions.uni.example.edu/hidden-file"
    manifest = {
        "title": "No native picker test",
        "official_application_url": url,
        "official_hosts": ["uni.example.edu"],
        "applicant_id": "synthetic",
        "fields": {},
        "attachments": ["proof.pdf"],
        "portal_bindings": [{"field": "proof.pdf", "selector": "#hidden-upload", "kind": "upload"}],
    }
    plan = plan_from_manifest(manifest, manifest_dir=tmp_path)
    html = (
        "<input type='file' id='hidden-upload' style='display:none'>"
        "<button type='submit' id='danger'>Submit application</button>"
    )
    with sync_api.sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(service_workers="block")
        context.route(url, lambda route: route.fulfill(status=200, content_type="text/html", body=html))
        page = context.new_page()
        chooser_events = []
        page.on("filechooser", lambda chooser: chooser_events.append(chooser))
        page.goto(url)
        assert prepare_fields(page, plan) == ("proof.pdf",)
        assert page.locator("#hidden-upload").evaluate(
            "(e) => Array.from(e.files).map(f => f.name)"
        ) == ["proof.pdf"]
        assert chooser_events == []
        assert page.locator("#danger").count() == 1
        context.close()
        browser.close()


def test_guarded_ajax_upload_receipt_and_idempotence_without_file_picker(tmp_path):
    import json

    from aihawk.academic_uploads import upload_one, upload_plan_from_manifest

    sync_api = pytest.importorskip("playwright.sync_api")
    (tmp_path / "proof.pdf").write_bytes(b"%PDF-1.4 synthetic academic document")
    url = "https://admissions.uni.example.edu/apply"
    data = {
        "title": "Synthetic AJAX institution",
        "official_application_url": url,
        "official_hosts": ["uni.example.edu"],
        "applicant_id": "synthetic-user",
        "fields": {},
        "attachments": ["proof.pdf"],
        "portal_uploads": [{
            "field": "proof.pdf",
            "input_selector": "#proof",
            "upload_button_selector": "#proof-upload",
            "container_selector": "#proof-container",
            "receipt_selector": ".file a",
            "remove_selector": "button.remove",
            "expected_path": "/apply",
            "upload_endpoint_path": "/file/ajax",
        }],
    }
    plan = upload_plan_from_manifest(data, manifest_dir=tmp_path)
    html = """<html><body><section id="proof-container">
      <input id="proof" type="file" style="display:none">
      <button id="proof-upload" type="button" onclick="uploadProof()">Upload</button>
      <div class="file"></div></section>
      <button id="final" type="submit" onclick="document.body.dataset.final='sent'">Submit application</button>
      <script>
      async function uploadProof(){
        const file=document.getElementById('proof').files[0];
        const form=new FormData();form.append('file',file);
        fetch('/submission',{method:'POST',body:'unexpected'}).catch(()=>{});
        const response=await fetch('/file/ajax',{method:'POST',body:form});
        if(response.ok){
          document.querySelector('.file').innerHTML='<a>'+file.name+'</a>';
          const remove=document.createElement('button');
          remove.className='remove';remove.textContent='Remove';
          document.querySelector('#proof-container').append(remove);
        }
      }
      </script></body></html>"""
    requests = []
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(service_workers="block")
        def routes(route):
            requests.append((route.request.method, route.request.url))
            if route.request.url == url:
                route.fulfill(status=200, content_type="text/html", body=html)
            elif route.request.url == "https://admissions.uni.example.edu/file/ajax":
                route.fulfill(status=200, content_type="application/json", body=json.dumps({"ok": True}))
            else:
                route.fulfill(status=500, body="unexpected")
        context.route("**/*", routes)
        page = context.new_page()
        chooser_events = []
        page.on("filechooser", lambda chooser: chooser_events.append(chooser))
        page.goto(url)
        assert upload_one(page, context, plan, plan.bindings[0]) == "uploaded"
        assert upload_one(page, context, plan, plan.bindings[0]) == "already_uploaded"
        assert chooser_events == []
        assert page.locator("#final").count() == 1
        assert page.locator("body").get_attribute("data-final") is None
        assert sum(u.endswith("/file/ajax") for _, u in requests) == 1
        assert not any(u.endswith("/submission") for _, u in requests)
        context.close()
        browser.close()


def test_isolated_persistent_browser_keeps_only_its_synthetic_login(tmp_path):
    import time

    from aihawk.academic_browser_session import launch_academic_context

    sync_api = pytest.importorskip("playwright.sync_api")
    fake_url = "https://admissions.uni.example.edu/apply"
    with sync_api.sync_playwright() as playwright:
        first = launch_academic_context(playwright, manifest_dir=tmp_path, headless=True)
        first.add_cookies([{
            "name": "synthetic_session", "value": "test-only",
            "url": fake_url, "expires": int(time.time()) + 3600,
        }])
        assert any(c["name"] == "synthetic_session" for c in first.cookies([fake_url]))
        first.close()

        resumed = launch_academic_context(playwright, manifest_dir=tmp_path, headless=True)
        try:
            cookies = resumed.cookies([fake_url])
            assert any(c["name"] == "synthetic_session" and c["value"] == "test-only" for c in cookies)
            assert not any(c["name"] == "personal_chrome_cookie" for c in cookies)
        finally:
            resumed.close()


def test_real_chromium_inventory_discovers_hidden_file_control(tmp_path):
    from aihawk.academic_inspect import inspect_controls

    sync_api = pytest.importorskip("playwright.sync_api")
    url = "https://admissions.uni.example.edu/hidden"
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(service_workers="block")
        context.route(url, lambda route: route.fulfill(
            content_type="text/html",
            body="<label for='proof'>Proof</label><input id='proof' type='file' style='display:none'>"
                 "<input id='secret' type='password' value='do-not-export'>",
        ))
        page = context.new_page()
        page.goto(url)
        result = inspect_controls(page, official_hosts=("uni.example.edu",))
        assert len(result["controls"]) == 1
        assert result["controls"][0]["kind"] == "upload"
        assert result["controls"][0]["hidden_upload"] is True
        assert "do-not-export" not in str(result)
        context.close()
        browser.close()


def test_onchange_auto_upload_is_guarded_before_file_attachment(tmp_path):
    from aihawk.academic_uploads import upload_one, upload_plan_from_manifest

    sync_api = pytest.importorskip("playwright.sync_api")
    (tmp_path / "auto.pdf").write_bytes(b"%PDF-1.4 test only")
    url = "https://admissions.uni.example.edu/apply"
    manifest = {
        "title": "Synthetic auto-upload applicant",
        "official_application_url": url,
        "official_hosts": ["uni.example.edu"],
        "applicant_id": "synthetic",
        "fields": {},
        "attachments": ["auto.pdf"],
        "portal_uploads": [{
            "field": "auto.pdf", "input_selector": "#auto",
            "upload_button_selector": "#auto-upload", "container_selector": "#area",
            "receipt_selector": ".file a", "remove_selector": "button.remove",
            "expected_path": "/apply", "upload_endpoint_path": "/file/ajax",
        }],
    }
    plan = upload_plan_from_manifest(manifest, manifest_dir=tmp_path)
    html = """<section id="area"><input id="auto" type="file" hidden>
      <button type="button" id="auto-upload">Upload</button>
      <div class="file"></div></section>
      <button id="final-submit" type="submit">Submit application</button>
      <script>
      document.querySelector('#auto').addEventListener('change',async function() {
        fetch('/submission',{method:'POST',body:'should-be-blocked'}).catch(()=>{});
        const res=await fetch('/file/ajax',{method:'POST',body:'approved-test-only'});
        if(res.ok){
          const file=this.files[0];
          document.querySelector('.file').innerHTML='<a>'+file.name+'</a>';
          const remove=document.createElement('button');
          remove.className='remove';remove.textContent='Remove';
          document.querySelector('#area').append(remove);
        }
      });
      </script>"""
    intercepted = []
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(service_workers="block")
        def synthetic(route):
            intercepted.append(route.request.url)
            if route.request.url == url:
                route.fulfill(content_type="text/html", body=html)
            elif route.request.url.endswith("/file/ajax"):
                route.fulfill(content_type="application/json", body='{"ok":true}')
            else:
                route.fulfill(status=400, body="unexpected")
        context.route("**/*", synthetic)
        page = context.new_page()
        page.goto(url)
        assert upload_one(page, context, plan, plan.bindings[0]) == "uploaded"
        assert "/file/ajax" in " ".join(intercepted)
        assert not any(url.endswith("/submission") for url in intercepted)
        assert page.locator("#final-submit").count() == 1
        context.close()
        browser.close()


def test_reviewed_accordion_opens_only_its_file_section(tmp_path):
    from aihawk.academic_uploads import upload_one, upload_plan_from_manifest

    sync_api = pytest.importorskip("playwright.sync_api")
    (tmp_path / "degree.pdf").write_bytes(b"%PDF-1.4 degree sample")
    url = "https://admissions.uni.example.edu/apply"
    data = {
        "title": "Synthetic accordion upload",
        "official_application_url": url,
        "official_hosts": ["uni.example.edu"],
        "applicant_id": "synthetic",
        "fields": {},
        "attachments": ["degree.pdf"],
        "portal_uploads": [{
            "field": "degree.pdf", "input_selector": "#degree",
            "upload_button_selector": "#degree-upload",
            "container_selector": "#degree-section",
            "receipt_selector": ".file a", "remove_selector": "button.remove",
            "expected_path": "/apply", "upload_endpoint_path": "/file/ajax",
            "expand_selector": "#expand-degree",
        }],
    }
    plan = upload_plan_from_manifest(data, manifest_dir=tmp_path)
    html = """<button id='expand-degree' type='button'
          onclick="document.querySelector('#panel').hidden=false">Degree documents</button>
       <section id='degree-section'>
         <div id='panel' hidden>
           <input id='degree' type='file' hidden>
           <button id='degree-upload' type='button' onclick='uploadIt()'>Upload</button>
         </div>
         <div class='file'></div>
       </section>
       <button id='submit' type='submit'>Submit application</button>
       <script>async function uploadIt(){
         const f=document.getElementById('degree').files[0];
         const r=await fetch('/file/ajax',{method:'POST',body:'synthetic'});
         if(r.ok){
            document.querySelector('.file').innerHTML='<a>'+f.name+'</a>';
            const b=document.createElement('button');
            b.className='remove';b.textContent='Remove';
            document.getElementById('degree-section').append(b);
         }
       }</script>"""
    with sync_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(service_workers="block")
        def routes(route):
            if route.request.url == url:
                route.fulfill(content_type="text/html", body=html)
            elif route.request.url.endswith("/file/ajax"):
                route.fulfill(content_type="application/json", body='{"ok":true}')
            else:
                route.fulfill(status=403, body="disallowed")
        context.route("**/*", routes)
        page = context.new_page()
        page.goto(url)
        assert not page.locator("#degree-upload").is_visible()
        assert upload_one(page, context, plan, plan.bindings[0]) == "uploaded"
        assert page.locator("#degree-upload").is_visible()
        assert page.locator("#submit").count() == 1
        context.close()
        browser.close()
