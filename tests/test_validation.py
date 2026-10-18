from __future__ import annotations

import pytest

from urlshortener.errors import InvalidUrl
from urlshortener.validation import validate_long_url


def test_normalizes_scheme_host_and_keeps_path_case() -> None:
    assert validate_long_url("  HTTP://Example.COM/Foo  ") == "http://example.com/Foo"


def test_preserves_query_and_fragment() -> None:
    assert (
        validate_long_url("https://example.com/a?q=1&x=y#section")
        == "https://example.com/a?q=1&x=y#section"
    )


def test_drops_default_ports_and_keeps_custom_ports() -> None:
    assert validate_long_url("https://example.com:443/a") == "https://example.com/a"
    assert validate_long_url("http://example.com:80") == "http://example.com"
    assert validate_long_url("https://example.com:8443/a") == "https://example.com:8443/a"


def test_encodes_internationalized_host_and_path() -> None:
    normalized = validate_long_url("https://bücher.example/bücher")
    assert normalized.startswith("https://xn--bcher-kva.example/")
    assert normalized.isascii()
    assert "%" in normalized


def test_accepts_public_ipv4_and_ipv6() -> None:
    assert validate_long_url("https://8.8.8.8/dns") == "https://8.8.8.8/dns"
    assert validate_long_url("https://[2001:4860:4860::8888]/") == "https://[2001:4860:4860::8888]/"


@pytest.mark.parametrize(
    "value",
    [
        "",
        "   ",
        "example.com",
        "ftp://example.com",
        "javascript:alert(1)",
        "http://",
        "http://example.com/has space",
        "http://example.com/a\nb",
        "http://user:pass@example.com",
        "http://user@example.com",
        "http://localhost",
        "http://localhost:8080",
        "http://printer.local",
        "http://metadata.google.internal/computeMetadata",
        "http://127.0.0.1",
        "http://127.1",
        "http://0177.0.0.1",
        "http://2130706433",
        "http://10.1.2.3",
        "http://192.168.1.1",
        "http://172.16.0.1",
        "http://169.254.169.254/latest/meta-data",
        "http://100.64.0.1",
        "http://0.0.0.0",
        "http://[::1]/",
        "http://[fc00::1]/",
        "http://[fe80::1]/",
        "http://example",
        "https://example.com:0/",
        "https://example.com:99999/",
        "http://example.com/a\\b",
        42,
        "https://" + ("a" * 2049) + ".com",
    ],
)
def test_rejects_unsafe_or_malformed_urls(value: object) -> None:
    with pytest.raises(InvalidUrl):
        validate_long_url(value)


def test_rejection_messages_do_not_echo_the_input() -> None:
    secret = "https://user:secret-token@example.com/private"
    with pytest.raises(InvalidUrl) as caught:
        validate_long_url(secret)
    assert "secret-token" not in caught.value.message
    assert "private" not in caught.value.message
