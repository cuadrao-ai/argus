"""Behavior both connection repositories must share.

Imported by the in-memory module and the real-Postgres module so the twin and
the database are held to one specification, not two copies of it.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from argus.domain.ingestion.connections import (
    ConnectionNotFound,
    DuplicateConnection,
)
from argus.domain.owner_scope import PERSONAL

NOW = datetime(2026, 10, 1, 13, 0, tzinfo=timezone.utc)


def make(repo, user, ref="item-1", source="plaid", secret=b"sealed"):
    return repo.create(
        user_id=user,
        source=source,
        external_ref=ref,
        label="Chase",
        now=NOW,
        secret=secret,
        scope=PERSONAL,
    )


def test_one_live_connection_per_reference_and_reconnect_after_disconnect(repo, users):
    first = make(repo, users["owner"])
    with pytest.raises(DuplicateConnection) as caught:
        make(repo, users["owner"])
    assert caught.value.existing_id == first.id
    # Nobody else can hold the same provider grant while it is live.
    with pytest.raises(DuplicateConnection) as elsewhere:
        make(repo, users["other"])
    assert elsewhere.value.elsewhere and elsewhere.value.existing_id == ""
    repo.disconnect(user_id=users["owner"], connection_id=first.id, now=NOW)
    again = make(repo, users["owner"])
    assert again.id != first.id and again.status == "active"


def test_reads_are_owner_scoped(repo, users):
    row = make(repo, users["owner"])
    assert [c.id for c in repo.list(user_id=users["owner"], scope=PERSONAL)] == [row.id]
    assert repo.list(user_id=users["other"], scope=PERSONAL) == []
    with pytest.raises(ConnectionNotFound):
        repo.get(user_id=users["other"], connection_id=row.id, scope=PERSONAL)
    with pytest.raises(ConnectionNotFound):
        repo.get(user_id=users["owner"], connection_id="not-a-uuid", scope=PERSONAL)
    with pytest.raises(ConnectionNotFound):
        repo.disconnect(user_id=users["other"], connection_id=row.id, now=NOW)
    assert (
        repo.get(user_id=users["owner"], connection_id=row.id, scope=PERSONAL).status
        == "active"
    )


def test_webhook_lookup_finds_only_live_connections(repo, users):
    row = make(repo, users["owner"], ref="item-hook")
    assert [c.id for c in repo.find_live(source="plaid", external_ref="item-hook")] == [
        row.id
    ]
    assert repo.find_live(source="gmail", external_ref="item-hook") == []
    repo.disconnect(user_id=users["owner"], connection_id=row.id, now=NOW)
    assert repo.find_live(source="plaid", external_ref="item-hook") == []


def test_lease_is_exclusive_until_released_or_expired(repo, users):
    row = make(repo, users["owner"])
    assert repo.lease(connection_id=row.id, holder="a", now=NOW)
    assert not repo.lease(connection_id=row.id, holder="b", now=NOW)
    assert repo.lease(connection_id=row.id, holder="a", now=NOW)  # renew
    later = NOW + timedelta(minutes=6)
    assert repo.lease(connection_id=row.id, holder="b", now=later)  # expired
    repo.release(connection_id=row.id, holder="a")  # stale holder: no effect
    assert not repo.lease(connection_id=row.id, holder="c", now=later)
    repo.release(connection_id=row.id, holder="b")
    assert repo.lease(connection_id=row.id, holder="c", now=later)


def test_concurrent_lease_has_one_winner(repo, users):
    row = make(repo, users["owner"])
    with ThreadPoolExecutor(max_workers=8) as pool:
        won = list(
            pool.map(
                lambda i: repo.lease(connection_id=row.id, holder=f"h{i}", now=NOW),
                range(8),
            )
        )
    assert won.count(True) == 1


def test_cursor_advances_only_by_compare_and_set_under_the_lease(repo, users):
    row = make(repo, users["owner"])
    assert repo.lease(connection_id=row.id, holder="a", now=NOW)
    assert not repo.record_success(
        connection_id=row.id, holder="b", expected_cursor=None, cursor="c1", now=NOW
    )
    assert repo.record_success(
        connection_id=row.id, holder="a", expected_cursor=None, cursor="c1", now=NOW
    )
    # A stale sync that started from the old cursor cannot rewind it.
    assert not repo.record_success(
        connection_id=row.id, holder="a", expected_cursor=None, cursor="c0", now=NOW
    )
    current = repo.get(user_id=users["owner"], connection_id=row.id, scope=PERSONAL)
    assert current.cursor == "c1" and current.last_success_at == NOW


def test_failure_keeps_old_freshness_and_cursor(repo, users):
    row = make(repo, users["owner"])
    repo.lease(connection_id=row.id, holder="a", now=NOW)
    repo.record_success(
        connection_id=row.id, holder="a", expected_cursor=None, cursor="c1", now=NOW
    )
    later = NOW + timedelta(hours=3)
    failed = repo.record_failure(
        connection_id=row.id, code="item_login_required", status="needs_reauth", now=later
    )
    assert failed.status == "needs_reauth"
    assert failed.last_success_at == NOW and failed.cursor == "c1"
    assert failed.last_attempt_at == later
    assert failed.last_error_code == "item_login_required"
    # Re-authenticating stores the new credential and clears the failure.
    fixed = repo.set_secret(
        connection_id=row.id, secret=b"new", status="active", now=later
    )
    assert fixed.status == "active" and fixed.last_error_code is None
    assert fixed.secret == b"new" and fixed.cursor == "c1"


def test_disconnect_clears_credential_cursor_and_lease_and_is_idempotent(repo, users):
    row = make(repo, users["owner"])
    repo.lease(connection_id=row.id, holder="a", now=NOW)
    repo.record_success(
        connection_id=row.id, holder="a", expected_cursor=None, cursor="c1", now=NOW
    )
    ended = repo.disconnect(user_id=users["owner"], connection_id=row.id, now=NOW)
    assert ended.status == "disconnected" and ended.disconnected_at == NOW
    assert ended.secret is None and ended.cursor is None and ended.lease_holder is None
    assert ended.last_success_at == NOW  # history of freshness is kept
    again = repo.disconnect(user_id=users["owner"], connection_id=row.id, now=NOW)
    assert again.version == ended.version
    # A disconnected connection cannot sync or take a credential again.
    assert not repo.lease(connection_id=row.id, holder="a", now=NOW)
    with pytest.raises(ConnectionNotFound):
        repo.set_secret(connection_id=row.id, secret=b"x", status="active", now=NOW)
    with pytest.raises(ConnectionNotFound):
        repo.record_failure(connection_id=row.id, code="x", status="error", now=NOW)


def test_attention_survives_successful_syncs_until_reauthorization(repo, users):
    row = make(repo, users["owner"])
    flagged = repo.flag_attention(
        connection_id=row.id, code="plaid_pending_expiration", now=NOW
    )
    assert flagged.attention_code == "plaid_pending_expiration"
    assert repo.lease(connection_id=row.id, holder="a", now=NOW)
    assert repo.record_success(
        connection_id=row.id, holder="a", expected_cursor=None, cursor="c1", now=NOW
    )
    synced = repo.get(user_id=users["owner"], connection_id=row.id, scope=PERSONAL)
    assert synced.status == "active"
    assert synced.attention_code == "plaid_pending_expiration"
    renewed = repo.set_secret(connection_id=row.id, secret=b"n", status="active", now=NOW)
    assert renewed.attention_code is None and renewed.attention_at is None
    repo.flag_attention(connection_id=row.id, code="plaid_pending_expiration", now=NOW)
    ended = repo.disconnect(user_id=users["owner"], connection_id=row.id, now=NOW)
    assert ended.attention_code is None
    with pytest.raises(ConnectionNotFound):
        repo.flag_attention(connection_id=row.id, code="x", now=NOW)


def test_failure_reported_during_a_sync_wins_over_that_sync_finishing(repo, users):
    """A webhook marks re-authorization needed while a sync is in flight; the
    finishing sync must not flip the connection back to active."""

    row = make(repo, users["owner"])
    assert repo.lease(connection_id=row.id, holder="sync", now=NOW)
    repo.record_failure(
        connection_id=row.id,
        code="plaid_item_login_required",
        status="needs_reauth",
        now=NOW,
    )
    assert not repo.record_success(
        connection_id=row.id, holder="sync", expected_cursor=None, cursor="c1", now=NOW
    )
    current = repo.get(user_id=users["owner"], connection_id=row.id, scope=PERSONAL)
    assert current.status == "needs_reauth" and current.cursor is None
    assert current.last_error_code == "plaid_item_login_required"


def test_renew_extends_only_a_lease_still_held(repo, users):
    row = make(repo, users["owner"])
    assert not repo.renew(connection_id=row.id, holder="sync", now=NOW)
    assert repo.lease(connection_id=row.id, holder="sync", now=NOW)
    assert repo.renew(connection_id=row.id, holder="sync", now=NOW + timedelta(minutes=4))
    # A failure releases the lease; renewing must not take it back.
    repo.record_failure(connection_id=row.id, code="x", status="needs_reauth", now=NOW)
    assert not repo.renew(connection_id=row.id, holder="sync", now=NOW)
    assert (
        repo.get(
            user_id=users["owner"], connection_id=row.id, scope=PERSONAL
        ).lease_holder
        is None
    )
    assert repo.lease(connection_id=row.id, holder="other", now=NOW)
    assert not repo.renew(connection_id=row.id, holder="sync", now=NOW)


def test_stale_sync_failure_cannot_overwrite_a_newer_sync(repo, users):
    """A sync that lost its lease reports a failure after another sync
    succeeded: the failure is fenced off. Provider signals (webhooks) pass no
    holder and still apply."""

    row = make(repo, users["owner"])
    assert repo.lease(connection_id=row.id, holder="a", now=NOW)
    later = NOW + timedelta(minutes=6)
    assert repo.lease(connection_id=row.id, holder="b", now=later)
    assert repo.record_success(
        connection_id=row.id, holder="b", expected_cursor=None, cursor="c1", now=later
    )
    stale = repo.record_failure(
        connection_id=row.id,
        code="plaid_unavailable",
        status="error",
        now=later,
        holder="a",
    )
    assert stale.status == "active" and stale.last_error_code is None
    signal = repo.record_failure(
        connection_id=row.id,
        code="plaid_item_login_required",
        status="needs_reauth",
        now=later,
    )
    assert signal.status == "needs_reauth"


@pytest.mark.parametrize(
    "field, value",
    [
        ("external_ref", "x" * 201),
        ("external_ref", ""),
    ],
)
def test_both_repositories_refuse_values_storage_cannot_hold(repo, users, field, value):
    values = {"external_ref": "item-1"} | {field: value}
    with pytest.raises(ValueError):
        repo.create(
            user_id=users["owner"],
            source="plaid",
            label=None,
            now=NOW,
            **values,
            scope=PERSONAL,
        )


def test_labels_are_normalized_identically_and_codes_and_cursors_checked(repo, users):
    row = repo.create(
        user_id=users["owner"], source="plaid", external_ref="item-l",
        label="Banco‮ " + "x" * 200, now=NOW, scope=PERSONAL,
    )  # fmt: skip
    assert len(row.label) <= 80 and "‮" not in row.label
    with pytest.raises(ValueError):
        repo.record_failure(
            connection_id=row.id, code="Bad Code!", status="error", now=NOW
        )
    with pytest.raises(ValueError):
        repo.flag_attention(connection_id=row.id, code="x" * 65, now=NOW)
    assert repo.lease(connection_id=row.id, holder="h", now=NOW)
    with pytest.raises(ValueError):
        repo.record_success(
            connection_id=row.id,
            holder="h",
            expected_cursor=None,
            cursor="c" * 4097,
            now=NOW,
        )
    with pytest.raises(ValueError):
        repo.lease(connection_id=row.id, holder="h" * 65, now=NOW)
