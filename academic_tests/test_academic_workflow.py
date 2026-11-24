from datetime import UTC, datetime

import pytest

from aihawk.academic_approval import ApplicationPreview, ApprovalGate
from aihawk.academic_sources import RequirementSource, validate_source

NOW = datetime(2026, 11, 20, tzinfo=UTC)


def test_official_subdomain_accepted():
    s = RequirementSource("Example", "https://admissions.uni.example.edu/program", NOW, "English B2", "B2 required")
    assert validate_source(s, official_hosts=("uni.example.edu",), now=NOW) is s


@pytest.mark.parametrize(
    "url",
    [
        "https://uni.example.edu.evil.test/program",
        "http://uni.example.edu/program",
        "https://user:password@uni.example.edu/program",
        "https://uni.example.edu:8443/program",
    ],
)
def test_disallowed_sources(url):
    s = RequirementSource("Example", url, NOW, "English B2", "B2 required")
    with pytest.raises(ValueError):
        validate_source(s, official_hosts=("uni.example.edu",), now=NOW)


def test_unknown_official_host_is_not_trusted():
    s = RequirementSource("Example", "https://uni.example.edu/program", NOW, "English B2", "B2 required")
    with pytest.raises(ValueError):
        validate_source(s, official_hosts=(), now=NOW)


def test_approval_exact_snapshot_and_single_use():
    original = ApplicationPreview("https://uni.example.edu/apply", "candidate", (("degree", "MSc"),))
    altered = ApplicationPreview("https://uni.example.edu/apply", "candidate", (("degree", "PhD"),))
    gate = ApprovalGate()
    with pytest.raises(PermissionError):
        gate.consume(original, reviewer="person")
    gate.approve(original, reviewer="person", now=NOW)
    with pytest.raises(PermissionError):
        gate.consume(altered, reviewer="person")
    gate.consume(original, reviewer="person")
    with pytest.raises(PermissionError):
        gate.consume(original, reviewer="person")


def test_wrong_reviewer_cannot_consume():
    preview = ApplicationPreview("https://uni.example.edu/apply", "candidate", ())
    gate = ApprovalGate()
    gate.approve(preview, reviewer="owner", now=NOW)
    with pytest.raises(PermissionError):
        gate.consume(preview, reviewer="other")
