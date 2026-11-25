import pytest
from aihawk.academic_session_controls import navigate, apply_plan
from aihawk.academic_exeter_react_select import select as custom_select
from aihawk.academic_session_batch import run_batch


@pytest.fixture
def portal():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        try:
            b = p.chromium.launch(channel="chrome", headless=True)
        except Exception as e:
            pytest.skip(str(e))
        page = b.new_page()
        yield page
        b.close()


def test_completed_reference_tab_is_navigable(portal):
    portal.route(
        "https://example.edu/**",
        lambda r: r.fulfill(
            status=200,
            content_type="text/html",
            body="<h1>Example project</h1><button onclick=\"document.getElementById('here').textContent='References'\">References&#10003;</button><h2 id=\"here\">Other</h2>",
        ),
    )
    portal.goto("https://example.edu/form")
    navigate(portal, ("example.edu",), "Example project", "References")
    assert portal.locator("#here").inner_text() == "References"


def test_duplicate_label_with_identical_value_is_safe(portal, tmp_path):
    portal.route(
        "https://example.edu/**",
        lambda r: r.fulfill(
            status=200,
            content_type="text/html",
            body='<h1>Example project</h1><select id="score" hidden><option value="">Choose...</option><option value="93">93</option><option value="93">93</option></select>',
        ),
    )
    portal.goto("https://example.edu/form")
    plan = {
        "schema": "aihawk.session.draft.v1",
        "project_title": "Example project",
        "section": "Qualifications",
        "visible_heading": "Example project",
        "actions": [{"type": "select", "selector": "#score", "label": "93"}],
    }
    assert apply_plan(portal, tmp_path, ("example.edu",), "Example project", plan)[0]["local_readback"]
    assert portal.locator("#score").input_value() == "93"


def test_react_dropdown_exact_choice(portal):
    portal.set_content(
        """<h2>Example project</h2><label for="years">How many years has it been since you were last studying within the Higher Education system?</label><input id="years" oninput="document.getElementById('options').hidden=false"><div id="options" hidden><button role="option" onclick="document.getElementById('display').innerText=this.innerText;this.parentNode.hidden=true">3-5 years</button></div><div id="display"></div>"""
    )
    assert custom_select(
        portal,
        {
            "type": "react_select",
            "source_evidence": "MSc 2024",
            "label_contains": "How many years has it been since you were last studying",
            "option": "3-5 years",
        },
    )["local_readback"]


def test_batch_skips_incomplete_section_and_reports_all(portal, tmp_path):
    portal.route(
        "https://example.edu/**",
        lambda r: r.fulfill(
            status=200, content_type="text/html", body="<h1>Example project</h1><button>About You</button><button>Address</button><h2>About you</h2>"
        ),
    )
    portal.goto("https://example.edu/form")
    plan = {
        "schema": "aihawk.session.batch.v1",
        "project_title": "Example project",
        "continue_on_stage_error": True,
        "stages": [
            {"section": "About You", "visible_heading": "Example project", "reviewed_complete": False},
            {"section": "Address", "visible_heading": "Example project", "reviewed_complete": False},
        ],
    }
    report = run_batch(portal, tmp_path, ("example.edu",), "Example project", plan)
    assert len(report["stages"]) == 2
    assert report["final_submission"] is False
    assert report["status"] != "reviewed_stages_completed"
