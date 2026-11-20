"""Constrained university form preparation; never invokes a submit action.

The form mapping is explicit and provided by the operator. The only permitted
DOM mutations are text/select/file-input changes. During preparation, unsafe
network methods and all frame navigations are intercepted. This is defense in
depth, not a browser security boundary: an arbitrary site can have side effects
through GET or JavaScript, so final submission remains a *human* action.
"""

from __future__ import annotations

import hashlib
import ipaddress
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aihawk.academic_approval import ApplicationPreview
from aihawk.academic_ops import application_from_manifest
from aihawk.academic_sources import _host

TEXT_INPUT_TYPES = frozenset({"text", "email", "tel", "url", "number", "search", "date"})
BINDING_KINDS = frozenset({"text", "select", "upload"})


class PortalPreparationError(ValueError):
    """The portal or an element does not agree with the reviewed mapping."""


def verified_portal_host(url: str, hosts: tuple[str, ...]) -> str:
    """Reject credential-bearing, non-HTTPS, non-university and local targets."""
    try:
        host = _host(url)
    except (ValueError, TypeError) as error:
        raise PortalPreparationError("The portal requires an approved HTTPS URL.") from error
    if host in ("localhost", "localhost.localdomain") or host.endswith((".local", ".internal")) or "." not in host:
        raise PortalPreparationError("Local/intranet portal targets are not allowed.")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise PortalPreparationError("Literal IP addresses are not allowed.")
    normalized = tuple(h.casefold().rstrip(".") for h in hosts if isinstance(h, str) and h)
    if not normalized or not any(host == h or host.endswith("." + h) for h in normalized):
        raise PortalPreparationError("Portal URL is not on the explicitly approved institutional host list.")
    return host


@dataclass(frozen=True)
class Binding:
    """A single inspected form field; never a button or consent checkbox."""

    field: str
    selector: str
    kind: str

    def __post_init__(self) -> None:
        if not self.field or not self.selector.strip() or self.kind not in BINDING_KINDS:
            raise PortalPreparationError("Each mapping needs a field, selector and supported kind.")
        if len(self.selector) > 300 or "\n" in self.selector or "\r" in self.selector:
            raise PortalPreparationError("Invalid/oversized CSS selector.")


