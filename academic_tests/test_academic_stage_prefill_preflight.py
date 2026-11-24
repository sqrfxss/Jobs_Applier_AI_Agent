import pytest
from playwright.sync_api import sync_playwright
from aihawk.academic_browser import PortalPreparationError
from aihawk.academic_session_controls import apply_plan

PAGE = '<html><h1>Example University Project</h1><h2>Address</h2><input id="a" value=""><input id="b" value="old"></html>'
HOSTS = ("example.edu",)
TITLE = "Example University Project"


def test_preflight_detects_later_conflict_before_first_field_mutation(tmp_path):
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page()
        page.route("https://example.edu/**", lambda route: route.fulfill(status=200, content_type="text/html", body=PAGE))
        page.goto("https://example.edu/form")
        plan = {
            "schema": "aihawk.session.draft.v1",
            "project_title": TITLE,
            "section": "Address",
            "visible_heading": "Address",
            "actions": [{"type": "fill", "selector": "#a", "value": "new"}, {"type": "fill", "selector": "#b", "value": "other"}],
        }
        with pytest.raises(PortalPreparationError, match="Preflight existing value conflict"):
            apply_plan(page, tmp_path, HOSTS, TITLE, plan)
        assert page.locator("#a").input_value() == ""
        assert page.locator("#b").input_value() == "old"
        browser.close()


def test_preflight_allows_explicitly_reviewed_existing_value(tmp_path):
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page()
        page.route("https://example.edu/**", lambda route: route.fulfill(status=200, content_type="text/html", body=PAGE))
        page.goto("https://example.edu/form")
        plan = {
            "schema": "aihawk.session.draft.v1",
            "project_title": TITLE,
            "section": "Address",
            "visible_heading": "Address",
            "actions": [{"type": "fill", "selector": "#a", "value": "new"}, {"type": "fill", "selector": "#b", "value": "other", "reviewed_previous": "old"}],
        }
        result = apply_plan(page, tmp_path, HOSTS, TITLE, plan)
        assert len(result) == 2
        assert page.locator("#a").input_value() == "new"
        assert page.locator("#b").input_value() == "other"
        browser.close()
