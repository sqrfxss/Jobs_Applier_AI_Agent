"""Source-backed academic requirements, without pretending a page was verified.

Only operator-supplied, timestamped records from an explicitly configured
institutional host are admitted. HTML and page content remain untrusted.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urlsplit


@dataclass(frozen=True)
class RequirementSource:
    institution: str
    source_url: str
    retrieved_at: datetime
    requirement: str
    evidence: str


def _host(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError("Source must be an HTTPS URL without credentials or a custom port.")
    host = (parsed.hostname or "").rstrip(".").lower()
    if not host or host == "localhost" or host.replace(".", "").isdigit():
        raise ValueError("A valid official institutional domain is required.")
    return host


def validate_source(source: RequirementSource, *, official_hosts: tuple[str, ...], now: datetime) -> RequirementSource:
    """Validate metadata and domain membership; does not verify the page's truth."""
    host = _host(source.source_url)
    allowed = tuple(h.rstrip(".").lower() for h in official_hosts)
    if not allowed or not any(host == h or host.endswith("." + h) for h in allowed):
        raise ValueError("Source host is not on the institution's approved domain list.")
    if not source.institution.strip() or not source.requirement.strip() or not source.evidence.strip():
        raise ValueError("Institution, requirement and quoted evidence are required.")
    if source.retrieved_at.tzinfo is None or now.tzinfo is None:
        raise ValueError("Retrieval and evaluation timestamps must include a timezone.")
    if source.retrieved_at > now:
        raise ValueError("Retrieval timestamp cannot be in the future.")
    if len(source.evidence) > 2000:
        raise ValueError("Evidence excerpt is too long; store a short attributable excerpt.")
    return source
