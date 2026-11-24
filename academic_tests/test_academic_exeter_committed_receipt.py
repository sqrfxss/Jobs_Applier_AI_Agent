import pytest
from playwright.sync_api import sync_playwright
from aihawk.academic_exeter_upload import committed_receipt
from aihawk.academic_session_progress import _verify_upload
from aihawk.academic_browser import PortalPreparationError


def _page(p, content):
    b = p.chromium.launch(channel="chrome", headless=True)
    page = b.new_page()
    page.set_content(content)
    return b, page


BASE = """<button onclick="document.querySelector('[role=dialog]').style.display='block'">Upload transcript 1</button>
  <div role="dialog" style="display:none"><h3>Please upload your transcript</h3>
  <a href="#">Applicant_BSc_Transcript.pdf</a>
  <a href="#">Delete Applicant_BSc_Transcript.pdf</a>
  {extra}
  <button onclick="this.parentElement.style.display='none'">Close</button></div>"""


def test_exeter_existing_document_receipt_is_not_reuploaded():
    with sync_playwright() as p:
        b, page = _page(p, BASE.format(extra=""))
        page.get_by_role("button", name="Upload transcript 1").click()
        assert committed_receipt(page.get_by_role("dialog"), "Applicant_BSc_Transcript.pdf")
        action = {"role": "transcript", "index": 0, "file": "Documents/Applicant_BSc_Transcript.pdf"}
        _verify_upload(page, action)
        assert not page.get_by_role("dialog").is_visible()
        b.close()


def test_queued_attachment_is_never_misclassified_as_saved():
    with sync_playwright() as p:
        b, page = _page(p, BASE.format(extra="<p>File Status: Awaiting Upload</p>"))
        page.get_by_role("button", name="Upload transcript 1").click()
        assert not committed_receipt(page.get_by_role("dialog"), "Applicant_BSc_Transcript.pdf")
        action = {"role": "transcript", "index": 0, "file": "Documents/Applicant_BSc_Transcript.pdf"}
        with pytest.raises(PortalPreparationError):
            _verify_upload(page, action)
        b.close()
