"""Private transcript extraction with reviewable page provenance.
Only use OCR when a PDF page has no usable text. OCR rows are candidates,
never verified grades or converted credits.
"""

from pathlib import Path
import argparse
import hashlib
import json
from datetime import datetime, timezone
from aihawk.academic_outreach_workflow import atomic_json


def extract(path, *, ocr_scanned=False):
    import fitz

    path = path.resolve(strict=True)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    pages = []
    engine = None
    with fitz.open(path) as doc:
        if not 1 <= len(doc) <= 30:
            raise ValueError("Unexpected transcript page count")
        for index, page in enumerate(doc):
            text = page.get_text("text").strip()
            lines = []
            method = "pdf_text"
            if len(text) < 50:
                method = "scan_unreviewed"
                if ocr_scanned:
                    import numpy as np
                    from rapidocr_onnxruntime import RapidOCR

                    if engine is None:
                        engine = RapidOCR()
                    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
                    items, _ = engine(arr)
                    lines = [{"text": str(t), "confidence": float(c), "box": b, "verified": False} for b, t, c in (items or [])]
                    method = "ocr_candidates"
            else:
                lines = [{"text": t, "confidence": None, "verified": False} for t in text.splitlines() if t.strip()]
            pages.append({"page": index + 1, "method": method, "lines": lines, "reviewed": False})
    return {
        "schema": "aihawk.transcript.candidates.v1",
        "source_file": str(path),
        "source_sha256": digest,
        "recorded_utc": datetime.now(timezone.utc).isoformat(),
        "pages": pages,
        "verified_courses": [],
        "requires_independent_review": True,
    }


def reviewed_courses(candidate, review):
    if review.get("source_sha256") != candidate.get("source_sha256"):
        raise ValueError("Transcript source changed")
    if review.get("reviewed") is not True or not review.get("reviewer"):
        raise ValueError("Explicit transcript review required")
    pages = {p["page"]: p for p in candidate["pages"]}
    seen = set()
    out = []
    for c in review.get("courses", []):
        if c.get("id") in seen or not c.get("id"):
            raise ValueError("Unique course ID required")
        page = pages.get(c.get("page"))
        if not page or not c.get("title") or c.get("credit_unit") not in ("ECTS", "local_credit", "US_credit"):
            raise ValueError("Course and source evidence incomplete")
        if not c.get("source_excerpt") or c.get("source_excerpt") not in " ".join(x["text"] for x in page["lines"]):
            raise ValueError("Course source excerpt not present")
        if not isinstance(c.get("credits"), (float, int)) or not 0 < c["credits"] <= 60:
            raise ValueError("Invalid credits")
        if c.get("reviewed") is not True:
            raise ValueError("Course unreviewed")
        seen.add(c["id"])
        out.append({**c, "source_sha256": candidate["source_sha256"], "verified": True})
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("pdf", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--ocr-scanned", action="store_true")
    a = p.parse_args()
    if a.output.exists():
        raise FileExistsError("Use a new extraction output")
    if any((x / ".git").exists() for x in a.output.resolve().parents):
        raise ValueError("Private transcript extraction outside Git only")
    r = extract(a.pdf, ocr_scanned=a.ocr_scanned)
    atomic_json(a.output, r)
    print(
        json.dumps(
            {
                "pages": len(r["pages"]),
                "ocr_pages": sum(x["method"] == "ocr_candidates" for x in r["pages"]),
                "candidate_lines": sum(len(x["lines"]) for x in r["pages"]),
                "verified_courses": 0,
            }
        )
    )


if __name__ == "__main__":
    main()
