"""Read-only diagnostic for university date widgets; never exports field values."""
from __future__ import annotations
from datetime import datetime,timezone
from aihawk.academic_outreach_workflow import atomic_json
from aihawk.academic_browser import verified_portal_host,PortalPreparationError
from aihawk.academic_field_journal import validation_labels

def probe(page,folder,hosts,title,field_id="IPQ_ELQUAL_DATE"):
    verified_portal_host(page.url,hosts)
    project=page.get_by_text(title,exact=True)
    if project.count()!=1 or not project.is_visible():
        raise PortalPreparationError("Project identity not verified")
    field=page.locator("#"+field_id)
    if field.count()!=1:raise PortalPreparationError("Date control missing/ambiguous")
    data=field.evaluate("""el=>{
      const a=el.attributes;
      const allow=['id','type','class','placeholder','pattern','maxlength',
                   'min','max','readonly','required','data-date-format','autocomplete'];
      const attrs={};
      for(const name of allow){
        const v=el.getAttribute(name);
        if(v!==null)attrs[name]=String(v).slice(0,120);
      }
      const jq=window.jQuery;
      let listeners=[];
      try{
        listeners=jq && jq._data ? Object.keys(jq._data(el,'events')||{}) : [];
      }catch(e){}
      const validity=el.validity;
      const safeValidity=validity ? {
         valid:validity.valid,
         badInput:validity.badInput,
         patternMismatch:validity.patternMismatch,
         typeMismatch:validity.typeMismatch,
         valueMissing:validity.valueMissing,
         customError:validity.customError
      }:{};
      const names=[];
      for(const node of [el.parentElement,el.parentElement?.parentElement]){
        if(node){names.push({tag:node.tagName,
          classes:String(node.className||'').slice(0,110)})}
      }
      const dp=jq ? (jq(el).data('datepicker')||jq(el).data('datepick')):null;
      return {attributes:attrs,required:el.required,disabled:el.disabled,
        readOnly:el.readOnly,validation:safeValidity,
        jqueryHandlers:listeners,parents:names,
        jQuery:!!jq,datepickerPlugin:!!(jq&&jq.fn&&jq.fn.datepicker),
        datepickerInstance:!!dp,
        nativeType:el.type,uiVisible:!!el.getClientRects().length};
    }""")
    data.update({"schema":"aihawk.date.widget.probe.v1",
       "checked_at":datetime.now(timezone.utc).isoformat(),
       "field":field_id,"validation_fields":validation_labels(page),
       "raw_field_value_logged":False,"final_submission":False})
    atomic_json(folder/"Agent_Date_Widget_Diagnostic.json",data)
    return {k:v for k,v in data.items() if k not in ("attributes","parents")}
