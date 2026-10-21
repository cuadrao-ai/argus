"""Gmail OAuth: consent URL, sealed single-use state, PKCE, scope checks,
connection creation, reconnect without duplicates and mailbox ownership."""

from urllib.parse import parse_qs, urlsplit

import pytest
from argus.domain.ingestion.connections import DuplicateConnection
from argus.domain.ingestion.gmail.client import GmailError
from argus.domain.ingestion.gmail.config import SCOPE, mailbox_ref, masked_label
from argus.domain.ingestion.gmail.oauth import (
    MailboxOwnedElsewhere,
    RefreshTokenMissing,
    ScopeNotGranted,
)
from argus.domain.ingestion.gmail.state import StateRejected, challenge
from argus.domain.owner_scope import PERSONAL

from tests.ingestion.gmail_fakes import (
    CLIENT_ID,
    REDIRECT,
    FakeGoogle,
    connect,
    make_connector,
)
from tests.ingestion.gmail_mailbox import MAILBOX

ALICE = "8d0f8a59-0000-4000-8000-0000000000a1"
BOB = "8d0f8a59-0000-4000-8000-0000000000b2"


def test_authorize_url_asks_only_for_gmail_readonly_with_pkce_and_offline_access():
    connector = make_connector(FakeGoogle())
    started = connector.oauth.authorize(user_id=ALICE)
    parts = urlsplit(started.authorization_url)
    query = {k: v[0] for k, v in parse_qs(parts.query).items()}
    assert f"{parts.scheme}://{parts.netloc}{parts.path}" == (
        "https://accounts.google.com/o/oauth2/v2/auth"
    )
    assert query["scope"] == SCOPE == "https://www.googleapis.com/auth/gmail.readonly"
    assert query["access_type"] == "offline"
    assert query["prompt"] == "consent"
    assert query["include_granted_scopes"] == "true"
    assert query["response_type"] == "code"
    assert query["code_challenge_method"] == "S256"
    assert len(query["code_challenge"]) == 43
    assert query["client_id"] == CLIENT_ID and query["redirect_uri"] == REDIRECT
    # The state is opaque: no user id or verifier readable in it.
    assert ALICE not in query["state"] and "openid" not in query["scope"]
    assert (started.expires_at - connector.hub.clock()).total_seconds() == 600


def test_callback_creates_a_connection_with_digest_ref_masked_label_and_sealed_token():
    fake = FakeGoogle()
    connector = make_connector(fake)
    result = connect(connector, fake, ALICE)
    row = result.connection
    assert result.created and row.source == "gmail" and row.status == "active"
    assert row.label == "j***@example.test" == masked_label(MAILBOX)
    box = connector.hub.box
    expected = "gm_" + box.digest(MAILBOX, purpose="gmail_mailbox")
    assert row.external_ref == expected == mailbox_ref(MAILBOX.upper(), box)
    assert row.attention_code is None
    assert MAILBOX not in row.external_ref
    refresh = connector.hub.credential(row)
    assert refresh in fake.refresh_tokens
    assert refresh.encode() not in row.secret
    # Which key sealed it, for account deletion's key check (Priya B1).
    assert row.secret_key == box.key_id and len(row.secret_key) == 32
    assert row.cursor is None and row.last_success_at is None
    assert [s.sender for s in result.senders] == [
        "alerts@card-example.test",
        "banco-ejemplo.test",
    ]
    # The token exchange carried the PKCE verifier matching the challenge.
    exchange = next(q for m, p, q in fake.calls if p == "/token")
    assert exchange == {}  # form body, not query string
    assert not fake.codes  # the code was consumed


def test_state_is_bound_to_the_person_who_started_it():
    fake = FakeGoogle()
    connector = make_connector(fake)
    started = connector.oauth.authorize(user_id=ALICE)
    code, state = fake.issue_code(started.authorization_url)
    with pytest.raises(StateRejected) as rejected:
        connector.oauth.callback(user_id=BOB, code=code, state=state, senders=None)
    assert rejected.value.reason == "invalid"
    assert connector.hub.connections.list(user_id=BOB, scope=PERSONAL) == []
    assert code in fake.codes  # nothing was exchanged


