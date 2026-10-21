"""Review hardening: bad items cannot stall a mailbox, the state ledger cannot
lock everyone out, failed callbacks release their grant, concurrent callbacks
from two people cannot share a mailbox, and disconnect still revokes while the
OAuth client is unconfigured."""

import json

import httpx
import pytest
from argus.api import gmail as gmail_api
from argus.domain.ingestion.connections import (
    DuplicateConnection,
    InMemoryConnectionRepository,
)
from argus.domain.ingestion.gmail.adapter import GmailAdapter
from argus.domain.ingestion.gmail.client import GmailError
from argus.domain.ingestion.gmail.oauth import MailboxOwnedElsewhere
from argus.domain.ingestion.gmail.senders import InMemorySenderRepository
from argus.domain.ingestion.gmail.state import (
    InMemoryStateLedger,
    OAuthStates,
    StateRejected,
)
from argus.domain.ingestion.hub import IngestionHub
from argus.domain.ingestion.secrets import SecretBox
from argus.domain.ingestion.sink import SubmitResult
from argus.domain.owner_scope import PERSONAL

from tests.ingestion.gmail_fakes import (
    FakeGoogle,
    RecordingSink,
    connect,
    google_error,
    make_connector,
)
from tests.ingestion.gmail_mailbox import NOW, alert_es, statement_ready

ALICE = "8d0f8a59-0000-4000-8000-0000000000a1"
BOB = "8d0f8a59-0000-4000-8000-0000000000b2"


def _reply(status: int, body: object) -> httpx.Response:
    raw = body if isinstance(body, bytes) else json.dumps(body).encode()
    return httpx.Response(status, content=raw)


def _synced(mails, **replies):  # noqa: ANN001, ANN003
    fake = FakeGoogle(mails=mails)
    sink = RecordingSink()
    connector = make_connector(fake, sink=sink)
    row = connect(connector, fake, ALICE).connection
    fake.item_replies.update(replies.get("replies", {}))
    return fake, sink, connector, row, connector.sync(row)


@pytest.mark.parametrize(
    ("reply", "skip"),
    [
        # Bigger than the 4 MiB JSON cap: cut off mid-stream.
        (_reply(200, b"{" + b" " * (5 * 1024 * 1024) + b"}"), "too_large"),
        (_reply(200, b"<html>not json</html>"), "unreadable"),
        (_reply(*google_error(400, "invalidArgument", "INVALID_ARGUMENT")), "unreadable"),
    ],
)
def test_one_bad_message_is_skipped_and_the_cursor_moves_past_it(reply, skip):
    bad, good = alert_es("a0700bad"), alert_es("a0701good")
    fake, sink, connector, row, outcome = _synced(
        [bad, good], replies={("a0700bad", "full"): reply}
    )
    assert outcome.status == "synced" and outcome.skipped == {skip: 1}
    assert [c.source.external_id for c in sink.batches[0]] == ["a0701good"]
    stored = connector.hub.connections.get(
        user_id=ALICE, connection_id=row.id, scope=PERSONAL
    )
    assert stored.cursor == "1000" and stored.status == "active"


def test_malformed_metadata_is_skipped_too():
    *_, outcome = _synced(
        [alert_es("a0702")], replies={("a0702", "metadata"): _reply(200, b"[1, 2]")}
    )
    assert (outcome.status, outcome.skipped) == ("synced", {"unreadable": 1})


def test_a_refused_attachment_is_skipped_but_the_message_is_kept():
    *_, sink, _connector, _row, outcome = _synced(
        [statement_ready()],
        replies={
            ("s0003pdf", "attachment"): _reply(
                *google_error(400, "invalidArgument", "INVALID_ARGUMENT")
            )
        },
    )
    assert outcome.candidates == 1 and outcome.attachments_skipped == {"unreadable": 2}
    assert sink.batches[0][0].attachments == ()


