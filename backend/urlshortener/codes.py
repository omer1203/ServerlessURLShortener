"""Short-code alphabet and generator.

Codes are 6 characters from an uppercase alphanumeric alphabet: 36^6 =
2,176,782,336 possibilities. `secrets` is used so codes are not predictable
from process state. Uniqueness is not a property of the generator. Callers
must still use a conditional write and a bounded retry.
"""

from __future__ import annotations

import re
import secrets

CODE_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
CODE_LENGTH = 6
MAX_ATTEMPTS = 5
CODE_PATTERN = re.compile(rf"^[{CODE_ALPHABET}]{{{CODE_LENGTH}}}$")


def generate_code(
    *,
    length: int = CODE_LENGTH,
    alphabet: str = CODE_ALPHABET,
    chooser: object | None = None,
) -> str:
    """Return one new code. Pass `chooser` only from tests."""
    pick = secrets.choice if chooser is None else chooser
    if not callable(pick):
        raise TypeError("chooser must be callable")
    return "".join(pick(alphabet) for _ in range(length))


def normalize_code(raw: str) -> str | None:
    """Return the canonical code, or None when the value cannot be a code.

    Lookup is case-insensitive because the generator only emits uppercase.
    Over-long input is rejected before it is logged or used as a key.
    """
    if not isinstance(raw, str):
        return None
    candidate = raw.strip().upper()
    if len(candidate) != CODE_LENGTH:
        return None
    if CODE_PATTERN.fullmatch(candidate) is None:
        return None
    return candidate
