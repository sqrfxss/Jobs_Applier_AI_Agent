"""Propose exact field bindings from DOM metadata and verified private profile.
Never guesses values or approves an application. File uploads need receipt mapping.
"""
import re,unicodedata,json,argparse
from pathlib import Path

def norm(s):
 return " ".join(re.findall(r"[a-z0-9]+",unicodedata.normalize("NFKD",str(s)).encode("ascii","ignore").decode().lower()))
ALIASES={
 "first_name":("first name","given name","forename","firstname","givenname"),
 "last_name":("last name","family name","surname","lastname","familyname"),
 "full_name":("full name","applicant name","fullname"),
 "email":("email","e mail","email address","e mail address"),
 "phone":("phone","telephone","mobile phone","phone number"),
 "nationality":("nationality","citizenship","country of citizenship"),
 "country_of_residence":("country of residence","residence country"),
 "date_of_birth":("date of birth","birth date","dob"),
 "city":("city","town"),"postal_code":("postal code","zip code","postcode"),
 "street_address":("street address","address line 1"),
 "degree_title":("degree title","degree name"),"graduation_date":("graduation date","date of graduation"),
 "english_test":("english language test","language test type","english test"),
 "english_score":("english test score","toefl total score"),
}
DOCS={"cv":("cv","curriculum vitae","resume"),"motivation":("motivation letter","letter of motivation","cover letter","statement of purpose"),"bsc_transcript":("bachelor transcript","bachelor s transcript","bsc transcript"),"msc_transcript":("master transcript","master s transcript","msc transcript"),"bsc_diploma":("bachelor diploma","bachelor degree certificate"),"msc_diploma":("master diploma","master degree certificate"),"language_certificate":("toefl certificate","english language certificate","english test report")}
def identify(control,aliases):
 labels=[norm(control.get(k,"")) for k in ("label_untrusted","name","placeholder_untrusted")]
 hits={k for k,values in aliases.items() if any(x in values for x in labels if x)}
 return next(iter(hits)) if len(hits)==1 else None
def build_plan(inventory,profile):
 bindings=[]; uploads=[]; unresolved=[]; field_values={}
 for c in inventory.get("controls",[]):
  selector=c.get("selector_candidate",""); kind=c.get("kind")
  if not selector or c.get("selector_unique") is not True:
   unresolved.append({"label":c.get("label_untrusted"),"reason":"missing_or_ambiguous_selector"}); continue
  key=identify(c,DOCS if kind=="upload" else ALIASES)
  if not key:
   unresolved.append({"selector":selector,"reason":"unknown_or_ambiguous_field"}); continue
  if kind=="upload":
   record=profile.get("documents",{}).get(key,{})
   if record.get("verified") is True and record.get("path") and record.get("sha256"):
    uploads.append({"document_role":key,"selector":selector,"requires_reviewed_receipt_and_endpoint":True})
   else: unresolved.append({"selector":selector,"reason":"verified_document_missing","role":key})
   continue
  record=profile.get("fields",{}).get(key,{})
  if record.get("verified") is not True or not isinstance(record.get("value"),str) or not record["value"].strip():
   unresolved.append({"selector":selector,"reason":"verified_value_missing","field":key}); continue
  value=record["value"]
  if kind=="select":
   options=[o for o in c.get("options_untrusted",[]) if norm(o.get("label",""))==norm(value) and str(o.get("value","")).strip()]
   if len(options)!=1:
    unresolved.append({"selector":selector,"reason":"no_unique_exact_option","field":key}); continue
   value=str(options[0]["value"])
  elif kind!="text":
   unresolved.append({"selector":selector,"reason":"unsupported_control"}); continue
  field=key
  if field in field_values and field_values[field]!=value:
   unresolved.append({"selector":selector,"reason":"conflicting_binding_value"}); continue
  field_values[field]=value
  bindings.append({"field":field,"selector":selector,"kind":kind})
 return {"schema":"aihawk.field_proposal.v1","bindings":bindings,"upload_proposals":uploads,"unresolved":unresolved,"field_values":field_values,"approved_for_draft":False}
def main():
 p=argparse.ArgumentParser();p.add_argument("inventory",type=Path);p.add_argument("profile",type=Path);p.add_argument("out",type=Path);a=p.parse_args()
 result=build_plan(json.loads(a.inventory.read_text(encoding="utf8")),json.loads(a.profile.read_text(encoding="utf8")))
 with a.out.open("x",encoding="utf8") as f: json.dump(result,f,ensure_ascii=False,indent=2)
 print(json.dumps({k:len(result[k]) for k in ("bindings","upload_proposals","unresolved")}))
if __name__=="__main__": main()
