"""Public academic discovery pilot. No login, submission, or sheet mutation."""
import argparse, concurrent.futures, hashlib, json, re, urllib.request
from datetime import datetime, timezone, date
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit, parse_qsl, urlencode
from bs4 import BeautifulSoup
from aihawk.academic_discovery_evidence import signals,admission_links
from aihawk.official_fetch import validate_network_host, _SecureRedirect

TERMS = {"biomechan":5,"human movement":5,"musculoskeletal":5,"gait":5,"exercise physiology":5,"sports medicine":5,"sport science":4,"rehabilitation":4,"motor control":4,"neuromechan":5,"knee":4,"wearable":3,"digital health":4,"biomedical":3,"physiotherapy":3,"physical activity":3,"motion analysis":5,"exercise science":4,"health informatics":3,"medical imaging":2,"health data":3,"digital interventions":3,"human performance":4,"action neuroscience":4,"sport management":3,"business of sport":3,"health and digital transformation":4,"healthcare":2}
SOURCES = [
 ("ETH Zurich","PhD","ethz.ch","https://jobs.ethz.ch/",r"/job/view/[^/]+$",True),
 ("Umea University","PhD","umu.se","https://www.umu.se/en/work-with-us/open-positions/",r"/en/work-with-us/open-positions/[^/]+/?$",True),
 ("University of Jyvaskyla","Master","jyu.fi","https://www.jyu.fi/en/study-with-us/find-your-programme",r"/en/study-with-us/masters-degree-programmes/[^/]+/?$",True),
 ("Maastricht University","Master","maastrichtuniversity.nl","https://www.maastrichtuniversity.nl/education/master/programmes",r"/education/master/programmes/[^/]+/?$",True),
 ("EURAXESS latest","PhD","euraxess.ec.europa.eu","https://euraxess.ec.europa.eu/jobs/search",r"/jobs/\d+$",False),
 ("KU Leuven","PhD","kuleuven.be","https://www.kuleuven.be/personeel/jobsite/rss-jobsite-phd-en",r"/personeel/jobsite/jobs/(?:vacatures/)?\d+$",True),
  ("EURAXESS biomechanics","PhD","euraxess.ec.europa.eu","https://euraxess.ec.europa.eu/jobs/search?keywords=biomechanics",r"/jobs/\d+$",False),
 ("EURAXESS human movement","PhD","euraxess.ec.europa.eu","https://euraxess.ec.europa.eu/jobs/search?keywords=human+movement",r"/jobs/\d+$",False),
 ("EURAXESS musculoskeletal","PhD","euraxess.ec.europa.eu","https://euraxess.ec.europa.eu/jobs/search?keywords=musculoskeletal",r"/jobs/\d+$",False),
 ("EURAXESS rehabilitation","PhD","euraxess.ec.europa.eu","https://euraxess.ec.europa.eu/jobs/search?keywords=rehabilitation",r"/jobs/\d+$",False),
 ("EURAXESS exercise physiology","PhD","euraxess.ec.europa.eu","https://euraxess.ec.europa.eu/jobs/search?keywords=exercise+physiology",r"/jobs/\d+$",False),
 ("EURAXESS digital health","PhD","euraxess.ec.europa.eu","https://euraxess.ec.europa.eu/jobs/search?keywords=digital+health",r"/jobs/\d+$",False),
 ("Academic Positions","PhD","academicpositions.com","https://academicpositions.com/jobs/field/mechanics",r"/ad/[^/]+/\d{4}/[^/]+/\d+/?$",False),
 ("FindAPhD","PhD","findaphd.com","https://www.findaphd.com/phds/?Keywords=biomechanics",r"/phds/project/[^/]+/?$",False),
 ("AcademicTransfer","PhD","academictransfer.com","https://www.academictransfer.com/en/jobs/",r"/en/jobs/\d+/[^/]+/?$",False),
 ("Study in NL","Master","studyinnl.org","https://www.studyinnl.org/dutch-education/studies",r"/dutch-education/studies/[^/]+$",False),
]
PHD = re.compile(r"\b(ph\.?d\.?|doctoral|doctorate|doctorandus|promovendus)\b",re.I)
MASTER = re.compile(r"\b(master|msc|m\.sc\.)\b",re.I)
CLOSED = re.compile(r"(?:applications? (?:are |is |have )?closed|vacancy (?:is |has been )?closed|no longer accepting applications|deadline has passed|position has been filled)",re.I)
FUNDING = re.compile(r"\b(?:fully funded|funded ph[dD]|doctoral scholarship|phd scholarship|doctoral fellowship|doctoral researcher contract|employment contract|salary of|gross monthly salary|monthly salary|marie sk[lł]odowska.curie doctoral network)\b",re.I)
DATE = r"(?:\d{4}-\d{2}-\d{2}|\d{1,2}[ ./-]\d{1,2}[ ./-]\d{4}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}|[A-Za-z]{3,9}\s+\d{1,2},?\s+\d{4})"
DEADLINE = re.compile(r"(?:application deadline|closing date|apply (?:by|before|no later than)|applications? close[sd]?|deadline for applications|deadline|apply until|no later than|solliciteren tot)\s*[:\-]?\s*(?:on\s+)?("+DATE+r")",re.I)
def canonical(url):
 p=urlsplit(url); q=[(k,v) for k,v in parse_qsl(p.query) if k.lower() not in {"lang","hl","utm_source","utm_medium","utm_campaign","tracking"}]
 return urlunsplit((p.scheme,p.netloc.lower(),p.path.rstrip("/"),urlencode(sorted(q)),""))
