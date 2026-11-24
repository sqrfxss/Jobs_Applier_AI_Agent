"""Explicitly reviewed custom menus and modal document controls.

No generic clicking, final submission, legal declarations or outgoing mail.
"""
from pathlib import Path
import re,hashlib
from aihawk.academic_browser import PortalPreparationError
from aihawk.academic_portal_limits import check_access
from aihawk.academic_action_budget import ActionBudget

def exact_selector(s):
    if not isinstance(s,str) or not re.fullmatch(r'#[A-Za-z0-9_-]+|\[id="[^"\r\n]{1,180}"\]|\[name="[^"\r\n]{1,180}"\]',s):
        raise PortalPreparationError("Expected reviewed exact ID/name selector")
    return s

def one(loc,*,visible=True):
    if loc.count()!=1 or not loc.is_enabled() or (visible and not loc.is_visible()):
        raise PortalPreparationError("Expected unique enabled reviewed control")
    return loc

def safe_label(label):
    if not isinstance(label,str) or not label.strip() or re.search(r"(?i)submit|signatur|consent|declarat|password|captcha|payment|send|invite|delete|remove",label):
        raise PortalPreparationError("Protected or ambiguous action")
    return label

def menu_value(page,item):
    node=page.locator(exact_selector(item["selected_selector"]))
    if node.count()!=1:raise PortalPreparationError("Selected-value marker missing")
    return (node.input_value() if node.evaluate("e=>e.tagName==='INPUT'||e.tagName==='SELECT'") else node.inner_text()).strip()

def custom_select(page,item):
    """Scope trigger and option to one reviewed custom control; verify actual selection."""
    label=safe_label(item["label"])
    if not item.get("source_evidence"):raise PortalPreparationError("Custom choice requires evidence")
    if menu_value(page,item)==label:return
    container=one(page.locator(exact_selector(item["container_selector"])))
    trigger=one(container.locator(exact_selector(item["trigger_selector"])))
    trigger.click(timeout=6000)
    option=container.get_by_role("option",name=label,exact=True)
    if option.count()==0:option=container.get_by_role("listitem",name=label,exact=True)
    if option.count()==0:option=container.get_by_text(label,exact=True)
    one(option).click(timeout=6000)
    if menu_value(page,item)!=label:raise PortalPreparationError("Custom selection not confirmed")

def file_evidence(folder,item):
    from aihawk.academic_uploads import _verify_file
    root=folder.resolve(strict=True);p=(root/item["file"]).resolve(strict=True)
    if not p.is_relative_to(root) or not p.is_file():raise PortalPreparationError("Upload outside private case")
    allowed=tuple(item.get("allowed_extensions",()))
    if not allowed:raise PortalPreparationError("Reviewed file types required")
    digest=item["sha256"]
    if not isinstance(digest,str):raise PortalPreparationError("Approved SHA256 missing")
    if digest.startswith("sha256:"):digest=digest[7:]
    if not re.fullmatch(r"[a-fA-F0-9]{64}",digest):raise PortalPreparationError("Invalid approved SHA256")
    _verify_file(p,"sha256:"+digest.casefold(),allowed_extensions=allowed)
    return p

def receipt(page,item):
    node=page.locator(exact_selector(item["receipt_container_selector"]))
    if node.count()!=1:return False
    name=item["receipt_text"]
    link=node.get_by_text(name,exact=True)
    return link.count()==1 and link.is_visible()

def modal_upload(page,folder,hosts,item):
    """Open exact document dialog and use its file input; never OS picker."""
    file=file_evidence(folder,item)
    if receipt(page,item):return "already_present"
    caption=safe_label(item["open_label"])
    if not caption.casefold().startswith("upload "):raise PortalPreparationError("Unreviewed document role")
    one(page.get_by_role("button",name=caption,exact=True)).click(timeout=6000)
    dialog=one(page.locator(exact_selector(item["dialog_selector"])))
    control=one(dialog.locator(exact_selector(item["input_selector"])),visible=False)
    if control.get_attribute("type")!="file":raise PortalPreparationError("Expected file input")
    selected=control.evaluate("x=>[...x.files].map(f=>f.name)")
    if selected and selected!=[file.name]:raise PortalPreparationError("Another file already selected")
    check_access(hosts);ActionBudget().reserve_url(page.url,"upload",hosts)
    control.set_input_files(str(file))
    if control.evaluate("x=>[...x.files].map(f=>f.name)")!=[file.name]:
        if not receipt(page,item):raise PortalPreparationError("File selection not confirmed")
        return "receipt_visible"
    if receipt(page,item):return "receipt_visible"
    button=one(dialog.get_by_role("button",name=safe_label(item["upload_label"]),exact=True))
    if item["upload_label"].casefold() not in ("upload","upload file","attach"):raise PortalPreparationError("Unreviewed upload commit")
    button.click(timeout=6000)
    page.locator(exact_selector(item["receipt_container_selector"])).get_by_text(item["receipt_text"],exact=True).wait_for(state="visible",timeout=12000)
    check_access(hosts)
    if not receipt(page,item):raise PortalPreparationError("No upload receipt")
    return "receipt_visible"
