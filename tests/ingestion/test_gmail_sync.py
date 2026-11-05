"""Gmail sync: allowlisted, authenticated messages become conservative
candidates; history increments, pagination, duplicates and leases."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from argus.domain.ingestion.gmail import sync as sync_module
from argus.domain.owner_scope import PERSONAL

from tests.ingestion.gmail_fakes import (
    FakeGoogle,
    RecordingSink,
    connect,
    make_connector,
)
from tests.ingestion.gmail_mailbox import (
    BANK,
    INJECTION,
    alert_es,
    newsletter,
    standard_mailbox,
)

USER = "8d0f8a59-0000-4000-8000-000000000001"
IMPORTED = {"a0001es", "a0002en", "s0003pdf", "d0004due", "m0006evil", "h0007huge"}


def connected(fake=None, sink=None, **kwargs):
    fake = fake or FakeGoogle(mails=standard_mailbox())
    sink = sink if sink is not None else RecordingSink()
    connector = make_connector(fake, sink=sink)
    row = connect(connector, fake, USER, **kwargs).connection
    return fake, sink, connector, row


def stored(connector, row):
    return connector.hub.connections.get(
        user_id=USER, connection_id=row.id, scope=PERSONAL
    )


def full_fetches(fake):
    return [
        path.rsplit("/", 1)[1]
        for _, path, query in fake.calls
        if "/messages/" in path and query.get("format") == ["full"]
    ]


def test_initial_sync_imports_allowlisted_authenticated_messages_only():
    fake, sink, connector, row = connected()
    outcome = connector.sync(row)
    assert (outcome.status, outcome.mode) == ("synced", "initial")
    assert outcome.messages == 8 and outcome.candidates == 6
    assert outcome.skipped == {"unverified_sender": 1, "not_allowlisted": 1}
    assert outcome.attachments == 2
    assert outcome.attachments_skipped == {
        "media_type": 1,
        "signature": 1,
        "too_large": 1,
    }
    assert {c.source.external_id for c in sink.batches[0]} == IMPORTED
    after = stored(connector, row)
    assert after.cursor == "1000" and after.last_success_at == fake.clock()
    assert after.lease_holder is None
    query = next(q["q"][0] for _, p, q in fake.calls if p.endswith("/messages"))
    assert query == "from:(alerts@card-example.test OR banco-ejemplo.test) newer_than:90d"
    # Bodies are read only for allowlisted, authenticated senders.
    assert set(full_fetches(fake)) == IMPORTED
    assert "n0005news" not in "".join(fake.paths())
    assert not fake.unexpected
    assert all(
        rule.backfilled_at for rule in connector.senders.list(connection_id=row.id)
    )


def test_candidates_claim_only_machine_certain_facts():
    fake, sink, connector, row = connected()
    connector.sync(row)
    by_id = {c.source.external_id: c for c in sink.batches[0]}
    alert = by_id["a0001es"]
    assert alert.source.source == "gmail" and alert.source.connection_id == row.id
    assert int(alert.source.observed_at.timestamp() * 1000) == fake.mails[0].internal_ms
    assert alert.evidence == "unclassified" and alert.uncertain == frozenset()
    assert alert.kind_hint == "unknown" and alert.status == "unknown"
    assert (alert.amount, alert.currency, alert.occurred_on, alert.direction) == (
        None, None, None, "unknown",
    )  # fmt: skip
    assert alert.account.institution == BANK and alert.account.mask is None
    assert alert.unresolved() == {"amount", "currency", "occurred_on", "direction",
                                  "account", "kind"}  # fmt: skip
    assert all(c.evidence == "unclassified" for c in by_id.values())
    assert alert.excerpt.startswith("Alerta de consumo: tarjeta terminada en 1234 · ")
    statement = by_id["s0003pdf"]
    assert [(a.external_id, a.media_type) for a in statement.attachments] == [
        ("s0003pdf:1", "application/pdf"),
        ("s0003pdf:2", "image/png"),
    ]
    assert statement.account.institution == f"mail.{BANK}"
    hostile = by_id["m0006evil"]
    assert "fetch(" not in hostile.excerpt and "(hidden)" not in hostile.excerpt
    assert INJECTION in hostile.excerpt and "‮" not in hostile.excerpt
    assert hostile.attachments == ()
    assert by_id["h0007huge"].attachments == ()
    assert all(len(c.excerpt) <= 280 for c in by_id.values())


def test_scan_paginates_and_reports_truncation(monkeypatch):
    monkeypatch.setattr(sync_module, "PAGE_SIZE", 2)
    monkeypatch.setattr(sync_module, "MAX_SCAN_PAGES", 2)
    mails = [alert_es(f"a{i:04d}", days_ago=1 + i) for i in range(5)]
    fake, sink, connector, row = connected(FakeGoogle(mails=mails))
    outcome = connector.sync(row)
    assert outcome.scan_truncated and outcome.candidates == 4
    tokens = [q.get("pageToken") for _, p, q in fake.calls if p.endswith("/messages")]
    assert tokens == [None, ["2"]]
    assert stored(connector, row).cursor == "1000"


def test_incremental_sync_reads_history_and_filters_by_allowlist():
    fake, sink, connector, row = connected()
    connector.sync(row)
    fake.deliver(alert_es("a0100new", days_ago=0))
    fake.deliver(newsletter("n0101news", days_ago=0))
    outcome = connector.sync(stored(connector, row))
    assert (outcome.status, outcome.mode) == ("synced", "incremental")
    assert outcome.candidates == 1 and outcome.skipped == {"not_allowlisted": 1}
    assert [c.source.external_id for c in sink.batches[-1]] == ["a0100new"]
    assert stored(connector, row).cursor == "1002"
    history = [q for _, p, q in fake.calls if p.endswith("/history")]
    assert history[0]["startHistoryId"] == ["1000"]
    assert history[0]["historyTypes"] == ["messageAdded", "labelRemoved"]
    assert "n0101news" not in full_fetches(fake)
    # Nothing new: still a success, cursor unchanged.
    quiet = connector.sync(stored(connector, row))
    assert (quiet.status, quiet.candidates) == ("synced", 0)


def test_history_pagination_is_bounded_and_resumes(monkeypatch):
    monkeypatch.setattr(sync_module, "PAGE_SIZE", 1)
    monkeypatch.setattr(sync_module, "MAX_HISTORY_PAGES", 2)
    fake, sink, connector, row = connected()
    connector.sync(row)
    for i in range(3):
        fake.deliver(alert_es(f"a02{i:02d}", days_ago=0))
    first = connector.sync(stored(connector, row))
    assert first.more_pending and first.candidates == 2
    assert stored(connector, row).cursor == "1002"
    second = connector.sync(stored(connector, row))
    assert not second.more_pending and second.candidates == 1
    assert [c.source.external_id for c in sink.batches[-1]] == ["a0202"]
    assert stored(connector, row).cursor == "1003"


def test_message_rescued_from_spam_is_picked_up():
    fake, sink, connector, row = connected()
    connector.sync(row)
    rescued = alert_es("a0300spam", days_ago=0)
    rescued.labels = ("INBOX",)
    fake.deliver(rescued, record=False)
    fake.history.append(
        {"id": str(fake.history_id), "labelsRemoved": [
            {"message": {"id": rescued.id, "labelIds": ["INBOX"]}, "labelIds": ["SPAM"]}
        ]}
    )  # fmt: skip
    outcome = connector.sync(stored(connector, row))
    assert [c.source.external_id for c in sink.batches[-1]] == ["a0300spam"]
    assert outcome.candidates == 1


def test_same_message_from_scan_and_history_is_one_observation():
    fake, sink, connector, row = connected()
    connector.sync(row)
    # History reports a message the initial scan already imported.
    fake.history_id += 1
    fake.history.append(
        {"id": str(fake.history_id),
         "messagesAdded": [{"message": {"id": "a0001es", "labelIds": ["INBOX"]}}]}
    )  # fmt: skip
    connector.sync(stored(connector, row))
    first, again = sink.batches[0], sink.batches[-1]
    assert [c.key for c in again] == [c.key for c in first if c.key[2] == "a0001es"]
    assert sink.results[-1].unchanged == 1 and sink.results[-1].recorded == 0


def test_a_retried_sync_after_a_sink_failure_redelivers_identically():
    sink = RecordingSink()
    fake, sink, connector, row = connected(sink=sink)
    sink.fail = True
    failed = connector.sync(row)
    assert failed.status == "sink_failed" and stored(connector, row).cursor is None
    assert not any(r.backfilled_at for r in connector.senders.list(connection_id=row.id))
    sink.fail = False
    assert connector.sync(stored(connector, row)).status == "synced"
    # The failed attempt never reached the sink; the retry delivers the same ids.
    assert len(sink.batches) == 1
    assert {c.source.external_id for c in sink.batches[0]} == IMPORTED
    assert stored(connector, row).cursor == "1000"


def test_concurrent_syncs_advance_the_cursor_once():
    barrier = Barrier(2)

    class SlowFake(FakeGoogle):
        def __call__(self, request):  # noqa: ANN001
            if request.url.path.endswith("/profile") and not self.slowed:
                self.slowed = True
                barrier.wait(timeout=10)
            return super().__call__(request)

    fake = SlowFake(mails=standard_mailbox())
    fake.slowed = True  # the connect callback's profile read is not slowed
    fake, sink, connector, row = connected(fake)
    fake.slowed = False

    def guarded(_):  # noqa: ANN001
        outcome = connector.sync(row)
        if outcome.status == "busy":
            barrier.wait(timeout=10)
        return outcome.status

    with ThreadPoolExecutor(2) as pool:
        statuses = sorted(pool.map(guarded, [1, 2]))
    assert statuses == ["busy", "synced"]
    assert len(sink.batches) == 1
    after = stored(connector, row)
    assert after.cursor == "1000" and after.lease_holder is None


def test_sender_added_later_is_searched_once_over_the_lookback():
    fake, sink, connector, row = connected(senders=["alerts@card-example.test"])
    first = connector.sync(row)
    assert {c.source.external_id for c in sink.batches[0]} == {"a0002en", "m0006evil"}
    assert first.candidates == 2
    connector.replace_senders(
        user_id=USER, connection_id=row.id,
        senders=["alerts@card-example.test", BANK], now=fake.clock(),
    )  # fmt: skip
    second = connector.sync(stored(connector, row))
    assert second.mode == "incremental"
    assert {c.source.external_id for c in sink.batches[-1]} == IMPORTED - {
        "a0002en", "m0006evil",
    }  # fmt: skip
    queries = [q["q"][0] for _, p, q in fake.calls if p.endswith("/messages")]
    assert queries[-1] == f"from:({BANK}) newer_than:90d"
    third = connector.sync(stored(connector, row))
    assert third.candidates == 0
    assert len([p for p in fake.paths() if p.endswith("/messages")]) == 2


@pytest.mark.parametrize("senders", [[], None])
def test_no_senders_means_no_provider_calls(senders):
    fake = FakeGoogle(mails=standard_mailbox())
    connector = make_connector(fake, sink=RecordingSink())
    row = connect(connector, fake, USER, senders=senders).connection
    calls = len(fake.calls)
    outcome = connector.sync(row)
    assert outcome.status == "no_senders" and len(fake.calls) == calls
    assert stored(connector, row).last_success_at is None
