from datetime import date
from bs4 import BeautifulSoup
from aihawk import academic_discovery as d


def test_canonical():
    assert d.canonical("https://example.edu/jobs/2/?lang=en&utm_source=test") == "https://example.edu/jobs/2"


def test_date():
    assert d.parse_date("January 31, 2027") == date(2027, 1, 31)
    assert d.parse_date("bad") is None


def test_score():
    assert d.score("Gait biomechanics and knee rehabilitation")[0] > d.score("Unrelated music")[0]


def test_listing_scope(monkeypatch):
    source = ("Example", "PhD", "example.edu", "https://example.edu/jobs", r"/jobs/\d+$", True)
    soup = BeautifulSoup(
        '<a href="/jobs/1">PhD in biomechanics</a><a href="/jobs/1?lang=en">PhD in biomechanics</a><a href="https://evil.test/jobs/2">PhD in gait</a><a href="/jobs/3">Postdoctoral biomechanics</a>',
        "html.parser",
    )
    monkeypatch.setattr(d, "fetch", lambda *a: (soup, source[3], "test"))
    stats, items = d.listing(source)
    assert stats["links"] == 2 and len(items) == 1


def test_closed_and_no_approval(monkeypatch):
    source = ("Example", "PhD", "example.edu", "https://example.edu/jobs", r"/jobs/\d+$", True)
    monkeypatch.setattr(
        d,
        "fetch",
        lambda *a: (BeautifulSoup("Fully funded PhD in gait. Application deadline: 2026-11-01", "html.parser"), "https://example.edu/jobs/1", "test"),
    )
    r = d.detail((source, "PhD in gait", "https://example.edu/jobs/1"), date(2026, 11, 24))
    assert r["state"] == "closed" and not r["approved_for_draft"]


def test_missing_deadline(monkeypatch):
    source = ("Example", "PhD", "example.edu", "https://example.edu/jobs", r"/jobs/\d+$", True)
    monkeypatch.setattr(d, "fetch", lambda *a: (BeautifulSoup("Fully funded PhD in gait", "html.parser"), "https://example.edu/jobs/1", "test"))
    r = d.detail((source, "PhD in gait", "https://example.edu/jobs/1"), date(2026, 11, 24))
    assert r["state"] == "needs_review" and r["deadline"] is None and not r["approved_for_draft"]
