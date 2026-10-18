"""Link creation and redirect decisions.

These functions do not know about API Gateway. Handlers translate their
results into HTTP.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from urllib.parse import urlsplit

from urlshortener.codes import MAX_ATTEMPTS, generate_code, normalize_code
from urlshortener.errors import (
    CodeAlreadyExists,
    CodeGenerationExhausted,
    InvalidExpiration,
    RepositoryError,
)
from urlshortener.log import log_event
from urlshortener.repository import LinkRecord, UrlRepository
from urlshortener.validation import MAX_EXPIRES_DAYS, validate_long_url


class Outcome(Enum):
    REDIRECT = "redirect"
    NOT_FOUND = "not_found"
    INVALID_CODE = "invalid_code"
    EXPIRED = "expired"


@dataclass(frozen=True)
class RedirectDecision:
    outcome: Outcome
    location: str | None = None
    short_code: str | None = None


def create_link(
    repo: UrlRepository,
    long_url: object,
    *,
    expires_in_days: int | None = None,
    now: int | None = None,
    code_factory: object | None = None,
    max_attempts: int = MAX_ATTEMPTS,
) -> LinkRecord:
    normalized = validate_long_url(long_url)
    created_at = int(time.time()) if now is None else now
    expires_at = _expiry(expires_in_days, created_at)
    factory = generate_code if code_factory is None else code_factory
    if not callable(factory):
        raise TypeError("code_factory must be callable")

    for _ in range(max_attempts):
        record = LinkRecord(
            short_code=factory(),
            long_url=normalized,
            created_at=created_at,
            expires_at=expires_at,
        )
        try:
            repo.create(record)
        except CodeAlreadyExists:
            continue
        return record
    raise CodeGenerationExhausted()


def resolve_redirect(
    repo: UrlRepository,
    raw_code: object,
    *,
    now: int | None = None,
) -> RedirectDecision:
    if not isinstance(raw_code, str) or len(raw_code) > 64:
        return RedirectDecision(Outcome.INVALID_CODE)
    code = normalize_code(raw_code)
    if code is None:
        return RedirectDecision(Outcome.INVALID_CODE)

    record = repo.get(code)
    if record is None:
        return RedirectDecision(Outcome.NOT_FOUND, short_code=code)

    current = int(time.time()) if now is None else now
    if record.expires_at is not None and record.expires_at <= current:
        # Do not count a click on a link we are refusing to follow.
        return RedirectDecision(Outcome.EXPIRED, short_code=code)

    location = _safe_location(record.long_url)
    # Tracking is best-effort. A failed counter update must not turn a
    # working redirect into an error, or hide a link during a throttle.
    try:
        recorded = repo.record_click(code, current)
        if not recorded:
            log_event("warning", "click_not_recorded", short_code=code, reason="missing")
    except RepositoryError as exc:
        log_event(
            "warning",
            "click_not_recorded",
            short_code=code,
            reason=exc.reason,
        )
    return RedirectDecision(Outcome.REDIRECT, location=location, short_code=code)


def _expiry(expires_in_days: int | None, created_at: int) -> int | None:
    if expires_in_days is None:
        return None
    if isinstance(expires_in_days, bool) or not isinstance(expires_in_days, int):
        raise InvalidExpiration()
    if not 1 <= expires_in_days <= MAX_EXPIRES_DAYS:
        raise InvalidExpiration()
    return created_at + expires_in_days * 86400


def _safe_location(url: str) -> str:
    """Guard the redirect against a corrupted or legacy unsafe item.

    Previously stored links are still followed when they are ordinary http(s)
    URLs. Control characters are rejected so a value cannot break out of the
    Location header.
    """
    if any(ord(char) < 32 or ord(char) == 127 for char in url):
        raise RepositoryError("unsafe_location")
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise RepositoryError("unsafe_location")
    return url
