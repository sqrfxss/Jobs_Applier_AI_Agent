"""Read-only tracker reconciliation and per-university discovery evidence."""
import argparse, json, re, unicodedata, os
from datetime import datetime, timezone
from pathlib import Path
from aihawk.academic_discovery import canonical

FOLDERS={"ETH Zurich":("Switzerland","ETH Zurich"),"University of Jyvaskyla":("finland","University of Jyvaskyla"),"Maastricht University":("Netherland","Maastricht"),"KU Leuven":("belgium","KU Leuven"),"Umea University":("sweden","Umea University")}
def normalize(s):
 return re.sub(r"[^a-z0-9]","",unicodedata.normalize("NFKD",str(s)).encode("ascii","ignore").decode().lower())
def matches(item,rows):
 result=[]
 for row in rows:
  same_url=bool(row.get("url") and canonical(str(row["url"]))==canonical(item["url"]))
  university_match=normalize(row["university"])==normalize(item["source"])
  same_title=normalize(row["title"])==normalize(item["title"])
  if same_url or (university_match and same_title): result.append({"row":row["row"],"status":row["status"],"match":"url" if same_url else "title+university"})
 return result
def write_json(path,value):
 path.parent.mkdir(parents=True,exist_ok=True)
 if path.exists(): raise FileExistsError(path)
 with path.open("x",encoding="utf-8") as f: json.dump(value,f,ensure_ascii=False,indent=2)
def main():
 p=argparse.ArgumentParser(); p.add_argument("report",type=Path); p.add_argument("index",type=Path); p.add_argument("--root",type=Path,default=Path(os.environ.get("AIHAWK_CASE_ROOT","applications"))); args=p.parse_args()
 report=json.loads(args.report.read_text(encoding="utf-8")); index=json.loads(args.index.read_text(encoding="utf-8")); stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
 for item in report["candidates"]:
  item["tracker_matches"]=matches(item,index["rows"])
  item["tracker_status"]="already_listed" if item["tracker_matches"] else "not_matched_in_snapshot"
  item["approved_for_draft"]=False
  if item["source"] in FOLDERS:
   country,university=FOLDERS[item["source"]]
   slug=re.sub(r"[^A-Za-z0-9]+","_",item["title"])[:85]
   path=args.root/country/university/"Discovery"/(slug+"_"+stamp+".json")
   write_json(path,item)
 report["tracker_snapshot"]={"read_at":index["read_at"],"row_count":len(index["rows"]),"live_write":False}
 report["eligible_for_auto_apply"]=[]
 dest=args.report.with_name(args.report.stem+"_reconciled_"+stamp+".json"); write_json(dest,report)
 print(json.dumps({"existing_candidates":sum(bool(i["tracker_matches"]) for i in report["candidates"]),"unmatched_candidates":sum(not i["tracker_matches"] for i in report["candidates"]),"output":str(dest),"sheet_writes":0}))
if __name__=="__main__": main()
