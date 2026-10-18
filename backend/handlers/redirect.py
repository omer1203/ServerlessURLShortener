"""Lambda entry point for GET /r/{code}."""

from __future__ import annotations

from handlers.runtime import resolve_dependencies
from urlshortener.config import Settings
from urlshortener.errors import ConfigurationError, RepositoryError
from urlshortener.http import (
    extract_redirect_code,
    http_method,
    redirect_response,
    request_id_from,
    text_response,
)
from urlshortener.log import log_event, log_exception
from urlshortener.repository import UrlRepository
from urlshortener.service import Outcome, resolve_redirect

_MESSAGES = {
    Outcome.NOT_FOUND: (404, "This short link does not exist.\n"),
    Outcome.INVALID_CODE: (400, "This short link is not valid.\n"),
    Outcome.EXPIRED: (410, "This short link has expired.\n"),
}


def lambda_handler(
    event: object,
    context: object,
    repo: UrlRepository | None = None,
    settings: Settings | None = None,
) -> dict[str, object]:
    request_id = request_id_from(event, context)
    try:
        resolved_settings, resolved_repo = resolve_dependencies(repo, settings)
    except ConfigurationError:
        log_event("error", "configuration_error", request_id=request_id)
        return text_response(500, "This short link is temporarily unavailable.\n")
    except Exception as exc:
        log_exception("startup_failed", exc, request_id=request_id)
        return text_response(503, "This short link is temporarily unavailable.\n")
    return handle_redirect_event(event, context, resolved_settings, resolved_repo)


def handle_redirect_event(
    event: object,
    context: object,
    settings: Settings,
    repo: UrlRepository,
) -> dict[str, object]:
    del settings
    request_id = request_id_from(event, context)
    if isinstance(event, dict):
        method = http_method(event)
        if method is not None and method != "GET":
            return text_response(405, "Method not allowed.\n", {"Allow": "GET"})
    try:
        decision = resolve_redirect(repo, extract_redirect_code(event))
        if decision.outcome is Outcome.REDIRECT:
            log_event(
                "info",
                "redirect",
                request_id=request_id,
                short_code=decision.short_code,
            )
            assert decision.location is not None
            return redirect_response(decision.location)
        status, message = _MESSAGES[decision.outcome]
        log_event(
            "info",
            "redirect_rejected",
            request_id=request_id,
            outcome=decision.outcome.value,
            short_code=decision.short_code,
        )
        return text_response(status, message)
    except RepositoryError as exc:
        log_event("error", "repository_error", request_id=request_id, reason=exc.reason)
        return text_response(503, "This short link is temporarily unavailable.\n")
    except Exception as exc:
        log_exception("unhandled_error", exc, request_id=request_id, operation="redirect")
        return text_response(500, "This short link is temporarily unavailable.\n")
