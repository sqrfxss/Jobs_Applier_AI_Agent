"""Regression coverage for draft resume, session expiry, and avoidable navigation."""
import json
from pathlib import Path
import pytest
from aihawk.academic_session_progress import (
    update,load,stage_digest,is_verified_checkpoint,should_skip_verified_stage)
from aihawk.academic_session_supervisor import supervise
from aihawk.academic_session_controls import navigate

@pytest.fixture
def page():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        try:b=p.chromium.launch(channel="chrome",headless=True)
        except Exception as exc:pytest.skip(str(exc))
        context=b.new_context()
        pg=context.new_page()
        yield pg
        b.close()

def stage(value="Example"):
    return {"section":"About You","visible_heading":"About you","reviewed_complete":True,
            "actions":[{"type":"fill","selector":"#first","value":value}],
            "next_visible_heading":"Home address line 1"}

def setup_server(pg,state):
    from urllib.parse import parse_qs,urlsplit
    def serve(route):
        state["requests"]+=1
        q=parse_qs(urlsplit(route.request.url).query)
        if q.get("section")==["About You"]:state["section"]="About You"
        current=state["section"]
        heading="About you" if current=="About You" else "Home address line 1"
        control=f'<input id="first" value="{state["value"]}">' if current=="About You" else ""
        html=f'<h1>Example project</h1><h2>{heading}</h2><form><button name="section" value="About You">About You</button><button name="section" value="Address">Address</button></form>{control}'
        route.fulfill(status=200,content_type="text/html",body=html)
    pg.route("https://example.edu/**",serve)
    pg.goto("https://example.edu/apply")

def test_completed_draft_rechecked_from_server_not_just_local_journal(page,tmp_path):
    state={"section":"About You","value":"Example","requests":0}
    setup_server(page,state)
    s=stage()
    update(tmp_path,s,"server_readback_verified",verified=True,duration_ms=125)
    assert is_verified_checkpoint(tmp_path,s)
    before=state["requests"]
    assert should_skip_verified_stage(page,tmp_path,s,("example.edu",),"Example project")
    assert state["requests"]>before, "Resume must request fresh university state"
    assert load(tmp_path)["stages"]["About You"]["server_saved_verified"] is True
    # Simulate a server rollback after local success.
    state["value"]="Some other text"
    assert not should_skip_verified_stage(page,tmp_path,s,("example.edu",),"Example project")
    assert load(tmp_path)["stages"]["About You"]["status"]=="requires_reconciliation"
    assert not is_verified_checkpoint(tmp_path,s)

def test_changed_reviewed_plan_invalidates_saved_stage(tmp_path):
    original=stage()
    update(tmp_path,original,"server_readback_verified",verified=True)
    assert is_verified_checkpoint(tmp_path,original)
    changed=stage("Changed")
    assert stage_digest(original)!=stage_digest(changed)
    assert not is_verified_checkpoint(tmp_path,changed)

def test_navigate_current_section_zero_network_and_forced_audit_one(page):
    state={"section":"About You","value":"Example","requests":0}
    setup_server(page,state)
    before=state["requests"]
    navigate(page,("example.edu",),"Example project","About You",expected_heading="About you")
    assert state["requests"]==before, "No unnecessary navigation when already on target"
    navigate(page,("example.edu",),"Example project","About You",expected_heading="About you",force=True)
    assert state["requests"]==before+1, "Audit must make one new portal request"

def test_supervisor_continues_after_relogin_without_new_user_command(tmp_path):
    plan={"schema":"aihawk.session.batch.v1",
          "project_title":"Example project","final_submission":False,
          "stages":[stage()]}
    path=tmp_path/"Session_Batch_Plan.json"
    path.write_text(json.dumps(plan),encoding="utf8")
    class P:
        def is_closed(self):return False
    observations={"wait":0,"batch":0}
    def wait(page,folder,hosts,title):
        observations["wait"]+=1
        return True
    def execute(page,folder,hosts,title,plan):
        observations["batch"]+=1
        return {"status":"awaiting_manual_login" if observations["batch"]==1
                else "reviewed_stages_completed","final_submission":False}
    report=supervise(P(),tmp_path,("example.edu",),"Example project",path,wait=wait,execute=execute)
    assert report["status"]=="reviewed_stages_completed"
    assert observations=={"wait":2,"batch":2}
    state=json.loads((tmp_path/"Session_Checkpoint.json").read_text())
    assert state["status"]=="reviewed_stages_completed"
    assert state["final_submission"] is False

def test_supervisor_never_retries_uncertain_upload(tmp_path):
    plan={"schema":"aihawk.session.batch.v1","project_title":"Example project",
          "final_submission":False,"stages":[stage()]}
    path=tmp_path/"Session_Batch_Plan.json"
    path.write_text(json.dumps(plan),encoding="utf8")
    class P:
        def is_closed(self):return False
    count=[]
    def execute(*args):
        count.append(1)
        return {"status":"blocked_modal_review_required","final_submission":False}
    result=supervise(P(),tmp_path,("example.edu",),"Example project",path,
                    wait=lambda *args:True,execute=execute)
    assert result["status"]=="blocked_modal_review_required"
    assert len(count)==1

def test_supervisor_refuses_unreviewed_or_submit_plan(tmp_path):
    path=tmp_path/"Session_Batch_Plan.json"
    path.write_text(json.dumps({"schema":"aihawk.session.batch.v1",
         "project_title":"Example project","final_submission":True,"stages":[stage()]}))
    class P:
        def is_closed(self):return False
    from aihawk.academic_browser import PortalPreparationError
    with pytest.raises(PortalPreparationError,match="unsafe"):
        supervise(P(),tmp_path,("example.edu",),"Example project",path,
                  wait=lambda *args:True,execute=lambda *args:None)
