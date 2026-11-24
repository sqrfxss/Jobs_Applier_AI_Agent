"""Read-only current Exeter DOM diagnostic; never changes section or submits."""
from datetime import datetime,timezone
from urllib.parse import urlsplit
from aihawk.academic_outreach_workflow import atomic_json
from aihawk.academic_browser import verified_portal_host

def scan_all(page,folder,hosts,title):
    verified_portal_host(page.url,hosts)
    headings=page.locator("h1,h2,h3,h4").evaluate_all("""es=>es.map(e=>({
      text:(e.innerText||'').trim().replace(/\s+/g,' '),
      visible:!!e.getClientRects().length,tag:e.tagName
    }))""")
    buttons=page.get_by_role("button").evaluate_all("""es=>es.map(e=>({
      text:(e.innerText||'').trim().replace(/\s+/g,' '),
      visible:!!e.getClientRects().length,disabled:e.disabled
    })).filter(e=>e.visible)""")
    controls=page.locator("input,textarea,select").evaluate_all("""es=>es.map(e=>({
      id:e.id,name:e.name||'',tag:e.tagName,type:e.type||'',
      label:[...(e.labels||[])].map(x=>x.textContent.trim()).join(' ')||
         e.getAttribute('aria-label')||'',
      value:e.type==='password'?'[REDACTED]':(e.type==='file'?'[FILE INPUT]':(e.value||'')),
      visible:!!e.getClientRects().length,disabled:e.disabled,
      selected:e.tagName==='SELECT'?e.selectedOptions[0]?.text:null
    })).filter(e=>e.type!=='hidden')""")
    data={"schema":"aihawk.exeter.current.audit.v2",
      "checked_at":datetime.now(timezone.utc).isoformat(),
      "host":urlsplit(page.url).hostname,"path":urlsplit(page.url).path,
      "headings":headings,"buttons":buttons,"controls":controls,
      "matched_project_heading":any(x["text"]==title and x["visible"] for x in headings),
      "final_submission":False}
    atomic_json(folder/"Session_Immediate_Inspection.json",data)
    return {"matched_project_heading":data["matched_project_heading"],
      "headings":[x["text"] for x in headings if x["visible"]],
      "buttons":[x["text"] for x in buttons],
      "field_count":len(controls),
      "path":str(folder/"Session_Immediate_Inspection.json"),
      "final_submission":False}
