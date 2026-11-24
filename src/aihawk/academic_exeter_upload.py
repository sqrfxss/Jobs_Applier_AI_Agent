"""University of Exeter e:Vision HTML5 upload modal driver; no native file chooser."""
from __future__ import annotations
from pathlib import Path
import re
from aihawk.academic_browser import PortalPreparationError,verified_portal_host
from aihawk.academic_portal_limits import check_access
from aihawk.academic_action_budget import ActionBudget
from aihawk.academic_custom_controls import file_evidence

ROLES={
    "CV":"Please upload your CV",
    "personal statement":"Please upload your personal statement",
    "transcript":"Please upload your transcript",
    "certificate":"Please upload your certificate, if you have it.",
    "test results":"Please upload your test results",
    "reference":"Please upload a copy of your reference",
}

def _one(loc,desc,*,visible=True):
    if loc.count()!=1 or not loc.is_enabled() or (visible and not loc.is_visible()):
        raise PortalPreparationError(f"Exeter {desc}: expected a single enabled control")
    return loc

def _modal(page,heading):
    checks=[page.get_by_role("dialog"),page.locator("div.modal:visible"),page.locator(".modal-dialog:visible")]
    for c in checks:
        if c.count()==1 and c.is_visible() and c.get_by_text(heading,exact=True).count()>0:
            return c
    raise PortalPreparationError("Exeter upload modal not uniquely identified")

def _trigger(page,role,index):
    name=f"Upload {role}"
    buttons=page.get_by_role("button",name=re.compile(r"^"+re.escape(name)+r"\s*\d*\s*$",re.I))
    matches=[]
    for i in range(buttons.count()):
        x=buttons.nth(i)
        if x.is_visible() and x.is_enabled():matches.append(x)
    if index is None and len(matches)!=1:raise PortalPreparationError("Exeter attachment role is repeated; reviewed ordinal required")
    if index is not None and not (0<=index<len(matches)):raise PortalPreparationError("Exeter attachment ordinal outside visible fields")
    return matches[0] if index is None else matches[index]

def normalized_visible(value):
    # Exeter's HTML5 control renders filenames with NBSP. Some browser text
    # serialization also displays the mojibake marker U+00C2.
    return " ".join(value.replace("\u00c2", "").replace("\u00a0", " ").split())

def _receipt_text(modal,filename):
    return modal.get_by_text(re.compile(re.escape(filename),re.I))

def committed_receipt(modal,filename):
    """Exeter shows an existing server file as a download/name hyperlink plus
    a separate Delete hyperlink, without the word 'Uploaded'. A queue entry
    still has 'Awaiting Upload'. Require both links and no queue markers.
    This is a candidate receipt only until reloaded from the university.
    """
    current=normalized_visible(modal.inner_text(timeout=2500))
    name=normalized_visible(filename)
    if name not in current or re.search(
        r"(?i)awaiting upload|pending upload|queued|uploading|failed",current):
        return False
    named=modal.get_by_role("link",name=name,exact=True)
    deleted=modal.get_by_role("link",
                name=re.compile(r"^Delete\s+"+re.escape(name)+r"$",re.I))
    return named.count()==1 and deleted.count()==1

def upload(page,folder,hosts,item):
    if item.get("portal")!="Exeter eVision" or item.get("role") not in ROLES:
        raise PortalPreparationError("Exeter-specific reviewed attachment metadata required")
    if not item.get("source_evidence"):raise PortalPreparationError("Reviewed source evidence required")
    verified_portal_host(page.url,hosts)
    if not set(hosts).issubset({"srs.exeter.ac.uk"}):
        raise PortalPreparationError("Exeter uploader cannot operate on other institutions")
    check_access(hosts)
    path=file_evidence(folder,item)
    role=item["role"]
    index=item.get("index")
    if index is not None and (not isinstance(index,int) or index<0 or index>3):
        raise PortalPreparationError("Invalid upload role ordinal")
    trigger=_trigger(page,role,index)
    heading=ROLES[role]
    candidates=page.get_by_role("dialog")
    already_open=any(candidates.nth(i).is_visible() and
                     candidates.nth(i).get_by_text(heading,exact=True).count()>0
                     for i in range(candidates.count()))
    if not already_open:
        if any(candidates.nth(i).is_visible() for i in range(candidates.count())):
            raise PortalPreparationError("Unrelated upload modal already open")
        trigger.click(timeout=6000,no_wait_after=True)
    dialog=_modal(page,heading)
    # Match by institutional heading and unique input; the HTML5 widget generates
    # a new dynamic input ID each time, so never bind to a stale ID.
    files=dialog.locator('input[type="file"]')
    node=_one(files,"file input",visible=False)
    current=normalized_visible(dialog.inner_text(timeout=2500))
    name=normalized_visible(path.name)
    if name not in current:
        if re.search(r"awaiting upload|uploaded|queued|pending upload",current,re.I):
            raise PortalPreparationError("A different file is already queued; manual reconciliation required")
        ActionBudget().reserve_url(page.url,"upload",hosts)
        node.set_input_files(str(path),timeout=7000)
        # Do not assume the file input keeps its value: Exeter's component
        # clears it after constructing an upload queue entry.
        for _ in range(24):
            current=normalized_visible(dialog.inner_text(timeout=2500))
            if name in current:break
            page.wait_for_timeout(250)
    if name not in current:raise PortalPreparationError("Exeter queued file name not verified")
    if re.search(r"awaiting upload|queued|pending upload",current,re.I):
        link=dialog.get_by_role("link",name="Upload",exact=True)
        button=dialog.get_by_role("button",name="Upload",exact=True)
        commit=link if link.count()==1 else button
        _one(commit,"Upload commit").click(timeout=7000,no_wait_after=True)
        # One commit only. Wait for the server-confirmed status text.
        verified=False
        for _ in range(48):
            if not dialog.is_visible():break
            current=normalized_visible(dialog.inner_text(timeout=2500))
            if name in current and (
                (re.search(r"uploaded|completed|successful",current,re.I) and
                 not re.search(r"awaiting upload",current,re.I)) or
                committed_receipt(dialog,name)):
                verified=True
                break
            page.wait_for_timeout(250)
        if not verified:
            raise PortalPreparationError("Exeter upload outcome uncertain after one commit; do not retry")
    elif not re.search(r"uploaded|completed|successful",current,re.I):
        if not committed_receipt(dialog,name):
            raise PortalPreparationError(
                "Exeter attachment neither queued nor recognized as committed")
    closer=dialog.get_by_role("button",name="Close",exact=True)
    _one(closer,"Close").click(timeout=5000,no_wait_after=True)
    # A parent badge count of one does not itself prove persistence; separate
    # server-loaded readback is required in the batch reviewer.
    return {"state":"modal_upload_acknowledged","filename":path.name,"server_saved_verified":False}
