import hashlib
import pytest
from playwright.sync_api import sync_playwright
from aihawk.academic_exeter_upload import upload
from aihawk.academic_browser import PortalPreparationError


def test_unreviewed_existing_file_never_replaced_or_duplicated(tmp_path, monkeypatch):
    monkeypatch.setenv("AIHAWK_PORTAL_LIMIT_DB", str(tmp_path / "limits.sqlite3"))
    evidence = tmp_path / "approved.pdf"
    evidence.write_bytes(b"%PDF-1.4\napproved fixture")
    item = {
        "portal": "Exeter eVision",
        "role": "CV",
        "file": evidence.name,
        "sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
        "allowed_extensions": ["pdf"],
        "source_evidence": "synthetic reviewed source",
    }
    html = """<html><button onclick="document.getElementById('modal').hidden=false">Upload CV 1</button>
      <div id='modal' role='dialog' hidden><h2>Please upload your CV</h2>
       <a href='#'>different.pdf</a><a href='#'>Delete different.pdf</a>
       <input type='file' style='display:none' onchange='window.uploads+=1'/>
       <button onclick="document.getElementById('modal').hidden=true">Close</button></div>
       <script>window.uploads=0</script></html>"""
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page()
        page.route("https://srs.exeter.ac.uk/**", lambda r: r.fulfill(status=200, content_type="text/html", body=html))
        page.goto("https://srs.exeter.ac.uk/urd/sits.urd/run/siw_ipp_cgi.start")
        with pytest.raises(PortalPreparationError, match="different"):
            upload(page, tmp_path, ("srs.exeter.ac.uk",), item)
        assert page.evaluate("window.uploads") == 0
        assert page.get_by_role("link", name="different.pdf", exact=True).count() == 1
        browser.close()
