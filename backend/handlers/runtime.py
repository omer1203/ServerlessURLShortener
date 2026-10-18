"""Shared Lambda cold-start wiring."""

from __future__ import annotations

from urlshortener.config import Settings, load_settings
from urlshortener.errors import ConfigurationError
from urlshortener.log import configure_logging
from urlshortener.repository import DynamoUrlRepository, UrlRepository

_settings: Settings | None = None
_repository: UrlRepository | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = load_settings()
        configure_logging(_settings.log_level)
    return _settings


def get_repository() -> UrlRepository:
    global _repository
    if _repository is None:
        settings = get_settings()
        if not settings.table_name:
            raise ConfigurationError("TABLE_NAME is not set")
        _repository = DynamoUrlRepository.from_env()
    return _repository


def resolve_dependencies(
    repo: UrlRepository | None,
    settings: Settings | None,
) -> tuple[Settings, UrlRepository]:
    resolved_settings = settings if settings is not None else get_settings()
    if settings is not None:
        configure_logging(resolved_settings.log_level)
    if repo is not None:
        return resolved_settings, repo
    return resolved_settings, get_repository()
