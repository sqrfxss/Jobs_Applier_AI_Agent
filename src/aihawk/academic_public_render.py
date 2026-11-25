"""Bounded read-only public study information rendering. No account or profile."""

from urllib.parse import urlsplit
from aihawk.official_fetch import validate_network_host
import hashlib
import re

HOSTS = ("opintopolku.fi", "studyinfo.fi")


def allowed_url(url):
    try:
        p = urlsplit(url)
        h = p.hostname or ""
        return p.scheme == "https" and not p.username and not p.password and p.port in (None, 443) and any(h == x or h.endswith("." + x) for x in HOSTS)
    except ValueError:
        return False


def render(url):
    if not allowed_url(url):
        raise ValueError("Public render domain not approved")
    validate_network_host(url, HOSTS)
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="chrome", headless=True)
        try:
            context = browser.new_context(accept_downloads=False, service_workers="block")

            def gate(route):
                req = route.request
                if req.method not in ("GET", "HEAD", "OPTIONS") or not allowed_url(req.url):
                    return route.abort()
                return route.continue_()

            context.route("**/*", gate)
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=12000)
            page.wait_for_function("document.body && document.body.innerText.length > 800", timeout=12000)
            if not allowed_url(page.url):
                raise ValueError("Unexpected redirect")
            text = page.locator("body").inner_text(timeout=5000)
            text = re.sub(r"\s+", " ", text).strip()
            if len(text) < 800:
                raise ValueError("Insufficient rendered text")
            links = page.locator("a[href]").evaluate_all("(xs) => xs.map(a => ({title: a.innerText.trim(),url:a.href}))")
            links = [x for x in links if x["title"] and x["url"].startswith("https://")][:400]
            return {
                "url": page.url,
                "links": links,
                "text": text[:150000],
                "sha256": hashlib.sha256(text.encode()).hexdigest(),
                "capture_type": "rendered_visible_text",
            }
        finally:
            browser.close()
