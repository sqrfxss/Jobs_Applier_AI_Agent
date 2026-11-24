"""Exeter labelled searchable dropdown; exact visible label, option, and readback."""
import re
from aihawk.academic_browser import PortalPreparationError

def select(page,item):
    if item.get("type")!="react_select" or not item.get("source_evidence"):
        raise PortalPreparationError("Reviewed dropdown fact required")
    label=item.get("label_contains")
    option=item.get("option")
    if not isinstance(label,str) or len(label)<12 or not isinstance(option,str) or not option:
        raise PortalPreparationError("Exact dropdown label and option required")
    if re.search(r"(?i)password|submit|agree|consent|legal",label):
        raise PortalPreparationError("Protected control")
    # Exeter hides its native SELECT behind an autocomplete textbox. Prefer
    # the authoritative SELECT: a unique labelled option is stable, whereas
    # the rendered textbox can be covered by overlays or moved by re-renders.
    selects=page.locator("select")
    ids=selects.evaluate_all("""(els,q)=>els.flatMap((e,i)=>{
      const labels=[...(e.labels||[])].map(x=>x.textContent||"").join(" ");
      return labels.toLowerCase().includes(q.toLowerCase())?[i]:[];
    })""",label)
    if len(ids)==1:
        native=selects.nth(ids[0])
        options=native.locator("option").evaluate_all(
            "es=>es.map(x=>({label:x.text.trim(),value:x.value}))")
        matches=[x for x in options if x["label"]==option]
        if len(matches)==1 and matches[0]["value"]:
            native.select_option(value=matches[0]["value"],force=True,timeout=6000)
            chosen=native.locator("option:checked")
            if chosen.count()!=1 or chosen.inner_text().strip()!=option:
                raise PortalPreparationError("Native searchable selection readback failed")
            return {"label":label,"option":option,"local_readback":True,
                    "control":"native_select"}
    input_=page.get_by_role("textbox",name=re.compile(re.escape(label),re.I))
    if input_.count()!=1 or not input_.is_visible() or not input_.is_enabled():
        # Locate the single labelled custom text input by its attached DOM
        # label, even if its ARIA role name was not exposed by Exeter.
        all_inputs=page.locator("input[type='text'],input[type='search']")
        indices=all_inputs.evaluate_all("""(es,query)=>es.flatMap((e,i)=>{
          const names=[...(e.labels||[])].map(l=>l.textContent||'').join(' ')+
             ' '+(e.getAttribute('aria-label')||'');
          return e.getClientRects().length && names.toLowerCase().includes(query.toLowerCase())?[i]:[]
        })""",label)
        if len(indices)!=1:
            raise PortalPreparationError("University searchable dropdown not uniquely labelled")
        input_=all_inputs.nth(indices[0])
        if not input_.is_visible() or not input_.is_enabled():
            raise PortalPreparationError("Reviewed searchable control disabled")
    input_.click(timeout=4000)
    input_.fill(option,timeout=5000)
    target=page.get_by_role("option",name=option,exact=True)
    if target.count()!=1:
        target=page.get_by_role("listitem",name=option,exact=True)
    if target.count()!=1:
        target=page.get_by_text(option,exact=True)
    if target.count()!=1 or not target.is_visible():
        raise PortalPreparationError("Searched option not uniquely visible")
    target.click(timeout=5000)
    selected=page.get_by_text(option,exact=True)
    visible=[selected.nth(i) for i in range(selected.count()) if selected.nth(i).is_visible()]
    if len(visible)<1:
        raise PortalPreparationError("Selected dropdown value not confirmed")
    return {"label":label,"option":option,"local_readback":True}
