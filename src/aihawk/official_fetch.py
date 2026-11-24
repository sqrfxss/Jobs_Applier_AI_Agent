"""Evidence-only retrieval of allowlisted official university pages.

Fetches public HTTPS pages, extracts readable text, and creates an attributable
snapshot. It does NOT infer admission rules or treat a matching host as proof
that a statement is true. No credentials, browser profiles, or LLM calls.
"""

from __future__ import annotations

import hashlib
import ipaddress
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from io import BytesIO

from aihawk.academic_sources import _host

MAX_BYTES = 3_000_000
USER_AGENT = "AIHawkAcademicEvidence/1.0 (public-pages-only)"


class SourceFetchError(ValueError):
    """An untrusted, unreachable, or unsuitable source cannot be captured."""


class _PlainText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.items: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style", "noscript", "template", "svg"):
            self.hidden += 1
        if tag in ("p", "div", "br", "li", "h1", "h2", "h3", "tr", "td"):
            self.items.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "noscript", "template", "svg") and self.hidden:
            self.hidden -= 1
        if tag in ("p", "div", "li", "tr", "td"):
            self.items.append(" ")

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.items.append(data)

    def text(self) -> str:
        return re.sub(r"\s+", " ", " ".join(self.items)).strip()


def validate_network_host(url: str, hosts: tuple[str, ...], resolver: Callable = socket.getaddrinfo) -> str:
    """Allow exact institutional hosts or subdomains, rejecting private DNS answers."""
    try:
        host = _host(url)
    except (ValueError, TypeError) as exc:
        raise SourceFetchError(str(exc)) from exc
    normalized = tuple(h.rstrip(".").casefold() for h in hosts if h)
    if not normalized or not any(host == h or host.endswith("." + h) for h in normalized):
        raise SourceFetchError("URL is not on an explicitly approved institutional host.")
    try:
        addresses = resolver(host, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise SourceFetchError("Official host could not be resolved.") from exc
    if not addresses:
        raise SourceFetchError("No addresses were returned for official host.")
    for item in addresses:
        try:
            ip = ipaddress.ip_address(item[4][0])
        except (ValueError, IndexError, KeyError, TypeError) as exc:
            raise SourceFetchError("Invalid DNS address.") from exc
        if not ip.is_global:
            raise SourceFetchError("Non-public network destination is forbidden.")
    return host


@dataclass(frozen=True)
class PageSnapshot:
    requested_url: str
    final_url: str
    retrieved_at: datetime
    sha256: str
    content_type: str
    text: str

    def excerpt(self, phrase: str, *, context: int = 210) -> str:
        """Find an exact phrase in visible text; absent phrase is an error, not evidence."""
        if not phrase.strip() or len(phrase) > 500:
            raise ValueError("Provide a non-empty, short literal phrase.")
        match = re.search(re.escape(phrase.strip()), self.text, re.IGNORECASE)
        if match is None:
            raise ValueError("Phrase was not present in the captured document.")
        return self.text[max(0, match.start() - context) : min(len(self.text), match.end() + context)].strip()


class _SecureRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, hosts: tuple[str, ...], resolver: Callable) -> None:
        self.hosts = hosts
        self.resolver = resolver

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_network_host(newurl, self.hosts, self.resolver)
        if len(getattr(req, "redirect_dict", {})) > 4:
            raise SourceFetchError("Too many redirects.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_official_page(
    url: str,
    *,
    official_hosts: tuple[str, ...],
    timeout: float = 15.0,
    max_bytes: int = MAX_BYTES,
    resolver: Callable = socket.getaddrinfo,
    opener=None,
) -> PageSnapshot:
    """Retrieve public HTML/plain text/PDF, bounded in time/size.

    The caller must independently establish that official_hosts belong to the
    university. DNS is checked before requesting but final network egress
    filtering is still required against time-of-check/time-of-use DNS changes.
    """
    validate_network_host(url, official_hosts, resolver)
    if not 0 < timeout <= 60 or not 1024 <= max_bytes <= MAX_BYTES:
        raise ValueError("Timeout or byte limit outside allowed bounds.")
    if opener is None:
        # Ignore ambient HTTP_PROXY settings and refuse off-domain redirects.
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            _SecureRedirect(official_hosts, resolver),
        )
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,text/plain,application/pdf"})
    try:
        with opener.open(req, timeout=timeout) as response:
            final_url = response.geturl()
            validate_network_host(final_url, official_hosts, resolver)
            mime = response.headers.get("Content-Type", "").split(";", 1)[0].lower().strip()
            if mime not in ("text/html", "text/plain", "application/pdf"):
                raise SourceFetchError(f"Unsupported document type: {mime!r}")
            raw = response.read(max_bytes + 1)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise SourceFetchError("Official page could not be fetched.") from exc
    if len(raw) > max_bytes:
        raise SourceFetchError("Page exceeds the permitted download limit.")
    digest = hashlib.sha256(raw).hexdigest()
    if mime == "application/pdf":
        try:
            from pypdf import PdfReader

            reader = PdfReader(BytesIO(raw), strict=False)
            if len(reader.pages) > 75:
                raise SourceFetchError("PDF exceeds the permitted page count.")
            content = " ".join(page.extract_text() or "" for page in reader.pages)
        except ImportError as exc:
            raise SourceFetchError("PDF extraction requires pypdf.") from exc
        except Exception as exc:
            if isinstance(exc, SourceFetchError):
                raise
            raise SourceFetchError("PDF text could not be extracted.") from exc
    else:
        enc = "utf-8"
        content = raw.decode(enc, errors="replace")
        if mime == "text/html":
            parser = _PlainText()
            parser.feed(content)
            content = parser.text()
    return PageSnapshot(
        requested_url=url,
        final_url=final_url,
        retrieved_at=datetime.now(UTC),
        sha256=digest,
        content_type=mime,
        text=re.sub(r"\s+", " ", content).strip(),
    )
