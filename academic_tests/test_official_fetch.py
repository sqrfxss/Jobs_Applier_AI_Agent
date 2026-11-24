"""Network-free official-source retrieval tests."""
import io
import socket

import pytest

from aihawk.official_fetch import SourceFetchError, fetch_official_page, validate_network_host


def resolver(host, port, type):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]


class Response:
    def __init__(self, url, text, mime="text/html"):
        self.url = url
        self.contents = io.BytesIO(text)
        self.headers = {"Content-Type": mime}

    def __enter__(self): return self
    def __exit__(self, *_): return False
    def geturl(self): return self.url
    def read(self, size): return self.contents.read(size)


class Opener:
    def __init__(self, result): self.result = result
    def open(self, request, timeout): return self.result


def test_extracts_readable_and_attributable_evidence():
    url = "https://apply.university.example.edu/requirements"
    page = fetch_official_page(
        url, official_hosts=("university.example.edu",), resolver=resolver,
        opener=Opener(Response(url, b"<html><script>bad instructions</script><p>TOEFL Home Edition accepted.</p></html>")),
    )
    assert "bad instructions" not in page.text
    assert "TOEFL Home Edition" in page.excerpt("TOEFL Home Edition")
    assert len(page.sha256) == 64
    assert page.final_url == url


def test_unknown_phrase_is_not_inferred():
    url = "https://uni.example.edu/requirements"
    page = fetch_official_page(url, official_hosts=("uni.example.edu",), resolver=resolver,
        opener=Opener(Response(url, b"<p>Only IELTS accepted</p>")))
    with pytest.raises(ValueError):
        page.excerpt("TOEFL")


@pytest.mark.parametrize("url", [
    "http://uni.example.edu/",
    "https://uni.example.edu.attacker.test/",
    "https://127.0.0.1/",
    "https://user:password@uni.example.edu/",
])
def test_rejects_non_official_url(url):
    with pytest.raises(SourceFetchError):
        validate_network_host(url, ("uni.example.edu",), resolver)


def test_rejects_private_dns_address():
    def private(host, port, type):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))]
    with pytest.raises(SourceFetchError, match="Non-public"):
        validate_network_host("https://uni.example.edu", ("uni.example.edu",), private)


def test_rejects_redirect_to_other_host():
    url = "https://uni.example.edu/requirements"
    with pytest.raises(SourceFetchError):
        fetch_official_page(
            url, official_hosts=("uni.example.edu",), resolver=resolver,
            opener=Opener(Response("https://attacker.test/", b"<p>accepted</p>")),
        )


def test_rejects_oversized_page():
    url = "https://uni.example.edu/requirements"
    with pytest.raises(SourceFetchError, match="limit"):
        fetch_official_page(url, official_hosts=("uni.example.edu",), resolver=resolver,
            opener=Opener(Response(url, b"x" * 1100)), max_bytes=1024)


def test_rejects_invalid_type():
    url = "https://uni.example.edu/requirements"
    with pytest.raises(SourceFetchError, match="Unsupported"):
        fetch_official_page(url, official_hosts=("uni.example.edu",), resolver=resolver,
            opener=Opener(Response(url, b"123", "application/octet-stream")))
