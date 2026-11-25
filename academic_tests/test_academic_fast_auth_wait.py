"""Known login pages must not burn the supervisor's twenty-second timeout."""

import json

from aihawk.academic_session_supervisor import await_authentication


class LoginPage:
    def is_closed(self):
        return False

    def wait_for_timeout(self, ms):
        raise AssertionError("A known university login screen requires no extra polling")


def test_known_login_returns_immediately_and_checkpoints(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "aihawk.academic_resume_session.inspect_page",
        lambda *args: {"status": "manual_sign_in_required"},
    )
    result = await_authentication(LoginPage(), tmp_path, ("example.edu",), "Example", limit_seconds=20)
    assert result is False
    report = json.loads((tmp_path / "Session_Checkpoint.json").read_text(encoding="utf-8"))
    assert report["status"] == "waiting_for_manual_login"
    assert report["final_submission"] is False
