"""Sync safety under interleaving, bounds and malformed provider data."""

from argus.domain.ingestion.plaid.connector import PlaidConnector
from argus.domain.owner_scope import PERSONAL

from tests.ingestion.plaid_fakes import (
    CHECKING,
    PUBLIC_TOKEN,
    FakePlaid,
    RecordingSink,
    make_connector,
    page,
    txn,
)

USER = "8d0f8a59-0000-4000-8000-000000000001"


class HookedFake(FakePlaid):
    """Runs ``hook`` while Plaid answers one ``/transactions/sync`` call."""

    hook = None

    def _transactions_sync(self, body):  # noqa: ANN001
        if self.hook is not None:
            hook, self.hook = self.hook, None
            hook()
        return super()._transactions_sync(body)


def connected(fake: FakePlaid, sink: RecordingSink | None = None):
    connector = make_connector(fake, sink=sink or RecordingSink())
    row = connector.link.exchange(user_id=USER, public_token=PUBLIC_TOKEN).connection
    return connector, row


def stored(connector: PlaidConnector, row):  # noqa: ANN001
    return connector.hub.connections.get(
        user_id=USER, connection_id=row.id, scope=PERSONAL
    )


def webhook_login_required(connector: PlaidConnector, row):  # noqa: ANN001
    def hook() -> None:
        connector.webhooks.plan(
            {
                "webhook_type": "ITEM",
                "webhook_code": "ERROR",
                "item_id": row.external_ref,
                "environment": "sandbox",
                "error": {"error_code": "ITEM_LOGIN_REQUIRED"},
            }
        )

    return hook


def test_needs_reauth_from_a_webhook_mid_sync_is_not_overwritten():
    fake = HookedFake(sync={None: [page(added=[txn("t1", 4.5)], next_cursor="c1")]})
    connector, row = connected(fake)
    fake.hook = webhook_login_required(connector, row)
    outcome = connector.sync(row)
    assert outcome.status == "superseded"
    after = stored(connector, row)
    assert after.status == "needs_reauth"
    assert after.last_error_code == "plaid_item_login_required"
    assert after.cursor is None and after.lease_holder is None


def test_a_lost_lease_stops_pagination_before_the_next_page():
    fake = HookedFake(
        sync={
            None: [page(added=[txn("t1", 1)], next_cursor="c1", has_more=True)],
            "c1": [page(added=[txn("t2", 2)], next_cursor="c2")],
        }
    )
    sink = RecordingSink()
    connector, row = connected(fake, sink)
    fake.hook = webhook_login_required(connector, row)
    outcome = connector.sync(row)
    assert outcome.status == "superseded"
    cursors = [b.get("cursor") for p, b, _ in fake.calls if p == "/transactions/sync"]
    assert cursors == [None]
    assert sink.batches == []
    assert stored(connector, row).status == "needs_reauth"


def test_lease_is_renewed_for_every_page():
    fake = FakePlaid(
        sync={
            None: [page(added=[txn("t1", 1)], next_cursor="c1", has_more=True)],
            "c1": [page(added=[txn("t2", 2)], next_cursor="c2")],
        }
    )
    connector, row = connected(fake)
    repo = connector.hub.connections
    acquired: list[str] = []
    renewals: list[str] = []
    original_lease, original_renew = repo.lease, repo.renew

    def counting_lease(**kwargs):  # noqa: ANN003
        acquired.append(kwargs["holder"])
        return original_lease(**kwargs)

    def counting_renew(**kwargs):  # noqa: ANN003
        renewals.append(kwargs["holder"])
        return original_renew(**kwargs)

    repo.lease, repo.renew = counting_lease, counting_renew
    assert connector.sync(row).status == "synced"
    # One acquisition, then one held-only renewal per page, same holder.
    assert len(acquired) == 1 and len(renewals) == 2
    assert set(renewals) == set(acquired)


def failure_just_before_renewal(connector: PlaidConnector, row):  # noqa: ANN001
    """Record ``needs_reauth`` immediately before the second page's renewal:
    the narrowest window a read-then-lease renewal could not see."""

    repo = connector.hub.connections
    original = repo.renew
    calls = []

    def renew(**kwargs):  # noqa: ANN003
        calls.append(kwargs)
        if len(calls) == 2:
            repo.record_failure(
                connection_id=row.id,
                code="plaid_item_login_required",
                status="needs_reauth",
                now=connector.hub.clock(),
            )
        return original(**kwargs)

    repo.renew = renew
    return calls


