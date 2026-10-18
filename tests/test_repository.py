from __future__ import annotations

from urlshortener.errors import CodeAlreadyExists, RepositoryError
from urlshortener.repository import DynamoUrlRepository, InMemoryUrlRepository, LinkRecord


class _AwsError(Exception):
    def __init__(self, code: str, message: str = "internal table message") -> None:
        super().__init__(message)
        self.response = {"Error": {"Code": code, "Message": message}}


class StubTable:
    def __init__(self) -> None:
        self.puts: list[dict] = []
        self.gets: list[dict] = []
        self.updates: list[dict] = []
        self.fail_put: str | None = None
        self.fail_update: str | None = None
        self.item: dict | None = None

    def put_item(self, **kwargs: object) -> None:
        self.puts.append(kwargs)
        if self.fail_put:
            raise _AwsError(self.fail_put)

    def get_item(self, **kwargs: object) -> dict:
        self.gets.append(kwargs)
        if self.item is None:
            return {}
        return {"Item": self.item}

    def update_item(self, **kwargs: object) -> None:
        self.updates.append(kwargs)
        if self.fail_update:
            raise _AwsError(self.fail_update)


def _record() -> LinkRecord:
    return LinkRecord(
        short_code="ABC123",
        long_url="https://example.com/a",
        created_at=10,
        expires_at=20,
    )


def test_memory_create_is_conditional() -> None:
    repo = InMemoryUrlRepository()
    repo.create(_record())
    try:
        repo.create(_record())
    except CodeAlreadyExists:
        pass
    else:
        raise AssertionError("existing code was overwritten")


def test_memory_click_does_not_recreate_a_deleted_code() -> None:
    repo = InMemoryUrlRepository()
    assert repo.record_click("MISSING", 10) is False


def test_dynamo_create_uses_a_conditional_put() -> None:
    table = StubTable()
    DynamoUrlRepository(table).create(_record())
    assert table.puts[0]["ConditionExpression"] == "attribute_not_exists(short_code)"
    item = table.puts[0]["Item"]
    assert item["ttl"] == 20
    assert item["expires_at"] == 20


def test_dynamo_collision_is_not_a_repository_failure() -> None:
    table = StubTable()
    table.fail_put = "ConditionalCheckFailedException"
    try:
        DynamoUrlRepository(table).create(_record())
    except CodeAlreadyExists:
        pass
    else:
        raise AssertionError("conditional failure was not mapped")


def test_dynamo_errors_hide_the_provider_message() -> None:
    table = StubTable()
    table.fail_put = "ProvisionedThroughputExceededException"
    try:
        DynamoUrlRepository(table).create(_record())
    except RepositoryError as exc:
        assert exc.reason == "dynamodb_put_failed"
        assert "internal table message" not in exc.reason
    else:
        raise AssertionError("provider error was not mapped")


def test_dynamo_get_is_strongly_consistent_and_converts_numbers() -> None:
    table = StubTable()
    table.item = {
        "short_code": "ABC123",
        "long_url": "https://example.com/a",
        "created_at": _Decimal(10),
        "clicks": _Decimal(2),
        "expires_at": _Decimal(40),
    }
    record = DynamoUrlRepository(table).get("ABC123")
    assert table.gets[0]["ConsistentRead"] is True
    assert record is not None
    assert record.created_at == 10
    assert record.clicks == 2
    assert record.expires_at == 40


def test_dynamo_click_requires_the_item_to_exist() -> None:
    table = StubTable()
    assert DynamoUrlRepository(table).record_click("ABC123", 99) is True
    update = table.updates[0]
    assert update["ConditionExpression"] == "attribute_exists(short_code)"
    assert update["UpdateExpression"] == "ADD clicks :one SET last_accessed = :ts"
    assert update["ExpressionAttributeValues"] == {":one": 1, ":ts": 99}

    table.fail_update = "ConditionalCheckFailedException"
    assert DynamoUrlRepository(table).record_click("ABC123", 100) is False


class _Decimal:
    """Stand-in for boto3's Decimal values without importing boto3."""

    def __init__(self, value: int) -> None:
        self.value = value

    def __int__(self) -> int:
        return self.value