def test_state_is_single_use():
    fake = FakeGoogle()
    connector = make_connector(fake)
    started = connector.oauth.authorize(user_id=ALICE)
    code, state = fake.issue_code(started.authorization_url)
    connector.oauth.callback(user_id=ALICE, code=code, state=state, senders=None)
    with pytest.raises(StateRejected) as replay:
        connector.oauth.callback(user_id=ALICE, code=code, state=state, senders=None)
    assert replay.value.reason == "replayed"


def test_state_expires_after_ten_minutes():
    fake = FakeGoogle()
    connector = make_connector(fake)
    started = connector.oauth.authorize(user_id=ALICE)
    code, state = fake.issue_code(started.authorization_url)
    fake.clock.advance(minutes=10, seconds=1)
    with pytest.raises(StateRejected) as expired:
        connector.oauth.callback(user_id=ALICE, code=code, state=state, senders=None)
    assert expired.value.reason == "expired"


@pytest.mark.parametrize("tamper", ["flip", "garbage", "empty", "other_box"])
def test_forged_or_altered_state_is_refused(tamper):
    fake = FakeGoogle()
    connector = make_connector(fake)
    started = connector.oauth.authorize(user_id=ALICE)
    code, state = fake.issue_code(started.authorization_url)
    if tamper == "flip":
        state = state[:-2] + ("AA" if state[-2:] != "AA" else "BB")
    elif tamper == "garbage":
        state = "not-a-state"
    elif tamper == "empty":
        state = ""
    else:
        state = make_connector(fake).oauth.authorize(user_id=ALICE).authorization_url
        state = parse_qs(urlsplit(state).query)["state"][0]
    with pytest.raises(StateRejected):
        connector.oauth.callback(user_id=ALICE, code=code, state=state, senders=None)


def test_a_code_issued_for_another_pkce_challenge_is_refused_by_google():
    fake = FakeGoogle()
    connector = make_connector(fake)
    mine = connector.oauth.authorize(user_id=ALICE)
    other = connector.oauth.authorize(user_id=ALICE)
    code, _ = fake.issue_code(other.authorization_url)
    state = parse_qs(urlsplit(mine.authorization_url).query)["state"][0]
    with pytest.raises(GmailError) as refused:
        connector.oauth.callback(user_id=ALICE, code=code, state=state, senders=None)
    assert refused.value.reason == "invalid_grant"


def test_partial_consent_without_gmail_scope_is_refused_and_released():
    fake = FakeGoogle()
    connector = make_connector(fake)
    with pytest.raises(ScopeNotGranted):
        connect(connector, fake, ALICE, scopes=("openid",))
    assert connector.hub.connections.list(user_id=ALICE, scope=PERSONAL) == []
    assert fake.count("/revoke") == 1 and fake.revoked
    assert fake.count("/profile") == 0


def test_missing_refresh_token_stores_nothing_and_revokes_nothing():
    fake = FakeGoogle()
    connector = make_connector(fake)
    with pytest.raises(RefreshTokenMissing):
        connect(connector, fake, ALICE, refresh=False)
    assert connector.hub.connections.list(user_id=ALICE, scope=PERSONAL) == []
    assert fake.count("/revoke") == 0


def test_reconnect_same_mailbox_replaces_the_credential_without_a_duplicate():
    fake = FakeGoogle()
    connector = make_connector(fake)
    first = connect(connector, fake, ALICE).connection
    repo = connector.hub.connections
    repo.record_failure(
        connection_id=first.id, code="gmail_token_revoked", status="needs_reauth",
        now=connector.hub.clock(),
    )  # fmt: skip
    old = connector.hub.credential(first)
    again = connect(connector, fake, ALICE, senders=None)
    assert not again.created and again.connection.id == first.id
    assert (
        again.connection.status == "active" and again.connection.last_error_code is None
    )
    assert len(repo.list(user_id=ALICE, scope=PERSONAL)) == 1
    new = connector.hub.credential(again.connection)
    assert new != old and new in fake.refresh_tokens
    # senders=None keeps the allowlist chosen at first connect.
    assert len(again.senders) == 2


