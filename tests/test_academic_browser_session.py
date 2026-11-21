"""Safe session tests. Never launch the applicant's personal browser."""
from __future__ import annotations

import sys

import pytest

from aihawk.academic_browser import PortalPreparationError
from aihawk.academic_browser_session import (
    launch_academic_context,
    official_session_page,
    private_profile_dir,
    run_interactive_session,
    workflow_context,
)

MISSING = RuntimeError("BrowserType.launch: Executable doesn't exist at example/path")


class FakeChromium:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def launch_persistent_context(self, **kwargs):
        self.calls.append(kwargs)
        result = self.outcomes.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class FakePlaywright:
    def __init__(self, outcomes):
        self.chromium = FakeChromium(outcomes)


class FakePage:
    def __init__(self, url="about:blank"):
        self.url = url
        self.visits = []

    def goto(self, url, **_):
        self.visits.append(url)
        self.url = url


class FakeContext:
    def __init__(self, urls):
        self.pages = [FakePage(url) for url in urls]
        self.spawned = []

    def new_page(self):
        page = FakePage()
        self.pages.append(page)
        self.spawned.append(page)
        return page


def test_private_profile_is_inside_application_directory(tmp_path):
    location = private_profile_dir(tmp_path)
    assert location.parent == tmp_path.resolve()
    assert location.name == ".aihawk-academic-session"
    assert location.is_dir()


def test_reject_repository_path_for_credentials(tmp_path):
    (tmp_path / ".git").mkdir()
    with pytest.raises(PortalPreparationError, match="Git repository"):
        private_profile_dir(tmp_path)


def test_reject_symlinked_profile(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "private"
    root.mkdir()
    try:
        (root / ".aihawk-academic-session").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("This OS does not permit unprivileged directory symlinks")
    with pytest.raises(PortalPreparationError, match="symlinked"):
        private_profile_dir(root)


def test_bundled_browser_persistent_profile(tmp_path):
    browser = object()
    fake = FakePlaywright([browser])
    assert launch_academic_context(fake, manifest_dir=tmp_path) is browser
    call = fake.chromium.calls[0]
    assert call["user_data_dir"] == str((tmp_path / ".aihawk-academic-session").resolve())
    assert call["headless"] is False
    assert call["accept_downloads"] is False
    assert call["service_workers"] == "block"
    assert "channel" not in call


def test_installed_chrome_fallback_never_uses_remote_debugging(tmp_path):
    browser = object()
    fake = FakePlaywright([MISSING, browser])
    assert launch_academic_context(fake, manifest_dir=tmp_path) is browser
    assert fake.chromium.calls[-1]["channel"] == "chrome"
    assert "connect_over_cdp" not in repr(fake.chromium.calls)
    assert all("user_data_dir" in call for call in fake.chromium.calls)


def test_does_not_retry_unrelated_browser_errors(tmp_path):
    fake = FakePlaywright([PermissionError("Browser rejected profile")])
    with pytest.raises(PermissionError):
        launch_academic_context(fake, manifest_dir=tmp_path)
    assert len(fake.chromium.calls) == 1


def test_refuses_institutional_multi_tab_ambiguity():
    ctx = FakeContext(["https://admissions.uni.example.edu/apply", "https://admissions.uni.example.edu/other"])
    with pytest.raises(PortalPreparationError, match="Multiple"):
        official_session_page(
            ctx, url="https://admissions.uni.example.edu/apply", official_hosts=("uni.example.edu",)
        )


def test_refuses_unrelated_tab_even_if_other_tab_is_official():
    ctx = FakeContext(["https://google.com", "https://admissions.uni.example.edu/apply"])
    with pytest.raises(PortalPreparationError, match="Unexpected"):
        official_session_page(
            ctx, url="https://admissions.uni.example.edu/apply", official_hosts=("uni.example.edu",)
        )


def test_reuses_existing_institutional_tab_without_navigation():
    page = FakePage("https://admissions.uni.example.edu/apply")
    context = FakeContext([])
    context.pages.append(page)
    assert official_session_page(
        context, url="https://admissions.uni.example.edu/apply", official_hosts=("uni.example.edu",)
    ) is page
    assert page.visits == []


def test_navigates_blank_persistent_tab_for_first_run():
    context = FakeContext(["about:blank"])
    page = official_session_page(
        context, url="https://admissions.uni.example.edu/apply", official_hosts=("uni.example.edu",)
    )
    assert page.visits == ["https://admissions.uni.example.edu/apply"]
    assert len(context.pages) == 1


def test_interactive_session_refuses_background_execution(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, "stdin", type("NonTTY", (), {"isatty": lambda self: False})())
    with pytest.raises(PortalPreparationError, match="interactive"):
        run_interactive_session(tmp_path / "missing.json")


def test_persistent_workflows_share_the_same_context_factory(tmp_path):
    sentinel = object()
    fake = FakePlaywright([sentinel])
    context, browser = workflow_context(fake, manifest_dir=tmp_path, persistent=True)
    assert context is sentinel
    assert browser is None
    assert fake.chromium.calls[0]["user_data_dir"].endswith(".aihawk-academic-session")
