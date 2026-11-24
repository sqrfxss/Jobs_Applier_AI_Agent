"""Source-bound reusable profile. No hardcoded applicant identity in source code."""

from pathlib import Path
from datetime import datetime, timezone
import hashlib
import re
import json
import argparse
from pypdf import PdfReader
from aihawk.academic_outreach_workflow import atomic_json


def digest(p):
    with p.open("rb") as f:
        return hashlib.file_digest(f, "sha256").hexdigest()


def read_cv(path):
    path = path.resolve(strict=True)
    lines = [x.strip() for p in PdfReader(path).pages for x in (p.extract_text() or "").splitlines() if x.strip()]
    if len(lines) < 10:
        raise ValueError("CV text unavailable")
    text = "\n".join(lines)
    fields = {}
    h = digest(path)

    def add(k, v):
        fields[k] = {"value": v, "verified": True, "source": "CV self-reported text", "source_sha256": h, "institutional_verification": False}

    name = lines[0]
    if re.fullmatch(r"[A-Za-z][A-Za-z .'-]{2,100}", name) and len(name.split()) >= 2:
        add("full_name", name.title())
        if len(name.split()) == 2:
            add("first_name", name.split()[0].title())
            add("last_name", name.split()[1].title())
    header = " ".join(lines[:4])
    emails = re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", header)
    if len(set(emails)) == 1:
        add("email", emails[0])
    phone = re.search(r"\+\d[\d ()-]{7,18}\d", header)
    if phone:
        add("phone", re.sub(r"\s+", " ", phone.group(0)))
    degree = []
    for line in lines:
        m = re.match(r"((?:M|B)\.Sc\.\s+in\s+[^|]+)\|\s*([^|]+)\|\s*(\d{4})[–—-](\d{4})", line)
        if m:
            degree.append(
                {
                    "title": m[1].strip(),
                    "level": "MSc" if m[1].startswith("M.Sc.") else "BSc",
                    "field": m[1].split(" in ", 1)[-1].strip(),
                    "institution": m[2].strip(),
                    "start_year": m[3],
                    "end_year": m[4],
                    "source_sha256": h,
                    "verified_from_cv": True,
                    "verified": False,
                }
            )
    gpas = re.findall(r"GPA:\s*(\d+(?:\.\d+)?)/(\d+)", text)
    if len(gpas) == len(degree):
        for d, g in zip(degree, gpas):
            d["gpa_reported"] = {"value": float(g[0]), "scale": int(g[1])}
    m = re.search(
        r"TOEFL iBT\s*\((\d+\s+[A-Za-z]+\s+\d{4})\)\s*:\s*Total\s*(\d+)\s*\(Reading\s*(\d+),\s*Listening\s*(\d+),\s*Speaking\s*(\d+),\s*Writing\s*(\d+)\)", text
    )
    language = {}
    if m:
        try:
            day = datetime.strptime(m[1], "%d %b %Y").date().isoformat()
        except ValueError:
            day = None
        language = {
            "test": "TOEFL iBT",
            "test_date": day,
            "scale": "0-120",
            "total": int(m[2]),
            "sections": dict(zip(("reading", "listening", "speaking", "writing"), map(int, m.groups()[2:]))),
            "delivery_mode": None,
            "verified": False,
            "verified_from_cv": True,
            "source_sha256": h,
        }
    return {"fields": fields, "education": degree, "language": language, "cv_sha256": h}


def build(cv, previous):
    p = read_cv(cv)
    old = json.loads(previous.read_text(encoding="utf8"))
    for k, v in old.get("fields", {}).items():
        if k not in p["fields"] and v.get("verified") is True and v.get("source_sha256") == p["cv_sha256"]:
            p["fields"][k] = v
    docs = {}
    for role, item in old.get("documents", {}).items():
        f = Path(item["path"])
        if f.is_file() and digest(f) == item.get("sha256"):
            docs[role] = item
    p.update(
        schema="aihawk.private.reusable-profile.v2",
        documents=docs,
        recorded_at=datetime.now(timezone.utc).isoformat(),
        courses=[],
        transcript_review_required=True,
    )
    return p


def main():
    p = argparse.ArgumentParser()
    p.add_argument("cv", type=Path)
    p.add_argument("previous", type=Path)
    p.add_argument("out", type=Path)
    a = p.parse_args()
    if a.out.exists():
        raise FileExistsError("Use a new profile version")
    if any((x / ".git").exists() for x in a.out.resolve().parents):
        raise ValueError("Private profile outside Git only")
    r = build(a.cv, a.previous)
    atomic_json(a.out, r)
    print(
        json.dumps(
            {
                "fields": len(r["fields"]),
                "education_records": len(r["education"]),
                "document_roles": len(r["documents"]),
                "language_cv_reported": bool(r["language"]),
                "course_records": 0,
            }
        )
    )


if __name__ == "__main__":
    main()
