"""Follow public admission evidence links; never infer eligibility from mentions."""
import argparse,json,re
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlsplit
from concurrent.futures import ThreadPoolExecutor
from aihawk.academic_discovery import fetch
from aihawk.academic_discovery_evidence import signals
from aihawk.academic_public_render import allowed_url,render
from aihawk.academic_policy_signals import extract_policy,review_policy

def follow(link):
 url=link["url"]; host=urlsplit(url).hostname
 try:
  soup,final,digest=fetch(url,host)
  for el in soup(["script","style","noscript","nav","header","footer"]): el.decompose()
  main=soup.select_one("main,[role=main],article") or soup
  txt=" ".join(main.stripped_strings)
  capture_type="html_text"; more_links=[]
  if len(txt)<800 and allowed_url(final):
   capture=render(final); final=capture["url"]; txt=capture["text"]; digest=capture["sha256"]; capture_type=capture["capture_type"]
   more_links=[x for x in capture.get("links",[]) if re.search(r"English skills|language requirements|assessment guidelines",x["title"],re.I) and (urlsplit(x["url"]).hostname or "") in ("www.jyu.fi","jyu.fi")][:3]
  status="retrieved" if len(txt)>=800 else "insufficient_content"
  return {"url":final,"sha256":digest,"retrieved_at":datetime.now(timezone.utc).isoformat(),"status":status,"capture_type":capture_type,"evidence":signals(txt) if status=="retrieved" else {},"text_length":len(txt),"policy_signals":extract_policy(txt),"language_links":more_links}
 except Exception as e: return {"url":url,"status":"error","error":str(e)}
def main():
 p=argparse.ArgumentParser(); p.add_argument("report",type=Path); p.add_argument("--out",type=Path,required=True); args=p.parse_args()
 r=json.loads(args.report.read_text(encoding="utf8"))
 cache={}
 with ThreadPoolExecutor(max_workers=4) as pool:
  links={x["url"]:x for item in r["candidates"] if item["official_source"] for x in item.get("admission_links",[])[:3] if x["fetch_allowed"]}
  cache=dict(zip(links,pool.map(follow,links.values())))
 with ThreadPoolExecutor(max_workers=3) as pool:
  additional={x["url"]:x for row in cache.values() for x in row.get("language_links",[])}
  secondary=dict(zip(additional,pool.map(follow,additional.values())))
 for item in r["candidates"]:
  item["admission_page_evidence"]=[cache[x["url"]] for x in item.get("admission_links",[])[:3] if x["url"] in cache]
  item["language_page_evidence"]=[secondary[x["url"]] for row in item["admission_page_evidence"] for x in row.get("language_links",[]) if x["url"] in secondary]
  item["policy_checks"]=review_policy([x.get("policy_signals",{}) for x in item["admission_page_evidence"]+item["language_page_evidence"]])
  item["approved_for_draft"]=False
 r["eligible_for_auto_apply"]=[]
 args.out.write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding="utf8")
 print(json.dumps({"linked_pages":len(cache),"secondary_language_pages":len(secondary),"secondary_retrieved":sum(x["status"]=="retrieved" for x in secondary.values()),"retrieved":sum(x["status"]=="retrieved" for x in cache.values()),"home_edition_mentions":sum(bool(x.get("evidence",{}).get("requirement_evidence",{}).get("home_edition")) for x in cache.values()),"legalization_mentions":sum(bool(x.get("evidence",{}).get("requirement_evidence",{}).get("legalization")) for x in cache.values()),"errors":[x for x in cache.values() if x["status"]=="error"],"out":str(args.out)}))
if __name__=="__main__": main()
