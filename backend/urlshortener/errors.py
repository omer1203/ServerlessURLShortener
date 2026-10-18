"""Errors that cross the boundary between domain code and HTTP handlers."""

from __future__ import annotations


class AppError(Exception):
    """Base class for failures that have a safe, public message."""

    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


class BadRequest(AppError):
    """The caller sent a request the API contract rejects."""


class MethodNotAllowed(AppError):
    def __init__(self) -> None:
        super().__init__("method_not_allowed", "Method not allowed.", status=405)


class InvalidUrl(BadRequest):
    def __init__(self, message: str) -> None:
        super().__init__("invalid_url", message)


class InvalidExpiration(BadRequest):
    def __init__(self) -> None:
        super().__init__(
            "invalid_expiration",
            "Expiration must be a whole number of days from 1 to 365.",
        )


class CodeAlreadyExists(Exception):
    """A conditional write lost the race for this short code."""


class CodeGenerationExhausted(Exception):
    """Every bounded attempt to allocate a short code collided."""


class RepositoryError(Exception):
    """The datastore failed. The reason is an internal token, not a user message."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class ConfigurationError(Exception):
    """The process is missing or has invalid runtime configuration."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
