"""Academic operator workflow: capture evidence, preview, and manual portal handoff.

No automatic filling, form submission, login, or third-party AI calls.
All official domains are configured explicitly by the operator.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from aihawk.academic_approval import ApplicationPreview
from aihawk.academic_portal import open_manual_portal, render_preview, save_preview
from aihawk.official_fetch import fetch_official_page


def _payload(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError("Application manifest must contain a JSON object.")
    return data


def _hash_file(path: Path) -> str:
    if not path.is_file() or path.stat().st_size > 30_000_000:
        raise ValueError(f"Attachment not found or exceeds 30 MB: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(262_144):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def application_from_manifest(data: dict, *, manifest_dir: Path) -> tuple[ApplicationPreview, str, tuple[str, ...], tuple[str, ...]]:
    """Derive fingerprints from real attachment contents, never user-supplied hashes."""
    fields = data["fields"]
    if not isinstance(fields, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in fields.items()):
        raise ValueError("Application fields must be a mapping of strings.")
    files = data.get("attachments", [])
    if not isinstance(files, list) or not all(isinstance(f, str) for f in files):
        raise ValueError("Attachments must be a list of paths.")
    root = manifest_dir.resolve()
    paths = tuple((root / name).resolve() for name in files)
    if any(not path.is_relative_to(root) for path in paths):
        raise ValueError("Attachment paths must remain inside the private manifest directory.")
    hashes = tuple(_hash_file(path) for path in paths)
    preview = ApplicationPreview(
        opportunity_url=data["official_application_url"],
        applicant_id=data["applicant_id"],
        fields=tuple(sorted(fields.items())),
        attachment_hashes=hashes,
    )
    hosts = tuple(data["official_hosts"])
    return preview, str(data["title"]), hosts, tuple(data.get("source_urls", ()))


def evidence_capture(url: str, *, official_hosts: tuple[str, ...], exact_phrase: str, requirement: str) -> dict:
    """Capture a real source and exact excerpt, not its semantic meaning."""
    if not requirement.strip():
        raise ValueError("An explicit requirement field name is needed.")
    snapshot = fetch_official_page(url, official_hosts=official_hosts)
    excerpt = snapshot.excerpt(exact_phrase)
    return {
        "schema_version": "aihawk.academic.evidence.v1",
        "source_url": snapshot.final_url,
        "retrieved_at": snapshot.retrieved_at.isoformat(),
        "document_sha256": snapshot.sha256,
        "mime_type": snapshot.content_type,
        "requirement": requirement,
        "matched_phrase": exact_phrase,
        "exact_phrase_found": True,
        "excerpt": excerpt,
        "interpretation_reviewed": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Human-reviewed university workflow; NEVER submits forms.")
    subs = parser.add_subparsers(dest="action", required=True)
    capture = subs.add_parser("capture", help="Fetch and capture evidence from an approved official host.")
    capture.add_argument("--url", required=True)
    capture.add_argument("--host", required=True, action="append", help="Official institutional hostname; repeatable.")
    capture.add_argument("--phrase", required=True, help="Exact phrase to locate in source.")
    capture.add_argument("--requirement", required=True, help="Requirement name in the application record.")
    capture.add_argument("--out", required=True, type=Path)
    preview = subs.add_parser("preview", help="Produce a static review HTML (no submit controls).")
    preview.add_argument("manifest", type=Path)
    preview.add_argument("output", type=Path)
    handoff = subs.add_parser("handoff", help="Open the official portal after typing a human challenge.")
    handoff.add_argument("manifest", type=Path)
    autofill = subs.add_parser("autofill", help="Prepare explicitly mapped controls in a visible browser; user submits manually.")
    autofill.add_argument("manifest", type=Path)
    args = parser.parse_args(argv)

    if args.action == "autofill":
        from aihawk.academic_browser import run_interactive

        return run_interactive(args.manifest)

    if args.action == "capture":
        record = evidence_capture(args.url, official_hosts=tuple(args.host), exact_phrase=args.phrase, requirement=args.requirement)
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Captured: {record['source_url']} ({record['document_sha256'][:12]}…). Interpretation still needs review.")
        return 0

    manifest = _payload(args.manifest)
    application, title, hosts, sources = application_from_manifest(manifest, manifest_dir=args.manifest.parent)
    if args.action == "preview":
        binding_summary: tuple[tuple[str, str, str], ...] = ()
        binding_fingerprint: str | None = None
        if "portal_bindings" in manifest:
            from aihawk.academic_browser import plan_from_manifest

            plan = plan_from_manifest(manifest, manifest_dir=args.manifest.parent)
            binding_summary = tuple((entry.field, entry.selector, entry.kind) for entry in plan.bindings)
            binding_fingerprint = plan.fingerprint()
        markup = render_preview(
            application, title=title, official_hosts=hosts, sources=sources,
            binding_summary=binding_summary, binding_fingerprint=binding_fingerprint,
        )
        save_preview(args.output, markup)
        print(f"Saved review preview: {args.output}. Fingerprint: {application.fingerprint()}. Nothing submitted.")
        return 0
    if not open_manual_portal(application, official_hosts=hosts):
        print("Cancelled or browser did not open; nothing submitted.")
        return 1
    print("Official portal opened for manual review and submission. AIHawk did not fill or submit the form.")
    return 0


def run() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    run()
