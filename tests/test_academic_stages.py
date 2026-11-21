"""Multi-page portal plans must fail closed on wrong URLs, values and mappings."""

from __future__ import annotations

import json

import pytest

from aihawk.academic_browser import PortalPreparationError
from aihawk.academic_stages import (
    journey_from_manifest,
    prepare_stage,
    verify_stage_location,
)


def manifest():
    return {
        "title": "Example university MSc",
        "official_application_url": "https://admissions.uni.example.edu/apply",
        "official_hosts": ["uni.example.edu"],
        "applicant_id": "local-only",
        "fields": {"legal_name": "Test Applicant", "degree": "MSc", "city": "Example"},
        "attachments": [],
        "portal_stages": [
            {
                "name": "Personal details",
                "expected_host": "admissions.uni.example.edu",
                "expected_path": "/apply",
                "bindings": [{"field": "legal_name", "selector": "#name", "kind": "text"}],
            },
            {
                "name": "Programme choice",
                "expected_host": "admissions.uni.example.edu",
                "expected_path": "/apply/degree",
                "bindings": [{"field": "degree", "selector": "#degree", "kind": "select"}],
            },
        ],
    }


class Locator:
    def __init__(self, tag="input"):
        self.tag = tag
        self.changes = []
        self.value = ""

    def count(self):
        return 1

    def is_visible(self):
        return True

    def is_enabled(self):
        return True

    def evaluate(self, expr):
        return self.tag

    def get_attribute(self, name):
        return "text"

    def fill(self, text, **_):
        self.value = text
        self.changes.append(("fill", text))

    def select_option(self, *, value, **_):
        self.value = value
        self.changes.append(("select", value))

    def input_value(self, **_):
        return self.value


class Page:
    def __init__(self, url):
        self.url = url
        self.name = Locator()
        self.degree = Locator("select")

    def locator(self, css):
        return {"#name": self.name, "#degree": self.degree}[css]


def test_builds_two_distinct_reviewed_stages(tmp_path):
    journey = journey_from_manifest(manifest(), manifest_dir=tmp_path)
    assert len(journey.stages) == 2
    assert journey.stages[0].fingerprint() != journey.stages[1].fingerprint()
    assert journey.fingerprint() != journey.stages[0].fingerprint()


def test_correct_page_only_fills_matching_stage(tmp_path):
    j = journey_from_manifest(manifest(), manifest_dir=tmp_path)
    page = Page("https://admissions.uni.example.edu/apply?session=untrusted")
    assert prepare_stage(page, j.stages[0], hosts=j.hosts) == ("legal_name",)
    assert page.name.changes == [("fill", "Test Applicant")]
    assert page.degree.changes == []
    page.url = "https://admissions.uni.example.edu/apply/degree"
    assert prepare_stage(page, j.stages[1], hosts=j.hosts) == ("degree",)
    assert page.degree.changes == [("select", "MSc")]


@pytest.mark.parametrize("url", [
    "https://uni.example.edu.evil.test/apply",
    "http://admissions.uni.example.edu/apply",
    "https://admissions.uni.example.edu/apply/degree",
    "https://admissions.uni.example.edu/apply-extra",
    "https://admissions.uni.example.edu/other",
])
def test_rejects_wrong_page_before_mutating_any_input(tmp_path, url):
    journey = journey_from_manifest(manifest(), manifest_dir=tmp_path)
    page = Page(url)
    with pytest.raises(PortalPreparationError):
        prepare_stage(page, journey.stages[0], hosts=journey.hosts)
    assert page.name.changes == []


@pytest.mark.parametrize("path", [
    "//attacker.test/path", "/apply?source=other", "relative/path", "/apply#stage", "",
])
def test_rejects_ambiguous_stage_paths(tmp_path, path):
    data = manifest()
    data["portal_stages"][1]["expected_path"] = path
    with pytest.raises(PortalPreparationError):
        journey_from_manifest(data, manifest_dir=tmp_path)


def test_rejects_duplicate_stage_name(tmp_path):
    data = manifest()
    data["portal_stages"][1]["name"] = data["portal_stages"][0]["name"]
    with pytest.raises(PortalPreparationError):
        journey_from_manifest(data, manifest_dir=tmp_path)


def test_disallows_legacy_mapping_mixed_with_stage_plan(tmp_path):
    data = manifest()
    data["portal_bindings"] = [{"field": "city", "selector": "#city", "kind": "text"}]
    with pytest.raises(PortalPreparationError, match="never both"):
        journey_from_manifest(data, manifest_dir=tmp_path)


def test_changed_step_route_or_mapping_invalidates_journey_digest(tmp_path):
    j = journey_from_manifest(manifest(), manifest_dir=tmp_path)
    data = manifest()
    data["portal_stages"][1]["expected_path"] = "/apply/program"
    changed = journey_from_manifest(data, manifest_dir=tmp_path)
    assert j.fingerprint() != changed.fingerprint()
    data = manifest()
    data["portal_stages"][1]["bindings"][0]["selector"] = "#program-new"
    changed = journey_from_manifest(data, manifest_dir=tmp_path)
    assert j.fingerprint() != changed.fingerprint()


def test_stage_location_must_match_exact_path(tmp_path):
    journey = journey_from_manifest(manifest(), manifest_dir=tmp_path)
    verify_stage_location("https://admissions.uni.example.edu/apply/degree?auth=opaque", journey.stages[1], journey.hosts)
    with pytest.raises(PortalPreparationError, match="Wrong portal page"):
        verify_stage_location("https://admissions.uni.example.edu/apply/degree/edit", journey.stages[1], journey.hosts)


def test_terminal_execution_must_be_interactive(tmp_path, monkeypatch):
    import sys

    from aihawk.academic_stages import run_interactive_journey

    monkeypatch.setattr(sys, "stdin", type("NoTTY", (), {"isatty": lambda self: False})())
    with pytest.raises(PortalPreparationError, match="interactive"):
        run_interactive_journey(tmp_path / "missing.json")


def test_multistage_review_html_includes_every_stage_and_fingerprint(tmp_path):
    from aihawk.academic_ops import main

    manifest_path = tmp_path / "application.json"
    output_path = tmp_path / "review.html"
    manifest_path.write_text(json.dumps(manifest()), encoding="utf-8")
    assert main(["preview", str(manifest_path), str(output_path)]) == 0
    body = output_path.read_text(encoding="utf-8")
    journey = journey_from_manifest(manifest(), manifest_dir=tmp_path)
    assert journey.fingerprint() in body
    assert "Personal details [admissions.uni.example.edu/apply]" in body
    assert "Programme choice [admissions.uni.example.edu/apply/degree]" in body
    assert "form-action 'none'" in body


def test_page_change_during_field_preparation_is_detected(tmp_path):
    journey = journey_from_manifest(manifest(), manifest_dir=tmp_path)
    page = Page("https://admissions.uni.example.edu/apply")
    original_fill = page.name.fill

    def deceptive_fill(value, **kwargs):
        original_fill(value, **kwargs)
        page.url = "https://admissions.uni.example.edu/apply/degree"

    page.name.fill = deceptive_fill
    with pytest.raises(PortalPreparationError, match="Wrong portal page"):
        prepare_stage(page, journey.stages[0], hosts=journey.hosts)


def test_cli_disallows_multi_step_without_real_human_terminal(tmp_path, monkeypatch):
    import sys

    from aihawk.academic_ops import main

    monkeypatch.setattr(sys, "stdin", type("NoTTY", (), {"isatty": lambda self: False})())
    with pytest.raises(PortalPreparationError, match="interactive"):
        main(["autofill-stages", str(tmp_path / "not-read.json")])
