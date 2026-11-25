"""SITS may load its login page without an input[type=password] yet."""

from aihawk.academic_resume_session import inspect_page


class Locator:
    def __init__(self, visible=False):
        self.visible = visible

    def count(self):
        return int(self.visible)

    def is_visible(self):
        return self.visible


class Page:
    def __init__(self, path, *, project=False):
        self.url = "https://srs.exeter.ac.uk" + path
        self.project = project

    def get_by_text(self, title, exact=True):
        return Locator(self.project)

    def get_by_role(self, role, name, exact=True):
        return Locator(self.project and name == "About You")

    def locator(self, selector):
        # The login transition document has no password field.
        return Locator(False)


def test_sits_login_redirect_is_immediate_auth_request(monkeypatch):
    monkeypatch.setattr("aihawk.academic_resume_session.check_access", lambda hosts: None)
    for path in ("/urd/sits.urd/run/SIW_IPP_LGN", "/urd/sits.urd/run/siw_ipp_lgn.login"):
        result = inspect_page(Page(path), ("srs.exeter.ac.uk",), "Reviewed project")
        assert result["status"] == "manual_sign_in_required"
        assert result["project_marker_verified"] is False
        assert result["final_submission"] is False


def test_non_login_blank_document_not_falsely_authenticated(monkeypatch):
    monkeypatch.setattr("aihawk.academic_resume_session.check_access", lambda hosts: None)
    result = inspect_page(Page("/urd/sits.urd/run/siw_ipp_cgi.start"), ("srs.exeter.ac.uk",), "Reviewed project")
    assert result["status"] == "unverified_page"


def test_authenticated_project_takes_precedence_over_url_classification(monkeypatch):
    monkeypatch.setattr("aihawk.academic_resume_session.check_access", lambda hosts: None)
    result = inspect_page(Page("/urd/sits.urd/run/siw_ipp_cgi.start", project=True), ("srs.exeter.ac.uk",), "Reviewed project")
    assert result["status"] == "project_session_verified"
