"""File-upload safety and idempotence checks; no university contacted."""

from __future__ import annotations

import sys
from dataclasses import replace
from types import SimpleNamespace

import pytest

from aihawk.academic_browser import PortalPreparationError
from aihawk.academic_uploads import (
    UploadNetworkGuard,
    _verify_file,
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
        "portal_uploads": [
            {
                "field": "proof.pdf",
                "input_selector": "#proof",
                "upload_button_selector": "#proof-upload",
                "container_selector": "#proof-section",
                "receipt_selector": ".file a",
                "remove_selector": "button.remove",
                "expected_path": "/apply",
                "upload_endpoint_path": "/file/ajax",
            }
        ],
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


@pytest.mark.parametrize(
    "method,url,resource,allowed",
    [
        ("POST", "https://admissions.uni.example.edu/file/ajax", "xhr", True),
        ("POST", "https://admissions.uni.example.edu/file/ajax", "fetch", True),
        ("GET", "https://admissions.uni.example.edu/file/ajax", "xhr", False),
        ("POST", "https://admissions.uni.example.edu/submit", "xhr", False),
        ("POST", "https://evil.test/file/ajax", "fetch", False),
        ("POST", "http://admissions.uni.example.edu/file/ajax", "xhr", False),
        ("POST", "https://admissions.uni.example.edu/file/ajax/extra", "xhr", False),
        ("POST", "https://admissions.uni.example.edu/file/ajax", "document", False),
    ],
)
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


def test_multiple_upload_receipts_have_matching_remove_controls(tmp_path):
    mapping = replace(build(tmp_path).bindings[0], expected_existing_files=("original.pdf",))
    assert receipt_present(FakeContainer(["original.pdf", "proof.pdf"], 2), mapping, "proof.pdf")
    assert not receipt_present(FakeContainer(["original.pdf", "proof.pdf"], 1), mapping, "proof.pdf")
    assert not receipt_present(FakeContainer(["original.pdf", "proof.pdf"], 3), mapping, "proof.pdf")
    assert not receipt_present(FakeContainer(["proof.pdf"], 1), mapping, "proof.pdf")
    assert not receipt_present(FakeContainer(["original.pdf", "proof.pdf", "unreviewed.pdf"], 3), mapping, "proof.pdf")


def test_prior_files_require_explicit_manifest_approval(tmp_path):
    data = manifest()
    data["portal_uploads"][0]["expected_existing_files"] = ["original.pdf"]
    (tmp_path / "proof.pdf").write_bytes(b"%PDF-1.4")
    with pytest.raises(PortalPreparationError, match="Previously approved"):
        upload_plan_from_manifest(data, manifest_dir=tmp_path)

    data["attachments"].append("original.pdf")
    (tmp_path / "original.pdf").write_bytes(b"%PDF-1.4 original")
    plan = upload_plan_from_manifest(data, manifest_dir=tmp_path)
    assert plan.bindings[0].expected_existing_files == ("original.pdf",)


@pytest.mark.parametrize(
    "prior",
    [
        ["../unsafe.pdf"],
        ["other.pdf", "other.pdf"],
        ["proof.pdf"],
    ],
)
def test_prior_file_names_reject_traversal_duplicates_and_self_reference(tmp_path, prior):
    data = manifest()
    data["portal_uploads"][0]["expected_existing_files"] = prior
    (tmp_path / "proof.pdf").write_bytes(b"%PDF-1.4")
    with pytest.raises(PortalPreparationError):
        upload_plan_from_manifest(data, manifest_dir=tmp_path)


def test_bmai_rejects_docx_before_attempting_pdf_only_field(tmp_path):
    data = manifest()
    data["attachments"] = ["motivation.docx"]
    data["portal_uploads"][0]["field"] = "motivation.docx"
    data["portal_uploads"][0]["allowed_extensions"] = ["txt", "doc", "pptx", "pdf", "jpg", "jpeg", "png"]
    (tmp_path / "motivation.docx").write_bytes(b"PK synthetic Word")
    with pytest.raises(PortalPreparationError, match="extension"):
        upload_plan_from_manifest(data, manifest_dir=tmp_path)


def test_bmai_allows_pdf_after_conversion_with_valid_bytes(tmp_path):
    data = manifest()
    data["portal_uploads"][0]["allowed_extensions"] = [".PDF", ".JPG"]
    (tmp_path / "proof.pdf").write_bytes(b"%PDF-1.4 valid-synthetic")
    plan = upload_plan_from_manifest(data, manifest_dir=tmp_path)
    assert plan.bindings[0].allowed_extensions == ("pdf", "jpg")
    _verify_file(plan.attachments[0][1], plan.attachments[0][2], allowed_extensions=("pdf",))


def test_renamed_word_document_is_not_mistaken_for_pdf(tmp_path):
    data = manifest()
    data["portal_uploads"][0]["allowed_extensions"] = ["pdf"]
    (tmp_path / "proof.pdf").write_bytes(b"PK word document disguised as PDF")
    plan = upload_plan_from_manifest(data, manifest_dir=tmp_path)
    with pytest.raises(PortalPreparationError, match="signature"):
        _verify_file(plan.attachments[0][1], plan.attachments[0][2], allowed_extensions=("pdf",))


def test_exact_approved_server_renaming_is_supported(tmp_path):
    mapping = replace(build(tmp_path).bindings[0], receipt_filename="proof_lowercase.pdf")
    assert receipt_present(FakeContainer(["proof_lowercase.pdf"], 1), mapping, "proof.pdf")
    assert not receipt_present(FakeContainer(["proof.pdf"], 1), mapping, "proof.pdf")
    assert not receipt_present(FakeContainer(["proof_lowercase.pdf"], 0), mapping, "proof.pdf")


@pytest.mark.parametrize("receipt", ["../proof.pdf", "other/thing.pdf", "proof.docx", ""])
def test_unapproved_server_receipt_filename_fails_closed(tmp_path, receipt):
    data = manifest()
    data["portal_uploads"][0]["receipt_filename"] = receipt
    (tmp_path / "proof.pdf").write_bytes(b"%PDF-1.4 synthetic")
    with pytest.raises(PortalPreparationError, match="receipt"):
        upload_plan_from_manifest(data, manifest_dir=tmp_path)


@pytest.mark.parametrize("extensions", [["pdf", "pdf"], ["../pdf"], ["pdf;exe"], [""], [True]])
def test_malformed_extension_allowlist_fails_closed(tmp_path, extensions):
    data = manifest()
    data["portal_uploads"][0]["allowed_extensions"] = extensions
    (tmp_path / "proof.pdf").write_bytes(b"%PDF-1.4 synthetic")
    with pytest.raises(PortalPreparationError, match="allowlist"):
        upload_plan_from_manifest(data, manifest_dir=tmp_path)
