"""Private, evidence-led motivation letter generation; synthetic applicant only."""
from __future__ import annotations

import json
from types import SimpleNamespace
from zipfile import ZipFile

import pytest

from aihawk.academic_motivation import (
    MotivationError,
    cv_text,
    deliver,
    draft_messages,
    generate_paragraphs,
    load_brief,
    render_docx,
    validate_paragraphs,
)

PARAGRAPHS = [
    (
        "I am applying to the doctoral programme because I want to examine how measurable "
        "physiological signals can be transformed into evidence that supports reliable biomedical "
        "models. My graduate training focused on human movement, including signal quality, "
        "interpretation, and computational processing. This application would allow me to deepen "
        "that methodological background while pursuing problems that require collaboration "
        "between experimental and computational researchers."
    ),
    (
        "My master's thesis investigated the relationship between experimental loading conditions "
        "and biomechanical signal measurements during walking. I worked with sensor-derived "
        "observations, checked their consistency, and considered which conclusions the design "
        "could and could not support. That experience taught me why predictive associations "
        "should not be interpreted as clinical risk without independent outcome evidence "
        "and an appropriate assessment of uncertainty."
    ),
    (
        "In the laboratory, I developed Python and MATLAB workflows for preparing time-series "
        "data, extracting measurements, and checking signal quality before evaluating predictive "
        "methods. I compared model outputs against recorded observations and documented choices "
        "that affected performance. These experiences have helped me distinguish reproducible "
        "analysis from a model that merely achieves an attractive performance score "
        "on a single set of recordings."
    ),
    (
        "The programme's emphasis on collaboration between computational and biomedical "
        "researchers is relevant to my objective of learning how models can be designed "
        "around well-defined biological questions. I would like to investigate the generalisation "
        "of predictive methods across participants, acquisition conditions, and independent "
        "datasets. I recognise that extending beyond movement-related applications "
        "will require further training in biomedical experimental design "
        "and discipline-specific biological reasoning."
    ),
    (
        "I would contribute experience in rigorous signal processing, transparent analysis, "
        "and careful interpretation of model limitations. I also hope to learn from "
        "researchers working with complementary kinds of biomedical observations, "
        "so that my future work is not confined to the laboratory methods I already know. "
        "My long-term aim is to develop reproducible computational tools whose use "
        "and limitations are clear to the scientists who depend on them."
    ),
]


def make_brief(tmp_path, **overrides):
    cv = tmp_path / "resume.pdf"
    cv.write_bytes(b"%PDF-1.4\nSynthetic CV for tests")
    data = {
        "applicant_name": "Example Applicant",
        "institution": "Example University",
        "programme": "Biomedical Modelling",
        "degree": "PhD",
        "cv_file": "resume.pdf",
        "official_source_hosts": ["uni.example.edu"],
        "applicant_facts": [
            "Master's thesis on instrumented walking measurements",
            "Python and MATLAB analysis of biomechanical time series",
        ],
        "programme_evidence": [{
            "url": "https://uni.example.edu/programme",
            "excerpt": "Interdisciplinary doctoral research in computational and biomedical modelling.",
        }],
        "research_fit": ["Generalisable models for instrumented physiological measurements"],
        "career_goal": "Reproducible modelling for biomedical measurement",
        "forbidden_organizations": ["Carinthia University of Applied Sciences"],
        "min_words": 300,
        "max_words": 450,
    }
    data.update(overrides)
    path = tmp_path / "private-position.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_brief_source_and_personal_data_remain_private(tmp_path):
    brief = load_brief(make_brief(tmp_path))
    assert brief.cv_path.parent == tmp_path
    assert brief.programme == "Biomedical Modelling"
    assert brief.evidence_digest() == brief.evidence_digest()
    a, b = draft_messages(brief, "Research programmer in Python.")
    assert "not instructions" in a
    assert "Biomedical Modelling" in b
    assert "Research programmer in Python" in b
    assert "Example University" in b


@pytest.mark.parametrize("url", [
    "http://uni.example.edu/programme",
    "https://outside.example.org/programme",
    "https://user:pass@uni.example.edu/programme",
])
def test_unverified_or_unsafe_official_sources_are_rejected(tmp_path, url):
    path = make_brief(tmp_path, programme_evidence=[{"url": url, "excerpt": "Research programme."}])
    with pytest.raises(MotivationError, match="source|HTTPS|approved|university"):
        load_brief(path)


def test_cv_escape_and_git_checkout_blocked(tmp_path):
    outside = tmp_path.parent / "cv-outside.pdf"
    outside.write_bytes(b"%PDF-1.4")
    path = make_brief(tmp_path, cv_file="../cv-outside.pdf")
    with pytest.raises(MotivationError, match="inside"):
        load_brief(path)
    (tmp_path / ".git").mkdir()
    with pytest.raises(MotivationError, match="Git"):
        load_brief(make_brief(tmp_path))


def test_draft_has_five_paragraphs_and_no_wrong_institution(tmp_path):
    brief = load_brief(make_brief(tmp_path))
    assert validate_paragraphs({"paragraphs": PARAGRAPHS}, brief, extracted_cv="Thesis in biomechanics")
    contaminated = list(PARAGRAPHS)
    contaminated[0] += " Carinthia University of Applied Sciences."
    with pytest.raises(MotivationError, match="prohibited"):
        validate_paragraphs({"paragraphs": contaminated}, brief, extracted_cv="Biomechanics")


