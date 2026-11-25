"""No real applicant or API data used in PDF-export safety tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from aihawk.academic_motivation import MotivationError
from aihawk.academic_motivation_pdf import _verify_one_page_pdf, export_letter_pdf


def synthetic_word(tmp_path: Path) -> Path:
    from docx import Document

    doc = Document()
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    doc.styles["Normal"].font.name = "Times New Roman"
    doc.styles["Normal"].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    doc.add_paragraph("MOTIVATION LETTER")
    doc.add_paragraph("PhD Biomedical Modelling | Example University")
    doc.add_paragraph(
        "This is a synthetic example written only for verifying PDF export and covers sufficient academic text to test the justified body paragraph requirement correctly."
    )
    doc.add_paragraph("Example Person")
    file = tmp_path / "reviewed-letter.docx"
    doc.save(file)
    return file


def test_private_pdf_export_uses_office_and_rejects_unapproved_overwrite(tmp_path, monkeypatch):
    import aihawk.academic_motivation_pdf as module

    docx = synthetic_word(tmp_path)
    output = tmp_path / "reviewed-letter.pdf"
    calls = []

    def fake_export(source, destination):
        calls.append((source, destination))
        destination.write_bytes(b"%PDF-1.4 synthetic pdf test")

    monkeypatch.setattr(module, "_word_export", fake_export)
    monkeypatch.setattr(module, "_libreoffice_export", fake_export)
    monkeypatch.setattr(module, "_verify_one_page_pdf", lambda *a, **kw: None)
    # Conversion is mocked above, so only rendered-PDF inspection is mocked.
    monkeypatch.setattr("aihawk.academic_document_gate.validate_pdf", lambda path, **kw: path)
    assert export_letter_pdf(docx, output, expected_name="Example Person", expected_institution="Example University") == output
    assert len(calls) == 1
    assert output.read_bytes() == b"%PDF-1.4 synthetic pdf test"
    with pytest.raises(MotivationError, match="already exists"):
        export_letter_pdf(docx, output, expected_name="Example Person", expected_institution="Example University")


def test_export_does_not_commit_partial_pdf_on_conversion_failure(tmp_path, monkeypatch):
    import aihawk.academic_motivation_pdf as module

    docx = synthetic_word(tmp_path)
    output = tmp_path / "reviewed-letter.pdf"

    def failed_export(src, dst):
        dst.write_bytes(b"invalid truncated PDF")
        raise MotivationError("office failed")

    monkeypatch.setattr(module, "_word_export", failed_export)
    monkeypatch.setattr(module, "_libreoffice_export", failed_export)
    with pytest.raises(MotivationError, match="office failed"):
        export_letter_pdf(docx, output, expected_name="Example Person", expected_institution="Example University")
    assert not output.exists()


def test_incorrect_applicant_or_institution_refused(tmp_path):
    docx = synthetic_word(tmp_path)
    with pytest.raises(MotivationError, match="applicant and institution"):
        export_letter_pdf(docx, tmp_path / "out.pdf", expected_name="Different Person", expected_institution="Example University")


def test_pdf_must_remain_private_and_beside_source(tmp_path):
    docx = synthetic_word(tmp_path)
    outside = tmp_path.parent / "unreviewed.pdf"
    with pytest.raises(MotivationError, match="beside"):
        export_letter_pdf(docx, outside, expected_name="Example Person", expected_institution="Example University")
    (tmp_path / ".git").mkdir()
    with pytest.raises(MotivationError, match="repository"):
        export_letter_pdf(docx, tmp_path / "reviewed-letter.pdf", expected_name="Example Person", expected_institution="Example University")


def test_blank_pdf_without_letter_content_is_rejected(tmp_path):
    from pypdf import PdfWriter

    file = tmp_path / "blank.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=595.3, height=841.9)
    with file.open("wb") as handle:
        writer.write(handle)
    with pytest.raises(MotivationError, match="heading or signature"):
        _verify_one_page_pdf(file, expected_name="Example Person", expected_institution="Example University")
