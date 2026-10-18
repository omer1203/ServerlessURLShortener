from __future__ import annotations

import json
import logging

from urlshortener.log import configure_logging, log_event


def test_logs_are_structured_and_omit_destinations() -> None:
    configure_logging("INFO")
    logger = logging.getLogger("shortlink")
    messages: list[str] = []

    class ListHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            messages.append(record.getMessage())

    handler = ListHandler()
    logger.addHandler(handler)
    try:
        log_event(
            "info",
            "link_created",
            short_code="ABC123",
            long_url="https://secret.example/private-path",
            location="https://secret.example/private-path",
        )
    finally:
        logger.removeHandler(handler)

    payload = json.loads(messages[-1])
    assert payload["event"] == "link_created"
    assert payload["short_code"] == "ABC123"
    assert "secret.example" not in messages[-1]
    assert "long_url" not in payload
