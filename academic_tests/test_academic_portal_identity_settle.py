from aihawk.academic_session_batch import settle_project_identity


class Locator:
    def __init__(self, page, target):
        self.page = page
        self.target = target

    def count(self):
        if self.target == "password":
            return int(self.page.state == "login")
        if self.target == "project":
            return int(self.page.state == "verified")
        return 0

    def is_visible(self):
        return self.count() == 1


class Page:
    url = "https://srs.exeter.ac.uk/urd/sits.urd/run/siw_ipp_cgi.start"

    def __init__(self, sequence):
        self.sequence = sequence
        self.index = 0

    @property
    def state(self):
        return self.sequence[min(self.index, len(self.sequence) - 1)]

    def is_closed(self):
        return False

    def locator(self, selector):
        return Locator(self, "password")

    def get_by_text(self, title, exact=True):
        return Locator(self, "project")

    def wait_for_timeout(self, millis):
        self.index += 1


def test_redirect_to_login_stops_before_next_stage():
    p = Page(["blank", "blank", "login"])
    assert settle_project_identity(p, ("srs.exeter.ac.uk",), "Project", seconds=1) == "authentication_required"
    assert p.index >= 2


def test_transient_blank_page_can_recover_without_retry():
    p = Page(["blank", "verified"])
    assert settle_project_identity(p, ("srs.exeter.ac.uk",), "Project", seconds=1) == "authenticated"
    assert p.index == 1


def test_stable_login_reported_immediately():
    p = Page(["login"])
    assert settle_project_identity(p, ("srs.exeter.ac.uk",), "Project", seconds=1) == "authentication_required"
    assert p.index == 0
