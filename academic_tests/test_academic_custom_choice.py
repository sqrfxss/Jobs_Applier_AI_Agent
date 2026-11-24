"""Exact-value custom academic dropdown regression tests."""

import pytest
from aihawk.academic_browser import Binding, PortalPreparationError, plan_from_manifest, prepare_fields


class Control:
    def __init__(self, text, tag="a", *, page=None):
        self.text, self.tag, self.page, self.clicks = text, tag, page, 0

    def count(self):
        return 1

    def is_enabled(self):
        return True

    def is_visible(self):
        return True

    def evaluate(self, _: str):
        return self.tag

    def get_attribute(self, _: str):
        return None

    def inner_text(self, **_):
        return self.text

    def click(self, **_):
        self.clicks += 1
        if self.page and self.tag == "li":
            self.page.trigger.text = self.text


class Page:
    url = "https://admissions.uni.example.edu/apply"

    def __init__(self, value="Iran", option="Iran"):
        self.trigger = Control("- None -")
        self.option = Control(option, "li", page=self)
        self.nodes = {"#country": self.trigger, "#country-option-iran": self.option}

    def locator(self, s):
        return self.nodes[s]


def plan(tmp_path, value="Iran"):
    data = {
        "title": "Academic",
        "applicant_id": "candidate",
        "official_application_url": "https://admissions.uni.example.edu/apply",
        "official_hosts": ["uni.example.edu"],
        "fields": {"country": value},
        "attachments": [],
        "portal_bindings": [{"field": "country", "kind": "choice", "selector": "#country", "option_selector": "#country-option-iran"}],
    }
    return plan_from_manifest(data, manifest_dir=tmp_path)


def test_custom_dropdown_selects_exact_verified_value(tmp_path):
    page = Page()
    assert prepare_fields(page, plan(tmp_path)) == ("country",)
    assert page.trigger.text == "Iran"
    assert page.trigger.clicks == 1 and page.option.clicks == 1


def test_custom_dropdown_rejects_incorrect_option(tmp_path):
    page = Page(option="Iraq")
    with pytest.raises(PortalPreparationError, match="label differs"):
        prepare_fields(page, plan(tmp_path))
    assert page.option.clicks == 0


def test_custom_dropdown_preserves_existing_value(tmp_path):
    page = Page()
    page.trigger.text = "Iran"
    assert prepare_fields(page, plan(tmp_path)) == ("country",)
    assert page.trigger.clicks == page.option.clicks == 0


def test_custom_dropdown_rejects_conflicting_saved_value(tmp_path):
    page = Page()
    page.trigger.text = "Germany"
    with pytest.raises(PortalPreparationError, match="conflicts"):
        prepare_fields(page, plan(tmp_path))


def test_custom_dropdown_requires_reviewed_option_selector():
    with pytest.raises(PortalPreparationError, match="option selector"):
        Binding(field="country", selector="#country", kind="choice")
