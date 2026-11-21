"""Read-only inventory of candidate academic portal form controls.

The inspector never reads field values, cookies, hidden inputs or passwords,
never supplies field values and never activates form submission controls.
All page text is untrusted and must be reviewed as data.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from aihawk.academic_browser import PortalPreparationError, verified_portal_host

INSPECT_EXPRESSION = r"""() => {
  const allowed = new Set(['text','email','tel','url','number','search','date','file']);
  const controls = [];
  for (const element of document.querySelectorAll('input,select,textarea')) {
    if (controls.length >= 150) break;
    const tag = element.tagName.toLowerCase();
    const type = (element.getAttribute('type') || 'text').toLowerCase();
    if (tag === 'input' && !allowed.has(type)) continue;
    if (element.disabled || element.getClientRects().length === 0) continue;
    const id = element.id || '';
    const name = element.name || '';
    const selector = id ? '#' + CSS.escape(id)
      : name ? '[name="' + CSS.escape(name) + '"]' : '';
    const unique = !!selector && document.querySelectorAll(selector).length === 1;
    const label = Array.from(element.labels || []).map(e => e.textContent.trim()).join(' ');
    const placeholder = element.getAttribute('placeholder') || '';
    const options = tag === 'select'
      ? Array.from(element.options).slice(0, 35).map(x => ({
          label: x.textContent.trim().slice(0, 150), value: x.value.slice(0, 150)
        })) : [];
    controls.push({
      tag, type: tag === 'input' ? type : tag,
      name: name.slice(0, 120), label: label.slice(0, 180),
      placeholder: placeholder.slice(0, 160),
      selector: unique ? selector : '', unique,
      required: element.required === true, options
    });
  }
  return controls;
}"""


def inspect_controls(page: Any, *, official_hosts: tuple[str, ...]) -> dict[str, Any]:
    """Inspect explicit DOM metadata only, returning untrusted descriptions."""
    host = verified_portal_host(page.url, official_hosts)
    result = page.evaluate(INSPECT_EXPRESSION)
    if not isinstance(result, list) or len(result) > 150:
        raise PortalPreparationError("Browser returned an invalid or excessive control inventory.")
    cleaned: list[dict[str, Any]] = []
    for raw in result:
        if not isinstance(raw, dict):
            raise PortalPreparationError("Malformed form control record.")
        kind = raw.get("type")
        if kind not in {"text", "email", "tel", "url", "number", "search", "date", "file", "textarea", "select"}:
            continue
        cleaned.append({
            "name": str(raw.get("name", ""))[:120],
            "label_untrusted": str(raw.get("label", ""))[:180],
            "placeholder_untrusted": str(raw.get("placeholder", ""))[:160],
            "selector_candidate": str(raw.get("selector", ""))[:300],
            "selector_unique": raw.get("unique") is True,
            "kind": "select" if kind == "select" else ("upload" if kind == "file" else "text"),
            "html_type": kind,
            "required": raw.get("required") is True,
            "options_untrusted": raw.get("options", [])[:35] if isinstance(raw.get("options"), list) else [],
        })
    verified_portal_host(page.url, official_hosts)
    return {
        "schema": "aihawk.academic.control-inventory.v1",
        "institutional_host": host,
        "retrieved_at": datetime.now(UTC).isoformat(),
        "controls": cleaned,
        "values_captured": False,
        "mapping_approved": False,
        "submission_enabled": False,
    }


def export_inventory(path: Path, inventory: dict[str, Any]) -> None:
    """Caller must select a private local path, never a public repository."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run_interactive_inspection(manifest: Path, output: Path, *, prompt=input) -> int:
    import sys

    if not sys.stdin.isatty():
        raise PortalPreparationError("Read-only form inspection requires an interactive local terminal.")
    from aihawk.academic_ops import _payload, application_from_manifest

    preview, _, hosts, _ = application_from_manifest(_payload(manifest), manifest_dir=manifest.parent)
    verified_portal_host(preview.opportunity_url, hosts)
    if prompt("Type INSPECT to open the official portal for read-only field inventory: ") != "INSPECT":
        return 1
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise PortalPreparationError("Install the optional Playwright browser dependency.") from error
    with sync_playwright() as p:
        from aihawk.academic_browser_launch import launch_operator_browser

        browser = launch_operator_browser(p, headless=False)
        context = browser.new_context(service_workers="block", accept_downloads=False)
        page = context.new_page()
        try:
            page.goto(preview.opportunity_url, wait_until="domcontentloaded", timeout=45000)
            prompt("Log in manually if necessary, navigate to the form, then press Enter: ")
            inventory = inspect_controls(page, official_hosts=hosts)
            export_inventory(output, inventory)
            print(f"Saved {len(inventory['controls'])} control descriptions. No field values were read or submitted.")
            return 0
        finally:
            context.close()
            browser.close()
