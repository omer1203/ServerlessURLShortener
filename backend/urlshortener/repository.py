"""Persistence for short-code mappings.

Both implementations honor the same contract:

- create fails when the code already exists, instead of overwriting it
- get returns the current mapping or None
- record_click is conditional on the item still existing

The DynamoDB implementation uses a condition expression for that last point.
An UpdateItem that only sets a key would recreate a partial item if a mapping
were deleted between the read and the click update.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from typing import Protocol

from urlshortener.errors import CodeAlreadyExists, RepositoryError


@dataclass(frozen=True)
class LinkRecord:
    short_code: str
    long_url: str
    created_at: int
    expires_at: int | None = None
    clicks: int = 0
    last_accessed: int | None = None

    def to_item(self) -> dict[str, object]:
        item: dict[str, object] = {
            "short_code": self.short_code,
            "long_url": self.long_url,
            "created_at": self.created_at,
            "clicks": self.clicks,
        }
        # ttl matches expires_at so DynamoDB can delete the row later.
        # Deletion is asynchronous; reads still check expires_at.
        if self.expires_at is not None:
            item["expires_at"] = self.expires_at
            item["ttl"] = self.expires_at
        if self.last_accessed is not None:
            item["last_accessed"] = self.last_accessed
        return item


class UrlRepository(Protocol):
    def create(self, record: LinkRecord) -> None: ...

    def get(self, short_code: str) -> LinkRecord | None: ...

    def record_click(self, short_code: str, accessed_at: int) -> bool: ...


class InMemoryUrlRepository:
    """Process-local repository used by the dev server and tests."""

    def __init__(self) -> None:
        self._items: dict[str, LinkRecord] = {}
        self._lock = threading.Lock()

    def create(self, record: LinkRecord) -> None:
        with self._lock:
            if record.short_code in self._items:
                raise CodeAlreadyExists(record.short_code)
            self._items[record.short_code] = record

    def get(self, short_code: str) -> LinkRecord | None:
        with self._lock:
            return self._items.get(short_code)

    def record_click(self, short_code: str, accessed_at: int) -> bool:
        with self._lock:
            current = self._items.get(short_code)
            if current is None:
                return False
            self._items[short_code] = LinkRecord(
                short_code=current.short_code,
                long_url=current.long_url,
                created_at=current.created_at,
                expires_at=current.expires_at,
                clicks=current.clicks + 1,
                last_accessed=accessed_at,
            )
            return True


class DynamoUrlRepository:
    """Adapter over a boto3 DynamoDB Table resource."""

    def __init__(self, table: object) -> None:
        self._table = table

    @classmethod
    def from_env(cls) -> DynamoUrlRepository:
        import boto3

        name = os.environ["TABLE_NAME"]
        return cls(boto3.resource("dynamodb").Table(name))

    def create(self, record: LinkRecord) -> None:
        try:
            self._table.put_item(  # type: ignore[attr-defined]
                Item=record.to_item(),
                ConditionExpression="attribute_not_exists(short_code)",
            )
        except Exception as exc:
            self._map_write_error(exc, "put")

    def get(self, short_code: str) -> LinkRecord | None:
        try:
            # Strongly consistent so a link can be opened immediately after creation.
            # The default eventually consistent read can 404 that first click.
            response = self._table.get_item(  # type: ignore[attr-defined]
                Key={"short_code": short_code},
                ConsistentRead=True,
            )
        except Exception as exc:
            self._map_write_error(exc, "get")
            return None
        item = response.get("Item") if isinstance(response, dict) else None
        if not item:
            return None
        return link_from_item(item)

    def record_click(self, short_code: str, accessed_at: int) -> bool:
        try:
            self._table.update_item(  # type: ignore[attr-defined]
                Key={"short_code": short_code},
                UpdateExpression="ADD clicks :one SET last_accessed = :ts",
                ConditionExpression="attribute_exists(short_code)",
                ExpressionAttributeValues={":one": 1, ":ts": accessed_at},
            )
        except Exception as exc:
            if _error_code(exc) == "ConditionalCheckFailedException":
                return False
            self._map_write_error(exc, "update")
        return True

    def _map_write_error(self, exc: Exception, operation: str) -> None:
        code = _error_code(exc)
        if code == "ConditionalCheckFailedException":
            raise CodeAlreadyExists() from exc
        if code is None:
            raise exc
        raise RepositoryError(f"dynamodb_{operation}_failed") from exc


def link_from_item(item: dict) -> LinkRecord:
    code = item.get("short_code")
    long_url = item.get("long_url")
    created_at = _as_int(item.get("created_at"))
    if not isinstance(code, str) or not isinstance(long_url, str) or created_at is None:
        raise RepositoryError("incomplete_item")
    raw_expiry = item.get("expires_at")
    expires_at = None if raw_expiry is None else _as_int(raw_expiry)
    if raw_expiry is not None and expires_at is None:
        raise RepositoryError("incomplete_item")
    clicks = _as_int(item.get("clicks"))
    last_raw = item.get("last_accessed")
    last_accessed = None if last_raw is None else _as_int(last_raw)
    return LinkRecord(
        short_code=code,
        long_url=long_url,
        created_at=created_at,
        expires_at=expires_at,
        clicks=0 if clicks is None else clicks,
        last_accessed=last_accessed,
    )


def _as_int(value: object) -> int | None:
    # bool is a subclass of int and is never a valid timestamp or counter.
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if hasattr(value, "__int__"):
        try:
            return int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
    return None


def _error_code(exc: Exception) -> str | None:
    response = getattr(exc, "response", None)
    if not isinstance(response, dict):
        return None
    error = response.get("Error")
    if not isinstance(error, dict):
        return None
    code = error.get("Code")
    return code if isinstance(code, str) else None