def parse_date(s):
 for fmt in ("%Y-%m-%d","%d %B %Y","%d %b %Y","%B %d %Y","%b %d %Y","%d/%m/%Y","%d.%m.%Y","%d-%m-%Y"):
  try: return datetime.strptime(s.replace(",",""),fmt).date()
  except ValueError: pass
 return None
def score(s):
 matches={k:v for k,v in TERMS.items() if k in s.lower()}
 return min(100,round(sum(matches.values())*10)),list(matches)
def fetch(url,host):
 hosts=(host,); validate_network_host(url,hosts)
 opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),_SecureRedirect(hosts,__import__("socket").getaddrinfo))
 req=urllib.request.Request(url,headers={"User-Agent":"AIHawkAcademicDiscovery/0.1 (public research listings)","Accept":"text/html"})
 with opener.open(req,timeout=9) as r:
  validate_network_host(r.geturl(),hosts); raw=r.read(3000001)
  if len(raw)>3000000: raise ValueError("page too large")
  return BeautifulSoup(raw,"html.parser"),r.geturl(),hashlib.sha256(raw).hexdigest()
def listing(source):
 name,degree,host,url,pattern,official=source
 try:
  soup,final,digest=fetch(url,host); links={}
  for a in soup.select("a[href]"):
   link=urljoin(final,a["href"]); p=urlsplit(link); title=" ".join(a.stripped_strings); heading=a.select_one("h2,h3,h4,h5"); title=heading.get_text(" ",strip=True) if heading else title
   if p.scheme!="https" or not (p.hostname==host or (p.hostname or "").endswith("."+host)) or not re.search(pattern,p.path): continue
   if not title: continue
   key=canonical(link)
   if key not in links or len(title)>len(links[key][0]): links[key]=(title,link)
  candidates=[(t,u) for t,u in links.values() if score(t)[0] and (degree=="Master" or (PHD.search(t) and not re.match(r"post[ -]?doc",t,re.I)) or name=="FindAPhD")]
  candidates.sort(key=lambda x:score(x[0])[0],reverse=True)
  return {"source":name,"url":url,"status":"ok","links":len(links),"topic_candidates":len(candidates),"listing_sha256":digest},[(source,t,u) for t,u in candidates[:12]]
 except Exception as e: return {"source":name,"url":url,"status":"error","error":str(e)},[]
