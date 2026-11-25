"""Existing address formatting must not trigger duplicate writes or false failures."""

import pytest
from playwright.sync_api import sync_playwright

from aihawk.academic_browser import PortalPreparationError
from aihawk.academic_session_controls import apply_plan
from aihawk.academic_session_progress import verify_stage
from aihawk.academic_value_comparison import formatting_equivalent


@pytest.mark.parametrize(
    ("expected", "stored", "same"),
    [
        ("12, North Street", "12 NORTH STREET", True),
        ("Apartment #3; 12 Main St", "apartment 3, 12 main st", True),
        ("House 12A", "House 12B", False),
        ("House 12A", "House 12 A", False),  # Do not merge house-number tokens.
        ("Street 123", "Street 1234", False),
        ("", "Street 123", False),
    ],
)
def test_only_safe_address_token_equivalence(expected, stored, same):
    assert formatting_equivalent("#IPR_HAD1", expected, stored) is same
    assert formatting_equivalent("#IPQ_ELQUAL_DATE", expected, stored) is False
    assert formatting_equivalent("#IPR_HAPC", expected, stored) is False


def test_formatting_equivalent_address_is_preserved_and_reverified(tmp_path, monkeypatch):
    monkeypatch.setattr("aihawk.academic_session_controls.check_access", lambda hosts: None)
    monkeypatch.setattr("aihawk.academic_session_progress.field_record", lambda *args, **kwargs: None)
    plan = {
        "schema": "aihawk.session.draft.v1",
        "project_title": "Example project",
        "section": "Address",
        "visible_heading": "Address",
        "actions": [{"type": "fill", "selector": "#IPR_HAD1", "value": "12 North Street"}],
    }
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page()
        page.route(
            "https://example.edu/**",
            lambda route: route.fulfill(
                status=200,
                content_type="text/html",
                body='<h1>Example project</h1><h2>Address</h2><input id="IPR_HAD1" value="12, NORTH STREET">',
            ),
        )
        page.goto("https://example.edu/address")
        apply_plan(page, tmp_path, ("example.edu",), "Example project", plan)
        # Do not edit a field already present in the institution's database.
        assert page.locator("#IPR_HAD1").input_value() == "12, NORTH STREET"
        stage = {"section": "Address", "visible_heading": "Address", "actions": plan["actions"]}
        assert verify_stage(page, stage, ("example.edu",), "Example project", navigate_to=False) is True
        browser.close()


def test_materially_different_address_is_not_overwritten(tmp_path, monkeypatch):
    monkeypatch.setattr("aihawk.academic_session_controls.check_access", lambda hosts: None)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page()
        page.route(
            "https://example.edu/**",
            lambda route: route.fulfill(
                status=200,
                content_type="text/html",
                body='<h1>Example project</h1><h2>Address</h2><input id="IPR_HAD1" value="12 South Street">',
            ),
        )
        page.goto("https://example.edu/address")
        plan = {
            "schema": "aihawk.session.draft.v1",
            "project_title": "Example project",
            "section": "Address",
            "visible_heading": "Address",
            "actions": [{"type": "fill", "selector": "#IPR_HAD1", "value": "12 North Street"}],
        }
        with pytest.raises(PortalPreparationError, match="Preflight existing value conflict"):
            apply_plan(page, tmp_path, ("example.edu",), "Example project", plan)
        assert page.locator("#IPR_HAD1").input_value() == "12 South Street"
        browser.close()
