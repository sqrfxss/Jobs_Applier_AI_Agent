import pytest

from aihawk.academic_approval import ApplicationPreview
from aihawk.academic_portal import open_manual_portal, render_preview, save_preview


def preview():
    return ApplicationPreview(
        "https://admissions.uni.example.edu/form", "person",
        (("degree", "MSc"), ("notes", "<script>alert(1)</script>")),
        ("sha256:deadbeef",),
    )


def test_preview_is_non_submitting_and_escapes_fields(tmp_path):
    html = render_preview(preview(), title="<Test>", official_hosts=("uni.example.edu",))
    assert "&lt;script&gt;" in html
    assert "<script>" not in html
    assert "form-action 'none'" in html
    assert "nothing has been submitted" in html
    p = save_preview(tmp_path / "review.html", html)
    assert p.read_text(encoding="utf-8") == html


def test_rejects_portal_host_spoof():
    p = ApplicationPreview("https://uni.example.edu.evil.test", "person", ())
    with pytest.raises(ValueError):
        render_preview(p, title="Test", official_hosts=("uni.example.edu",))


def test_never_opens_non_interactive():
    opened = []
    with pytest.raises(PermissionError):
        open_manual_portal(preview(), official_hosts=("uni.example.edu",),
            is_interactive=False, browser_open=lambda url: opened.append(url))
    assert not opened


def test_rejects_wrong_challenge_without_browser():
    opened = []
    result = open_manual_portal(preview(), official_hosts=("uni.example.edu",),
        is_interactive=True, prompt=lambda _: "wrong", browser_open=lambda url: opened.append(url))
    assert result is False and not opened


def test_manual_handoff_requires_fingerprint_challenge():
    opened = []
    result = open_manual_portal(preview(), official_hosts=("uni.example.edu",),
        is_interactive=True,
        prompt=lambda _: "OPEN " + preview().fingerprint()[-12:],
        browser_open=lambda url: opened.append(url) or True)
    assert result is True
    assert opened == [preview().opportunity_url]
