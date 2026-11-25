"""Fail-closed quality gate for agent-authored academic documents.

Before a generated document is published or uploaded:
- no footnotes/endnotes, running footer, bottom-page decoration or watermark;
- all substantive body paragraphs are justified;
- the Normal Word style is Times New Roman and Justify;
- exported PDF must have an approved, matching DOCX source.
This does not rewrite external diplomas/transcripts or immutable source CVs.
"""

from __future__ import annotations

import re
from pathlib import Path
from zipfile import BadZipFile, ZipFile


class DocumentQualityError(ValueError):
    """An authored document may not be delivered or uploaded."""


WRITING_NAME = re.compile(
    r"(?i)(motivation|cover[_ -]?letter|research[_ -]?(?:plan|concept|proposal)"
    r"|project[_ -]?proposal|statement|personal[_ -]?letter"
    r"|writing[_ -]?sample|application[_ -]?letter|essay|letter[_ -]?of[_ -]?intent)"
)
EXEMPT_STYLES = ("title", "subtitle", "heading", "toc", "caption", "header", "footer")
MIN_BODY_WORDS = 13


def is_authored_writing(path: Path) -> bool:
    """Detect generated writing without treating original CV/diploma PDFs as generated writing."""
    path = Path(path)
    if path.suffix.casefold() == ".docx":
        return True
    if path.suffix.casefold() != ".pdf":
        return False
    return bool(WRITING_NAME.search(path.name) or path.with_suffix(".docx").is_file() or path.with_suffix(".review.json").is_file())


def _normal_style(paragraph):
    return not paragraph.style.name.casefold().startswith(EXEMPT_STYLES)


def _alignment(paragraph):
    if paragraph.alignment is not None:
        return paragraph.alignment
    if paragraph.style.paragraph_format.alignment is not None:
        return paragraph.style.paragraph_format.alignment
    return None


def validate_docx(path: Path) -> Path:
    """Require justification and no document-level notes, running footers or watermarks."""
    try:
        from docx import Document
        from docx.enum.text import WD_ALIGN_PARAGRAPH
    except ImportError as exc:
        raise DocumentQualityError("python-docx is required; refusing unverified academic writing.") from exc
    path = Path(path)
    if not path.is_file() or path.suffix.casefold() != ".docx":
        raise DocumentQualityError("The written document is missing or not a DOCX file.")
    try:
        with ZipFile(path) as z:
            parts = z.namelist()
            note_parts = [name for name in parts if re.search(r"^word/(?:footnotes|endnotes)\.xml$", name, re.I)]
            if note_parts:
                raise DocumentQualityError("Word document contains footnotes or endnotes.")
            for name in parts:
                if name.startswith("word/footer") and name.endswith(".xml"):
                    xml = z.read(name)
                    if any(token in xml for token in (b"<w:t>", b"<w:instrText", b"<w:drawing", b"<w:pict", b"<v:shape", b"<v:textpath")):
                        raise DocumentQualityError("Word document contains a running footer or footer decoration.")
                if name.startswith("word/header") and name.endswith(".xml"):
                    xml = z.read(name)
                    if b"<v:textpath" in xml or b"PowerPlusWaterMarkObject" in xml:
                        raise DocumentQualityError("Word document contains a watermark.")
            main = z.read("word/document.xml")
            if b"<w:footnoteReference" in main or b"<w:endnoteReference" in main:
                raise DocumentQualityError("Word document contains footnote/endnote references.")
            if b"PowerPlusWaterMarkObject" in main:
                raise DocumentQualityError("Word document contains a watermark.")
        doc = Document(path)
        normal = doc.styles["Normal"]
        if normal.paragraph_format.alignment != WD_ALIGN_PARAGRAPH.JUSTIFY:
            raise DocumentQualityError("Normal paragraph style is not explicitly justified.")
        if (normal.font.name or "").casefold().replace(" ", "") != "timesnewroman":
            raise DocumentQualityError("Academic body text must use Times New Roman.")
        body_count = 0
        for number, paragraph in enumerate(doc.paragraphs, start=1):
            text = paragraph.text.strip()
            if not text or not _normal_style(paragraph):
                continue
            if len(re.findall(r"\b\w+\b", text)) < MIN_BODY_WORDS:
                continue
            body_count += 1
            if _alignment(paragraph) != WD_ALIGN_PARAGRAPH.JUSTIFY:
                raise DocumentQualityError(f"Body paragraph {number} is not Justify-aligned.")
        if body_count < 1:
            raise DocumentQualityError("No substantive justified body paragraph found.")
        for section in doc.sections:
            for footer in (section.footer, section.even_page_footer, section.first_page_footer):
                if any(p.text.strip() for p in footer.paragraphs):
                    raise DocumentQualityError("Document footer contains visible text.")
        return path
    except DocumentQualityError:
        raise
    except (BadZipFile, KeyError, ValueError, OSError) as exc:
        raise DocumentQualityError("Word structure could not be inspected; output blocked.") from exc


def validate_pdf(path: Path, *, source_docx: Path | None = None) -> Path:
    """Block PDF without a compliant editable source and check exported text and footer area."""
    path = Path(path)
    if not path.is_file() or path.suffix.casefold() != ".pdf":
        raise DocumentQualityError("Generated PDF is missing.")
    source = Path(source_docx) if source_docx else path.with_suffix(".docx")
    if not source.is_file():
        raise DocumentQualityError("Generated PDF has no matching reviewed DOCX source; sending blocked.")
    validate_docx(source)
    try:
        import fitz
    except ImportError as exc:
        raise DocumentQualityError("PyMuPDF is required for rendered-PDF quality checking.") from exc
    try:
        with fitz.open(str(path)) as pdf:
            if not 1 <= len(pdf) <= 30:
                raise DocumentQualityError("Unexpected PDF page count.")
            words_pdf = []
            for page_index, page in enumerate(pdf):
                if not page.get_text().strip():
                    raise DocumentQualityError(f"PDF page {page_index + 1} has no readable text.")
                blocks = page.get_text("blocks")
                for block in blocks:
                    if len(block) >= 5 and block[4].strip() and float(block[1]) >= page.rect.height - 45:
                        raise DocumentQualityError(f"PDF page {page_index + 1} has footer/bottom-margin text.")
                words_pdf.extend(re.findall(r"\b[a-z0-9]+\b", page.get_text().casefold()))
        from docx import Document

        source_text = "\n".join(p.text for p in Document(source).paragraphs)
        words_doc = re.findall(r"\b[a-z0-9]+\b", source_text.casefold())
        if not words_pdf or not words_doc:
            raise DocumentQualityError("PDF/source text extraction failed.")
        from collections import Counter

        matched = sum((Counter(words_doc) & Counter(words_pdf)).values())
        if matched / len(words_doc) < 0.85:
            raise DocumentQualityError("Exported PDF does not preserve the approved Word text.")
        return path
    except DocumentQualityError:
        raise
    except Exception as exc:
        raise DocumentQualityError("Rendered PDF could not be verified; sending blocked.") from exc


def require_writing_preflight(path: Path, *, source_docx: Path | None = None) -> Path:
    """Single blocking call for both generated document output and portal uploads."""
    path = Path(path)
    if path.suffix.casefold() == ".docx":
        return validate_docx(path)
    if path.suffix.casefold() == ".pdf":
        return validate_pdf(path, source_docx=source_docx)
    raise DocumentQualityError("Generated written file format is not verified.")
