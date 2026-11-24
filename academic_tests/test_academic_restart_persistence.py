"""Two separate headless browsers with independent simulated server state."""

import pytest
from aihawk.academic_background_journey import run_stage
from aihawk.academic_stages import PortalStage
from aihawk.academic_browser import plan_from_manifest


def test_browser_restart_revalidates_saved_draft(tmp_path):
    sync = pytest.importorskip("playwright.sync_api")
    origin = "https://admissions.uni.example.edu"
    state = {"name": "", "saves": 0, "submissions": 0}
    save = {"selector": "#save", "label": "Save", "receipt_selector": "#saved", "receipt_text": "Saved draft"}
    data = {
        "title": "Synthetic application",
        "official_application_url": origin + "/apply",
        "official_hosts": ["uni.example.edu"],
        "applicant_id": "synthetic",
        "attachments": [],
        "fields": {"name": "Casey Sample"},
        "portal_stages": [
            {
                "name": "Identity",
                "expected_host": "admissions.uni.example.edu",
                "expected_path": "/apply",
                "bindings": [{"field": "name", "selector": "#name", "kind": "text"}],
                "draft_save": save,
            }
        ],
    }
    single = {**data, "portal_bindings": data["portal_stages"][0]["bindings"]}
    single.pop("portal_stages")
    stage = PortalStage("Identity", "admissions.uni.example.edu", "/apply", plan_from_manifest(single, manifest_dir=tmp_path))

    def serve(route):
        req = route.request
        if req.url == origin + "/apply":
            html = (
                '<input id="name" value="'
                + state["name"]
                + '"><button id="save" type="button" onclick="saveDraft()">Save</button><div id="saved"></div><button id="final">Submit application</button><script>async function saveDraft(){await fetch("/draft",{method:"POST",body:document.querySelector("#name").value});document.querySelector("#saved").textContent="Saved draft"}</script>'
            )
            route.fulfill(status=200, content_type="text/html", body=html)
        elif req.url == origin + "/draft" and req.method == "POST":
            state["name"] = req.post_data
            state["saves"] += 1
            route.fulfill(status=200, body="saved")
        elif "/submit" in req.url:
            state["submissions"] += 1
            route.abort()
        else:
            route.abort()

    with sync.sync_playwright() as p:
        for already in (False, True):
            b = p.chromium.launch(channel="chrome", headless=True)
            try:
                c = b.new_context(service_workers="block")
                c.route("**/*", serve)
                page = c.new_page()
                page.goto(origin + "/apply")
                outcome = run_stage(page, c, stage, ("uni.example.edu",), data["portal_stages"][0], already_confirmed=already)
                assert outcome["state"] == ("reverified_no_change" if already else "server_saved_verified")
            finally:
                b.close()
    assert state == {"name": "Casey Sample", "saves": 1, "submissions": 0}
