"""Resumable application case coordinator. No final submit or email send."""
import argparse,json,re
from datetime import date,datetime,timezone
from pathlib import Path
from aihawk.academic_outreach_workflow import atomic_json,next_actions

def reply_review(state,thread):
    sup=state.get("supervisor",{})
    if thread.get("thread_id")!=sup.get("thread_id"):
        raise ValueError("Wrong Gmail thread")
    if thread.get("truncated"):
        return {"status":"thread_review_incomplete","messages":[]}
    from email.utils import parseaddr
    target=sup.get("email","").casefold()
    incoming=[m for m in thread.get("messages",[]) if m.get("id") and "SENT" not in m.get("labels",[]) and parseaddr(m.get("from") or m.get("from_") or "")[1].casefold()==target]
    if not incoming: return {"status":"awaiting_reply","messages":[]}
    from aihawk.academic_reply_review import classify_reply
    assessments=[classify_reply({**m,"thread_id":thread["thread_id"],"from":m.get("from") or m.get("from_") or ""},sup["email"],sup["thread_id"]) for m in incoming]
    return {"status":"reply_requires_classification","messages":[{"id":m["id"],"body":m.get("body",""),"subject":m.get("subject",""),"date":m.get("email_ts")} for m in incoming],"assessments":assessments}

def plan(state,*,today,thread=None):
    tasks=[]
    if state.get("application_submitted") is True or state.get("status") in ("Submitted","Admitted","Rejected","Closed"):
        return {"status":"terminal","tasks":[]}
    deadline=state.get("deadline")
    if deadline and date.fromisoformat(deadline)<today:
        return {"status":"deadline_passed","tasks":["verify_new_intake_or_archive"],"submission_allowed":False}
    blockers=list(state.get("remaining_blockers",[]))
    sup=state.get("supervisor",{})
    reply=reply_review(state,thread) if thread is not None else None
    for action in next_actions(blockers):
        if action=="research_supervisors_and_prepare_personalized_outreach" and sup.get("message_id"):
            if reply and reply["status"]=="reply_requires_classification":
                tasks.append("classify_actual_supervisor_reply")
            else: tasks.append("check_existing_supervisor_thread")
        else: tasks.append(action)
    if sup.get("message_id") and not state.get("tracker_sync",{}).get("verified"):
        tasks.insert(0,"reconcile_sent_message_and_sync")
    if not blockers:
        tasks.extend(["validate_verified_profile_and_documents","generate_position_specific_documents","prepare_reviewed_portal_manifest","run_reviewed_draft_journey"])
    return {"status":state.get("status","Researching"),"tasks":list(dict.fromkeys(tasks)),"reply_review":reply,"submission_allowed":False,"email_send_allowed":False}

def main():
    p=argparse.ArgumentParser();p.add_argument("case",type=Path);p.add_argument("--thread",type=Path);p.add_argument("--out",type=Path);a=p.parse_args()
    case=a.case.resolve(strict=True); state=json.loads(case.read_text(encoding="utf8"))
    thread=json.loads(a.thread.read_text(encoding="utf8")) if a.thread else None
    report=plan(state,today=date.today(),thread=thread)
    report["checked_at"]=datetime.now(timezone.utc).isoformat()
    out=(a.out or case.with_name("AIHawk_Next_Actions.json")).resolve()
    if out.parent!=case.parent or out==case: raise ValueError("Output must be separate and in case folder")
    atomic_json(out,report)
    print(json.dumps({"status":report["status"],"tasks":report["tasks"],"reply_status":(report.get("reply_review") or {}).get("status")},ensure_ascii=True))
if __name__=="__main__": main()
