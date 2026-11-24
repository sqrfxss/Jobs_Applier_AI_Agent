import hashlib
import pytest
from aihawk.academic_custom_controls import custom_select, modal_upload, receipt
from aihawk.academic_session_batch import run_batch
from aihawk.academic_browser import PortalPreparationError


@pytest.fixture
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        try:
            b = p.chromium.launch(channel="chrome", headless=True)
        except Exception as e:
            pytest.skip(str(e))
        yield b
        b.close()


def test_custom_dropdown_scoped(browser):
    p = browser.new_page()
    p.set_content(
        """<div id="menu"><button id="trigger" onclick="document.getElementById('opts').hidden=false">Choose</button><span id="picked">Choose...</span><div id="opts" hidden><button role="option" onclick="document.getElementById('picked').textContent='Iran';this.parentNode.hidden=true">Iran</button></div></div><button role="option">Iran</button>"""
    )
    item = {
        "container_selector": "#menu",
        "trigger_selector": "#trigger",
        "selected_selector": "#picked",
        "label": "Iran",
        "source_evidence": "reviewed citizenship",
    }
    custom_select(p, item)
    assert p.locator("#picked").inner_text() == "Iran"
    custom_select(p, item)
    item["label"] = "Unknown"
    with pytest.raises(PortalPreparationError):
        custom_select(p, item)
    p.close()


def test_modal_upload_receipt_and_no_duplicate(browser, tmp_path, monkeypatch):
    monkeypatch.setenv("AIHAWK_PORTAL_LIMIT_DB", str(tmp_path / "limits.sqlite"))
    f = tmp_path / "example.pdf"
    f.write_bytes(b"%PDF-1.4\nexample")
    p = browser.new_page()
    p.route(
        "https://example.edu/**",
        lambda r: r.fulfill(
            status=200,
            content_type="text/html",
            body="""<button onclick="document.getElementById('dialog').hidden=false">Upload CV</button><div id="dialog" hidden><input type="file" id="file" style="display:none"><button onclick="document.getElementById('receipt').textContent=document.getElementById('file').files[0].name;document.getElementById('dialog').hidden=true">Upload</button></div><div id="receipt"></div>""",
        ),
    )
    p.goto("https://example.edu/apply")
    item = {
        "open_label": "Upload CV",
        "dialog_selector": "#dialog",
        "input_selector": "#file",
        "upload_label": "Upload",
        "receipt_container_selector": "#receipt",
        "receipt_text": f.name,
        "file": f.name,
        "sha256": hashlib.sha256(f.read_bytes()).hexdigest(),
        "allowed_extensions": ["pdf"],
    }
    assert modal_upload(p, tmp_path, ("example.edu",), item) == "receipt_visible"
    assert receipt(p, item)
    assert modal_upload(p, tmp_path, ("example.edu",), item) == "already_present"
    item["sha256"] = "0" * 64
    with pytest.raises(PortalPreparationError):
        modal_upload(p, tmp_path, ("example.edu",), item)
    p.close()


def test_batch_reopens_and_verifies_and_stops_before_final(browser, tmp_path, monkeypatch):
    monkeypatch.setenv("AIHAWK_PORTAL_LIMIT_DB", str(tmp_path / "limits.sqlite"))
    p = browser.new_page()
    state = {"section": "About You", "value": ""}

    def handler(route):
        from urllib.parse import parse_qs, urlsplit

        q = parse_qs(urlsplit(route.request.url).query)
        if "save" in q:
            state.update(value=q.get("first", [""])[0], section="Address")
        elif "section" in q:
            state["section"] = q["section"][0]
        section = state["section"]
        head = "About you" if section == "About You" else "Home address line 1"
        field = f'<input name="first" id="first" value="{state["value"]}">' if section == "About You" else '<input id="address">'
        html = f'<h1>Example project</h1><form><button name="section" value="About You">About You</button><button name="section" value="Address">Address</button></form><h2>{head}</h2><form>{field}<button name="save" value="yes">Save and continue</button></form>'
        route.fulfill(status=200, content_type="text/html", body=html)

    p.route("https://example.edu/**", handler)
    p.goto("https://example.edu/apply")
    plan = {
        "schema": "aihawk.session.batch.v1",
        "project_title": "Example project",
        "stages": [
            {
                "section": "About You",
                "visible_heading": "About you",
                "reviewed_complete": True,
                "actions": [{"type": "fill", "selector": "#first", "value": "Example"}],
                "next_visible_heading": "Home address line 1",
            },
            {"section": "Address", "visible_heading": "Home address line 1", "reviewed_complete": False},
        ],
    }
    r = run_batch(p, tmp_path, ("example.edu",), "Example project", plan)
    assert r["stages"][0]["server_saved_verified"] is True
    assert r["stages"][1]["state"] == "mapping_review_required"
    assert r["status"] == "blocked" and r["final_submission"] is False
    p.close()
