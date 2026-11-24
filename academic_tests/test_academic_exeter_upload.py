import hashlib
import pytest
from aihawk.academic_exeter_upload import upload
from aihawk.academic_browser import PortalPreparationError

def test_exeter_html5_queue_then_real_commit(tmp_path,monkeypatch):
 from playwright.sync_api import sync_playwright
 monkeypatch.setenv("AIHAWK_PORTAL_LIMIT_DB",str(tmp_path/"limits.sqlite"))
 f=tmp_path/"verified.pdf";f.write_bytes(b"%PDF-1.4\nverified data")
 item={"portal":"Exeter eVision","role":"CV","file":f.name,"sha256":hashlib.sha256(f.read_bytes()).hexdigest(),"allowed_extensions":["pdf"],"source_evidence":"user-approved original PDF"}
 with sync_playwright() as p:
  try:b=p.chromium.launch(channel="chrome",headless=True)
  except Exception as e:pytest.skip(str(e))
  page=b.new_page()
  html="""<button id='up' onclick="document.getElementById('modal').hidden=false">Upload CV&nbsp; 0</button>
<div id='modal' role='dialog' hidden><h2>Please upload your CV</h2>
<input id='upfile' type='file' style='display:none' onchange="document.getElementById('queue').innerText=this.files[0].name+' Awaiting Upload';this.value='';">
<div id='queue'></div><a href='javascript:void(0)' onclick="document.getElementById('queue').innerText='verified.pdf Uploaded';document.getElementById('up').textContent='Upload CV 1';">Upload</a>
<button onclick="document.getElementById('modal').hidden=true">Close</button></div>"""
  page.route("https://srs.exeter.ac.uk/**",lambda r:r.fulfill(status=200,content_type="text/html",body=html))
  page.goto("https://srs.exeter.ac.uk/urd/sits.urd/run/siw_ipp_cgi.start")
  r=upload(page,tmp_path,("srs.exeter.ac.uk",),item)
  assert r["state"]=="modal_upload_acknowledged"
  assert r["server_saved_verified"] is False
  assert "CV 1" in page.locator("#up").inner_text()
  with pytest.raises(PortalPreparationError):
   upload(page,tmp_path,("other.example.edu",),item)
  b.close()
