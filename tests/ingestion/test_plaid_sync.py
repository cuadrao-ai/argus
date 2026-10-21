"""Plaid transaction sync: pagination, restarts, cursor safety and leases."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import httpx
from argus.domain.ingestion.plaid.config import PlaidConfig
from argus.domain.ingestion.plaid.connector import PlaidConnector
from argus.domain.owner_scope import PERSONAL

from tests.ingestion.plaid_fakes import (
    PUBLIC_TOKEN,
    FakePlaid,
    RecordingSink,
    make_connector,
    page,
    plaid_error,
    txn,
)

USER = "8d0f8a59-0000-4000-8000-000000000001"
MUTATION = plaid_error(
    "TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION", "TRANSACTIONS_ERROR"
)


def connected(fake: FakePlaid, sink: RecordingSink | None = None, **kwargs):
    connector = make_connector(fake, sink=sink, **kwargs)
    result = connector.link.exchange(user_id=USER, public_token=PUBLIC_TOKEN)
    return connector, result.connection


def stored(connector: PlaidConnector, connection):
    return connector.hub.connections.get(
        user_id=USER, connection_id=connection.id, scope=PERSONAL
    )


def test_pages_until_has_more_is_false_then_advances_once():
    fake = FakePlaid(
        sync={
            None: [page(added=[txn("t1", 4.5)], next_cursor="c1", has_more=True)],
            "c1": [page(added=[txn("t2", -1200)], next_cursor="c2", has_more=True)],
            "c2": [
                page(
                    removed=[{"transaction_id": "t0", "account_id": "acc-card"}],
                    next_cursor="c3",
                )
            ],
        }
    )
    sink = RecordingSink()
    connector, row = connected(fake, sink)
    outcome = connector.sync(row)
    assert (outcome.status, outcome.pages) == ("synced", 3)
    assert (outcome.added, outcome.removed) == (2, 1)
    assert len(sink.batches) == 1 and len(sink.batches[0]) == 3
    after = stored(connector, row)
    assert after.cursor == "c3" and after.last_success_at is not None
    assert after.lease_holder is None
    cursors = [
        body.get("cursor") for path, body, _ in fake.calls if path == "/transactions/sync"
    ]
    assert cursors == [None, "c1", "c2"]
    assert all(
        body["count"] == 500
        for path, body, _ in fake.calls
        if path == "/transactions/sync"
    )


def test_mutation_during_pagination_restarts_from_the_starting_cursor():
    fake = FakePlaid(
        sync={
            None: [page(added=[txn("t1", 4.5)], next_cursor="c1", has_more=True)],
            "c1": [MUTATION, page(added=[txn("t2", 9)], next_cursor="c2")],
        }
    )
    sink = RecordingSink()
    connector, row = connected(fake, sink)
    outcome = connector.sync(row)
    assert (outcome.status, outcome.restarts) == ("synced", 1)
    cursors = [
        body.get("cursor") for path, body, _ in fake.calls if path == "/transactions/sync"
    ]
    assert cursors == [None, "c1", None, "c1"]
    # Only the completed attempt reaches the sink.
    assert [c.source.external_id for c in sink.batches[0]] == ["t1", "t2"]
    assert stored(connector, row).cursor == "c2"


def test_mutation_restarts_are_bounded_and_keep_the_cursor():
    fake = FakePlaid(
        sync={
            None: [page(added=[txn("t1", 4.5)], next_cursor="c1", has_more=True)],
            "c1": [MUTATION],
        }
    )
    sink = RecordingSink()
    connector, row = connected(fake, sink)
    outcome = connector.sync(row)
    assert outcome.status == "failed"
    assert outcome.error_code == "plaid_transactions_sync_mutation_during_pagination"
    assert sum(1 for p in fake.paths() if p == "/transactions/sync") == 8
    after = stored(connector, row)
    assert after.cursor is None and after.status == "active"
    assert sink.batches == []


def test_sink_failure_or_absence_never_advances_the_cursor():
    fake = FakePlaid(sync={None: [page(added=[txn("t1", 4.5)], next_cursor="c1")]})
    sink = RecordingSink()
    sink.fail = True
    connector, row = connected(fake, sink)
    assert connector.sync(row).status == "sink_failed"
    assert stored(connector, row).cursor is None
    assert stored(connector, row).lease_holder is None

    connector.hub.sink = None
    calls = len(fake.calls)
    assert connector.sync(row).status == "no_sink"
    assert len(fake.calls) == calls  # refused before calling Plaid

    sink.fail = False
    connector.hub.sink = sink
    assert connector.sync(row).status == "synced"
    assert stored(connector, row).cursor == "c1"


def test_resync_is_idempotent_and_sends_nothing_new():
    fake = FakePlaid(
        sync={
            None: [page(added=[txn("t1", 4.5)], next_cursor="c1")],
            "c1": [page(next_cursor="c1")],
        }
    )
    sink = RecordingSink()
    connector, row = connected(fake, sink)
    connector.sync(row)
    again = connector.sync(stored(connector, row))
    assert (again.status, again.added, again.modified, again.removed) == (
        "synced",
        0,
        0,
        0,
    )
    assert stored(connector, row).cursor == "c1"


def test_not_ready_item_claims_no_freshness():
    fake = FakePlaid(sync={None: [page(next_cursor="", status="NOT_READY")]})
    connector, row = connected(fake, RecordingSink())
    assert connector.sync(row).status == "not_ready"
    after = stored(connector, row)
    assert after.cursor is None and after.last_success_at is None


def test_pending_then_posted_names_the_pending_row():
    fake = FakePlaid(
        sync={
            None: [
                page(
                    added=[
                        txn(
                            "p1",
                            58,
                            pending=True,
                            date="2026-09-30",
                            authorized_date="2026-09-30",
                        )
                    ],
                    next_cursor="c1",
                )
            ],
            "c1": [
                page(
                    added=[
                        txn(
                            "x1",
                            58,
                            pending_transaction_id="p1",
                            date="2026-10-01",
                            authorized_date="2026-09-30",
                        )
                    ],
                    removed=[{"transaction_id": "p1", "account_id": "acc-checking"}],
                    next_cursor="c2",
                )
            ],
        }
    )
    sink = RecordingSink()
    connector, row = connected(fake, sink)
    first = connector.sync(row)
    assert (first.pending, first.posted) == (1, 0)
    second = connector.sync(stored(connector, row))
    assert (second.posted, second.replacing, second.removed) == (1, 1, 1)
    posted = sink.evidence[("plaid", row.id, "x1")]
    assert posted.status == "posted" and posted.source.replaces_external_id == "p1"
    assert (
        str(posted.occurred_on) == "2026-09-30" and str(posted.posted_on) == "2026-10-01"
    )
    assert sink.evidence[("plaid", row.id, "p1")].status == "removed"


def test_concurrent_syncs_take_one_lease_and_advance_once():
    barrier = Barrier(2)

    class SlowFake(FakePlaid):
        def _transactions_sync(self, body):  # noqa: ANN001
            barrier.wait(timeout=5)
            return super()._transactions_sync(body)

    fake = SlowFake(sync={None: [page(added=[txn("t1", 4.5)], next_cursor="c1")]})
    sink = RecordingSink()
    connector, row = connected(fake, sink)
    # A second connector instance shares the repository: two processes.
    other = PlaidConnector(
        connector.hub,
        PlaidConfig(client_id="client-id", secret="plaid-secret-value"),
        transport=httpx.MockTransport(fake),
    )

    # Whoever finds the lease held releases the barrier for the holder.
    def guarded(c):  # noqa: ANN001
        outcome = c.sync(row)
        if outcome.status == "busy":
            barrier.wait(timeout=5)
        return outcome

    with ThreadPoolExecutor(2) as pool:
        outcomes = sorted(o.status for o in pool.map(guarded, [connector, other]))
    assert outcomes == ["busy", "synced"]
    assert len(sink.batches) == 1
    assert stored(connector, row).cursor == "c1"
    assert sum(1 for p in fake.paths() if p == "/transactions/sync") == 1


def test_item_login_required_marks_needs_reauth_and_keeps_freshness():
    fake = FakePlaid(sync={None: [page(added=[txn("t1", 4.5)], next_cursor="c1")]})
    sink = RecordingSink()
    connector, row = connected(fake, sink)
    connector.sync(row)
    before = stored(connector, row)
    fake.item_error = "ITEM_LOGIN_REQUIRED"
    connector.hub.clock.advance(hours=1)
    outcome = connector.sync(before)
    assert (outcome.status, outcome.error_code) == ("failed", "plaid_item_login_required")
    after = stored(connector, row)
    assert after.status == "needs_reauth"
    assert after.last_error_code == "plaid_item_login_required"
    assert after.last_success_at == before.last_success_at
    assert after.cursor == "c1" and after.lease_holder is None


def test_transient_provider_failure_keeps_status():
    fake = FakePlaid(sync={None: [plaid_error("INSTITUTION_DOWN", "INSTITUTION_ERROR")]})
    connector, row = connected(fake, RecordingSink())
    outcome = connector.sync(row)
    assert outcome.error_code == "plaid_institution_down"
    after = stored(connector, row)
    assert after.status == "active" and after.last_error_code == "plaid_institution_down"
