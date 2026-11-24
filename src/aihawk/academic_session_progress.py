"""Persistent, source-verified application progress, with no automatic Submit.

A stage is complete only after navigating away and independently re-reading the
saved values or an unambiguous uploaded-document receipt. A local checkpoint
alone never certifies a university server write.
"""
from __future__ import annotations
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from aihawk.academic_outreach_workflow import atomic_json
from aihawk.academic_browser import PortalPreparationError
from aihawk.academic_field_journal import record as field_record

SCHEMA = "aihawk.session.progress.v2"
FILE = "Session_Progress.json"

def stage_digest(stage):
    return hashlib.sha256(json.dumps(stage,sort_keys=True,ensure_ascii=False,
                                     separators=(",",":")).encode("utf-8")).hexdigest()

def load(folder):
    path=Path(folder)/FILE
    if not path.exists():
        return {"schema":SCHEMA,"stages":{},"final_submission":False}
    data=json.loads(path.read_text(encoding="utf-8-sig"))
    if data.get("schema")!=SCHEMA or data.get("final_submission") is not False:
        raise PortalPreparationError("Unexpected application checkpoint: review required")
    return data

def update(folder,stage,status,*,verified=False,duration_ms=None,reason=None):
    name=stage["section"]
    if not name or name=="Declaration and Submission":
        raise PortalPreparationError("Final submission cannot be checkpointed")
    data=load(folder)
    data["stages"][name]={
        "stage_hash":stage_digest(stage),
        "status":status,
        "server_saved_verified":bool(verified),
        "checked_at":datetime.now(timezone.utc).isoformat(),
        "duration_ms":duration_ms,
        "reason":reason[:180] if reason else None,
    }
    atomic_json(Path(folder)/FILE,data)
    return data["stages"][name]

def is_verified_checkpoint(folder,stage):
    entry=load(folder)["stages"].get(stage["section"],{})
    return (entry.get("stage_hash")==stage_digest(stage) and
            entry.get("status")=="server_readback_verified" and
            entry.get("server_saved_verified") is True)

def _single(loc,label):
    if loc.count()!=1:
        raise PortalPreparationError("Stored "+label+" missing or ambiguous")
    return loc

def _verify_searchable(page,action):
    label=action["label_contains"]
    value=action["option"]
    native=page.locator("select")
    matches=native.evaluate_all("""(es,q)=>es.flatMap((e,i)=>{
      const labs=[...(e.labels||[])].map(x=>x.textContent||"").join(" ");
      return labs.toLowerCase().includes(q.toLowerCase())?[i]:[];
    })""",label)
    if len(matches)==1:
        chosen=native.nth(matches[0]).locator("option:checked")
        if chosen.count()!=1 or chosen.inner_text().strip()!=value:
            raise PortalPreparationError("Stored native searchable selection mismatch")
        return
    if len(matches)>1:
        raise PortalPreparationError("Stored searchable native fields ambiguous")
    # Genuinely custom dropdown; no native select available.
    loc=page.get_by_text(value,exact=True)
    visible=[loc.nth(i) for i in range(loc.count()) if loc.nth(i).is_visible()]
    if len(visible)!=1:
        raise PortalPreparationError("Stored custom selection not independently verifiable")

def _verify_upload(page,action):
    from aihawk.academic_exeter_upload import _trigger,_modal,ROLES,normalized_visible,committed_receipt
    from aihawk.academic_custom_controls import file_evidence
    filename=Path(action["file"]).name
    control=_trigger(page,action["role"],action.get("index"))
    caption=control.inner_text()
    if not re.search(r"\b[1-9]\d*\b",caption):
        raise PortalPreparationError("Document upload count absent after server readback")
    control.click(timeout=5000,no_wait_after=True)
    try:
        dialog=_modal(page,ROLES[action["role"]])
        content=normalized_visible(dialog.inner_text(timeout=3000))
        if normalized_visible(filename) not in content:
            raise PortalPreparationError("Uploaded document filename not found on server")
        if (not re.search(r"(?i)uploaded|successful|completed",content) or
            re.search(r"(?i)awaiting upload",content)) and not committed_receipt(dialog,filename):
            raise PortalPreparationError("Uploaded document lacks a fresh server receipt")
    finally:
        dialog=page.get_by_role("dialog")
        if dialog.count()==1 and dialog.is_visible():
            close=dialog.get_by_role("button",name="Close",exact=True)
            if close.count()==1:close.click(timeout=4000,no_wait_after=True)

