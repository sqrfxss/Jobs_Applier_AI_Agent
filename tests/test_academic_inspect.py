from __future__ import annotations

import json

import pytest

from aihawk.academic_browser import PortalPreparationError
from aihawk.academic_inspect import INSPECT_EXPRESSION, export_inventory, inspect_controls


class ReadOnlyPage:
    def __init__(self, items=None, url="https://admissions.uni.example.edu/apply"):
        self.url = url
        self.items = items or []
        self.scripts = []

    def evaluate(self, expression):
        self.scripts.append(expression)
        return self.items


def test_control_inventory_never_reads_application_values(tmp_path):
    page = ReadOnlyPage([{
        "type": "email",
        "name": "email",
        "label": "Email address",
        "placeholder": "Your email",
        "selector": "#email",
        "unique": True,
        "required": True,
        "options": [],
    }])
    report = inspect_controls(page, official_hosts=("uni.example.edu",))
    assert report["submission_enabled"] is False
    assert report["values_captured"] is False
    assert report["mapping_approved"] is False
    assert report["controls"][0]["selector_candidate"] == "#email"
    assert "element.value" not in INSPECT_EXPRESSION
    assert "input.value" not in INSPECT_EXPRESSION
    assert "submit()" not in INSPECT_EXPRESSION
    assert len(page.scripts) == 1
    dest = tmp_path / "private" / "controls.json"
    export_inventory(dest, report)
    assert json.loads(dest.read_text(encoding="utf-8"))["controls"][0]["kind"] == "text"


def test_rejects_unapproved_portal_hostname():
    page = ReadOnlyPage(url="https://uni.example.edu.evil.test/apply")
    with pytest.raises(PortalPreparationError):
        inspect_controls(page, official_hosts=("uni.example.edu",))


def test_ignores_unexpected_control_types():
    page = ReadOnlyPage([{"type": "password"}, {"type": "submit"}, {"type": "select", "options": []}])
    report = inspect_controls(page, official_hosts=("uni.example.edu",))
    assert len(report["controls"]) == 1
    assert report["controls"][0]["kind"] == "select"


def test_rejects_oversized_page_result():
    page = ReadOnlyPage([{"type": "text"}] * 151)
    with pytest.raises(PortalPreparationError, match="excessive"):
        inspect_controls(page, official_hosts=("uni.example.edu",))


def test_noninteractive_inspection_forbidden(tmp_path, monkeypatch):
    import sys

    from aihawk.academic_inspect import run_interactive_inspection

    monkeypatch.setattr(sys, "stdin", type("NotTerminal", (), {"isatty": lambda self: False})())
    with pytest.raises(PortalPreparationError, match="interactive"):
        run_interactive_inspection(tmp_path / "manifest.json", tmp_path / "out.json")
