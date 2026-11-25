"""Exeter's upload badge can contain browser replacement glyphs."""

import pytest
from playwright.sync_api import sync_playwright

from aihawk.academic_browser import PortalPreparationError
from aihawk.academic_exeter_upload import _trigger


def test_malformed_unicode_count_badge_still_selects_exact_upload_button():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page()
        page.set_content(
            "<button>Upload personal statement\ufffd\ufffd 1</button>"
            "<button>Upload personal statement Delete 1</button>"
            "<button>Submit your application</button>"
        )
        selected = _trigger(page, "personal statement", None)
        assert "\ufffd" in selected.inner_text()
        assert selected.is_visible()
        browser.close()


def test_duplicate_upload_buttons_require_reviewed_ordinal():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page()
        page.set_content("<button>Upload transcript 1</button><button>Upload transcript\ufffd 2</button>")
        with pytest.raises(PortalPreparationError, match="reviewed ordinal"):
            _trigger(page, "transcript", None)
        assert "2" in _trigger(page, "transcript", 1).inner_text()
        browser.close()


def test_unexpected_suffix_is_not_an_upload_trigger():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page()
        page.set_content("<button>Upload CV and submit application</button>")
        with pytest.raises(PortalPreparationError, match="reviewed ordinal"):
            _trigger(page, "CV", None)
        browser.close()
