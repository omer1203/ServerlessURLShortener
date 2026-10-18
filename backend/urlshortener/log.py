"""JSON logs for CloudWatch.

Destination URLs are not logged. The mapping is the sensitive part of a
shortener: access logs would otherwise retain every link people create.
"""

from __future__ import annotations

import json
import logging
import traceback

LOGGER_NAME = "shortlink"
_REDACTED_KEYS = frozenset({"long_url", "url", "location", "destination", "authorization", "body"})
_configured = False


def configure_logging(level: str) -> None:
    """Attach one JSON formatter. Safe to call on a warm Lambda container."""
    global _configured
    logger = logging.getLogger(LOGGER_NAME)
    numeric = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(numeric)
    if _configured:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.propagate = False
    _configured = True


def log_event(level: str, event: str, **fields: object) -> None:
    logger = logging.getLogger(LOGGER_NAME)
    payload: dict[str, object] = {"level": level.lower(), "event": event}
    for key, value in fields.items():
        if key in _REDACTED_KEYS:
            continue
        if isinstance(value, str) and len(value) > 300:
            continue
        payload[key] = value
    numeric = getattr(logging, level.upper(), logging.INFO)
    logger.log(numeric, json.dumps(payload, default=str, separators=(",", ":")))


def log_exception(event: str, exc: BaseException, **fields: object) -> None:
    frames = traceback.extract_tb(exc.__traceback__)
    trace = " | ".join(f"{frame.name}:{frame.lineno}" for frame in frames[-6:])
    log_event(
        "error",
        event,
        error_type=type(exc).__name__,
        trace=trace,
        **fields,
    )
