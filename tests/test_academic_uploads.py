"""File-upload safety and idempotence checks; no university contacted."""
from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest

from aihawk.academic_browser import PortalPreparationError
from aihawk.academic_uploads import (
    UploadNetworkGuard,
    receipt_present,
    run_interactive_uploads,
    upload_plan_from_manifest,
)


def manifest():
    return {
        "title": "Synthetic MSc admission",
        "official_application_url": "https://admissions.uni.example.edu/apply",
        "official_hosts": ["uni.example.edu"],
        "applicant_id": "offline",
        "fields": {},
        "attachments": ["proof.pdf"],
        "portal_uploads": [{
            "field": "proof.pdf",
            "input_selector": "#proof",
            "upload_button_selector": "#proof-upload",
            "container_selector": "#proof-section",
            "receipt_selector": ".file a",
            "remove_selector": "button.remove",
            "expected_path": "/apply",
            "upload_endpoint_path": "/file/ajax",
        }],
    }


def build(tmp_path):
    (tmp_path / "proof.pdf").write_bytes(b"%PDF-1.4 fake")
    return upload_plan_from_manifest(manifest(), manifest_dir=tmp_path)


def test_manifest_fingerprint_changes_with_attachment_bytes(tmp_path):
    a = build(tmp_path)
    digest = a.fingerprint()
    (tmp_path / "proof.pdf").write_bytes(b"%PDF-1.4 a DIFFERENT file")
    b = upload_plan_from_manifest(manifest(), manifest_dir=tmp_path)
    assert b.fingerprint() != digest


def test_plan_rejects_duplicate_upload_fields(tmp_path):
    data = manifest()
    data["portal_uploads"].append(dict(data["portal_uploads"][0]))
    (tmp_path / "proof.pdf").write_bytes(b"%PDF-1.4")
    with pytest.raises(PortalPreparationError, match="twice"):
        upload_plan_from_manifest(data, manifest_dir=tmp_path)


def test_plan_rejects_nonlisted_file(tmp_path):
    data = manifest()
    data["portal_uploads"][0]["field"] = "private.pdf"
    (tmp_path / "proof.pdf").write_bytes(b"%PDF-1.4")
    with pytest.raises(PortalPreparationError, match="outside"):
        upload_plan_from_manifest(data, manifest_dir=tmp_path)


@pytest.mark.parametrize("path", ["//other", "/upload?token=abc", "relative", "/route#fragment", "/route\nother"])
def test_rejects_ambiguous_upload_endpoints(tmp_path, path):
    data = manifest()
    data["portal_uploads"][0]["upload_endpoint_path"] = path
    (tmp_path / "proof.pdf").write_bytes(b"%PDF-1.4")
    with pytest.raises(PortalPreparationError, match="path"):
        upload_plan_from_manifest(data, manifest_dir=tmp_path)


class Route:
    def __init__(self, method, url, resource_type):
        self.request = SimpleNamespace(method=method, url=url, resource_type=resource_type)
        self.record = []

    def fallback(self):
        self.record.append("allow")

    def abort(self):
        self.record.append("block")


@pytest.mark.parametrize("method,url,resource,allowed", [
    ("POST", "https://admissions.uni.example.edu/file/ajax", "xhr", True),
    ("POST", "https://admissions.uni.example.edu/file/ajax", "fetch", True),
    ("GET", "https://admissions.uni.example.edu/file/ajax", "xhr", False),
    ("POST", "https://admissions.uni.example.edu/submit", "xhr", False),
    ("POST", "https://evil.test/file/ajax", "fetch", False),
    ("POST", "http://admissions.uni.example.edu/file/ajax", "xhr", False),
    ("POST", "https://admissions.uni.example.edu/file/ajax/extra", "xhr", False),
    ("POST", "https://admissions.uni.example.edu/file/ajax", "document", False),
])
def test_network_guard_is_exact_host_method_path_and_xhr_only(tmp_path, method, url, resource, allowed):
    plan = build(tmp_path)
    page = SimpleNamespace(url=plan.application_url)
    guard = UploadNetworkGuard(page, plan.bindings[0], plan.hosts)
    route = Route(method, url, resource)
    guard(route)
    assert route.record == (["allow"] if allowed else ["block"])


class FakeLinks:
    def __init__(self, text, count):
        self.text = text
        self.number = count

    def all_text_contents(self):
        return self.text

    def count(self):
        return self.number


class FakeContainer:
    def __init__(self, links, remove):
        self.links = FakeLinks(links, 0)
        self.remove = FakeLinks([], remove)

    def locator(self, selector):
        return self.remove if selector == "button.remove" else self.links


def test_receipt_requires_exact_server_filename_and_remove_control(tmp_path):
    mapping = build(tmp_path).bindings[0]
    assert receipt_present(FakeContainer(["proof.pdf"], 1), mapping, "proof.pdf")
    assert not receipt_present(FakeContainer(["other.pdf"], 1), mapping, "proof.pdf")
    assert not receipt_present(FakeContainer(["proof.pdf"], 0), mapping, "proof.pdf")
    assert not receipt_present(FakeContainer(["proof.pdf"], 2), mapping, "proof.pdf")


def test_upload_command_refuses_noninteractive_execution(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "stdin", type("NoTTY", (), {"isatty": lambda self: False})())
    with pytest.raises(PortalPreparationError, match="interactive"):
        run_interactive_uploads(tmp_path / "missing.json")
