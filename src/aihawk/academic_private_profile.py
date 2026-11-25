"""Generic private reusable profile inventory. No applicant-specific defaults."""

from pathlib import Path
from datetime import datetime, timezone
import argparse
import json
from pypdf import PdfReader
from aihawk.academic_profile_v2 import read_cv, digest
from aihawk.academic_outreach_workflow import atomic_json


def build(cv, documents):
    cv = cv.resolve(strict=True)
    profile = read_cv(cv)
    paths = {"cv": str(cv), **documents}
    inventory = {}
    for role, filename in paths.items():
        p = Path(filename).resolve(strict=True)
        if p.suffix.lower() != ".pdf":
            raise ValueError("Reviewed PDF source required")
        r = PdfReader(p)
        inventory[role] = {
            "path": str(p),
            "sha256": digest(p),
            "page_count": len(r.pages),
            "readable_text": sum(len(x.extract_text() or "") for x in r.pages) > 100,
            "verified": role == "cv",
            "requires_role_review": role != "cv",
        }
    profile.update(
        schema="aihawk.private.reusable-profile.v2",
        recorded_at=datetime.now(timezone.utc).isoformat(),
        documents=inventory,
        courses=[],
        transcript_review_required=True,
    )
    return profile


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--cv", type=Path, required=True)
    p.add_argument("--document-map", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    a = p.parse_args()
    if a.out.exists() or any((x / ".git").exists() for x in a.out.resolve().parents):
        raise ValueError("New private profile path outside Git required")
    a.out.parent.mkdir(parents=True, exist_ok=True)
    r = build(a.cv, json.loads(a.document_map.read_text(encoding="utf8")))
    atomic_json(a.out, r)
    print(
        json.dumps(
            {
                "verified_field_count": len(r["fields"]),
                "document_roles": len(r["documents"]),
                "scanned_documents": sum(not x["readable_text"] for x in r["documents"].values()),
            }
        )
    )


if __name__ == "__main__":
    main()