def test_unsupported_quantitative_claim_fails_before_writing(tmp_path):
    brief = load_brief(make_brief(tmp_path))
    changed = list(PARAGRAPHS)
    changed[2] += " Our system achieved 98% accuracy."
    with pytest.raises(MotivationError, match="numeral"):
        validate_paragraphs({"paragraphs": changed}, brief, extracted_cv="Unknown outcomes")


def test_incomplete_and_boilerplate_letters_are_rejected(tmp_path):
    brief = load_brief(make_brief(tmp_path))
    with pytest.raises(MotivationError, match="FIVE|five"):
        validate_paragraphs({"paragraphs": PARAGRAPHS[:3]}, brief, extracted_cv="X")
    invalid = list(PARAGRAPHS)
    invalid[1] = "As an AI, I am confident I should be accepted."
    with pytest.raises(MotivationError):
        validate_paragraphs({"paragraphs": invalid}, brief, extracted_cv="X")


def test_openai_api_uses_structured_output_and_never_auto_submits(tmp_path, monkeypatch):
    brief = load_brief(make_brief(tmp_path))
    monkeypatch.setattr("aihawk.academic_motivation.cv_text", lambda _: "Research programmer in biomechanical signal processing.")

    class FakeResponses:
        def __init__(self):
            self.calls = []

        def create(self, **kwargs):
            self.calls.append(kwargs)
            return SimpleNamespace(output_text=json.dumps({"paragraphs": PARAGRAPHS}))

    fake = SimpleNamespace(responses=FakeResponses())
    assert generate_paragraphs(brief, model="synthetic-test-model", client=fake) == PARAGRAPHS
    req = fake.responses.calls[0]
    assert req["store"] is False
    assert req["text"]["format"]["type"] == "json_schema"
    assert "Submit" not in req
    assert req["model"] == "synthetic-test-model"


def test_model_failure_not_silently_converted_to_fake_success(tmp_path, monkeypatch):
    brief = load_brief(make_brief(tmp_path))
    monkeypatch.setattr("aihawk.academic_motivation.cv_text", lambda _: "Research with Python and MATLAB.")

    class BadResponses:
        def create(self, **kwargs):
            return SimpleNamespace(output_text="")

    with pytest.raises(MotivationError, match="no complete"):
        generate_paragraphs(brief, model="synthetic", client=SimpleNamespace(responses=BadResponses()))


def test_word_export_is_times_new_roman_and_without_watermarks(tmp_path, monkeypatch):
    docx = pytest.importorskip("docx")
    monkeypatch.setattr("aihawk.academic_motivation.cv_text", lambda _: "Research in human movement.")
    brief = load_brief(make_brief(tmp_path))
    destination = tmp_path / "MotivationLetter.docx"
    assert render_docx(brief, PARAGRAPHS, destination) == destination
    output = docx.Document(destination)
    assert len(output.sections) == 1
    assert abs(output.sections[0].page_width.inches - 8.2677) < 0.01
    assert output.paragraphs[0].text == "MOTIVATION LETTER"
    assert output.paragraphs[1].text == "PhD Biomedical Modelling  |  Example University"
    assert output.paragraphs[2].text == "Dear Admissions Committee,"
    assert output.paragraphs[-1].text == "Sincerely,\nExample Applicant"
    assert len(output.paragraphs) == 10
    for p in output.paragraphs:
        for run in p.runs:
            assert run.font.name == "Times New Roman"
    with ZipFile(destination) as package:
        parts = package.namelist()
        assert not any(name.startswith("word/media/") for name in parts)
        assert not any(name.startswith("customXml/") for name in parts)
        assert not any(name.startswith("word/header") for name in parts)
        assert not any("comments" in name for name in parts)
    with pytest.raises(MotivationError, match="already exists"):
        render_docx(brief, PARAGRAPHS, destination)


def test_reviewed_draft_writes_docx_and_private_audit(tmp_path, monkeypatch):
    pytest.importorskip("docx")
    monkeypatch.setattr("aihawk.academic_motivation.cv_text", lambda _: "Movement measurements from research laboratory.")
    brief_file = make_brief(tmp_path)
    draft_file = tmp_path / "reviewed-draft.json"
    draft_file.write_text(json.dumps({"paragraphs": PARAGRAPHS}), encoding="utf-8")
    target = tmp_path / "motivation-letter.docx"
    assert deliver(brief_file, target, draft_path=draft_file) == target
    audit = json.loads(target.with_suffix(".review.json").read_text(encoding="utf-8"))
    assert audit["review_status"] == "DRAFT_REQUIRES_APPLICANT_APPROVAL"
    assert audit["university_submitted"] is False
    assert audit["model_generation"] == "reviewed_existing_draft"
    assert audit["word_count"] >= 300
    assert "resume" not in target.name


def test_reviewed_draft_cannot_be_loaded_from_external_directory(tmp_path):
    brief = make_brief(tmp_path)
    external = tmp_path.parent / "candidate.json"
    external.write_text(json.dumps({"paragraphs": PARAGRAPHS}), encoding="utf-8")
    with pytest.raises(MotivationError, match="private"):
        deliver(brief, tmp_path / "letter.docx", draft_path=external)