OFFICIAL_HOSTS=("kuleuven.be","maastrichtuniversity.nl","utwente.nl","tudelft.nl","ethz.ch","vu.nl","rug.nl","uni.lu","gu.se","umu.se","jyu.fi","aalto.fi","kth.se","uu.se","univie.ac.at")
def detail(item,today):
 source,title,url=item; name,degree,host,_,_,official=source
 result={"source":name,"degree":degree,"title":title,"url":url,"official_source":official,"retrieved_at":datetime.now(timezone.utc).isoformat(),"state":"needs_review","review_required":["transcript prerequisites","language test format and score","legalization timing","fees and tuition","existing applications"],"approved_for_draft":False}
 try:
  soup,final,digest=fetch(url,host)
  if not official:
   for a in soup.select("a[href]"):
    target=urljoin(final,a["href"]); h=urlsplit(target).hostname or ""
    if any(h==x or h.endswith("."+x) for x in OFFICIAL_HOSTS) and re.search(r"/(?:jobs?|vacancies|careers|position|admissions|education/master)/",urlsplit(target).path,re.I):
     try:
      second,actual,second_digest=fetch(target,h)
      if score(second.get_text(" ",strip=True))[0] and (degree!="PhD" or PHD.search(second.get_text(" ",strip=True))):
       result["discovery_url"]=final; soup,final,digest=second,actual,second_digest; official=True; result["official_source"]=True; break
     except Exception: continue
  for el in soup(["script","style","noscript","nav","footer","header"]): el.decompose()
  main=soup.select_one("main, [role=main], article") or soup
  txt=" ".join(main.stripped_strings); m=DEADLINE.search(txt); d=parse_date(m.group(1)) if m else None
  evidence=signals(txt); w=evidence.get("deadline"); d=d or (date.fromisoformat(w) if w else None)
  f=FUNDING.search(txt); n=score(title); body_topics=score(txt[:12000])[1]
  result.update(url=final,sha256=digest,deadline=d.isoformat() if d else None,deadline_evidence=m.group(0) if m else None,funding_evidence=f.group(0) if f else None,topic_score=n[0],matched_topics=n[1],intake_2027_evidence=bool(re.search(r"(?:intake|start(?:ing)?|entry|autumn|fall|spring|academic year).{0,40}2027",txt,re.I)),english_evidence=bool(re.search(r"(?:taught in English|language of instruction.{0,15}English|English.taught)",txt,re.I)),source_excerpt=txt[:2500])
  result.update(evidence)
  result["deadline"]=d.isoformat() if d else None
  result["deadline_evidence"]=m.group(0) if m else evidence.get("window_evidence") if d else None
  result["topic_score_basis"]="title keywords only, not eligibility probability"
  result["body_topics"]=body_topics
  result["admission_links"]=admission_links(main,final,urlsplit(final).hostname or host)
  result["intake_2027_evidence"]=bool(re.search(r"(?:next application period|application window|intake|start(?:ing)?|entry).{0,45}2027",txt,re.I))
  if CLOSED.search(txt) or (d and d<today): result["state"]="closed"
  elif official and evidence.get("opening_date") and date.fromisoformat(evidence["opening_date"])>today: result["state"]="future_application_window"
  elif official and degree=="Master" and evidence.get("application_month") and result["intake_2027_evidence"]: result["state"]="future_or_unspecified_2027_window"
  elif official and degree=="PhD" and d and d>today and f: result["state"]="official_future_deadline_funding_signal"
  # Aggregator links remain leads; no automatic eligibility or draft approval.
 except Exception as e: result.update(state="fetch_error",error=str(e),topic_score=score(title)[0])
 return result
def main():
 p=argparse.ArgumentParser(); p.add_argument("--out",type=Path,required=True); p.add_argument("--date",type=date.fromisoformat,default=date.today()); args=p.parse_args()
 with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
  listings=list(pool.map(listing,SOURCES))
  items=[i for _,ls in listings for i in ls]
  results=list(pool.map(lambda i:detail(i,args.date),items))
 seen=set(); unique=[]
 for r in sorted(results,key=lambda r:(not r["official_source"],-r.get("topic_score",0))):
  key=canonical(r["url"]); titlekey=(r["source"],re.sub(r"[^a-z0-9]","",r["title"].lower()))
  if key in seen or titlekey in seen: continue
  seen.update((key,titlekey)); unique.append(r)
 report={"schema":"aihawk.discovery.pilot.v1","run_at":datetime.now(timezone.utc).isoformat(),"date":str(args.date),"sources":[a for a,_ in listings],"candidates":[r for r in unique if r["state"]!="closed"],"excluded_closed":[r for r in unique if r["state"]=="closed"],"eligible_for_auto_apply":[],"limitations":["bounded listing pages only","no comprehensive country coverage","no transcript or applicant eligibility verification","no sheet sync or application submission"]}
 args.out.parent.mkdir(parents=True,exist_ok=True); tmp=args.out.with_suffix(".tmp"); tmp.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8"); tmp.replace(args.out)
 print(json.dumps({"sources":report["sources"],"candidates":len(report["candidates"]),"excluded_closed":len(report["excluded_closed"]),"output":str(args.out)},ensure_ascii=True))
if __name__=="__main__": main()
