"""Typed failures the recording domain raises; the router maps them to problems."""

from __future__ import annotations


class RecordingInputError(ValueError):
    """The request cannot be accepted as typed. ``code`` is the problem code."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


class StaleVersion(Exception):
    """The caller's expected version or revision no longer matches storage."""


class IdempotencyConflict(Exception):
    """The idempotency key was already used with a different request identity."""


class AccountNotFound(Exception):
    """No account with that id belongs to the caller."""


class RegisteredAccountRequired(Exception):
    """Storage refused the write because the owner is not a registered user."""
