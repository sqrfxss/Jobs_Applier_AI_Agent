"""Recover a truly empty university page with one official GET, never a POST replay."""
from __future__ import annotations
from pathlib import Path
from datetime import datetime,timezone
from aihawk.academic_browser import verified_portal_host,PortalPreparationError
from aihawk.academic_outreach_workflow import atomic_json
from aihawk.academic_field_journal import record as field_record

def recover_once(page,folder,hosts,title,official_entry):
    verified_portal_host(page.url,hosts)
    verified_portal_host(official_entry,hosts)
    data={"schema":"aihawk.portal.recovery.v1",
          "checked_at":datetime.now(timezone.utc).isoformat(),
          "attempted":False,"final_submission":False}
    path=Path(folder)/"Agent_Portal_Recovery.json"
    # Only recover a blank, authenticated-domain document, not a validation form.
    if page.get_by_text(title,exact=True).count()==1:
        data.update(status="already_on_project")
    elif page.locator('input[type="password"]:visible').count():
        data.update(status="manual_login_required")
    else:
        visible=page.locator('input:visible,select:visible,textarea:visible,button:visible')
        body=page.locator("body")
        text=body.inner_text(timeout=2000).strip() if body.count()==1 else ""
        if visible.count()>0 or len(text)>0:
            data.update(status="nonblank_unverified_page_manual_review")
        else:
            # Safe new GET, not reload() of a POST-backed form.
            data["attempted"]=True
            field_record(folder,stage="_portal",field="_document",action="navigation",
                         status="started",details="bounded_official_get_recovery")
            try:
                page.goto(official_entry,wait_until="domcontentloaded",timeout=12000)
                page.wait_for_timeout(600)
                verified_portal_host(page.url,hosts)
                project=page.get_by_text(title,exact=True)
                if project.count()==1 and project.is_visible():
                    data["status"]="project_restored"
                elif page.locator('input[type="password"]:visible').count():
                    data["status"]="manual_login_required"
                else:
                    data["status"]="unverified_after_official_get"
            except Exception as exc:
                data["status"]="official_get_failed"
                data["error_type"]=type(exc).__name__
            field_record(folder,stage="_portal",field="_document",action="navigation",
                         status="navigation_rejected" if data["status"] not in
                         ("project_restored",) else "local_verified",
                         details=data["status"])
    atomic_json(path,data)
    return data