def verify_stage(page,stage,hosts,title,*,navigate_to=True,folder=None):
    """Verify the previously saved stage by a FRESH request to the same portal."""
    from aihawk.academic_session_controls import navigate,_guard
    if navigate_to:
        navigate(page,hosts,title,stage["section"],expected_heading=stage["visible_heading"],force=True)
    _guard(page,hosts,title)
    heading=page.get_by_role("heading",name=stage["visible_heading"],exact=True)
    if heading.count()!=1 or not heading.is_visible():
        raise PortalPreparationError("Saved stage heading mismatch")
    for action in stage.get("actions",[]):
        typ=action["type"]
        target=str(action.get("selector") or action.get("target_selector") or
              (typ+":"+str(action.get("role","control"))+":"+
               str(action.get("index",""))))
        try:
            typ=action["type"]
            if typ=="repeater_add":
                target=page.locator(action["target_selector"])
                if target.count()!=1 or not target.is_visible():
                    raise PortalPreparationError("Saved second-degree panel is not visible")
            elif typ=="react_select":
                _verify_searchable(page,action)
            elif typ=="custom_select":
                from aihawk.academic_custom_controls import menu_value
                if menu_value(page,action)!=action["label"]:
                    raise PortalPreparationError("Stored custom selection mismatch")
            elif typ=="exeter_upload":
                _verify_upload(page,action)
            elif typ=="modal_upload":
                from aihawk.academic_custom_controls import receipt
                if not receipt(page,action):
                    raise PortalPreparationError("Stored attachment receipt missing")
            else:
                node=_single(page.locator(action["selector"]),typ)
                if typ=="fill" and node.input_value()!=str(action["value"]):
                    raise PortalPreparationError("Stored text field mismatch: "+action["selector"])
                elif typ=="select":
                    label=node.locator("option:checked")
                    if label.count()!=1 or label.inner_text()!=action["label"]:
                        raise PortalPreparationError("Stored select field mismatch: "+action["selector"])
                elif typ=="radio" and not node.is_checked():
                    raise PortalPreparationError("Stored radio field mismatch: "+action["selector"])
                elif typ=="upload":
                    raise PortalPreparationError("Native file selection alone is not a server receipt")
                elif typ not in ("fill","select","radio"):
                    raise PortalPreparationError("Unknown stage action "+str(typ))
        except Exception as exc:
            if folder is not None:
                field_record(folder,stage=stage["section"],field=target,
                            action=typ,status="blocked",
                            error_type=type(exc).__name__,
                            details="fresh_readback_mismatch")
            raise
        else:
            if folder is not None:
                field_record(folder,stage=stage["section"],field=target,
                            action=typ,status=("server_verified" if navigate_to
                            else "local_verified"),
                            details="fresh_university_response" if navigate_to
                            else "previous_loaded_document")
    return True

def should_skip_verified_stage(page,folder,stage,hosts,title):
    """A prior checkpoint is a hint, NOT proof; always re-open and re-read."""
    if not is_verified_checkpoint(folder,stage):
        return False
    try:
        verify_stage(page,stage,hosts,title,folder=folder)
        return True
    except Exception:
        update(folder,stage,"requires_reconciliation",verified=False,
               reason="Prior saved checkpoint did not pass a fresh server readback")
        return False
