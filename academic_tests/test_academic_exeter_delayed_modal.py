import hashlib
from playwright.sync_api import sync_playwright
from aihawk.academic_exeter_upload import upload


def test_slow_upload_modal_is_matched_without_double_upload(tmp_path, monkeypatch):
    monkeypatch.setenv("AIHAWK_PORTAL_LIMIT_DB", str(tmp_path / "limits.sqlite3"))
    evidence = tmp_path / "verified.pdf"
    evidence.write_bytes(b"%PDF-1.4\napplicant approved synthetic file")
    item = {
        "portal": "Exeter eVision",
        "role": "CV",
        "file": evidence.name,
        "sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
        "allowed_extensions": ["pdf"],
        "source_evidence": "synthetic reviewed evidence",
    }
    html = """<html><body>
      <button id="up" onclick="setTimeout(() => document.getElementById('modal').hidden=false, 300)">Upload CV 1</button>
      <div id="modal" role="dialog" hidden>
        <h2>Please upload your CV</h2>
        <input id="file" type="file" style="display:none" onchange="window.uploads += 1">
        <a href="#">verified.pdf</a>
        <a href="#">Delete verified.pdf</a>
        <button onclick="document.getElementById('modal').hidden=true">Close</button>
      </div>
      <script>window.uploads=0</script></body></html>"""
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page()
        page.route("https://srs.exeter.ac.uk/**", lambda r: r.fulfill(status=200, content_type="text/html", body=html))
        page.goto("https://srs.exeter.ac.uk/urd/sits.urd/run/siw_ipp_cgi.start")
        result = upload(page, tmp_path, ("srs.exeter.ac.uk",), item)
        assert result["state"] == "modal_upload_acknowledged"
        assert result["server_saved_verified"] is False
        assert page.evaluate("window.uploads") == 0
        assert page.locator("#modal").is_hidden()
        browser.close()
