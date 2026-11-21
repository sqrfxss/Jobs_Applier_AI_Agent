"""Explicit, human-driven university portal preparation across multiple pages.

The operator authenticates and navigates between stages. Each stage requires
an exact approved host/path and explicit selector mapping. No code clicks
Next, Save, Accept, Submit, or any other navigation/form button.
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from aihawk.academic_browser import (
    FormPlan,
    PortalPreparationError,
    PreparationNetworkGuard,
    plan_from_manifest,
    prepare_fields,
    verified_portal_host,
)


@dataclass(frozen=True)
class PortalStage:
    name: str
    expected_host: str
    expected_path: str
    form: FormPlan

    def fingerprint(self) -> str:
        payload = {
            "name": self.name,
            "expected_host": self.expected_host,
            "expected_path": self.expected_path,
            "form": self.form.fingerprint(),
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PortalJourney:
    stages: tuple[PortalStage, ...]
    starting_url: str
    hosts: tuple[str, ...]

    def fingerprint(self) -> str:
        raw = json.dumps(
            {
                "starting_url": self.starting_url,
                "stages": [stage.fingerprint() for stage in self.stages],
            },
            ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def journey_from_manifest(data: dict[str, Any], *, manifest_dir: Path) -> PortalJourney:
    """Reject omitted/ambiguous stage plans and unsupported navigation rules."""
    stages_data = data.get("portal_stages")
    if not isinstance(stages_data, list) or not 2 <= len(stages_data) <= 15:
        raise PortalPreparationError("Multi-page preparation requires 2–15 explicit portal_stages.")
    if data.get("portal_bindings"):
        raise PortalPreparationError("Use portal_stages or portal_bindings, never both.")
    hosts = tuple(data["official_hosts"])
    starting_url = str(data["official_application_url"])
    verified_portal_host(starting_url, hosts)
    stages: list[PortalStage] = []
    names: set[str] = set()
    for entry in stages_data:
        if not isinstance(entry, dict):
            raise PortalPreparationError("Each portal stage must be a named object.")
        name = entry.get("name")
        expected_host = entry.get("expected_host")
        expected_path = entry.get("expected_path")
        bindings = entry.get("bindings")
        if not isinstance(name, str) or not name.strip() or len(name) > 80 or name in names:
            raise PortalPreparationError("Each stage needs a distinct, nonempty short name.")
        if not isinstance(expected_host, str) or not isinstance(expected_path, str):
            raise PortalPreparationError("Every stage must specify an approved host and exact path.")
        if (
            not expected_path.startswith("/")
            or expected_path.startswith("//")
            or any(x in expected_path for x in ("?", "#", "\r", "\n"))
            or len(expected_path) > 500
        ):
            raise PortalPreparationError("Stage path must be an exact absolute path, without query or fragment.")
        host = verified_portal_host("https://" + expected_host + expected_path, hosts)
        if host != expected_host.lower().rstrip("."):
            raise PortalPreparationError("Expected stage hostname must be canonical.")
        if not isinstance(bindings, list) or not 1 <= len(bindings) <= 50:
            raise PortalPreparationError("Each stage needs 1–50 explicit field mappings.")
        stage_manifest = dict(data)
        stage_manifest["portal_bindings"] = bindings
        form = plan_from_manifest(stage_manifest, manifest_dir=manifest_dir)
        stages.append(PortalStage(name, host, expected_path, form))
        names.add(name)
    return PortalJourney(tuple(stages), starting_url, hosts)


def verify_stage_location(url: str, stage: PortalStage, hosts: tuple[str, ...]) -> None:
    host = verified_portal_host(url, hosts)
    path = urlsplit(url).path or "/"
    if host != stage.expected_host or path != stage.expected_path:
        raise PortalPreparationError(
            f"Wrong portal page for stage '{stage.name}': expected "
            f"{stage.expected_host}{stage.expected_path}; field preparation stopped."
        )


def prepare_stage(page: Any, stage: PortalStage, *, hosts: tuple[str, ...]) -> tuple[str, ...]:
    """Recheck stage location before and after every controlled field preparation."""
    verify_stage_location(page.url, stage, hosts)
    result = prepare_fields(page, stage.form)
    verify_stage_location(page.url, stage, hosts)
    return result


def run_interactive_journey(manifest: Path, *, prompt=input) -> int:
    """Human navigates stages; program only prepares verified fields."""
    if not sys.stdin.isatty():
        raise PortalPreparationError("Multi-step preparation requires an interactive local terminal.")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    journey = journey_from_manifest(data, manifest_dir=manifest.parent)
    challenge = journey.fingerprint()[-12:]
    if prompt(f"Type JOURNEY {challenge} after reviewing ALL portal stages: ") != f"JOURNEY {challenge}":
        return 1
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise PortalPreparationError("Install the optional Playwright browser dependency.") from error

    with sync_playwright() as playwright:
        from aihawk.academic_browser_launch import launch_operator_browser

        browser = launch_operator_browser(playwright, headless=False)
        context = browser.new_context(service_workers="block", accept_downloads=False)
        page = context.new_page()
        try:
            page.goto(journey.starting_url, wait_until="domcontentloaded", timeout=45000)
            print("Sign in and advance between stages yourself. The software NEVER clicks Next or Submit.")
            for index, stage in enumerate(journey.stages, start=1):
                print(f"Stage {index}/{len(journey.stages)}: {stage.name} "
                      f"at https://{stage.expected_host}{stage.expected_path}")
                prompt("Navigate manually to this stage and press Enter when its form is visible: ")
                verify_stage_location(page.url, stage, journey.hosts)
                step_key = stage.fingerprint()[-12:]
                if prompt(f"Type FILL {step_key} to prepare this approved stage: ") != f"FILL {step_key}":
                    return 1
                guard = PreparationNetworkGuard(journey.hosts)
                context.route("**/*", guard)
                try:
                    prepared = prepare_stage(page, stage, hosts=journey.hosts)
                    print(f"Prepared {len(prepared)} mapped fields; blocked {guard.blocked_requests} network requests.")
                finally:
                    context.unroute("**/*", guard)
                print("Review this stage. Only you may advance to the next page.")
            if prompt(f"Type MANUAL {challenge} to retain the browser for final manual steps: ") != f"MANUAL {challenge}":
                return 1
            print("You control final consents and Submit. Nothing has been submitted by AIHawk.")
            prompt("Press Enter when finished using the browser: ")
            return 0
        finally:
            context.close()
            browser.close()
