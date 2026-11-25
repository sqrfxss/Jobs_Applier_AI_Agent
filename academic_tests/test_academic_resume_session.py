import pytest
import json
from aihawk.academic_resume_session import case_lock, checkpoint, inspect_page
from aihawk.academic_browser import PortalPreparationError


def test_case_lock_exclusive_and_reusable(tmp_path):
    with case_lock(tmp_path):
        with pytest.raises(PortalPreparationError, match="active session"):
            with case_lock(tmp_path):
                pass
    with case_lock(tmp_path):
        pass


def test_checkpoint_not_submission(tmp_path):
    checkpoint(tmp_path, {"status": "manual_sign_in_required", "final_submission": False})
    assert json.loads((tmp_path / "Session_Checkpoint.json").read_text())["final_submission"] is False


def test_project_identity_and_independent_pages():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        try:
            b = p.chromium.launch(channel="chrome", headless=True)
        except Exception as e:
            pytest.skip(str(e))
        c = b.new_context()
        first = c.new_page()
        first.route(
            "**/*", lambda r: r.fulfill(status=200, content_type="text/html", body="<h1>Example project</h1><button>About You</button><button>Address</button>")
        )
        first.goto("https://example.edu/application")
        other = c.new_page()
        other.set_content("<h1>Other tab</h1>")
        other.bring_to_front()
        r = inspect_page(first, ("example.edu",), "Example project")
        assert r["status"] == "project_session_verified"
        assert r["visible_section_controls"] == ["About You", "Address"]
        assert r["final_submission"] is False
        assert inspect_page(first, ("example.edu",), "Wrong project")["status"] == "unverified_page"
        b.close()


def test_manual_wait_services_browser_network():
    import threading
    from playwright.sync_api import sync_playwright
    from aihawk.academic_resume_session import wait_command

    received = threading.Event()
    with sync_playwright() as p:
        try:
            b = p.chromium.launch(channel="chrome", headless=True)
        except Exception as e:
            pytest.skip(str(e))
        c = b.new_context()
        page = c.new_page()

        def handler(route):
            route.fulfill(status=200, content_type="text/plain", body="ok")
            received.set()

        page.route("https://example.edu/async-test", handler)
        page.goto("about:blank")
        page.evaluate("() => {setTimeout(()=>fetch('https://example.edu/async-test').catch(()=>{}), 250)}")

        def user_wait(_):
            assert received.wait(5), "Network event not processed while waiting"
            return "inspect"

        assert wait_command(page, read=user_wait, interval_ms=50) == "inspect"
        assert received.is_set()
        b.close()
