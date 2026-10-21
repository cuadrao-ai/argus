"""Exchange cleanup and bounded revocation retries."""

import pytest
from argus.domain.ingestion.connections import DuplicateConnection
from argus.domain.ingestion.plaid.adapter import PlaidAdapter
from argus.domain.ingestion.plaid.link import PlaidItemOwnedElsewhere
from argus.domain.owner_scope import PERSONAL

from tests.ingestion.plaid_fakes import (
    ACCESS_TOKEN,
    PUBLIC_TOKEN,
    FakePlaid,
    make_connector,
)

USER = "8d0f8a59-0000-4000-8000-000000000001"
SERVER_ERROR = {
    "status": 500,
    "error": {"error_type": "API_ERROR", "error_code": "INTERNAL_SERVER_ERROR"},
}
RATE_LIMITED = {
    "status": 429,
    "error": {"error_type": "RATE_LIMIT_EXCEEDED", "error_code": "RATE_LIMIT"},
}
OK = {"status": 200, "error": {"request_id": "r"}}


def removes(fake: FakePlaid) -> int:
    return fake.paths().count("/item/remove")


def connected(fake: FakePlaid):
    connector = make_connector(fake)
    connector.adapter.sleep = lambda seconds: None
    row = connector.link.exchange(user_id=USER, public_token=PUBLIC_TOKEN).connection
    return connector, row


def test_transient_revoke_failures_are_retried_then_succeed():
    fake = FakePlaid(errors={"/item/remove": [SERVER_ERROR, RATE_LIMITED, OK]})
    connector, row = connected(fake)
    outcome = connector.hub.disconnect(user_id=USER, connection_id=row.id, scope=PERSONAL)
    assert outcome.provider_revocation == "revoked" and removes(fake) == 3


def test_revoke_retries_are_bounded():
    fake = FakePlaid(errors={"/item/remove": [SERVER_ERROR]})
    connector, row = connected(fake)
    outcome = connector.hub.disconnect(user_id=USER, connection_id=row.id, scope=PERSONAL)
    assert outcome.provider_revocation == "failed" and removes(fake) == 3
    assert outcome.connection.secret is None


def test_permanent_revoke_errors_are_not_retried():
    invalid = {
        "status": 400,
        "error": {"error_type": "INVALID_REQUEST", "error_code": "MISSING_FIELDS"},
    }
    fake = FakePlaid(errors={"/item/remove": [invalid]})
    connector, row = connected(fake)
    outcome = connector.hub.disconnect(user_id=USER, connection_id=row.id, scope=PERSONAL)
    assert outcome.provider_revocation == "failed" and removes(fake) == 1


def test_backoff_grows_between_attempts():
    fake = FakePlaid(errors={"/item/remove": [SERVER_ERROR]})
    connector = make_connector(fake)
    waits: list[float] = []
    adapter = PlaidAdapter(connector.client, sleep=waits.append)
    with pytest.raises(RuntimeError):
        adapter.revoke(None, ACCESS_TOKEN)  # type: ignore[arg-type]
    assert len(waits) == 2 and waits[1] > waits[0] > 0


@pytest.mark.parametrize("stage", ["find_live", "seal", "label"])
def test_any_failure_after_exchange_ends_the_new_item(stage):
    fake = FakePlaid()
    connector = make_connector(fake)

    def boom(*args, **kwargs):  # noqa: ANN002, ANN003
        raise RuntimeError(stage)

    if stage == "find_live":
        connector.hub.connections.find_live = boom
    elif stage == "seal":
        connector.hub.box.seal = boom
    else:
        connector.link._institution_label = boom
    with pytest.raises(RuntimeError):
        connector.link.exchange(user_id=USER, public_token=PUBLIC_TOKEN)
    assert removes(fake) == 1


def test_item_won_by_another_person_in_a_race_is_refused_and_kept():
    fake = FakePlaid()
    connector = make_connector(fake)

    def elsewhere(**kwargs):  # noqa: ANN003
        raise DuplicateConnection("", elsewhere=True)

    connector.hub.connections.create = elsewhere
    with pytest.raises(PlaidItemOwnedElsewhere):
        connector.link.exchange(user_id=USER, public_token=PUBLIC_TOKEN)
    assert removes(fake) == 0


def test_relinking_my_own_item_never_removes_it():
    fake = FakePlaid()
    connector = make_connector(fake)
    first = connector.link.exchange(user_id=USER, public_token=PUBLIC_TOKEN)
    again = connector.link.exchange(user_id=USER, public_token=PUBLIC_TOKEN)
    assert again.connection.id == first.connection.id and removes(fake) == 0


def test_exchange_and_reconnect_record_the_key_that_sealed_the_token():
    """Priya B1: account deletion gives up on a token only under the key that
    sealed it, so every Plaid seal stores that key's fingerprint. Reconnect
    (Link update mode) re-stores a token that just opened under this key, so
    it fills in a row from before the fingerprint."""
    fake = FakePlaid()
    connector, row = connected(fake)
    box = connector.hub.box
    assert row.secret_key == box.key_id and len(row.secret_key) == 32
    repo = connector.hub.connections
    repo.set_secret(
        connection_id=row.id, secret=row.secret, status="needs_reauth",
        now=connector.hub.clock(), secret_key=None,
    )  # fmt: skip
    restored = connector.link.reconnected(user_id=USER, connection_id=row.id)
    assert restored.status == "active" and restored.secret_key == box.key_id