def test_auth_refusals_on_a_message_still_fail_the_whole_sync():
    fake, sink, connector, row, outcome = _synced(
        [alert_es("a0703")],
        replies={
            ("a0703", "full"): _reply(
                *google_error(403, "insufficientPermissions", "PERMISSION_DENIED")
            )
        },
    )
    assert (outcome.status, outcome.error_code) == ("failed", "gmail_scope_missing")
    stored = connector.hub.connections.get(
        user_id=ALICE, connection_id=row.id, scope=PERSONAL
    )
    assert stored.cursor is None and stored.lease_holder is None


def test_ignored_candidates_are_reported_not_counted_as_saved():
    class IgnoringSink(RecordingSink):
        def submit(self, **kwargs):  # noqa: ANN003
            super().submit(**kwargs)
            return SubmitResult(0, 0, 0, ignored=len(kwargs["candidates"]))

    fake = FakeGoogle(mails=[alert_es()])
    connector = make_connector(fake, sink=IgnoringSink())
    row = connect(connector, fake, ALICE).connection
    outcome = connector.sync(row)
    assert (outcome.status, outcome.ignored) == ("sink_failed", 1)
    # Not recorded, so not skipped: the cursor and sender backfill stay put.
    stored = connector.hub.connections.get(
        user_id=ALICE, connection_id=row.id, scope=PERSONAL
    )
    assert stored.cursor is None
    rules = connector.senders.list(connection_id=row.id)
    assert rules and all(rule.backfilled_at is None for rule in rules)


def test_state_ledger_caps_each_person_without_locking_out_others():
    clock = lambda: NOW  # noqa: E731
    states = OAuthStates(SecretBox(b"s" * 32), InMemoryStateLedger(per_user=2), clock)
    for _ in range(2):
        states.redeem(user_id=ALICE, state=states.issue(user_id=ALICE).state)
    with pytest.raises(StateRejected) as limited:
        states.redeem(user_id=ALICE, state=states.issue(user_id=ALICE).state)
    assert limited.value.reason == "rate_limited"
    assert states.redeem(user_id=BOB, state=states.issue(user_id=BOB).state)


def test_state_ledger_frees_a_person_once_their_states_expire():
    now = [NOW]
    ledger = InMemoryStateLedger(per_user=1)
    states = OAuthStates(SecretBox(b"s" * 32), ledger, lambda: now[0])
    states.redeem(user_id=ALICE, state=states.issue(user_id=ALICE).state)
    pending = states.issue(user_id=ALICE)
    with pytest.raises(StateRejected):
        states.redeem(user_id=ALICE, state=pending.state)
    now[0] = pending.expires_at
    assert states.redeem(user_id=ALICE, state=states.issue(user_id=ALICE).state)


@pytest.mark.parametrize(
    "failure",
    [
        google_error(403, "failedPrecondition", "FAILED_PRECONDITION"),
        google_error(503, "backendError", "UNAVAILABLE"),
    ],
)
def test_profile_failure_after_the_exchange_revokes_the_new_grant(failure):
    fake = FakeGoogle()
    connector = make_connector(fake)
    fake.fail["profile"] = [failure]
    with pytest.raises(GmailError):
        connect(connector, fake, ALICE)
    assert connector.hub.connections.list(user_id=ALICE, scope=PERSONAL) == []
    assert fake.count("/revoke") == 1
    assert set(fake.refresh_tokens) <= fake.revoked


