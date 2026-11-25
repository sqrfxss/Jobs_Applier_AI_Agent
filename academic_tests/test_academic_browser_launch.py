"""Tests use stub launchers and never start a real browser."""

import pytest

from aihawk.academic_browser_launch import launch_operator_browser


class Launcher:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def launch(self, **kwargs):
        self.calls.append(kwargs)
        result = self.outcomes.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class Playwright:
    def __init__(self, outcomes):
        self.chromium = Launcher(outcomes)


MISSING = RuntimeError("BrowserType.launch: Executable doesn't exist at C:/playwright/chrome")


def test_prefers_bundled_browser():
    page = object()
    fake = Playwright([page])
    assert launch_operator_browser(fake) is page
    assert fake.chromium.calls == [{"headless": False}]


def test_uses_installed_chrome_only_when_bundled_missing():
    page = object()
    fake = Playwright([MISSING, page])
    assert launch_operator_browser(fake) is page
    assert fake.chromium.calls == [{"headless": False}, {"headless": False, "channel": "chrome"}]


def test_can_use_edge_when_chrome_missing_too():
    page = object()
    fake = Playwright([MISSING, MISSING, page])
    assert launch_operator_browser(fake, headless=True) is page
    assert fake.chromium.calls[-1] == {"headless": True, "channel": "msedge"}


def test_does_not_hide_unrelated_browser_errors():
    fake = Playwright([PermissionError("Launching browser is blocked by policy")])
    with pytest.raises(PermissionError, match="policy"):
        launch_operator_browser(fake)
    assert len(fake.chromium.calls) == 1


def test_fails_if_no_browser_installed():
    fake = Playwright([MISSING, MISSING, MISSING])
    with pytest.raises(RuntimeError, match="No supported local"):
        launch_operator_browser(fake)
    assert len(fake.chromium.calls) == 3
