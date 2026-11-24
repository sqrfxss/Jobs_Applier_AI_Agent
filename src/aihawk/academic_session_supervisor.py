"""Automatic, bounded recovery after an institution expires a login session.

This does not bypass login, solve CAPTCHA, send messages, or click Submit.
Only authenticated, reviewed draft stages may run, and stored checkpoints are
revalidated against the university after reauthentication.
"""
from __future__ import annotations
import json
from pathlib import Path
from time import monotonic
from aihawk.academic_outreach_workflow import atomic_json
from aihawk.academic_browser import PortalPreparationError
from aihawk.academic_session_batch import run_batch,auth_expired
from aihawk.academic_session_progress import load

def await_authentication(page,folder,hosts,title,*,poll_ms=1000,limit_seconds=20):
    from aihawk.academic_resume_session import inspect_page,checkpoint
    from playwright.sync_api import Error as PlaywrightError
    deadline=monotonic()+limit_seconds if limit_seconds is not None else None
    previous=None
    while not page.is_closed() and (deadline is None or monotonic()<deadline):
        try:
            state=inspect_page(page,hosts,title)["status"]
            if state=="project_session_verified":
                checkpoint(folder,{"status":"authenticated_project_restored",
                                   "final_submission":False})
                return True
            if state!=previous:
                checkpoint(folder,{"status":"waiting_for_manual_login" if state=="manual_sign_in_required" else
                            "waiting_for_verified_project","final_submission":False})
                print(json.dumps({"session":state,"final_submission":False}),flush=True)
                previous=state
            page.wait_for_timeout(poll_ms)
        except PlaywrightError:
            if page.is_closed():return False
            page.wait_for_timeout(poll_ms)
    return False

def supervise(page,folder,hosts,title,plan_path,*,auth_recoveries=3,
              wait=await_authentication,execute=run_batch):
    from aihawk.academic_resume_session import checkpoint
    folder=Path(folder).resolve(strict=True)
    path=Path(plan_path).resolve(strict=True)
    if not path.is_relative_to(folder):
        raise PortalPreparationError("Plan outside the private application case")
    attempts=0
    while not page.is_closed():
        if not wait(page,folder,hosts,title):
            if page.is_closed():
                state="browser_closed"
            else:
                from aihawk.academic_resume_session import inspect_page
                try:
                    observed=inspect_page(page,hosts,title)["status"]
                    state=("authentication_required" if
                           observed=="manual_sign_in_required" else
                           "portal_unverified")
                except Exception:
                    state="portal_unverified"
            checkpoint(folder,{"status":state,"final_submission":False})
            return {"status":state,"final_submission":False}
        plan=json.loads(path.read_text(encoding="utf-8-sig"))
        if plan.get("schema")!="aihawk.session.batch.v1" or plan.get("project_title")!=title or plan.get("final_submission") is not False:
            raise PortalPreparationError("Invalid or unsafe revised batch plan")
        report=execute(page,folder,hosts,title,plan)
        if report.get("final_submission") is not False:
            raise PortalPreparationError("Unexpected final submission attempted")
        if report.get("status")=="awaiting_manual_login":
            attempts+=1
            checkpoint(folder,{"status":"authentication_expired_during_draft",
                               "recovery_attempt":attempts,"final_submission":False})
            if attempts>auth_recoveries:
                return {"status":"manual_session_review_required",
                        "final_submission":False,"auth_recoveries":attempts}
            continue
        # Do not blindly retry uncertain file uploads or a validation failure.
        checkpoint(folder,{"status":report.get("status","review_required"),
                           "recovery_attempts":attempts,"final_submission":False})
        return report
    return {"status":"browser_closed","final_submission":False}
