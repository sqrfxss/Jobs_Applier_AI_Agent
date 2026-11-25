"""Academic operator workflow: capture evidence, preview, and manual portal handoff.

University submission and logins are never automated. Optional motivation
writing uses a configured OpenAI API only after a user-triggered CLI command.
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
    autofill.add_argument("--persistent", action="store_true", help="Reuse the private academic browser login.")
    autofill_stages = subs.add_parser("autofill-stages", help="Prepare individually reviewed stages; human navigates between pages and submits.")
    autofill_stages.add_argument("manifest", type=Path)
    autofill_stages.add_argument("--persistent", action="store_true", help="Reuse the private academic browser login.")
    background_queue = subs.add_parser(
        "background-queue",
        help="Run only approved private manifests sequentially, no UI interruption or final submission.",
    )
    background_queue.add_argument("queue", type=Path)
    background_queue.add_argument("--out", type=Path)
    background_draft = subs.add_parser(
        "background-draft",
        help="Headless one-page draft Save and server readback; no consent, emails, or final Submit.",
    )
    background_draft.add_argument("manifest", type=Path)
    background_draft.add_argument("--out", type=Path, help="Resumable private JSON report.")
    background_journey = subs.add_parser(
        "background-journey",
        help="Headless mapped multi-stage draft Save, upload receipts, and server readback; NEVER final Submit.",
    )
    background_journey.add_argument("manifest", type=Path)
    background_journey.add_argument("--out", type=Path, help="Private resumable JSON report beside the manifest.")
    background = subs.add_parser(
        "background-prepare",
        help="Prepare mapped fields in isolated headless Chrome; no popup, emails, Save, or Submit.",
    )
    background.add_argument("manifest", type=Path)
    background.add_argument("--out", type=Path, help="Private audit JSON beside the manifest.")
    background.add_argument("--inspect-only", action="store_true", help="Read control inventory, don't fill values.")
    session = subs.add_parser("session", help="Open private academic browser; session-only logins may expire when it closes.")
    session.add_argument("manifest", type=Path)
    uploads = subs.add_parser("upload-reviewed", help="Upload reviewed files in one persistent browser, checking server receipts.")
    uploads.add_argument("manifest", type=Path)
    inspect = subs.add_parser("inspect", help="Read form labels and control types without accessing applicant values.")
    inspect.add_argument("manifest", type=Path)
    inspect.add_argument("output", type=Path)
    inspect.add_argument("--persistent", action="store_true", help="Reuse the private academic browser login.")
    audit = subs.add_parser("audit-snapshot", help="Audit a previously saved redacted form inventory offline; no portal access.")
    audit.add_argument("snapshot", type=Path)
    audit.add_argument("output", type=Path)
    audit.add_argument("--host", required=True, help="Previously verified exact institutional host.")
    motivation = subs.add_parser(
        "motivation-letter",
        help="Generate a personalised, source-reviewed motivation letter in Times New Roman Word format.",
    )
    motivation.add_argument("brief", type=Path, help="Private JSON brief with CV and programme evidence.")
    motivation.add_argument("output", type=Path, help="Private DOCX output path.")
    motivation.add_argument("--draft-json", type=Path, help="Optional reviewed model draft; otherwise use the configured OpenAI API.")
    motivation.add_argument("--model", help="OpenAI API model (or set OPENAI_MODEL).")
    motivation.add_argument("--overwrite", action="store_true", help="Replace an existing DOCX only when deliberately requested.")
    motivation.add_argument("--pdf", action="store_true", help="Also export a verified single-page A4 PDF in the private application folder.")
    motivation_auto = subs.add_parser(
        "motivation-auto",
        help="Generate individual, evidence-grounded draft DOCX letters from a private position queue.",
    )
    motivation_auto.add_argument("queue", type=Path, help="Private JSON position queue with a locally stored CV.")
    motivation_auto.add_argument("--model", help="OpenAI API model (or set OPENAI_MODEL).")
    verify_writing = subs.add_parser(
        "verify-written-file",
        help="BLOCKING layout inspection of an authored DOCX/PDF before email or university upload.",
    )
    verify_writing.add_argument("file", type=Path)
    verify_writing.add_argument("--source-docx", type=Path, help="Required editable source for PDF when names differ.")
    batch = subs.add_parser("motivation-batch-reviewed", help="Plan or explicitly generate separately reviewed letters for multiple positions.")
    batch.add_argument("queue", type=Path, help="Private queue JSON listing one brief per position.")
    batch.add_argument("--generate", action="store_true", help="Explicitly generate all reviewed letters; default only previews.")
    batch.add_argument("--model", help="OpenAI model for API-backed drafts.")
    batch.add_argument("--overwrite", action="store_true")
    for name in ("track-prepared", "track-submitted", "track-status"):
        track = subs.add_parser(name, help="Record or inspect local redacted application status.")
        track.add_argument("manifest", type=Path)
        track.add_argument("--db", type=Path, help="Private local SQLite file; defaults beside manifest.")
        if name == "track-submitted":
            track.add_argument("--proof", type=Path, help="Local confirmation evidence file (optional).")
    args = parser.parse_args(argv)

    if args.action == "verify-written-file":
        from aihawk.academic_document_gate import require_writing_preflight
        from aihawk.academic_ops import _hash_file

        validated = require_writing_preflight(args.file, source_docx=args.source_docx)
        print("PASS — no footnotes/footer; Justify; validated Word/PDF export; do not email or upload without this pass.")
        print("FILE: " + str(validated.resolve()))
        print("SHA256: " + _hash_file(validated))
        return 0

    if args.action == "motivation-batch-reviewed":
        from aihawk.academic_motivation_batch import run_batch

        results = run_batch(args.queue, generate=args.generate, model=args.model, overwrite=args.overwrite)
        for entry in results:
            print(f"{entry['institution']} — {entry['programme']}: {entry['status']} ({entry['output']})")
        if not args.generate:
            print("Read-only preview. Supply --generate explicitly to create any letters.")
        else:
            print("Private drafts created; applicant review required. No portal submission.")
        return 0

    if args.action == "motivation-auto":
        from aihawk.academic_motivation_auto import process_queue

        report = process_queue(args.queue, model=args.model)
        successful = sum(row["status"] == "drafted_review_required" for row in report["results"])
        pending = sum(row["status"] == "already_drafted_review_required" for row in report["results"])
        failed = sum(row["status"] == "error" for row in report["results"])
        print(f"New Word drafts: {successful}; previously drafted: {pending}; errors: {failed}.")
        print("Each draft requires applicant review. No application was submitted.")
        return 1 if failed else 0

    if args.action == "motivation-letter":
        from aihawk.academic_motivation import deliver

        result = deliver(
            args.brief,
            args.output,
            draft_path=args.draft_json,
            model=args.model,
            overwrite=args.overwrite,
        )
        print("Private Word motivation-letter draft: " + str(result))
        if args.pdf:
            from aihawk.academic_motivation import load_brief
            from aihawk.academic_motivation_pdf import export_letter_pdf

            review = load_brief(args.brief)
            pdf = export_letter_pdf(
                result,
                result.with_suffix(".pdf"),
                expected_name=review.applicant_name,
                expected_institution=review.institution,
            )
            print("Verified one-page PDF motivation draft: " + str(pdf))
        print("Times New Roman; no watermark; applicant review required. Nothing submitted.")
        return 0

    if args.action == "audit-snapshot":
        from aihawk.academic_readiness import write_readiness

        report = write_readiness(args.snapshot, args.output, expected_host=args.host)
        counts = report["counts"]
        print(
            "Historical redacted snapshot only; not current admission status. "
            f"Required blanks: {counts['required_blank']}; "
            f"unresolved selectors: {counts['unset_selects']}; "
            f"empty file inputs at capture: {counts['empty_file_inputs_at_capture']}."
        )
        return 0

    if args.action == "background-queue":
        from aihawk.academic_background_queue import run_approved_queue

        result = run_approved_queue(
            args.queue,
            args.out or args.queue.with_name(".aihawk-queue-progress.json"),
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["result"] == "queue_draft_work_complete" else 2

    if args.action == "background-draft":
        from aihawk.academic_background_single import run_background_draft_reported as run_background_draft

        result = run_background_draft(
            args.manifest,
            args.out or args.manifest.with_name(".aihawk-single-draft-status.json"),
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["result"] == "server_saved_verified" else 2

    if args.action == "background-journey":
        from aihawk.academic_background_journey import run_background_journey_reported as run_background_journey

        result = run_background_journey(
            args.manifest,
            args.out or args.manifest.with_name(".aihawk-journey-status.json"),
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["result"] == "all_draft_stages_saved_verified" else 2

    if args.action == "background-prepare":
        from aihawk.academic_background import run_background

        result = run_background(
            args.manifest,
            args.out or args.manifest.with_name(".aihawk-background-report.json"),
            inspect_only=args.inspect_only,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.action == "session":
        from aihawk.academic_browser_session import run_interactive_session

        return run_interactive_session(args.manifest)

    if args.action == "upload-reviewed":
        from aihawk.academic_uploads import run_interactive_uploads

        return run_interactive_uploads(args.manifest)

    if args.action == "inspect":
        from aihawk.academic_inspect import run_interactive_inspection

        return run_interactive_inspection(args.manifest, args.output, persistent=args.persistent)

    if args.action == "autofill-stages":
        from aihawk.academic_stages import run_interactive_journey

        return run_interactive_journey(args.manifest, persistent=args.persistent)

    if args.action == "autofill":
        from aihawk.academic_browser import run_interactive

        return run_interactive(args.manifest, persistent=args.persistent)

    if args.action.startswith("track-"):
        import sys
        from datetime import UTC, datetime

        from aihawk.academic_tracker import LocalApplicationRegistry, application_reference

        data = _payload(args.manifest)
        preview, title, hosts, _ = application_from_manifest(data, manifest_dir=args.manifest.parent)
        reference = application_reference(preview, title)
        database = args.db or args.manifest.parent / "academic-private.sqlite"
        with LocalApplicationRegistry(database) as registry:
            if args.action == "track-prepared":
                status = registry.record_prepared(preview, title=title, hosts=hosts, now=datetime.now(UTC))
            elif args.action == "track-status":
                status = registry.state_for(reference)
            else:
                if not sys.stdin.isatty():
                    raise PermissionError("Reporting a submission requires an interactive human terminal.")
                challenge = "SUBMITTED " + preview.fingerprint()[-12:]
                if input(f"Only after manual submission, type {challenge}: ") != challenge:
                    print("No submission recorded.")
                    return 1
                proof_path = None if args.proof is None else (args.manifest.parent / args.proof).resolve()
                status = registry.record_manual_submission(
                    preview,
                    title=title,
                    now=datetime.now(UTC),
                    human_attested=True,
                    proof_path=proof_path,
                    private_root=args.manifest.parent,
                )
        print(f"Local status: {status.state if status else 'not_recorded'}. No university contacted.")
        return 0

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
        if "portal_stages" in manifest:
            from aihawk.academic_stages import journey_from_manifest

            journey = journey_from_manifest(manifest, manifest_dir=args.manifest.parent)
            binding_summary = tuple(
                (f"{stage.name} [{stage.expected_host}{stage.expected_path}]: {entry.field}", entry.selector, entry.kind)
                for stage in journey.stages
                for entry in stage.form.bindings
            )
            binding_fingerprint = journey.fingerprint()
        elif "portal_bindings" in manifest:
            from aihawk.academic_browser import plan_from_manifest

            plan = plan_from_manifest(manifest, manifest_dir=args.manifest.parent)
            binding_summary = tuple((entry.field, entry.selector, entry.kind) for entry in plan.bindings)
            binding_fingerprint = plan.fingerprint()
        markup = render_preview(
            application,
            title=title,
            official_hosts=hosts,
            sources=sources,
            binding_summary=binding_summary,
            binding_fingerprint=binding_fingerprint,
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
