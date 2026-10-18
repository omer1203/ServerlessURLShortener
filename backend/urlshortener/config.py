"""Runtime configuration.

Lambda receives this through environment variables. The local server constructs
a Settings object directly so it does not need AWS credentials.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlsplit

from urlshortener.errors import ConfigurationError


@dataclass(frozen=True)
class Settings:
    table_name: str
    public_base_url: str = ""
    log_level: str = "INFO"


def load_settings() -> Settings:
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    if level not in {"DEBUG", "INFO", "WARNING", "ERROR"}:
        level = "INFO"
    return Settings(
        table_name=os.environ.get("TABLE_NAME", "").strip(),
        public_base_url=clean_public_base(os.environ.get("PUBLIC_BASE_URL", "")),
        log_level=level,
    )


def clean_public_base(value: str) -> str:
    """Accept an origin operators configured, including http://127.0.0.1:8000.

    This is not the user-supplied destination URL. Localhost is allowed here
    because the dev server is configuration, not a shortened link.
    """
    candidate = value.strip().rstrip("/")
    if not candidate:
        return ""
    if any(ord(char) < 32 or ord(char) == 127 or char.isspace() for char in candidate):
        raise ConfigurationError("PUBLIC_BASE_URL contains whitespace or control characters")
    parts = urlsplit(candidate)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ConfigurationError("PUBLIC_BASE_URL must be an absolute http(s) URL")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise ConfigurationError(
            "PUBLIC_BASE_URL must not include credentials, a query, or a fragment"
        )
    return candidate