@dataclass(frozen=True)
class FormPlan:
    preview: ApplicationPreview
    title: str
    hosts: tuple[str, ...]
    bindings: tuple[Binding, ...]
    file_paths: tuple[tuple[str, Path], ...]

    def file_for(self, name: str) -> Path:
        return dict(self.file_paths)[name]

    def fingerprint(self) -> str:
        """Bind approval to both reviewed facts AND exact selectors/actions."""
        payload = {
            "reviewed_content": self.preview.fingerprint(),
            "mappings": [{"field": item.field, "selector": item.selector, "kind": item.kind} for item in self.bindings],
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def plan_from_manifest(data: dict[str, Any], *, manifest_dir: Path) -> FormPlan:
    preview, title, hosts, _ = application_from_manifest(data, manifest_dir=manifest_dir)
    verified_portal_host(preview.opportunity_url, hosts)
    entries = data.get("portal_bindings", ())
    if not isinstance(entries, list) or not entries:
        raise PortalPreparationError("An explicit, nonempty portal_bindings mapping is required.")
    bindings = tuple(Binding(**entry) for entry in entries)
    if len({item.selector for item in bindings}) != len(bindings):
        raise PortalPreparationError("Each portal selector must be unique.")
    fields = dict(preview.fields)
    attached = data.get("attachments", [])
    root = manifest_dir.resolve()
    file_paths = tuple((name, (root / name).resolve()) for name in attached)
    if any(not path.is_relative_to(root) for _, path in file_paths):
        raise PortalPreparationError("Attachment path escapes the private manifest directory.")
    for item in bindings:
        if item.kind == "upload":
            if item.field not in attached:
                raise PortalPreparationError(f"Upload not listed in the manifest: {item.field}")
        elif item.field not in fields:
            raise PortalPreparationError(f"Missing reviewed value for field: {item.field}")
    return FormPlan(preview, title, hosts, bindings, file_paths)


def prepare_fields(page: Any, plan: FormPlan) -> tuple[str, ...]:
    """Fill only reviewed values via typed Playwright locators; NO click or press."""
    verified_portal_host(page.url, plan.hosts)
    fields = dict(plan.preview.fields)
    completed: list[str] = []
    for binding in plan.bindings:
        try:
            node = page.locator(binding.selector)
            if node.count() != 1 or not node.is_visible() or not node.is_enabled():
                raise PortalPreparationError(f"Missing, ambiguous or unavailable control: {binding.field}")
            tag = str(node.evaluate("(element) => element.tagName.toLowerCase()")).lower()
            control_type = (node.get_attribute("type") or "text").lower()
            if binding.kind == "text":
                if not (tag == "textarea" or (tag == "input" and control_type in TEXT_INPUT_TYPES)):
                    raise PortalPreparationError(f"Unsafe control type for: {binding.field}")
                node.fill(fields[binding.field], timeout=5000)
                if node.input_value(timeout=5000) != fields[binding.field]:
                    raise PortalPreparationError(f"Browser readback did not match: {binding.field}")
            elif binding.kind == "select":
                if tag != "select":
                    raise PortalPreparationError(f"Expected an HTML select: {binding.field}")
                node.select_option(value=fields[binding.field], timeout=5000)
                if node.input_value(timeout=5000) != fields[binding.field]:
                    raise PortalPreparationError(f"Browser selection did not match: {binding.field}")
            else:
                if tag != "input" or control_type != "file":
                    raise PortalPreparationError(f"Expected a file input: {binding.field}")
                node.set_input_files(str(plan.file_for(binding.field)), timeout=5000)
                names = node.evaluate("(element) => Array.from(element.files ?? []).map(file => file.name)")
                if names != [plan.file_for(binding.field).name]:
                    raise PortalPreparationError(f"File upload readback did not match: {binding.field}")
            completed.append(binding.field)
            verified_portal_host(page.url, plan.hosts)
        except PortalPreparationError:
            raise
        except Exception as error:
            raise PortalPreparationError(f"Form field could not be prepared: {binding.field}") from error
    return tuple(completed)


class PreparationNetworkGuard:
    """Request interceptor for the *preparation phase only*; default deny writes.

    Install with BrowserContext.route AFTER the human has finished any login.
    Do not treat this as a substitute for OS-level egress isolation.
    """

    def __init__(self, hosts: tuple[str, ...]) -> None:
        self.hosts = hosts
        self.blocked_requests = 0

    def should_block(self, request: Any) -> bool:
        # The page was loaded and any interactive login completed BEFORE this
        # guard is installed. During deterministic field preparation, NO network
        # traffic is necessary. Denying GET as well as POST prevents common
        # on-change uploads, analytics and GET-form submissions. This does not
        # retroactively close pre-existing WebSockets, so do not treat it as a
        # sandbox for hostile sites.
        return True

    def __call__(self, route: Any) -> None:
        if self.should_block(route.request):
            self.blocked_requests += 1
            route.abort()
        else:
            route.continue_()


def run_interactive(manifest: Path, *, prompt=input) -> int:
    """Open a visible browser and prepare the operator-mapped fields.

    The user alone logs in and eventually submits. The browser session is
    closed on exit. The operator can decline at either typed checkpoint.
    """
    import sys

    if not sys.stdin.isatty():
        raise PortalPreparationError("An interactive terminal is mandatory for live form preparation.")
    plan = plan_from_manifest(json.loads(manifest.read_text(encoding="utf-8")), manifest_dir=manifest.parent)
    challenge = plan.fingerprint()[-12:]
    if prompt(f"Type PREPARE {challenge} after reviewing the local preview: ") != f"PREPARE {challenge}":
        return 1
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise PortalPreparationError("Install the optional dependency: pip install 'aihawk[academic-browser]'") from error

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context(service_workers="block", accept_downloads=False)
        page = context.new_page()
        try:
            page.goto(plan.preview.opportunity_url, wait_until="domcontentloaded", timeout=45000)
            print("If needed, sign in to the university portal manually. No credentials are entered by AIHawk.")
            prompt("Press Enter after reaching the intended form, or Ctrl+C to cancel: ")
            verified_portal_host(page.url, plan.hosts)
            guard = PreparationNetworkGuard(plan.hosts)
            context.route("**/*", guard)
            try:
                prepared = prepare_fields(page, plan)
            finally:
                # Keep the network guard active while the user reviews.
                pass
            print(f"Prepared {len(prepared)} mapped controls; blocked {guard.blocked_requests} network requests.")
            print("Review the open form. Unknown fields, consents and Submit must be completed by you.")
            if prompt(f"Type MANUAL {challenge} to release the browser for YOUR actions: ") != f"MANUAL {challenge}":
                return 1
            # No automated clicks occur after the guard is removed.
            context.unroute("**/*", guard)
            print("The browser is now fully under your manual control. AIHawk will not click Submit.")
            prompt("Press Enter after you have finished using this browser window: ")
            return 0
        finally:
            context.close()
            browser.close()
