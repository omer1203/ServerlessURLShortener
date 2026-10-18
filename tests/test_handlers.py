from __future__ import annotations

import base64
import json

from handlers.redirect import handle_redirect_event
from handlers.shorten import handle_shorten_event
from urlshortener.config import Settings
from urlshortener.errors import RepositoryError
from urlshortener.repository import InMemoryUrlRepository

SETTINGS = Settings(
    table_name="local",
    public_base_url="https://short.example",
    log_level="ERROR",
)


class Context:
    aws_request_id = "req-123"


def _http_event(body: dict | str | None, *, method: str = "POST", encoded: bool = False) -> dict:
    raw = body if isinstance(body, str) or body is None else json.dumps(body)
    if encoded and isinstance(raw, str):
        raw = base64.b64encode(raw.encode()).decode()
    return {
        "version": "2.0",
        "rawPath": "/shorten",
        "requestContext": {
            "requestId": "gw-1",
            "domainName": "abc.execute-api.us-east-1.amazonaws.com",
            "stage": "$default",
            "http": {"method": method, "path": "/shorten"},
        },
        "body": raw,
        "isBase64Encoded": encoded,
    }


def test_shorten_contract_uses_the_configured_base_url() -> None:
    repo = InMemoryUrlRepository()
    response = handle_shorten_event(
        _http_event({"long_url": "https://example.com/article"}),
        Context(),
        SETTINGS,
        repo,
    )
    assert response["statusCode"] == 201
    payload = json.loads(response["body"])
    assert payload["long_url"] == "https://example.com/article"
    assert payload["short_url"] == f"https://short.example/r/{payload['short_code']}"
    assert payload["expires_at"] is None
    assert "request_id" not in payload
    assert response["headers"]["Cache-Control"] == "no-store"


def test_shorten_derives_the_default_stage_url() -> None:
    repo = InMemoryUrlRepository()
    response = handle_shorten_event(
        _http_event({"long_url": "https://example.com"}),
        None,
        Settings(table_name="local", public_base_url=""),
        repo,
    )
    payload = json.loads(response["body"])
    assert payload["short_url"].startswith("https://abc.execute-api.us-east-1.amazonaws.com/r/")


def test_named_stage_is_part_of_the_derived_url() -> None:
    event = _http_event({"long_url": "https://example.com"})
    event["requestContext"]["stage"] = "prod"
    response = handle_shorten_event(
        event,
        None,
        Settings(table_name="local", public_base_url=""),
        InMemoryUrlRepository(),
    )
    payload = json.loads(response["body"])
    assert payload["short_url"].startswith(
        "https://abc.execute-api.us-east-1.amazonaws.com/prod/r/"
    )


def test_base64_body_is_accepted() -> None:
    response = handle_shorten_event(
        _http_event({"long_url": "https://example.com/b64"}, encoded=True),
        None,
        SETTINGS,
        InMemoryUrlRepository(),
    )
    assert response["statusCode"] == 201


def test_invalid_input_is_a_stable_error_contract() -> None:
    cases = [
        ({"long_url": "http://127.0.0.1"}, 400, "invalid_url"),
        ({"long_url": "https://example.com", "expires_in_days": 0}, 400, "invalid_expiration"),
        ({"long_url": "https://example.com", "expires_in_days": True}, 400, "invalid_expiration"),
        ("{", 400, "invalid_json"),
        (None, 400, "invalid_json"),
    ]
    for body, status, code in cases:
        response = handle_shorten_event(
            _http_event(body),
            Context(),
            SETTINGS,
            InMemoryUrlRepository(),
        )
        payload = json.loads(response["body"])
        assert response["statusCode"] == status
        assert payload["code"] == code
        assert payload["request_id"] == "req-123"
        assert "Traceback" not in response["body"]
        assert "dynamodb" not in response["body"].lower()


def test_wrong_method_is_405() -> None:
    response = handle_shorten_event(
        _http_event({"long_url": "https://example.com"}, method="GET"),
        None,
        SETTINGS,
        InMemoryUrlRepository(),
    )
    assert response["statusCode"] == 405
    assert response["headers"]["Allow"] == "POST"


def test_repository_failure_does_not_leak() -> None:
    class Down(InMemoryUrlRepository):
        def create(self, record):
            raise RepositoryError("dynamodb_put_failed: sensitive table details")

    response = handle_shorten_event(
        _http_event({"long_url": "https://example.com"}),
        None,
        SETTINGS,
        Down(),
    )
    assert response["statusCode"] == 503
    assert "sensitive" not in response["body"]
    assert json.loads(response["body"])["code"] == "dependency_failure"


def test_direct_invoke_still_works() -> None:
    response = handle_shorten_event(
        {"long_url": "https://example.com/direct"},
        None,
        SETTINGS,
        InMemoryUrlRepository(),
    )
    assert response["statusCode"] == 201


def _redirect_event(code: str, method: str = "GET") -> dict:
    return {
        "version": "2.0",
        "rawPath": f"/r/{code}",
        "pathParameters": {"code": code},
        "requestContext": {
            "requestId": "redir-1",
            "domainName": "abc.execute-api.us-east-1.amazonaws.com",
            "stage": "$default",
            "http": {"method": method, "path": f"/r/{code}"},
        },
    }


def test_redirect_is_an_http_302_without_html() -> None:
    repo = InMemoryUrlRepository()
    created = json.loads(
        handle_shorten_event(
            _http_event({"long_url": "https://example.com/target?q=1"}),
            None,
            SETTINGS,
            repo,
        )["body"]
    )
    response = handle_redirect_event(
        _redirect_event(created["short_code"].lower()), None, SETTINGS, repo
    )
    assert response["statusCode"] == 302
    assert response["headers"]["Location"] == "https://example.com/target?q=1"
    body = response["body"].lower()
    assert "<" not in response["body"]
    assert "meta" not in body
    assert "refresh" not in body
    assert response["headers"]["Cache-Control"] == "no-store"


def test_redirect_error_statuses() -> None:
    repo = InMemoryUrlRepository()
    missing = handle_redirect_event(_redirect_event("ABCDEF"), None, SETTINGS, repo)
    assert missing["statusCode"] == 404
    assert "<" not in missing["body"]
    invalid = handle_redirect_event(_redirect_event("no"), None, SETTINGS, repo)
    assert invalid["statusCode"] == 400
    wrong_method = handle_redirect_event(
        _redirect_event("ABCDEF", method="POST"), None, SETTINGS, repo
    )
    assert wrong_method["statusCode"] == 405


def test_expired_redirect_is_410() -> None:
    repo = InMemoryUrlRepository()
    created = json.loads(
        handle_shorten_event(
            _http_event({"long_url": "https://example.com", "expires_in_days": 1}),
            None,
            SETTINGS,
            repo,
        )["body"]
    )
    # Move the stored expiry into the past without waiting.
    record = repo.get(created["short_code"])
    assert record is not None
    from urlshortener.repository import LinkRecord

    repo._items[record.short_code] = LinkRecord(  # type: ignore[attr-defined]
        short_code=record.short_code,
        long_url=record.long_url,
        created_at=record.created_at,
        expires_at=1,
    )
    response = handle_redirect_event(_redirect_event(record.short_code), None, SETTINGS, repo)
    assert response["statusCode"] == 410
    assert "Location" not in response["headers"]
