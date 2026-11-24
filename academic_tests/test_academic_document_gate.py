"""Regression tests: no agent-authored written file may escape layout preflight."""

import hashlib
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

import pytest
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH

from aihawk.academic_document_gate import (
    DocumentQualityError,
    validate_docx,
    validate_pdf,
    is_authored_writing,
)
from aihawk.academic_browser import PortalPreparationError
from aihawk.academic_uploads import _verify_file

TEXT = (
    "An academic document must use readable Times New Roman body paragraphs, "
    "accurately describe research methods without inventing results, and remain "
    "fully justified throughout the main body of the academic proposal."
)


def make_docx(path: Path, *, align=True, footer=False):
    d = Document()
    d.styles["Normal"].font.name = "Times New Roman"
    d.styles["Normal"].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY if align else WD_ALIGN_PARAGRAPH.LEFT
    d.add_paragraph(TEXT)
    if footer:
        d.sections[0].footer.paragraphs[0].text = "An unwanted footer label"
    d.save(path)
    return path


def test_good_justified_docx_passes(tmp_path):
    p = make_docx(tmp_path / "letter.docx")
    assert validate_docx(p) == p
    assert is_authored_writing(p)


def test_bad_alignment_is_blocked(tmp_path):
    p = make_docx(tmp_path / "statement.docx", align=False)
    with pytest.raises(DocumentQualityError, match="Justify|justified"):
        validate_docx(p)


def test_bad_footer_is_blocked(tmp_path):
    p = make_docx(tmp_path / "proposal.docx", footer=True)
    with pytest.raises(DocumentQualityError, match="footer"):
        validate_docx(p)


def test_footnote_part_is_blocked(tmp_path):
    original = make_docx(tmp_path / "clean.docx")
    altered = tmp_path / "with_note.docx"
    with ZipFile(original) as src, ZipFile(altered, "w", ZIP_DEFLATED) as dst:
        for item in src.infolist():
            dst.writestr(item, src.read(item.filename))
        dst.writestr("word/footnotes.xml", "<w:footnotes xmlns:w='http://schemas.openxmlformats.org/wordprocessingml/2006/main'/>")
    with pytest.raises(DocumentQualityError, match="footnotes"):
        validate_docx(altered)


def test_pdf_without_compliant_source_is_blocked(tmp_path):
    p = tmp_path / "research_concept.pdf"
    p.write_bytes(b"%PDF-1.4 generated without reviewed Word source")
    with pytest.raises(DocumentQualityError, match="matching reviewed DOCX"):
        validate_pdf(p)


def test_pdf_upload_of_generated_writing_is_blocked(tmp_path):
    p = tmp_path / "Cover_Letter.pdf"
    p.write_bytes(b"%PDF-1.4 synthetic")
    digest = "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest()
    assert is_authored_writing(p)
    with pytest.raises(PortalPreparationError, match="layout preflight"):
        _verify_file(p, digest)


def test_original_scan_cvs_are_not_classified_as_new_writing(tmp_path):
    p = tmp_path / "Example_Applicant_CV.pdf"
    p.write_bytes(b"%PDF-1.4 synthetic")
    assert not is_authored_writing(p)
    digest = "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest()
    _verify_file(p, digest)


def test_existing_source_docx_checks_really_run_on_upload(tmp_path):
    p = make_docx(tmp_path / "research_plan.docx", footer=True)
    digest = "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest()
    with pytest.raises(PortalPreparationError, match="footer"):
        _verify_file(p, digest)
