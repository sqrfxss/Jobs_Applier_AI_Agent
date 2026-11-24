"""Private, append-only field lifecycle journal for academic portal automation.

No raw answers, credentials, tokens, uploaded document bodies, or applicant
identifiers. Local control identity and validation message labels only.
"""
from __future__ import annotations

from datetime import datetime,timezone
from pathlib import Path
import json,os,re
from aihawk.academic_outreach_workflow import atomic_json

JOURNAL="Agent_Field_Log.jsonl"
SUMMARY="Agent_Field_Status.json"
STATES={"planned","started","local_verified","server_verified","blocked","validation_rejected",
        "save_attempt","save_unverified","navigation_rejected","upload_pending",
        "receipt_unverified","skipped","stage_blocked"}
FIELDS={"stage","field","action","status","error_type","details","attempt",
        "server_saved_verified","elapsed_ms","validation_fields"}

def _safe(s):
    if s is None:return None
    s=str(s)
    # No free-form exception text or values; only known diagnostic codes.
    s=re.sub(r"[^a-zA-Z0-9_# .:-]","_",s)
    return s[:130]

def record(folder,*,stage,field=None,action=None,status,defer_summary=False,**extra):
    if status not in STATES:raise ValueError("Unreviewed field lifecycle state")
    folder=Path(folder).resolve(strict=True)
    data={"at_utc":datetime.now(timezone.utc).isoformat(),
          "stage":_safe(stage),"field":_safe(field),
          "action":_safe(action),"status":status,
          "server_saved_verified":status=="server_verified"}
    for k,v in extra.items():
        if k not in FIELDS:continue
        if k=="validation_fields":
            data[k]=[_safe(x) for x in v][:30]
        elif k in ("server_saved_verified",):
            data[k]=bool(v) and status=="server_verified"
        elif k in ("elapsed_ms","attempt"):
            data[k]=int(v)
        else:data[k]=_safe(v)
    line=json.dumps(data,ensure_ascii=False,separators=(",",":"))+"\n"
    p=folder/JOURNAL
    fd=os.open(str(p),os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600)
    try:
        os.write(fd,line.encode("utf8"))
        os.fsync(fd)
    finally:os.close(fd)
    if defer_summary:
        # The append-only journal is fsync'd above. During high-volume filling,
        # a single summary refresh at stage end avoids repeated JSON rewrites.
        return data
    path=folder/SUMMARY
    if path.is_file():
        summary=json.loads(path.read_text(encoding="utf-8-sig"))
    else:
        summary={"schema":"aihawk.field.status.v1","fields":{},
                 "final_submission":False}
    key=(data["stage"] or "")+"::"+(data["field"] or "_stage")
    summary["fields"][key]=data
    summary["checked_at"]=data["at_utc"]
    # No status is inflated to saved just because it was typed or Save clicked.
    summary["all_fields_server_verified"]=bool(summary["fields"]) and all(
        v.get("server_saved_verified") is True for v in summary["fields"].values())
    summary["final_submission"]=False
    atomic_json(path,summary)
    return data

def reconcile_summary(folder):
    """Regenerate a status snapshot from durable journal events after a crash.

    Partial final JSONL lines are ignored. Never infer server success from
    planned, started, locally typed or clicked-save events.
    """
    folder=Path(folder).resolve(strict=True)
    p=folder/JOURNAL
    path=folder/SUMMARY
    summary=(json.loads(path.read_text(encoding="utf-8-sig")) if path.is_file()
             else {"schema":"aihawk.field.status.v1","fields":{},"final_submission":False})
    fields=summary.setdefault("fields",{})
    if p.is_file():
        with p.open("rb") as f:
            for line in f:
                if not line.endswith(b"\n"):
                    continue
                try:entry=json.loads(line)
                except (UnicodeDecodeError,json.JSONDecodeError):
                    continue
                stage=entry.get("stage")
                field=entry.get("field") or "_stage"
                if not stage or entry.get("status") not in STATES:
                    continue
                fields[stage+"::"+field]=entry
                summary["checked_at"]=entry.get("at_utc")
    summary["all_fields_server_verified"]=bool(fields) and all(
        x.get("server_saved_verified") is True for x in fields.values())
    summary["final_submission"]=False
    atomic_json(path,summary)
    return summary

def validation_labels(page):
    """Read the university-rendered 'Errors' list without collecting form values."""
    try:
        return page.evaluate("""() => {
          const h=[...document.querySelectorAll('h1,h2,h3,h4')].find(
            e=>e.textContent.trim()==='Errors');
          if(!h)return [];
          const target=h.parentElement;
          if(!target)return [];
          const labels=[...target.querySelectorAll('li')]
               .map(x=>x.textContent.trim()).filter(Boolean);
          return labels.slice(0,30);
        }""")
    except Exception:
        return []


def seed_plan(folder,plan):
    """Seed reviewed controls in one journal append + one atomic summary write.

    Previous code rewrote the full growing status JSON for *every* field.
    This is O(n^2) serialization and many synchronous filesystem writes.
    Preserve the append-only evidence journal and existing review decisions.
    """
    folder=Path(folder).resolve(strict=True)
    path=folder/SUMMARY
    summary=(json.loads(path.read_text(encoding="utf-8-sig"))
             if path.is_file() else
             {"schema":"aihawk.field.status.v1","fields":{},
              "final_submission":False})
    fields=summary.setdefault("fields",{})
    journal=folder/JOURNAL
    if journal.is_file() and (not path.is_file() or
                               journal.stat().st_mtime_ns>path.stat().st_mtime_ns):
        summary=reconcile_summary(folder)
        fields=summary.setdefault("fields",{})
    planned=[]
    stamped=datetime.now(timezone.utc).isoformat()
    for stage in plan.get("stages",[]):
        name=str(stage.get("section",""))
        for item in stage.get("actions",[]):
            typ=str(item.get("type","unknown"))
            field=str(item.get("selector") or item.get("target_selector") or
                      (typ+":"+str(item.get("role","control"))+":"+
                       str(item.get("index",""))))
            key=_safe(name)+"::"+_safe(field)
            if key in fields:
                continue
            entry={"at_utc":stamped,"stage":_safe(name),"field":_safe(field),
                   "action":_safe(typ),"status":"planned",
                   "server_saved_verified":False}
            planned.append((key,entry))
            fields[key]=entry
    if not planned:
        return len(fields)
    # One append with a single durability barrier; never logs form values.
    data="".join(json.dumps(entry,ensure_ascii=False,separators=(",",":"))+
                 "\n" for _,entry in planned).encode("utf8")
    fd=os.open(str(folder/JOURNAL),os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600)
    try:
        with os.fdopen(fd,"ab",closefd=False) as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
    finally:
        os.close(fd)
    summary["checked_at"]=stamped
    summary["all_fields_server_verified"]=False
    summary["final_submission"]=False
    atomic_json(path,summary)
    return len(fields)
