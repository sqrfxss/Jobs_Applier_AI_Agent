"""Test every executable form-preparation boundary without a live university."""
from __future__ import annotations

from pathlib import Path

import pytest
from aihawk.academic_browser import (
    PortalPreparationError,
    PreparationNetworkGuard,
    plan_from_manifest,
    prepare_fields,
    verified_portal_host,
)


class Locator:
    def __init__(self, *, tag="input", field_type="text", visible=True, enabled=True, count=1):
        self.tag = tag
        self.field_type = field_type
        self.visible = visible
        self.enabled = enabled
        self.matches = count
        self.calls = []
        self.value = None
        self.upload_name = None

    def count(self): return self.matches
    def is_visible(self): return self.visible
    def is_enabled(self): return self.enabled
    def evaluate(self, expression):
        if expression == "(element) => element.tagName.toLowerCase()":
            return self.tag
        if "element.files" in expression:
            return [self.upload_name] if self.upload_name else []
        raise AssertionError(f"Unexpected DOM evaluation: {expression}")
    def get_attribute(self, name):
        return self.field_type if name == "type" else None
    def fill(self, value, **kwargs):
        self.value = value
        self.calls.append(("fill", value))
    def select_option(self, **kwargs):
        self.value = kwargs["value"]
        self.calls.append(("select", kwargs["value"]))
    def set_input_files(self, path, **kwargs):
        self.upload_name = Path(path).name
        self.calls.append(("upload", path))
    def input_value(self, **kwargs):
        return self.value


class Page:
    def __init__(self, locators):
        self.url = "https://applications.uni.example.edu/apply"
        self.locators = locators
        self.other_actions = []

    def locator(self, selector):
        return self.locators[selector]


def document():
    return {
        "title": "Example University MSc",
        "official_application_url": "https://applications.uni.example.edu/apply",
        "official_hosts": ["uni.example.edu"],
        "applicant_id": "candidate-test",
        "fields": {"full_name": "Example Person", "programme": "MSc"},
        "attachments": ["cv.pdf"],
        "portal_bindings": [
            {"field": "full_name", "selector": "#name", "kind": "text"},
            {"field": "programme", "selector": "#programme", "kind": "select"},
            {"field": "cv.pdf", "selector": "#cv", "kind": "upload"},
        ],
    }


def plan(tmp_path):
    (tmp_path / "cv.pdf").write_bytes(b"test-only CV")
    return plan_from_manifest(document(), manifest_dir=tmp_path)


def test_preparation_only_fills_explicitly_mapped_fields(tmp_path):
    p = plan(tmp_path)
    inputs = {"#name": Locator(), "#programme": Locator(tag="select"), "#cv": Locator(field_type="file")}
    page = Page(inputs)
    result = prepare_fields(page, p)
    assert result == ("full_name", "programme", "cv.pdf")
    assert inputs["#name"].calls == [("fill", "Example Person")]
    assert inputs["#programme"].calls == [("select", "MSc")]
    assert inputs["#cv"].calls[0][0] == "upload"
    assert Path(inputs["#cv"].calls[0][1]).name == "cv.pdf"
    assert page.other_actions == []


@pytest.mark.parametrize("url", (
    "https://uni.example.edu.attacker.test/apply",
    "http://applications.uni.example.edu/apply",
    "https://localhost/apply",
    "https://127.0.0.1/apply",
    "https://uni.example.edu:1234/apply",
))
def test_rejects_untrusted_portal_targets(url):
    with pytest.raises(PortalPreparationError):
        verified_portal_host(url, ("uni.example.edu",))


def test_rejects_selector_duplicates(tmp_path):
    data = document()
    data["portal_bindings"][1]["selector"] = "#name"
    (tmp_path / "cv.pdf").write_bytes(b"file")
    with pytest.raises(PortalPreparationError, match="unique"):
        plan_from_manifest(data, manifest_dir=tmp_path)


def test_rejects_unknown_or_inferred_values(tmp_path):
    data = document()
    data["portal_bindings"][0]["field"] = "birthdate"
    (tmp_path / "cv.pdf").write_bytes(b"file")
    with pytest.raises(PortalPreparationError, match="Missing reviewed"):
        plan_from_manifest(data, manifest_dir=tmp_path)


@pytest.mark.parametrize("tag,kind,field_type", [
    ("button", "text", "submit"),
    ("input", "text", "hidden"),
    ("input", "text", "password"),
    ("input", "select", "text"),
    ("textarea", "upload", "text"),
])
def test_refuses_unsafe_element_types(tmp_path, tag, kind, field_type):
    data = document()
    data["portal_bindings"] = [{"field": "cv.pdf" if kind == "upload" else "full_name", "selector": "#name", "kind": kind}]
    (tmp_path / "cv.pdf").write_bytes(b"file")
    p = plan_from_manifest(data, manifest_dir=tmp_path)
    page = Page({"#name": Locator(tag=tag, field_type=field_type)})
    with pytest.raises(PortalPreparationError):
        prepare_fields(page, p)


def test_ambiguous_locator_rejected(tmp_path):
    p = plan(tmp_path)
    page = Page({"#name": Locator(count=2)})
    with pytest.raises(PortalPreparationError, match="ambiguous"):
        prepare_fields(page, p)


class FakeRoute:
    def __init__(self):
        self.calls = []
        self.request = object()

    def abort(self): self.calls.append("abort")
    def continue_(self): self.calls.append("continue")


def test_guard_denies_every_network_request_during_fill():
    guard = PreparationNetworkGuard(("uni.example.edu",))
    route = FakeRoute()
    guard(route)
    assert route.calls == ["abort"]
    assert guard.blocked_requests == 1


def test_no_bindings_denied(tmp_path):
    (tmp_path / "cv.pdf").write_bytes(b"file")
    payload = document()
    payload["portal_bindings"] = []
    with pytest.raises(PortalPreparationError, match="nonempty"):
        plan_from_manifest(payload, manifest_dir=tmp_path)

def test_mapping_edit_invalidates_approval_fingerprint(tmp_path):
    original = plan(tmp_path)
    altered = document()
    altered["portal_bindings"][0]["selector"] = "input[name='legal_name']"
    changed = plan_from_manifest(altered, manifest_dir=tmp_path)
    assert original.preview.fingerprint() == changed.preview.fingerprint()
    assert original.fingerprint() != changed.fingerprint()