def test_failure_between_pages_cannot_be_undone_by_renewal():
    fake = FakePlaid(
        sync={
            None: [page(added=[txn("t1", 1)], next_cursor="c1", has_more=True)],
            "c1": [page(added=[txn("t2", 2)], next_cursor="c2")],
        }
    )
    sink = RecordingSink()
    connector, row = connected(fake, sink)
    calls = failure_just_before_renewal(connector, row)
    outcome = connector.sync(row)
    assert len(calls) == 2 and outcome.status == "superseded"
    after = stored(connector, row)
    assert (after.status, after.cursor, after.lease_holder) == (
        "needs_reauth",
        None,
        None,
    )
    assert sink.batches == []
    assert [b.get("cursor") for p, b, _ in fake.calls if p == "/transactions/sync"] == [
        None
    ]


def test_page_cap_records_incomplete_and_keeps_the_cursor():
    fake = FakePlaid(
        sync={
            None: [page(added=[txn("t1", 1)], next_cursor="c1", has_more=True)],
            "c1": [page(added=[txn("t2", 2)], next_cursor="c2", has_more=True)],
        }
    )
    sink = RecordingSink()
    connector, row = connected(fake, sink)
    connector.syncer.max_pages = 2
    outcome = connector.sync(row)
    assert (outcome.status, outcome.error_code) == ("failed", "plaid_sync_incomplete")
    after = stored(connector, row)
    assert after.cursor is None and after.status == "active"
    assert after.last_error_code == "plaid_sync_incomplete"
    assert sink.batches == []


def test_time_bound_records_incomplete_and_keeps_the_cursor():
    fake = FakePlaid(
        sync={
            None: [page(added=[txn("t1", 1)], next_cursor="c1", has_more=True)],
            "c1": [page(added=[txn("t2", 2)], next_cursor="c2")],
        }
    )
    sink = RecordingSink()
    connector, row = connected(fake, sink)
    ticks = iter([0.0, 0.0, 10_000.0, 10_000.0])
    connector.syncer.timer = lambda: next(ticks)
    outcome = connector.sync(row)
    assert outcome.error_code == "plaid_sync_incomplete"
    assert stored(connector, row).cursor is None and sink.batches == []


def test_malformed_accounts_are_dropped_and_counted_not_fatal():
    bad_currency = {**CHECKING, "balances": {"iso_currency_code": "DOLLARS"}}
    bad_id = {**CHECKING, "account_id": "has spaces !"}
    odd_balances = {**CHECKING, "account_id": "acc-odd", "balances": ["x"]}
    fake = FakePlaid(
        sync={
            None: [
                page(
                    added=[txn("t1", 1), txn("t2", 2, account_id="acc-odd")],
                    accounts=[bad_currency, bad_id, odd_balances],
                    next_cursor="c1",
                )
            ]
        },
    )
    fake.accounts = [bad_currency]
    sink = RecordingSink()
    connector, row = connected(fake, sink)
    outcome = connector.sync(row)
    assert outcome.status == "synced" and outcome.added == 2
    assert outcome.skipped_accounts == 3
    t1 = sink.evidence[("plaid", row.id, "t1")]
    assert t1.account.external_account_id == "acc-checking" and t1.account.mask is None
    t2 = sink.evidence[("plaid", row.id, "t2")]
    assert t2.account.mask == "0000" and t2.account.currency is None


def test_sink_ignoring_candidates_does_not_advance_the_cursor():
    class IgnoringSink(RecordingSink):
        def submit(self, **kwargs):  # noqa: ANN003
            result = super().submit(**kwargs)
            return type(result)(0, 0, 0, ignored=len(kwargs["candidates"]))

    fake = FakePlaid(sync={None: [page(added=[txn("t1", 1)], next_cursor="c1")]})
    connector, row = connected(fake, IgnoringSink())
    assert connector.sync(row).status == "sink_failed"
    assert stored(connector, row).cursor is None
