"""Automatic, individually grounded academic motivation letters for an opportunity queue.

Reads a private CV and each institution's approved public source. Uses the
configured OpenAI API to draft new text per position. No cookies, passwords,
university logins, job applications or final submissions are performed.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import unicodedata
from collections.abc import Callable
from pathlib import Path
from typing import Any

from aihawk.academic_motivation import MotivationError, deliver
from aihawk.official_fetch import PageSnapshot, fetch_official_page

MAX_OPPORTUNITIES = 50
KEY_PHRASES = ("research", "programme", "program", "project", "method", "model", "training", "supervis", "biomed", "scientif", "application")


def _required(value: Any, field: str, limit: int = 350) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise MotivationError(f"{field} must be a nonempty, bounded string.")
    return value.strip()


def _slug(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-zA-Z0-9]+", "-", normalized).strip("-").lower()[:65] or "position"


def _cv_facts(cv_path: Path) -> list[str]:
    """Collect exact CV evidence excerpts. The writer still receives the full redacted CV."""
    try:
        from pypdf import PdfReader
    except ImportError as error:
        raise MotivationError("pypdf is required for private CV extraction.") from error
    reader = PdfReader(str(cv_path))
    if not 1 <= len(reader.pages) <= 12:
        raise MotivationError("CV page count is outside the supported range.")
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    text = re.split(r"(?im)^\s*(?:ACADEMIC REFEREES|REFERENCES)\s*$", text)[0]
    lines = [" ".join(line.split()) for line in text.splitlines()]
    keys = ("b.sc.", "m.sc.", "bachelor", "master", "research programmer", "thesis:", "neural network", "biomechanic", "data processing")
    facts = []
    for line in lines:
        if (
            any(key in line.casefold() for key in keys)
            and 20 <= len(line) <= 350
            and line not in facts
            and "@" not in line
            and not re.search(r"\+?\d[\d\s-]{9,}", line)
        ):
            facts.append(line)
        if len(facts) >= 9:
            break
    if len(facts) < 2:
        raise MotivationError("CV facts cannot be safely extracted for automatic personalisation.")
    return facts


def _official_excerpt(snapshot: PageSnapshot, title: str) -> str:
    """Select short, attributable excerpts; never ask the model to obey page instructions."""
    text = " ".join(snapshot.text.split())
    if len(text) < 180:
        raise MotivationError("Official position page does not contain enough readable evidence.")
    fragments = re.split(r"(?<=[.!?])\s+", text)
    title_tokens = {w.casefold() for w in re.findall(r"[A-Za-z]{4,}", title)}
    rows: list[tuple[int, int, str]] = []
    for idx, sentence in enumerate(fragments):
        if not 35 <= len(sentence) <= 600:
            continue
        lower = sentence.casefold()
        score = 2 * sum(token in lower for token in title_tokens) + sum(token in lower for token in KEY_PHRASES)
        if score:
            rows.append((score, idx, sentence))
    selected = sorted(sorted(rows, key=lambda item: item[0], reverse=True)[:8], key=lambda item: item[1])
    excerpt = " ".join(row[2] for row in selected)[:1750].strip()
    if len(excerpt) < 120:
        raise MotivationError("Official evidence does not adequately describe this position.")
    return excerpt


def _read_queue(queue_path: Path) -> tuple[Path, str, Path, list[dict[str, Any]]]:
    root = queue_path.resolve().parent
    if any((ancestor / ".git").exists() for ancestor in (root, *root.parents)):
        raise MotivationError("Private applicant data must not be saved in a Git repository.")
    data = json.loads(queue_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise MotivationError("Position queue must be a JSON object.")
    name = _required(data.get("applicant_name"), "applicant_name")
    cv_name = _required(data.get("cv_file"), "cv_file")
    cv_path = (root / cv_name).resolve()
    if not cv_path.is_relative_to(root) or not cv_path.is_file() or cv_path.suffix.lower() != ".pdf":
        raise MotivationError("CV must be a PDF inside the private queue directory.")
    if cv_path.stat().st_size > 10_000_000:
        raise MotivationError("CV exceeds the supported file-size limit.")
    items = data.get("positions")
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_OPPORTUNITIES:
        raise MotivationError("Provide between 1 and 50 academic positions.")
    for item in items:
        if not isinstance(item, dict):
            raise MotivationError("Each position must be a structured record.")
    return root, name, cv_path, items


def prepare_position(
    private_root: Path,
    name: str,
    cv_path: Path,
    position: dict[str, Any],
    *,
    fetcher: Callable[..., PageSnapshot] = fetch_official_page,
) -> tuple[Path, Path]:
    """Create an attributed private brief automatically for one official position."""
    institution = _required(position.get("institution"), "institution")
    programme = _required(position.get("programme"), "programme")
    degree = _required(position.get("degree"), "degree", 40)
    url = _required(position.get("official_url"), "official_url", 1200)
    hosts = position.get("official_hosts")
    if not isinstance(hosts, list) or not hosts or not all(isinstance(host, str) and host for host in hosts):
        raise MotivationError("Institutional hosts must be explicitly approved.")
    source = fetcher(url, official_hosts=tuple(hosts))
    if not isinstance(source, PageSnapshot) or not source.text:
        raise MotivationError("Cannot verify official position information.")
    digest = hashlib.sha256((url + institution + programme + degree).encode("utf-8")).hexdigest()[:10]
    directory = (private_root / "motivation_letters" / f"{_slug(institution)}-{_slug(programme)}-{digest}").resolve()
    if not directory.is_relative_to(private_root.resolve()):
        raise MotivationError("Position folder escapes the private application directory.")
    directory.mkdir(parents=True, exist_ok=True)
    # Maintain a private, SHA-verified CV copy beside each reviewed brief.
    target_cv = directory / "cv-source.pdf"
    if target_cv.exists():
        if hashlib.sha256(target_cv.read_bytes()).digest() != hashlib.sha256(cv_path.read_bytes()).digest():
            raise MotivationError("The position CV differs from the approved original.")
    else:
        shutil.copyfile(cv_path, target_cv)
    facts = _cv_facts(target_cv)
    brief = {
        "applicant_name": name,
        "institution": institution,
        "programme": programme,
        "degree": degree,
        "cv_file": target_cv.name,
        "official_source_hosts": hosts,
        "applicant_facts": facts,
        "programme_evidence": [{"url": source.final_url, "excerpt": _official_excerpt(source, programme)}],
        "research_fit": [
            "Identify a specific methodological match supported by the applicant CV and the official description.",
            "If this field is a research transition, acknowledge important disciplinary preparation gaps."
        ],
        "career_goal": "Pursue reproducible scientific research that addresses the concrete questions in the official position description.",
        "forbidden_organizations": position.get("forbidden_organizations", []),
        "min_words": 300,
        "max_words": 440,
        "application_method": "reviewed_document",
    }
    # Do not overwrite a previously drafted or independently edited brief.
    brief_path = directory / "position-brief.json"
    if brief_path.exists():
        previous = json.loads(brief_path.read_text(encoding="utf-8"))
        if previous != brief:
            raise MotivationError("Existing position brief has changed. Review the prior draft rather than overwrite it.")
    else:
        brief_path.write_text(json.dumps(brief, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    meta = directory / "official-source-audit.json"
    if not meta.exists():
        meta.write_text(json.dumps({
            "source_url": source.final_url, "retrieved_at": source.retrieved_at.isoformat(),
            "sha256": source.sha256, "content_type": source.content_type,
            "review_status": "SOURCE_CAPTURED_NOT_INTERPRETATION_APPROVED",
        }, indent=2) + "\n", encoding="utf-8")
    return brief_path, directory / "MotivationLetter_TimesNewRoman.docx"


def _required_portal_format(position: dict[str, Any]) -> str:
    """Select a verified portal-accepted format; never guess a university rule."""
    allowed = position.get("portal_allowed_extensions")
    if allowed is None:
        return "docx"  # No site-specific conversion is authorized or implied.
    if not isinstance(allowed, list) or not allowed or not all(
        isinstance(ext, str) and re.fullmatch(r"\.?[a-zA-Z0-9]{1,12}", ext) for ext in allowed
    ):
        raise MotivationError("Invalid official portal file-extension list.")
    normalized = {ext.casefold().lstrip(".") for ext in allowed}
    if "docx" in normalized:
        return "docx"
    if "pdf" in normalized:
        return "pdf"
    raise MotivationError("The portal does not accept DOCX or PDF; a suitable reviewed export is unavailable.")


def process_queue(
    queue_path: Path,
    *,
    model: str | None = None,
    fetcher: Callable[..., PageSnapshot] = fetch_official_page,
    draft_provider: Callable[[Path, dict[str, Any]], Path | None] | None = None,
) -> dict[str, Any]:
    """One run: one independently generated letter per position, never a submission."""
    root, name, cv_path, positions = _read_queue(queue_path)
    results: list[dict[str, str]] = []
    for position in positions:
        identifier = str(position.get("official_url", "unknown"))[:1200]
        try:
            required_format = _required_portal_format(position)
            brief, output = prepare_position(root, name, cv_path, position, fetcher=fetcher)
            final_path = output.with_suffix(".pdf") if required_format == "pdf" else output
            if final_path.exists():
                results.append({"official_url": identifier, "status": "already_drafted_review_required", "path": str(final_path)})
                continue
            created = False
            if not output.exists():
                draft = draft_provider(brief, position) if draft_provider is not None else None
                deliver(brief, output, draft_path=draft, model=model)
                created = True
            if required_format == "pdf":
                from aihawk.academic_motivation_pdf import export_letter_pdf

                export_letter_pdf(
                    output, final_path, expected_name=name,
                    expected_institution=str(position["institution"]),
                )
            results.append({
                "official_url": identifier,
                "status": "drafted_review_required" if created else "pdf_exported_review_required",
                "path": str(final_path),
            })
        except (OSError, ValueError, RuntimeError) as error:
            results.append({"official_url": identifier, "status": "error", "reason": type(error).__name__ + ": " + str(error)[:240]})
    summary = {
        "schema": "aihawk.academic.motivation-batch.v1",
        "university_submission": False,
        "human_review_required": True,
        "results": results,
    }
    path = root / "motivation_batch_review.json"
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary
