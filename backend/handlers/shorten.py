"""Lambda entry point for POST /shorten."""

from __future__ import annotations

from handlers.runtime import resolve_dependencies
from urlshortener.config import Settings
from urlshortener.errors import (
    AppError,
    CodeGenerationExhausted,
    ConfigurationError,
    RepositoryError,
)
from urlshortener.http import (
    error_body,
    isoformat_utc,
    json_response,
    parse_shorten_event,
    public_base_from_event,
    request_id_from,
)
from urlshortener.log import log_event, log_exception
from urlshortener.repository import UrlRepository
from urlshortener.service import create_link


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
        return json_response(
            500,
            error_body("internal_error", "The service is not configured.", request_id),
        )
    except Exception as exc:
        log_exception("startup_failed", exc, request_id=request_id)
        return json_response(
            503,
            error_body("dependency_failure", "The service is temporarily unavailable.", request_id),
        )
    return handle_shorten_event(event, context, resolved_settings, resolved_repo)


def handle_shorten_event(
    event: object,
    context: object,
    settings: Settings,
    repo: UrlRepository,
) -> dict[str, object]:
    request_id = request_id_from(event, context)
    try:
        long_url, expires_in_days = parse_shorten_event(event)
        created = create_link(repo, long_url, expires_in_days=expires_in_days)  # type: ignore[arg-type]
        base = public_base_from_event(event, settings.public_base_url)
        body: dict[str, object] = {
            "short_code": created.short_code,
            "short_url": f"{base}/r/{created.short_code}" if base else None,
            "long_url": created.long_url,
            "created_at": isoformat_utc(created.created_at),
            "expires_at": isoformat_utc(created.expires_at) if created.expires_at else None,
        }
        log_event(
            "info",
            "link_created",
            request_id=request_id,
            short_code=created.short_code,
            expires=created.expires_at is not None,
        )
        return json_response(201, body)
    except AppError as exc:
        log_event("info", "shorten_rejected", request_id=request_id, code=exc.code)
        headers = {"Allow": "POST"} if exc.status == 405 else None
        return json_response(exc.status, error_body(exc.code, exc.message, request_id), headers)
    except CodeGenerationExhausted:
        log_event("error", "code_generation_exhausted", request_id=request_id)
        return json_response(
            503,
            error_body(
                "code_generation_failed",
                "Could not allocate a short code. Try again.",
                request_id,
            ),
        )
    except RepositoryError as exc:
        log_event("error", "repository_error", request_id=request_id, reason=exc.reason)
        return json_response(
            503,
            error_body("dependency_failure", "The link could not be saved. Try again.", request_id),
        )
    except Exception as exc:
        log_exception("unhandled_error", exc, request_id=request_id, operation="shorten")
        return json_response(
            500,
            error_body("internal_error", "Something went wrong.", request_id),
        )
