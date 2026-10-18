"""API Gateway HTTP API payload format 2.0 helpers.

JSON is reserved for POST /shorten. The redirect route speaks HTTP redirects
and plain text because a browser is the usual client and the body must not
interpolate the destination into HTML.
"""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from urllib.parse import unquote

from urlshortener.errors import BadRequest, MethodNotAllowed

MAX_BODY_BYTES = 16_384

_JSON_HEADERS = {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
}
_TEXT_HEADERS = {
    "Content-Type": "text/plain; charset=utf-8",
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
}


def json_response(
    status: int,
    payload: dict[str, object],
    extra_headers: dict[str, str] | None = None,
) -> dict[str, object]:
    headers = dict(_JSON_HEADERS)
    if extra_headers:
        headers.update(extra_headers)
    return {
        "statusCode": status,
        "headers": headers,
        "body": json.dumps(payload, separators=(",", ":")),
    }


def text_response(
    status: int,
    message: str,
    extra_headers: dict[str, str] | None = None,
) -> dict[str, object]:
    headers = dict(_TEXT_HEADERS)
    if extra_headers:
        headers.update(extra_headers)
    return {"statusCode": status, "headers": headers, "body": message}


def redirect_response(location: str) -> dict[str, object]:
    if any(char in location for char in "\r\n\x00"):
        raise ValueError("refusing to emit an unsafe Location header")
    return {
        "statusCode": 302,
        "headers": {
            "Location": location,
            # no-store keeps intermediaries from skipping the function, which
            # would also skip the click update.
            "Cache-Control": "no-store",
            "Content-Type": "text/plain; charset=utf-8",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Strict-Transport-Security": "max-age=31536000",
        },
        "body": "Redirecting\n",
    }


def error_body(code: str, message: str, request_id: str) -> dict[str, object]:
    body: dict[str, object] = {"error": message, "code": code}
    if request_id:
        body["request_id"] = request_id
    return body


def request_id_from(event: object, context: object) -> str:
    if context is not None:
        aws_id = getattr(context, "aws_request_id", None)
        if isinstance(aws_id, str) and aws_id:
            return aws_id
    if isinstance(event, dict):
        ctx = event.get("requestContext") or {}
        if isinstance(ctx, dict):
            request_id = ctx.get("requestId")
            if isinstance(request_id, str):
                return request_id
    return ""


def http_method(event: dict) -> str | None:
    ctx = event.get("requestContext") or {}
    if not isinstance(ctx, dict):
        return None
    http = ctx.get("http") or {}
    if not isinstance(http, dict):
        return None
    method = http.get("method")
    if isinstance(method, str) and method:
        return method.upper()
    return None


def public_base_from_event(event: object, configured: str) -> str:
    """Prefer the configured base URL, otherwise derive the API Gateway URL.

    The $default stage is not part of the invoke URL. A named stage is.
    """
    if configured:
        return configured.rstrip("/")
    if not isinstance(event, dict):
        return ""
    ctx = event.get("requestContext") or {}
    if not isinstance(ctx, dict):
        return ""
    domain = ctx.get("domainName")
    if not isinstance(domain, str) or not domain or any(c in domain for c in " /\r\n"):
        return ""
    stage = ctx.get("stage")
    if isinstance(stage, str) and stage and stage != "$default":
        return f"https://{domain}/{stage}"
    return f"https://{domain}"


def parse_shorten_event(event: object) -> tuple[object, object]:
    """Return (long_url, expires_in_days) without applying the URL policy."""
    if not isinstance(event, dict):
        raise BadRequest("invalid_json", "Request body must be JSON.")
    method = http_method(event)
    if method is not None and method != "POST":
        raise MethodNotAllowed()
    if _is_direct_payload(event):
        return _fields_from_object(event)
    payload = _json_object(event)
    return _fields_from_object(payload)


def extract_redirect_code(event: object) -> str:
    """Pull the path code from an HTTP API event or a direct invoke."""
    if not isinstance(event, dict):
        return ""
    params = event.get("pathParameters") or {}
    if isinstance(params, dict) and isinstance(params.get("code"), str):
        return params["code"]
    raw_path = event.get("rawPath") or event.get("path") or ""
    if isinstance(raw_path, str) and "/r/" in raw_path:
        segment = raw_path.split("/r/", 1)[1]
        segment = segment.split("/", 1)[0]
        return unquote(segment)
    if "requestContext" not in event:
        for key in ("short_code", "code"):
            value = event.get(key)
            if isinstance(value, str):
                return value
    return ""


def isoformat_utc(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _is_direct_payload(event: dict) -> bool:
    return "long_url" in event and "requestContext" not in event and "body" not in event


def _json_object(event: dict) -> dict:
    raw = event.get("body")
    if raw is None or raw == "":
        raise BadRequest("invalid_json", "Request body must be JSON.")
    if not isinstance(raw, str):
        raise BadRequest("invalid_json", "Request body must be JSON.")
    if event.get("isBase64Encoded") is True:
        try:
            raw = base64.b64decode(raw, validate=True).decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise BadRequest("invalid_json", "Request body must be JSON.") from exc
    if len(raw.encode("utf-8")) > MAX_BODY_BYTES:
        raise BadRequest("invalid_json", "Request body is too large.")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise BadRequest("invalid_json", "Request body must be JSON.") from exc
    if not isinstance(parsed, dict):
        raise BadRequest("invalid_json", "Request body must be a JSON object.")
    return parsed


def _fields_from_object(payload: dict) -> tuple[object, object]:
    if "long_url" not in payload:
        raise BadRequest("invalid_url", "Enter a URL that starts with http:// or https://.")
    if "expires_in_days" not in payload or payload.get("expires_in_days") is None:
        return payload.get("long_url"), None
    expires = payload.get("expires_in_days")
    if isinstance(expires, bool) or not isinstance(expires, int):
        raise BadRequest(
            "invalid_expiration",
            "Expiration must be a whole number of days from 1 to 365.",
        )
    return payload.get("long_url"), expires
