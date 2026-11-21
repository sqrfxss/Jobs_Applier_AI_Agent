"""Reviewed, idempotent academic file uploads with real server-side receipts.

Unlike selecting a file input, a completed upload requires an exact file link
AND a matching removal control inside the same approved field container.
All browser activity happens in one isolated persistent Playwright context.
This module never clicks final Submit, Save, consent or referee invitations.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from aihawk.academic_browser import PortalPreparationError, verified_portal_host
from aihawk.academic_browser_session import launch_academic_context, official_session_page
from aihawk.academic_ops import _hash_file, application_from_manifest


@dataclass(frozen=True)
class UploadMapping:
    field: str
    input_selector: str
    upload_button_selector: str
    container_selector: str
    receipt_selector: str
    remove_selector: str
    expected_path: str
    upload_endpoint_path: str

    def __post_init__(self) -> None:
        if not self.field or not self.expected_path.startswith("/") or not self.upload_endpoint_path.startswith("/"):
            raise PortalPreparationError("Each upload needs an approved attachment and exact HTTPS paths.")
        for path in (self.expected_path, self.upload_endpoint_path):
            if path.startswith("//") or any(ch in path for ch in ("?", "#", "\r", "\n")) or len(path) > 500:
                raise PortalPreparationError("Upload path must be an exact absolute path.")
        selectors = (
            self.input_selector, self.upload_button_selector, self.container_selector,
            self.receipt_selector, self.remove_selector,
        )
        if any(not isinstance(value, str) or not value.strip() or len(value) > 300 for value in selectors):
            raise PortalPreparationError("Invalid or missing reviewed file upload selectors.")


@dataclass(frozen=True)
class UploadPlan:
    title: str
    application_url: str
    hosts: tuple[str, ...]
    bindings: tuple[UploadMapping, ...]
    attachments: tuple[tuple[str, Path, str], ...]

    def fingerprint(self) -> str:
        data = {
            "url": self.application_url, "hosts": self.hosts,
            "bindings": [item.__dict__ for item in self.bindings],
            "files": [(name, digest) for name, _, digest in self.attachments],
        }
        return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    def file_for(self, name: str) -> tuple[Path, str]:
        for filename, path, digest in self.attachments:
            if filename == name:
                return path, digest
        raise PortalPreparationError("Unreviewed attachment field.")


def upload_plan_from_manifest(data: dict[str, Any], *, manifest_dir: Path) -> UploadPlan:
    preview, title, hosts, _ = application_from_manifest(data, manifest_dir=manifest_dir)
    verified_portal_host(preview.opportunity_url, hosts)
    steps = data.get("portal_uploads")
    if not isinstance(steps, list) or not 1 <= len(steps) <= 20:
        raise PortalPreparationError("One to twenty explicit portal_uploads mappings are required.")
    bindings = tuple(UploadMapping(**step) for step in steps)
    names = [mapping.field for mapping in bindings]
    if len(names) != len(set(names)):
        raise PortalPreparationError("The same file cannot be uploaded twice in one plan.")
    files = data.get("attachments", [])
    if any(name not in files for name in names):
        raise PortalPreparationError("An upload mapping references a file outside the approved manifest.")
    root = manifest_dir.resolve(strict=True)
    attachments = tuple(
        (name, (root / name).resolve(), digest)
        for name, digest in zip(files, preview.attachment_hashes, strict=True)
    )
    for _, path, _ in attachments:
        if not path.is_relative_to(root):
            raise PortalPreparationError("Approved upload escapes the private application folder.")
    return UploadPlan(title, preview.opportunity_url, hosts, bindings, attachments)


def _verify_file(path: Path, expected_digest: str) -> None:
    try:
        actual = _hash_file(path)
    except OSError as error:
        raise PortalPreparationError("Approved file is missing or cannot be opened.") from error
    if actual != expected_digest:
        raise PortalPreparationError("Approved file changed after review. Stop and approve a new plan.")


def _require_page(page: Any, plan: UploadPlan, mapping: UploadMapping) -> None:
    verified_portal_host(page.url, plan.hosts)
    target = urlsplit(plan.application_url)
    current = urlsplit(page.url)
    if current.hostname != target.hostname or current.path != mapping.expected_path:
        raise PortalPreparationError("Wrong portal page for this approved upload; nothing changed.")


def receipt_present(container: Any, mapping: UploadMapping, filename: str) -> bool:
    """Require a server file link AND a Remove action, not a selected local file."""
    receipts = container.locator(mapping.receipt_selector)
    links = [name.strip() for name in receipts.all_text_contents()]
    remove = container.locator(mapping.remove_selector).count()
    return filename in links and remove == 1


class UploadNetworkGuard:
    """Permit only the exact reviewed AJAX upload POST; abort other requests."""

    def __init__(self, page: Any, mapping: UploadMapping, hosts: tuple[str, ...]) -> None:
        self.page = page
        self.mapping = mapping
        self.hosts = hosts
        self.allowed = 0
        self.blocked = 0

    def __call__(self, route: Any) -> None:
        request = route.request
        url = urlsplit(request.url)
        allowed = (
            request.method.upper() == "POST"
            and request.resource_type in ("xhr", "fetch")
            and url.path == self.mapping.upload_endpoint_path
            and url.hostname == urlsplit(self.page.url).hostname
            and url.scheme == "https"
        )
        if allowed:
            try:
                verified_portal_host(request.url, self.hosts)
            except PortalPreparationError:
                allowed = False
        if allowed:
            self.allowed += 1
            route.fallback()
        else:
            self.blocked += 1
            route.abort()


def upload_one(page: Any, context: Any, plan: UploadPlan, mapping: UploadMapping, *, timeout_ms: int = 12_000) -> str:
    """Upload at most once. Never retry uncertain transfers or invoke file pickers."""
    _require_page(page, plan, mapping)
    path, digest = plan.file_for(mapping.field)
    _verify_file(path, digest)
    container = page.locator(mapping.container_selector)
    if container.count() != 1:
        raise PortalPreparationError("File upload container is missing or ambiguous.")
    if receipt_present(container, mapping, path.name):
        return "already_uploaded"
    # Other existing filenames require manual review; never overwrite silently.
    existing = [name.strip() for name in container.locator(mapping.receipt_selector).all_text_contents() if name.strip()]
    if existing:
        raise PortalPreparationError("Another document is already uploaded in this field.")
    control = container.locator(mapping.input_selector)
    button = container.locator(mapping.upload_button_selector)
    if control.count() != 1 or button.count() != 1:
        raise PortalPreparationError("File input or its dedicated Upload button is missing/ambiguous.")
    if control.evaluate("(e) => e.tagName.toLowerCase()") != "input" or control.get_attribute("type") != "file":
        raise PortalPreparationError("Mapped upload control is not an HTML file input.")
    if not control.is_enabled() or not button.is_enabled():
        raise PortalPreparationError("Upload controls are disabled.")
    caption = button.evaluate("(e) => (e.value || e.textContent || '').trim()")
    if caption != "Upload":
        raise PortalPreparationError("Upload button did not match the reviewed action.")
    existing_selected = control.evaluate("(e) => [...e.files].map(f => f.name)")
    if existing_selected and existing_selected != [path.name]:
        raise PortalPreparationError("A different file is selected; refusing to overwrite it.")
    if not existing_selected:
        control.set_input_files(str(path), timeout=5_000)
    if control.evaluate("(e) => [...e.files].map(f => f.name)") != [path.name]:
        raise PortalPreparationError("Browser file-selection readback failed.")
    _verify_file(path, digest)
    _require_page(page, plan, mapping)
    guard = UploadNetworkGuard(page, mapping, plan.hosts)
    chooser_events: list[Any] = []
    def on_chooser(chooser: Any) -> None:
        chooser_events.append(chooser)
    page.on("filechooser", on_chooser)
    context.route("**/*", guard)
    try:
        if not button.is_visible():
            raise PortalPreparationError("Upload button is not visible; expand its approved section first.")
        button.click(timeout=5_000)
        end = time.monotonic() + timeout_ms / 1000
        while time.monotonic() < end:
            if receipt_present(container, mapping, path.name):
                if chooser_events:
                    raise PortalPreparationError("Unexpected file chooser opened.")
                _require_page(page, plan, mapping)
                return "uploaded"
            page.wait_for_timeout(200)
        raise PortalPreparationError("Upload result is unverified. Do not retry until server state is checked.")
    finally:
        context.unroute("**/*", guard)
        page.remove_listener("filechooser", on_chooser)


def run_interactive_uploads(manifest: Path, *, prompt=input) -> int:
    """One typed approval and one private browser context for the full batch."""
    if not sys.stdin.isatty():
        raise PortalPreparationError("Uploading requires an interactive terminal and explicit approval.")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    plan = upload_plan_from_manifest(data, manifest_dir=manifest.parent)
    challenge = "UPLOAD " + plan.fingerprint()[-12:]
    if prompt(f"After reviewing every upload mapping, type {challenge}: ") != challenge:
        return 1
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise PortalPreparationError("Install Playwright to upload with no native file pickers.") from error
    with sync_playwright() as playwright:
        context = launch_academic_context(playwright, manifest_dir=manifest.parent)
        try:
            page = official_session_page(context, url=plan.application_url, official_hosts=plan.hosts)
            prompt("If the university requires sign-in, complete it once, navigate to the upload form, and press Enter: ")
            for step in plan.bindings:
                print("Upload: " + step.field)
                try:
                    status = upload_one(page, context, plan, step)
                except PortalPreparationError:
                    print("Stopped. The upload is NOT confirmed; check the university receipt before retrying.")
                    raise
                print("University receipt status: " + status)
            print("All mapped uploads have been confirmed in their individual university fields.")
            print("No final application, referee invitation or consent was submitted.")
            prompt("Press Enter when finished reviewing the university browser: ")
            return 0
        finally:
            context.close()
