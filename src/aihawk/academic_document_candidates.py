"""Fast, bounded and read-only discovery of candidate application documents.

Document names are only hints. No document is considered verified until a
reviewed manifest independently validates the evidence.
"""
from __future__ import annotations
from collections import deque
from pathlib import Path
import hashlib,json,re,os
from aihawk.academic_outreach_workflow import atomic_json

EXT={".pdf",".docx",".doc",".jpg",".jpeg",".png"}
SKIP={".aihawk-academic-session",".git","Review","QA_Reports","__pycache__","tmp"}
ALIASES={
 "CV":(("cv","resume","curriculum"),),
 "motivation":(("motivation","personal statement","cover letter","statement of purpose"),),
 "BSc_transcripts":(("bsc","bachelor","undergraduate"),("transcript","grades")),
 "MSc_transcripts":(("msc","master","graduate"),("transcript","grades")),
 "English_evidence":(("toefl","ielts","english score","english evidence","language test"),),
 "reference_1":(("reference","referee","recommendation"),),
 "reference_2":(("reference","referee","recommendation"),)
}
MAX_FILES=400
MAX_ENTRIES=8000
MAX_BYTES=20_000_000

def classify(name,role):
    terms=ALIASES.get(role)
    if not terms:return False
    norm=re.sub(r"[^a-z0-9]+"," ",Path(name).stem.casefold()).strip()
    return all(any(word in norm for word in group) for group in terms)

def _candidate_files(root):
    """Bound directory enumeration, skip symlinks and irrelevant private trees."""
    todo=deque([root])
    visited=0
    scanned=0
    while todo and visited<MAX_ENTRIES and scanned<MAX_FILES:
        directory=todo.popleft()
        try:
            iterator=os.scandir(directory)
        except OSError:
            continue
        with iterator:
            for entry in iterator:
                visited+=1
                if visited>MAX_ENTRIES or scanned>=MAX_FILES:
                    break
                try:
                    if entry.is_symlink():
                        continue
                    if entry.is_dir(follow_symlinks=False):
                        if entry.name not in SKIP and not entry.name.startswith("."):
                            todo.append(Path(entry.path))
                        continue
                    if not entry.is_file(follow_symlinks=False):
                        continue
                    path=Path(entry.path)
                    if path.suffix.casefold() not in EXT:
                        continue
                    scanned+=1
                    yield path
                except OSError:
                    continue

def discover(folder,required_roles,verified_documents=None):
    root=Path(folder).resolve(strict=True)
    known=verified_documents if isinstance(verified_documents,dict) else {}
    candidates={role:[] for role in required_roles}
    seen=set()
    scanned=0
    for path in _candidate_files(root):
        scanned+=1
        try:
            if path.stat().st_size>MAX_BYTES:
                continue
            roles=[role for role in candidates if classify(path.name,role)]
            if not roles:
                continue
            digest=hashlib.sha256(path.read_bytes()).hexdigest()
            for role in roles:
                if (role,digest) in seen:
                    continue
                seen.add((role,digest))
                relative=path.relative_to(root)
                candidates[role].append({"file":str(relative),"sha256":digest,
                             "bytes":path.stat().st_size,
                             "evidence_verified":False,"upload_authorized":False})
        except OSError:
            continue
    result={}
    for role,files in candidates.items():
        existing=known.get(role,{})
        if isinstance(existing,dict) and existing.get("verified") is True:
            status="already_verified_in_case_manifest"
        elif len(files)==1:
            status="candidate_requires_review"
        elif files:
            status="ambiguous_candidates"
        else:
            status="not_found"
        result[role]={"status":status,"candidates":files}
    report={"schema":"aihawk.documents.candidates.v1","scanned_files":scanned,
            "roles":result,"all_documents_verified":False,
            "network_actions":False,"final_submission":False}
    atomic_json(root/"Agent_Document_Candidates.json",report)
    return report
