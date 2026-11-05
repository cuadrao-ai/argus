"""Lane 6: account deletion revokes provider tokens from the captured ciphertext."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone

from argus.domain.ingestion.hub import IngestionHub
from argus.domain.ingestion.secrets import SecretBox


class _Adapter:
    def __init__(self, source: str, fail: bool = False, gone: bool = False) -> None:
        self.source = source
        self.fail = fail
        self.gone = gone
        self.revoked: list[str | None] = []

    def revoke(self, connection, credential):  # noqa: ANN001, ANN201
        self.revoked.append(credential)
        if self.fail:
            raise RuntimeError("provider down")
        return "already_revoked" if self.gone else None

    def forget(self, connection):  # noqa: ANN001
        raise AssertionError("deletion never touches connection rows")


def _hub(*adapters):  # noqa: ANN002
    hub = IngestionHub(
        None,  # type: ignore[arg-type]
        box=SecretBox(secrets.token_bytes(32)),
        sink=None,
        clock=lambda: datetime(2026, 10, 3, tzinfo=timezone.utc),
    )
    for adapter in adapters:
        hub.register(adapter)
    return hub


def test_gmail_and_plaid_tokens_are_opened_and_revoked():
    gmail, plaid = _Adapter("gmail"), _Adapter("plaid")
    hub = _hub(gmail, plaid)
    for adapter, token in ((gmail, "google-refresh"), (plaid, "access-sandbox")):
        envelope = hub.box.seal(token, source=adapter.source, connection_id="c-1")
        outcome = hub.revoke_for_deletion(
            source=adapter.source,
            connection_id="c-1",
            external_ref="x",
            envelope=envelope,
        )
        assert outcome == "revoked"
        assert adapter.revoked == [token]


def test_a_failed_revoke_stays_pending_and_an_unreadable_one_is_named():
    gmail = _Adapter("gmail", fail=True)
    hub = _hub(gmail)
    envelope = hub.box.seal("t", source="gmail", connection_id="c-1")
    assert (
        hub.revoke_for_deletion(
            source="gmail", connection_id="c-1", external_ref="x", envelope=envelope
        )
        == "failed"
    )
    # Sealed under another key or for another connection: it does not open
    # here. A wrong key on this process looks the same as a rotated-away key,
    # so the hub only names it; the deletion run's key check decides.
    other = _Adapter("gmail")
    assert (
        _hub(other).revoke_for_deletion(
            source="gmail", connection_id="c-1", external_ref="x", envelope=envelope
        )
        == "unreadable"
    )
    assert (
        _hub(gmail).revoke_for_deletion(
            source="gmail", connection_id="c-2", external_ref="x", envelope=envelope
        )
        == "unreadable"
    )
    assert other.revoked == []
    # A connector that is switched off cannot revoke: pending, not success.
    assert (
        _hub().revoke_for_deletion(
            source="plaid", connection_id="c-1", external_ref="x", envelope=b"\x01" * 40
        )
        == "failed"
    )
    assert (
        _hub().revoke_for_deletion(
            source="plaid", connection_id="c-1", external_ref="x", envelope=None
        )
        == "not_applicable"
    )


class _GoogleSaying:
    def __init__(self, status: int, error: str) -> None:
        self.status, self.error = status, error

    def revoke(self, token: str) -> None:
        from argus.domain.ingestion.gmail.client import GmailError

        raise GmailError(status=self.status, reason=self.error)


def test_google_answering_invalid_grant_or_invalid_token_counts_as_revoked():
    import pytest
    from argus.domain.ingestion.gmail.adapter import (
        GmailAdapter,
        GmailRevocationUnavailable,
    )

    for error in ("invalid_grant", "invalid_token"):
        GmailAdapter(_GoogleSaying(400, error), senders=None).revoke(None, "refresh")  # type: ignore[arg-type]
    with pytest.raises(GmailRevocationUnavailable):
        GmailAdapter(_GoogleSaying(503, "backend"), senders=None).revoke(None, "refresh")  # type: ignore[arg-type]


def test_a_grant_the_provider_no_longer_holds_is_already_revoked():
    gone = _Adapter("gmail", gone=True)
    hub = _hub(gone)
    envelope = hub.box.seal("t", source="gmail", connection_id="c-1")
    assert (
        hub.revoke_for_deletion(
            source="gmail", connection_id="c-1", external_ref="x", envelope=envelope
        )
        == "already_revoked"
    )
