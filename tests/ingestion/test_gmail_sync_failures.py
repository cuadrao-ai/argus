"""Gmail sync failures: expired history, revoked or under-scoped grants,
provider outages with bounded backoff, missing sink and lost leases."""

import pytest
from argus.domain.ingestion.gmail.sync import LEASE_TTL
from argus.domain.owner_scope import PERSONAL

from tests.ingestion.gmail_fakes import (
    FakeGoogle,
    RecordingSink,
    connect,
    google_error,
    make_connector,
)
from tests.ingestion.gmail_mailbox import alert_es, standard_mailbox

USER = "8d0f8a59-0000-4000-8000-000000000002"


def synced_once(sink=None, sleeps=None):
    fake = FakeGoogle(mails=standard_mailbox())
    sink = sink if sink is not None else RecordingSink()
    connector = make_connector(fake, sink=sink, sleeps=sleeps)
    row = connect(connector, fake, USER).connection
    assert connector.sync(row).status == "synced"
    return fake, sink, connector, stored(connector, row)


def stored(connector, row):
    return connector.hub.connections.get(
        user_id=USER, connection_id=row.id, scope=PERSONAL
    )


def test_history_too_old_recovers_with_a_bounded_rescan_and_resets_the_cursor():
    fake, sink, connector, row = synced_once()
    succeeded_at = row.last_success_at
    fake.clock.advance(days=3)
    fake.deliver(alert_es("a0400late", days_ago=0))
    fake.min_history_id = 10**6  # Google no longer has history from our cursor
    outcome = connector.sync(row)
    assert (outcome.status, outcome.mode) == ("synced", "recovery")
    # Since last success minus a one-day margin: 3 + 1 days.
    query = [q["q"][0] for _, p, q in fake.calls if p.endswith("/messages")][-1]
    assert query.endswith("newer_than:4d")
    assert "a0400late" in {c.source.external_id for c in sink.batches[-1]}
    after = stored(connector, row)
    assert after.cursor == str(fake.history_id) == "1001"
    assert after.last_success_at > succeeded_at


def test_recovery_window_never_exceeds_the_lookback():
    fake, sink, connector, row = synced_once()
    fake.clock.advance(days=400)
    fake.min_history_id = 10**6
    connector.sync(row)
    query = [q["q"][0] for _, p, q in fake.calls if p.endswith("/messages")][-1]
    assert query.endswith("newer_than:90d")


def test_revoked_refresh_token_needs_reauth_and_keeps_freshness_and_cursor():
    fake, sink, connector, row = synced_once()
    fake.revoked.add(connector.hub.credential(row))
    fake.clock.advance(hours=1)
    outcome = connector.sync(row)
    assert (outcome.status, outcome.error_code) == ("failed", "gmail_token_revoked")
    after = stored(connector, row)
    assert (
        after.status == "needs_reauth" and after.last_error_code == "gmail_token_revoked"
    )
    assert after.cursor == row.cursor and after.last_success_at == row.last_success_at
    assert after.lease_holder is None
    assert len(sink.batches) == 1


@pytest.mark.parametrize(
    ("reply", "code"),
    [
        (google_error(401, "authError", "UNAUTHENTICATED"), "gmail_token_revoked"),
        (google_error(403, "insufficientPermissions", "PERMISSION_DENIED"),
         "gmail_scope_missing"),
        (google_error(403, "failedPrecondition", "FAILED_PRECONDITION"),
         "gmail_access_denied"),
    ],
)  # fmt: skip
def test_refused_access_needs_reauth(reply, code):
    fake, sink, connector, row = synced_once()
    fake.fail["history"] = [reply]
    outcome = connector.sync(row)
    assert outcome.error_code == code
    after = stored(connector, row)
    assert after.status == "needs_reauth" and after.cursor == row.cursor


@pytest.mark.parametrize("status", [429, 500, 503])
def test_outages_back_off_a_bounded_number_of_times_then_record_unavailable(status):
    sleeps: list[float] = []
    fake, sink, connector, row = synced_once(sleeps=sleeps)
    fake.fail["history"] = [google_error(status, "backendError")]
    outcome = connector.sync(row)
    assert (outcome.status, outcome.error_code) == ("failed", "gmail_unavailable")
    assert sleeps == [0.5, 1.0]
    assert fake.count("/history") == 3
    after = stored(connector, row)
    assert after.status == "error" and after.last_error_code == "gmail_unavailable"
    assert after.cursor == row.cursor and after.last_success_at == row.last_success_at
    # The next good sync clears the failure.
    fake.fail.clear()
    assert connector.sync(after).status == "synced"
    assert stored(connector, row).status == "active"


def test_a_transient_outage_recovers_inside_the_retry_budget():
    sleeps: list[float] = []
    fake, sink, connector, row = synced_once(sleeps=sleeps)
    fake.fail["history"] = [
        google_error(503, "backendError"),
        (200, {"historyId": "1000"}),
    ]
    assert connector.sync(row).status == "synced"
    assert sleeps == [0.5]


def test_without_a_sink_nothing_is_fetched_and_the_cursor_stays():
    fake = FakeGoogle(mails=standard_mailbox())
    connector = make_connector(fake, sink=None)
    row = connect(connector, fake, USER).connection
    calls = len(fake.calls)
    outcome = connector.sync(row)
    assert outcome.status == "no_sink" and len(fake.calls) == calls
    after = stored(connector, row)
    assert after.cursor is None and after.last_success_at is None


def test_unreadable_credential_is_an_actionable_error():
    fake, sink, connector, row = synced_once()
    connector.hub.connections.set_secret(
        connection_id=row.id, secret=b"\x01" + b"0" * 40, status="active",
        now=fake.clock(),
    )  # fmt: skip
    outcome = connector.sync(row)
    assert outcome.error_code == "gmail_credential_unavailable"
    assert stored(connector, row).cursor == row.cursor


def test_a_sync_that_outlives_its_lease_cannot_move_the_cursor():
    class LateSink(RecordingSink):
        def submit(self, **kwargs):  # noqa: ANN003
            result = super().submit(**kwargs)
            if self.steal:
                self.steal = False
                fake.clock.advance(seconds=LEASE_TTL.total_seconds() + 1)
                repo = connector.hub.connections
                assert repo.lease(connection_id=row.id, holder="other", now=fake.clock())
                assert repo.record_success(
                    connection_id=row.id, holder="other",
                    expected_cursor=row.cursor, cursor="2000", now=fake.clock(),
                )  # fmt: skip
            return result

    sink = LateSink()
    sink.steal = False
    fake, _, connector, row = synced_once(sink=sink)
    fake.deliver(alert_es("a0500", days_ago=0))
    sink.steal = True
    outcome = connector.sync(row)
    assert outcome.status == "superseded"
    assert stored(connector, row).cursor == "2000"
    assert stored(connector, row).lease_holder == "other"
