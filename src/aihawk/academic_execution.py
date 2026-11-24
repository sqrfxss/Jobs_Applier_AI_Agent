"""Single case execution entry point: preflight, preparation, verified report.

Unreviewed or missing evidence never triggers a network action. This runner
never signs, pays, sends emails, or submits applications.
"""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
from datetime import datetime,date,timezone
from aihawk.academic_outreach_workflow import atomic_json
from aihawk.academic_browser import verified_portal_host
from aihawk.academic_portal_limits import PortalLimits,PortalAccessHold

def sha(path):
 with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def evaluate(config,folder,today=None):
 today=today or date.today()
 issues=[]; verified=[]
 if config.get('schema')!='aihawk.execution.v1':raise ValueError('Invalid execution manifest')
 host=verified_portal_host(config['official_application_url'],tuple(config['official_hosts']))
 deadline=config.get('deadline')
 if not deadline:issues.append('deadline_unverified')
 elif date.fromisoformat(deadline)<today:issues.append('deadline_passed')
 for key in ('degree_eligibility','language_policy','credential_policy'):
  check=config.get('eligibility',{}).get(key,{})
  if check.get('status') not in ('verified_eligible','verified_not_required') or not check.get('source'):
   issues.append(key+':unresolved')
 docs=config.get('documents',{})
 for role in config.get('required_roles',[]):
  item=docs.get(role,{})
  if item.get('verified') is not True or not item.get('file') or not item.get('sha256'):
   issues.append('document:'+role+':missing_or_unverified');continue
  path=(folder/item['file']).resolve()
  if not path.is_relative_to(folder.resolve()) or not path.is_file():
   issues.append('document:'+role+':missing_or_external');continue
  if sha(path)!=item['sha256']:
   issues.append('document:'+role+':changed');continue
  verified.append(role)
 if not config.get('required_roles'):issues.append('document_requirements_unverified')
 if config.get('submission_previously_verified') is True:issues.append('already_submitted')
 if config.get('portal_manifest'):
  p=(folder/config['portal_manifest']).resolve()
  if not p.is_relative_to(folder.resolve()) or not p.is_file() or config.get('portal_manifest_sha256')!=sha(p):
   issues.append('portal_manifest_unverified')
 else:issues.append('portal_manifest_missing')
 return {'institution':config.get('institution'),'job_id':config.get('job_id'),'host':host,'deadline':deadline,'verified_documents':verified,'blockers':issues,'final_submission':False,'approval_required':True}

def language_reference_date(rule,bundle,config):
 """Never silently assess a start-date validity rule at the application deadline."""
 anchor=rule.get("validity_reference")
 if anchor=="programme_start":
  iso=bundle.get("programme_start_date")
 elif anchor=="application_deadline":
  iso=config.get("deadline")
 elif anchor=="explicit":
  iso=bundle.get("language_assessment_date")
 else:
  return None
 try:return date.fromisoformat(iso) if iso else None
 except (TypeError,ValueError):return None

def execute(case,*,run_draft=False,today=None):
 folder=case.resolve(strict=True).parent
 config=json.loads(case.read_text(encoding='utf8'))
 profile_report=None
 if config.get("reviewed_policy_bundle"):
  from aihawk.academic_eligibility import evaluate_language,evaluate_degree,evaluate_credentials,evaluate_credits
  bundle=config["reviewed_policy_bundle"]
  profile_path=Path(bundle["profile_path"]).resolve(strict=True)
  if sha(profile_path)!=bundle["profile_sha256"]:raise ValueError("Profile changed since review")
  profile=json.loads(profile_path.read_text(encoding="utf8"))
  policies=bundle["policies"]
  profile_report={}
  degree=next((d for d in profile.get("education",[]) if d.get("title","").startswith("M.Sc.")),{})
  if "degree" in policies:profile_report["degree_eligibility"]=evaluate_degree(policies["degree"],degree)
  if "language" in policies:
   language_rule=policies["language"]
   validity_date=language_reference_date(language_rule,bundle,config)
   if validity_date is None and language_rule.get("not_required") is not True:
    profile_report["language_policy"]={
      "status":"unknown",
      "reason":"Validity reference date must be explicitly reviewed; deadline is not assumed to be programme start",
      "source":language_rule.get("source")}
   else:
    profile_report["language_policy"]=evaluate_language(
       language_rule,profile.get("language",{}),on=validity_date or date.today())
  if "credentials" in policies:profile_report["credential_policy"]=evaluate_credentials(policies["credentials"],profile.get("documents",{}))
  if "courses" in policies:profile_report["prerequisites"]=evaluate_credits(policies["courses"],profile.get("courses",[]))
  for key,item in profile_report.items():
   if key!="prerequisites":config.setdefault("eligibility",{})[key]=item
 report=evaluate(config,folder,today=today)
 if profile_report is not None:
  report["eligibility_assessment"]=profile_report
  if any(r.get("status")!="verified_eligible" for r in profile_report.get("prerequisites",[])):report["blockers"].append("course_prerequisites:unresolved")
 report['checked_utc']=datetime.now(timezone.utc).isoformat()
 report['network_actions']=False
 report['result']='blocked_preflight' if report['blockers'] else 'ready_for_reviewed_draft'
 dest=folder/'Execution_Report.json'
 if not report['blockers'] and run_draft:
  try:PortalLimits().check(tuple(config['official_hosts']))
  except PortalAccessHold as e:
   report['result']='portal_hold';report['blockers'].append(str(e));atomic_json(dest,report);return report
  path=(folder/config['portal_manifest']).resolve()
  data=json.loads(path.read_text(encoding='utf8'))
  if data.get('official_application_url')!=config['official_application_url']:
   report['blockers'].append('portal_manifest_url_mismatch');report['result']='blocked_preflight'
  else:
   report['network_actions']=True
   from aihawk.academic_background_journey import run_background_journey_reported
   from aihawk.academic_background_single import run_background_draft_reported
   f=run_background_journey_reported if data.get('portal_stages') else run_background_draft_reported
   draft=f(path,folder/'Verified_Draft_Report.json')
   report['draft_result']=draft.get('result')
   verified_draft=draft.get('result') in ('server_saved_verified','all_draft_stages_saved_verified')
   complete_review=config.get('required_fields_and_uploads_reviewed_complete') is True
   if verified_draft and complete_review:
    report['result']='awaiting_final_submission_approval'
    report['approval_fingerprint']=hashlib.sha256(json.dumps({'case_sha256':sha(case),'manifest_sha256':sha(path),'draft_report_sha256':sha(folder/'Verified_Draft_Report.json')},sort_keys=True).encode()).hexdigest()
   elif verified_draft:
    report['result']='draft_saved_completeness_review_required'
    report['blockers'].append('required_fields_and_uploads_completeness_unverified')
   else:report['result']='draft_incomplete'
 atomic_json(dest,report)
 return report

def main():
 p=argparse.ArgumentParser()
 p.add_argument('case',type=Path);p.add_argument('--run-draft',action='store_true')
 a=p.parse_args()
 r=execute(a.case,run_draft=a.run_draft)
 print(json.dumps(r,ensure_ascii=True))
if __name__=='__main__': main()
