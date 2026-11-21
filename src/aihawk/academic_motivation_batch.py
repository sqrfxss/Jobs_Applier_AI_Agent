"""Batch generation for several independently evidenced programme letters.

No mail merge: each position has its own approved facts, official sources,
research fit and CV fingerprint. Default behavior is read-only planning;
generation requires an explicit user action and proceeds sequentially.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aihawk.academic_motivation import MotivationError, deliver, load_brief


@dataclass(frozen=True)
class BatchItem:
    brief: Path
    output: Path
    reviewed_draft: Path | None


def batch_from_queue(path: Path) -> tuple[BatchItem, ...]:
    base = path.resolve().parent
    if any((folder / ".git").exists() for folder in (base, *base.parents)):
        raise MotivationError("An applicant writing queue cannot be stored in a public source checkout.")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or set(data) != {"positions"}:
        raise MotivationError("Batch queue must contain only a positions array.")
    entries = data["positions"]
    if not isinstance(entries, list) or not 1 <= len(entries) <= 20:
        raise MotivationError("A batch must contain between one and twenty individually reviewed positions.")
    items = []
    outputs = set()
    for record in entries:
        if not isinstance(record, dict) or not {"brief", "output"} <= set(record):
            raise MotivationError("Each position needs a private brief and a DOCX destination.")
        if set(record) - {"brief", "output", "draft_json"}:
            raise MotivationError("Unrecognized batch position entry.")
        item_paths = []
        for key in ("brief", "output", "draft_json"):
            raw = record.get(key)
            if raw is None and key == "draft_json":
                item_paths.append(None)
                continue
            if not isinstance(raw, str) or not raw.strip() or len(raw) > 350:
                raise MotivationError("Invalid private batch path.")
            resolved = (base / raw).resolve()
            if not resolved.is_relative_to(base):
                raise MotivationError("All batch inputs and outputs must remain under the private queue directory.")
            item_paths.append(resolved)
        brief, output, draft = item_paths
        if brief.suffix.lower() != ".json" or output.suffix.lower() != ".docx" or (draft and draft.suffix.lower() != ".json"):
            raise MotivationError("Expected a JSON brief, DOCX output and optional JSON draft.")
        if output in outputs:
            raise MotivationError("Two positions cannot write the same motivation letter.")
        outputs.add(output)
        if not brief.is_file() or (draft and not draft.is_file()):
            raise MotivationError("An approved private batch file is missing.")
        load_brief(brief)
        items.append(BatchItem(brief=brief, output=output, reviewed_draft=draft))
    return tuple(items)


def run_batch(queue: Path, *, generate: bool = False, model: str | None = None, overwrite: bool = False,
              generator: Any = deliver) -> list[dict[str, str]]:
    items = batch_from_queue(queue)
    summary = []
    for item in items:
        brief = load_brief(item.brief)
        record = {
            "institution": brief.institution,
            "programme": brief.programme,
            "output": item.output.name,
            "mode": "reviewed_draft" if item.reviewed_draft else "configured_openai_api",
            "status": "ready_for_generation" if not generate else "pending",
        }
        summary.append(record)
    if not generate:
        return summary
    for item, record in zip(items, summary, strict=True):
        try:
            result = generator(
                item.brief, item.output, draft_path=item.reviewed_draft,
                model=model, overwrite=overwrite,
            )
        except Exception:
            record["status"] = "failed_review_required"
            # Keep the journal free of CV text, API credentials and exception payloads.
            _save_summary(queue, summary)
            raise
        else:
            record["status"] = "draft_requires_applicant_approval"
            record["file"] = result.name
            _save_summary(queue, summary)
    return summary


def _save_summary(queue: Path, records: list[dict[str, str]]) -> None:
    destination = queue.resolve().parent / ".aihawk-motivation-batch.json"
    content = {
        "schema": "aihawk.academic.motivation-batch.v1",
        "university_submitted": False,
        "records": records,
    }
    temporary = destination.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(content, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(destination)
