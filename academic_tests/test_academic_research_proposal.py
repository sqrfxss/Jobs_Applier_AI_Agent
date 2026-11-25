import json
import pytest
from aihawk.academic_research_proposal import SECTIONS, deliver, validate


def brief():
    return {
        "reviewed": True,
        "institution": "Example University",
        "programme": "Movement science",
        "project_description": "Methodological study",
        "applicant_facts": ["Verified experience"],
        "requirements": ["Research plan"],
        "sources": [
            {
                "id": "S1",
                "citation": "Example institutional project description",
                "url": "https://example.edu/project",
                "access": "official_description",
                "excerpt": "Proposed validation research.",
            }
        ],
    }


def draft():
    return {
        "title": "Prospective research plan",
        "sections": {
            k: "This proposed section specifies a planned research activity, a prospective validation criterion, documented limitations, and a reproducible procedure, subject to institutional approval [S1]."
            for k in SECTIONS
        },
    }


def test_unknown_citation_rejected():
    d = draft()
    d["sections"]["background"] += " [S9]"
    with pytest.raises(ValueError, match="source citations"):
        validate(brief(), d)


def test_reviewed_proposal_docx(tmp_path):
    b = tmp_path / "brief.json"
    d = tmp_path / "draft.json"
    o = tmp_path / "proposal.docx"
    b.write_text(json.dumps(brief()))
    d.write_text(json.dumps(draft()))
    result = deliver(b, o, reviewed_draft=d)
    assert o.is_file() and result["status"] == "draft_requires_scientific_review"
    from docx import Document

    doc = Document(o)
    assert doc.styles["Normal"].font.name == "Times New Roman"
    assert len([p for p in doc.paragraphs if p.style.name == "Heading 1"]) == len(SECTIONS) + 1
    assert result["final_submission"] is False
