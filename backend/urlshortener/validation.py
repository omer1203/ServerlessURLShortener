"""Public URL acceptance policy.

The Lambda never fetches the destination. Validation exists to reject malformed
input, keep the Location header safe, and refuse destinations that are
obviously local or non-routable. It does not make a public redirector safe
against phishing, and it does not resolve DNS. A hostname can still point at
a private address at click time.
"""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import quote, urlsplit

from urlshortener.errors import InvalidUrl

MAX_URL_LENGTH = 2048
MAX_EXPIRES_DAYS = 365

_BLOCKED_HOSTS = frozenset({"localhost", "localhost.localdomain"})
_BLOCKED_SUFFIXES = (".localhost", ".local", ".internal", ".localdomain")
_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")


def validate_long_url(value: object) -> str:
    """Return a normalized ASCII URL or raise InvalidUrl.

    Normalization lowercases the scheme and host, encodes internationalized
    hostnames with IDNA, drops default ports, and percent-encodes non-ASCII
    path, query, and fragment characters so the stored URL is safe to place
    in a Location header. The path is otherwise preserved, including case.
    """
    if not isinstance(value, str):
        raise InvalidUrl("Enter a URL that starts with http:// or https://.")
    raw = value.strip()
    if not raw:
        raise InvalidUrl("Enter a URL that starts with http:// or https://.")
    if len(raw) > MAX_URL_LENGTH:
        raise InvalidUrl("URLs must be 2048 characters or fewer.")
    if _has_forbidden_characters(raw) or "\\" in raw:
        raise InvalidUrl("That URL isn't valid.")

    try:
        parts = urlsplit(raw)
    except ValueError as exc:
        raise InvalidUrl("That URL isn't valid.") from exc

    scheme = parts.scheme.lower()
    if scheme not in {"http", "https"}:
        raise InvalidUrl("Enter a URL that starts with http:// or https://.")
    if parts.username is not None or parts.password is not None:
        raise InvalidUrl("That URL can't include a username or password.")

    try:
        port = parts.port
    except ValueError as exc:
        raise InvalidUrl("That URL isn't valid.") from exc
    if port == 0 or (port is not None and not 1 <= port <= 65535):
        raise InvalidUrl("That URL isn't valid.")

    host = _normalize_host(parts.hostname)
    if port is not None and not _is_default_port(scheme, port):
        host_for_netloc = f"[{host}]" if ":" in host else host
        netloc = f"{host_for_netloc}:{port}"
    else:
        netloc = f"[{host}]" if ":" in host else host

    path = quote(parts.path, safe="/%:@!$&'()*+,;=-._~")
    query = quote(parts.query, safe="/%&=+;:@,$?!()*'-._~")
    fragment = quote(parts.fragment, safe="/%&=+;:@,$?!()*'-._~")
    normalized = f"{scheme}://{netloc}{path}"
    if query:
        normalized = f"{normalized}?{query}"
    if fragment:
        normalized = f"{normalized}#{fragment}"
    if len(normalized) > MAX_URL_LENGTH or _has_forbidden_characters(normalized):
        raise InvalidUrl("That URL isn't valid.")
    return normalized


def _has_forbidden_characters(value: str) -> bool:
    return any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value)


def _is_default_port(scheme: str, port: int) -> bool:
    return (scheme == "http" and port == 80) or (scheme == "https" and port == 443)


def _normalize_host(hostname: str | None) -> str:
    if not hostname:
        raise InvalidUrl("That URL isn't valid.")
    host = hostname.strip().lower().rstrip(".")
    if not host or "\\" in host or "/" in host:
        raise InvalidUrl("That URL isn't valid.")

    literal = _ip_literal(host)
    if literal is not None:
        if not literal.is_global:
            raise InvalidUrl("Local and private addresses can't be shortened.")
        return literal.compressed

    if host in _BLOCKED_HOSTS or host.endswith(_BLOCKED_SUFFIXES):
        raise InvalidUrl("Local and private addresses can't be shortened.")

    try:
        ascii_host = host.encode("idna").decode("ascii").lower()
    except UnicodeError as exc:
        raise InvalidUrl("That URL isn't valid.") from exc

    labels = ascii_host.split(".")
    # A single label is a local name (`http://intranet`), not a public host.
    if len(labels) < 2 or len(ascii_host) > 253:
        raise InvalidUrl("That URL isn't valid.")
    if any(_LABEL.fullmatch(label) is None for label in labels):
        raise InvalidUrl("That URL isn't valid.")
    return ascii_host


def _ip_literal(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    if ":" in host:
        try:
            return ipaddress.ip_address(host)
        except ValueError as exc:
            raise InvalidUrl("That URL isn't valid.") from exc

    if host.startswith("0x") or ".0x" in host:
        raise InvalidUrl("That URL isn't valid.")

    # Decimal form such as 2130706433, which some clients treat as 127.0.0.1.
    if re.fullmatch(r"\d+", host):
        value = int(host)
        if value > 0xFFFFFFFF:
            raise InvalidUrl("That URL isn't valid.")
        return ipaddress.IPv4Address(value)

    if re.fullmatch(r"[0-9.]+", host):
        octets = host.split(".")
        if len(octets) != 4:
            raise InvalidUrl("That URL isn't valid.")
        if any(_invalid_octet(octet) for octet in octets):
            raise InvalidUrl("That URL isn't valid.")
        return ipaddress.IPv4Address(".".join(str(int(octet)) for octet in octets))
    return None


def _invalid_octet(octet: str) -> bool:
    if not octet.isdigit() or int(octet) > 255:
        return True
    # Leading zeros are octal in some clients (`0177.0.0.1`).
    return len(octet) > 1 and octet.startswith("0")