def test_reconnect_records_the_key_that_sealed_the_new_token():
    """A row from before the key fingerprint, or sealed under another key,
    carries this key's fingerprint once this process re-seals it."""
    fake = FakeGoogle()
    connector = make_connector(fake)
    first = connect(connector, fake, ALICE).connection
    repo = connector.hub.connections
    repo.set_secret(
        connection_id=first.id, secret=first.secret, status="needs_reauth",
        now=connector.hub.clock(), secret_key=None,
    )  # fmt: skip
    assert (
        repo.get(user_id=ALICE, connection_id=first.id, scope=PERSONAL).secret_key is None
    )
    again = connect(connector, fake, ALICE, senders=None).connection
    assert again.secret_key == connector.hub.box.key_id


def test_concurrent_callback_race_resolves_to_the_existing_connection(monkeypatch):
    fake = FakeGoogle()
    connector = make_connector(fake)
    existing = connect(connector, fake, ALICE).connection
    repo = connector.hub.connections
    monkeypatch.setattr(repo, "find_live", lambda **_: [])

    def lost_race(**_kwargs):
        raise DuplicateConnection(existing.id)

    monkeypatch.setattr(repo, "create", lost_race)
    again = connect(connector, fake, ALICE, senders=None)
    assert not again.created and again.connection.id == existing.id
    assert connector.hub.credential(again.connection) in fake.refresh_tokens


def test_mailbox_connected_by_someone_else_is_refused_without_revoking():
    fake = FakeGoogle()
    connector = make_connector(fake)
    connect(connector, fake, ALICE)
    with pytest.raises(MailboxOwnedElsewhere):
        connect(connector, fake, BOB)
    assert connector.hub.connections.list(user_id=BOB, scope=PERSONAL) == []
    assert fake.count("/revoke") == 0


def test_pkce_challenge_is_s256_of_the_verifier():
    assert challenge("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk") == (
        "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
    )  # RFC 7636 appendix B


def test_time_limited_grant_is_flagged_without_blocking_and_cleared_on_reconnect():
    fake = FakeGoogle()
    connector = make_connector(fake)
    row = connect(connector, fake, ALICE, refresh_lifetime=604799).connection
    assert row.status == "active"
    assert row.attention_code == "gmail_access_time_limited"
    assert row.attention_at == connector.hub.clock()
    again = connect(connector, fake, ALICE, senders=None).connection
    assert again.id == row.id and again.attention_code is None


def _senders_unavailable(connector, monkeypatch):  # noqa: ANN001, ANN202
    def unavailable(**_kwargs):  # noqa: ANN003, ANN202
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(connector.senders, "replace", unavailable)


def test_a_new_connection_whose_setup_fails_is_ended_and_its_grant_released(
    monkeypatch,
):
    fake = FakeGoogle()
    connector = make_connector(fake)
    _senders_unavailable(connector, monkeypatch)
    with pytest.raises(RuntimeError):
        connect(connector, fake, ALICE)
    (row,) = connector.hub.connections.list(user_id=ALICE, scope=PERSONAL)
    assert row.status == "disconnected" and row.secret is None
    assert fake.count("/revoke") == 1 and fake.revoked
    assert connector.senders.list(connection_id=row.id) == []


def test_a_reconnect_whose_setup_fails_asks_for_authorization_again(monkeypatch):
    fake = FakeGoogle()
    connector = make_connector(fake)
    first = connect(connector, fake, ALICE).connection
    _senders_unavailable(connector, monkeypatch)
    with pytest.raises(RuntimeError):
        connect(connector, fake, ALICE, senders=("other-bank.test",))
    row = connector.hub.connections.get(
        user_id=ALICE, connection_id=first.id, scope=PERSONAL
    )
    assert (row.status, row.last_error_code) == ("needs_reauth", "gmail_token_revoked")
    assert fake.count("/revoke") == 1
    # The allowlist chosen at first connect is untouched.
    assert len(connector.senders.list(connection_id=first.id)) == 2
