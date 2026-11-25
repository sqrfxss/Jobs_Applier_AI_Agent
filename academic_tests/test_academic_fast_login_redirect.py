"""Navigation must not burn 14 seconds when Exeter shows its login route."""

import pytest

from aihawk.academic_browser import PortalPreparationError
from aihawk.academic_session_controls import _login_redirected, navigate


class Locator:
    def __init__(self, page, kind):
        self.page = page
        self.kind = kind

    def count(self):
        if self.kind == "dialog":
            return 0
        if self.kind == "title":
            return int(not self.page.logged_out)
        if self.kind == "heading":
            return 0
        return 1

    def is_visible(self):
        return self.count() == 1

    def is_enabled(self):
        return True

    def inner_text(self):
        return "Qualifications"

    def click(self, **kwargs):
        self.page.logged_out = True
        self.page.url = "https://srs.exeter.ac.uk/urd/sits.urd/run/SIW_IPP_LGN"


class Page:
    def __init__(self):
        self.url = "https://srs.exeter.ac.uk/urd/sits.urd/run/siw_ipp_cgi.start"
        self.logged_out = False
        self.polls = 0
        self.listeners = []

    def get_by_text(self, *args, **kwargs):
        return Locator(self, "title")

    def get_by_role(self, role, **kwargs):
        if role == "dialog":
            return Locator(self, "dialog")
        if role == "heading":
            return Locator(self, "heading")
        return ButtonList(self)

    def wait_for_timeout(self, ms):
        self.polls += 1

    def on(self, event, fn):
        self.listeners.append(fn)

    def remove_listener(self, event, fn):
        self.listeners.remove(fn)


class ButtonList:
    def __init__(self, page):
        self.page = page

    def count(self):
        return 1

    def nth(self, i):
        assert i == 0
        return Locator(self.page, "button")


@pytest.mark.parametrize("force", [False, True])
def test_explicit_login_redirect_fails_in_first_poll(monkeypatch, force):
    monkeypatch.setattr("aihawk.academic_session_controls.check_access", lambda hosts: None)
    page = Page()
    with pytest.raises(PortalPreparationError, match="University login required"):
        navigate(
            page,
            ("srs.exeter.ac.uk",),
            "Research project",
            "Qualifications",
            expected_heading="Academic qualifications",
            force=force,
        )
    assert page.polls <= 1, "No 12–14-second blind wait on login redirect"
    assert page.logged_out is True
    assert page.listeners == [], "No orphaned network listeners"


def test_only_explicit_login_urls_count_as_redirect():
    p = Page()
    assert _login_redirected(p) is False
    p.url = "https://srs.exeter.ac.uk/urd/sits.urd/run/siw_ipp_lgn.login"
    assert _login_redirected(p) is True
