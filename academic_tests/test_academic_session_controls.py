import pytest
from aihawk.academic_session_controls import inventory, apply_plan, save_draft
from aihawk.academic_browser import PortalPreparationError


def test_reviewed_controls_no_final(tmp_path):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        try:
            b = p.chromium.launch(channel="chrome", headless=True)
        except Exception as e:
            pytest.skip(str(e))
        c = b.new_context()
        page = c.new_page()
        page.route(
            "https://example.edu/**",
            lambda r: r.fulfill(
                status=200,
                content_type="text/html",
                body='<h1>Example project</h1><h2>About you</h2><label for="first">First name</label><input id="first"><select id="country"><option value="1">Iran</option><option value="2">UK</option></select><input id="signature"><button>Save and continue</button><button>Submit your application</button>',
            ),
        )
        page.goto("https://example.edu/apply")
        plan = {
            "schema": "aihawk.session.draft.v1",
            "project_title": "Example project",
            "section": "About You",
            "visible_heading": "About you",
            "actions": [{"type": "fill", "selector": "#first", "value": "Example"}, {"type": "select", "selector": "#country", "label": "Iran"}],
        }
        assert len(inventory(page, ("example.edu",), "Example project")) == 5
        assert len(apply_plan(page, tmp_path, ("example.edu",), "Example project", plan)) == 2
        assert page.locator("#first").input_value() == "Example"
        plan["actions"] = [{"type": "fill", "selector": "#signature", "value": "Name"}]
        with pytest.raises(PortalPreparationError):
            apply_plan(page, tmp_path, ("example.edu",), "Example project", plan)
        with pytest.raises(PortalPreparationError):
            save_draft(page, ("example.edu",), "Example project")
        b.close()
