from __future__ import annotations

from urlshortener.codes import CODE_ALPHABET, CODE_LENGTH, generate_code, normalize_code
from urlshortener.errors import CodeGenerationExhausted, InvalidExpiration
from urlshortener.repository import InMemoryUrlRepository, LinkRecord
from urlshortener.service import Outcome, create_link, resolve_redirect


def test_generated_codes_use_the_public_alphabet() -> None:
    for _ in range(50):
        code = generate_code()
        assert len(code) == CODE_LENGTH
        assert all(char in CODE_ALPHABET for char in code)
        assert normalize_code(code.lower()) == code


def test_normalize_code_rejects_wrong_shape() -> None:
    assert normalize_code("abc12") is None
    assert normalize_code("ABC1234") is None
    assert normalize_code("AB-123") is None
    assert normalize_code("   ") is None


def test_create_retries_collisions_then_stores_the_normalized_url() -> None:
    repo = InMemoryUrlRepository()
    repo.create(LinkRecord(short_code="AAAAAA", long_url="https://example.com/old", created_at=1))
    codes = iter(["AAAAAA", "BBBBBB"])
    created = create_link(
        repo,
        " HTTP://Example.COM/New ",
        now=1_700_000_000,
        code_factory=lambda: next(codes),
    )
    assert created.short_code == "BBBBBB"
    assert created.long_url == "http://example.com/New"
    assert created.expires_at is None
    assert repo.get("AAAAAA") is not None


def test_create_stops_after_the_attempt_budget() -> None:
    repo = InMemoryUrlRepository()
    repo.create(LinkRecord(short_code="AAAAAA", long_url="https://example.com", created_at=1))
    try:
        create_link(
            repo,
            "https://example.com/new",
            now=10,
            code_factory=lambda: "AAAAAA",
            max_attempts=5,
        )
    except CodeGenerationExhausted:
        pass
    else:
        raise AssertionError("expected the attempt budget to be exhausted")
    stored = repo.get("AAAAAA")
    assert stored is not None
    assert stored.long_url == "https://example.com"


def test_expiration_is_a_whole_number_of_days() -> None:
    repo = InMemoryUrlRepository()
    created = create_link(
        repo,
        "https://example.com/a",
        expires_in_days=7,
        now=1_000,
        code_factory=lambda: "ABCDEF",
    )
    assert created.expires_at == 1_000 + 7 * 86400
    assert repo.get("ABCDEF").to_item()["ttl"] == created.expires_at  # type: ignore[union-attr]


def test_expiration_rejects_bools_and_out_of_range_values() -> None:
    repo = InMemoryUrlRepository()
    for bad in (True, 0, 366, -1):
        try:
            create_link(
                repo, "https://example.com", expires_in_days=bad, code_factory=lambda: "ZZZZZZ"
            )
        except InvalidExpiration:
            continue
        raise AssertionError(f"accepted invalid expiration {bad!r}")


def test_redirect_known_code_and_counts_a_click() -> None:
    repo = InMemoryUrlRepository()
    create_link(repo, "https://example.com/dest?x=1", now=50, code_factory=lambda: "ABC123")
    decision = resolve_redirect(repo, "abc123", now=80)
    assert decision.outcome is Outcome.REDIRECT
    assert decision.location == "https://example.com/dest?x=1"
    stored = repo.get("ABC123")
    assert stored is not None
    assert stored.clicks == 1
    assert stored.last_accessed == 80


def test_unknown_and_malformed_codes() -> None:
    repo = InMemoryUrlRepository()
    missing = resolve_redirect(repo, "ABCDEF", now=1)
    assert missing.outcome is Outcome.NOT_FOUND
    malformed = resolve_redirect(repo, "nope", now=1)
    assert malformed.outcome is Outcome.INVALID_CODE
    assert resolve_redirect(repo, "x" * 80, now=1).outcome is Outcome.INVALID_CODE


def test_expired_link_does_not_redirect_or_count() -> None:
    repo = InMemoryUrlRepository()
    create_link(
        repo,
        "https://example.com/gone",
        expires_in_days=1,
        now=1_000,
        code_factory=lambda: "GONE01",
    )
    decision = resolve_redirect(repo, "GONE01", now=1_000 + 86400)
    assert decision.outcome is Outcome.EXPIRED
    assert repo.get("GONE01").clicks == 0  # type: ignore[union-attr]


def test_click_failure_still_redirects() -> None:
    class BrokenClicks(InMemoryUrlRepository):
        def record_click(self, short_code: str, accessed_at: int) -> bool:
            from urlshortener.errors import RepositoryError

            raise RepositoryError("dynamodb_update_failed")

    repo = BrokenClicks()
    create_link(repo, "https://example.com/ok", now=5, code_factory=lambda: "OKOKOK")
    decision = resolve_redirect(repo, "OKOKOK", now=6)
    assert decision.outcome is Outcome.REDIRECT
    assert decision.location == "https://example.com/ok"


def test_missing_row_during_click_update_still_redirects() -> None:
    repo = InMemoryUrlRepository()
    create_link(repo, "https://example.com/ok", now=5, code_factory=lambda: "STILL1")

    class VanishOnClick(InMemoryUrlRepository):
        def get(self, short_code: str):
            return repo.get(short_code)

        def record_click(self, short_code: str, accessed_at: int) -> bool:
            return False

    decision = resolve_redirect(VanishOnClick(), "STILL1", now=9)
    assert decision.outcome is Outcome.REDIRECT


def test_refuses_to_redirect_a_header_breaking_stored_url() -> None:
    repo = InMemoryUrlRepository()
    repo.create(
        LinkRecord(
            short_code="BADURL",
            long_url="https://example.com/\r\nLocation: https://evil.example",
            created_at=1,
        )
    )
    from urlshortener.errors import RepositoryError

    try:
        resolve_redirect(repo, "BADURL", now=2)
    except RepositoryError as exc:
        assert exc.reason == "unsafe_location"
    else:
        raise AssertionError("unsafe location was accepted")