def test_database_failure_after_the_exchange_revokes_the_new_grant(monkeypatch):
    fake = FakeGoogle()
    connector = make_connector(fake)

    def broken(**_kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(connector.hub.connections, "create", broken)
    with pytest.raises(RuntimeError):
        connect(connector, fake, ALICE)
    assert set(fake.refresh_tokens) <= fake.revoked


def test_two_people_completing_the_callback_concurrently_cannot_share_a_mailbox(
    monkeypatch,
):
    fake = FakeGoogle()
    connector = make_connector(fake)
    alice = connect(connector, fake, ALICE).connection
    repo = connector.hub.connections
    # Bob's callback read no live row before Alice's insert committed.
    monkeypatch.setattr(repo, "find_live", lambda **_: [])
    with pytest.raises(MailboxOwnedElsewhere):
        connect(connector, fake, BOB)
    assert repo.list(user_id=BOB, scope=PERSONAL) == []
    # The grant is shared with Alice's connection: never revoked here.
    assert fake.count("/revoke") == 0
    assert connector.hub.credential(alice) not in fake.revoked


def test_the_repository_reports_another_persons_live_mailbox_as_elsewhere():
    repo = InMemoryConnectionRepository()
    repo.create(
        user_id=ALICE,
        source="gmail",
        external_ref="gm_x",
        label=None,
        now=NOW,
        scope=PERSONAL,
    )
    with pytest.raises(DuplicateConnection) as duplicate:
        repo.create(
            user_id=BOB,
            source="gmail",
            external_ref="gm_x",
            label=None,
            now=NOW,
            scope=PERSONAL,
        )
    assert duplicate.value.elsewhere


def test_unconfigured_oauth_still_registers_a_revoke_only_adapter(monkeypatch):
    for key in (
        "GOOGLE_OAUTH_CLIENT_ID",
        "GOOGLE_OAUTH_CLIENT_SECRET",
        "GOOGLE_OAUTH_REDIRECT_URI",
    ):
        monkeypatch.delenv(key, raising=False)
    fake = FakeGoogle()
    connector = make_connector(fake)
    row = connect(connector, fake, ALICE).connection
    refresh = connector.hub.credential(row)
    # The service restarts without the OAuth client: same hub state, new wiring.
    hub = IngestionHub(
        connector.hub.connections, box=connector.hub.box, sink=None, clock=fake.clock
    )
    try:
        gmail_api.start_gmail(hub, None, transport=httpx.MockTransport(fake))
        adapter = hub.adapter("gmail")
        assert gmail_api.gmail_connector() is None
        assert isinstance(adapter, GmailAdapter)
        assert adapter is gmail_api.revoke_only_adapter()
        senders = adapter.senders
        senders.replace(
            user_id=ALICE, connection_id=row.id, senders=("bank.test",), now=NOW
        )
        outcome = hub.disconnect(user_id=ALICE, connection_id=row.id, scope=PERSONAL)
    finally:
        gmail_api.stop_gmail()
    assert outcome.provider_revocation == "revoked" and refresh in fake.revoked
    assert senders.list(connection_id=row.id) == []
    assert (
        hub.connections.get(user_id=ALICE, connection_id=row.id, scope=PERSONAL).secret
        is None
    )


def test_without_a_sealing_key_disconnect_still_forgets_senders():
    fake = FakeGoogle()
    connector = make_connector(fake)
    row = connect(connector, fake, ALICE).connection
    # The service restarts without the sealing key: stored grants are
    # unreadable, but sender rows must still go when the connection ends.
    hub = IngestionHub(connector.hub.connections, box=None, sink=None, clock=fake.clock)
    try:
        gmail_api.start_gmail(hub, None, transport=httpx.MockTransport(fake))
        adapter = hub.adapter("gmail")
        assert gmail_api.gmail_connector() is None
        assert adapter is gmail_api.revoke_only_adapter() and adapter is not None
        senders = adapter.senders
        senders.replace(
            user_id=ALICE, connection_id=row.id, senders=("bank.test",), now=NOW
        )
        outcome = hub.disconnect(user_id=ALICE, connection_id=row.id, scope=PERSONAL)
    finally:
        gmail_api.stop_gmail()
    assert outcome.provider_revocation == "failed" and not fake.revoked
    assert senders.list(connection_id=row.id) == []
    assert (
        hub.connections.get(user_id=ALICE, connection_id=row.id, scope=PERSONAL).secret
        is None
    )


def test_forget_runs_even_when_google_revocation_fails():
    fake = FakeGoogle()
    fake.fail["revoke"] = [(503, {"error": "backend"})]
    connector = make_connector(fake)
    row = connect(connector, fake, ALICE).connection
    outcome = connector.hub.disconnect(
        user_id=ALICE, connection_id=row.id, scope=PERSONAL
    )
    assert outcome.provider_revocation == "failed"
    assert connector.senders.list(connection_id=row.id) == []
    assert isinstance(connector.senders, InMemorySenderRepository)
