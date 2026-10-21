"""Plaid Link server side, reconnect, disconnect and the HTTP client seam."""

import httpx
import pytest
import respx
from argus.domain.ingestion.connections import DuplicateConnection
from argus.domain.ingestion.plaid.client import PlaidClient, PlaidError
from argus.domain.ingestion.plaid.config import PlaidConfig, plaid_config_from_env
from argus.domain.ingestion.plaid.link import (
    ConnectionNotReauthorizable,
    PlaidItemOwnedElsewhere,
    client_user_id,
)
from argus.domain.owner_scope import PERSONAL

from tests.ingestion.plaid_fakes import (
    ACCESS_TOKEN,
    ITEM_ID,
    PUBLIC_TOKEN,
    FakePlaid,
    RecordingSink,
    make_connector,
    page,
    txn,
)

USER = "8d0f8a59-0000-4000-8000-000000000001"
OTHER = "8d0f8a59-0000-4000-8000-000000000002"


def test_link_token_asks_for_transactions_with_an_opaque_user():
    fake = FakePlaid()
    config = PlaidConfig(
        client_id="client-id",
        secret="plaid-secret-value",
        webhook_url="https://api.example.test/api/v1/financial-connections/plaid/webhook",
        country_codes=("US", "CA"),
    )
    connector = make_connector(fake, config=config)
    token = connector.link.link_token(user_id=USER, language="es")
    assert token.link_token == "link-sandbox-new" and token.expiration is not None
    path, body, headers = fake.calls[0]
    assert path == "/link/token/create"
    assert body["products"] == ["transactions"] and body["country_codes"] == ["US", "CA"]
    assert body["language"] == "es" and body["webhook"] == config.webhook_url
    assert body["user"]["client_user_id"] == client_user_id(USER) != USER
    assert headers["plaid-version"] == "2020-09-14"
    assert headers["plaid-client-id"] == "client-id"
    assert "secret" not in body and "client_id" not in body


def test_exchange_seals_the_token_and_is_idempotent():
    fake = FakePlaid()
    connector = make_connector(fake)
    first = connector.link.exchange(user_id=USER, public_token=PUBLIC_TOKEN)
    assert first.created and first.connection.external_ref == ITEM_ID
    assert first.connection.label == "First Platypus Bank"
    assert ACCESS_TOKEN.encode() not in first.connection.secret
    assert connector.hub.credential(first.connection) == ACCESS_TOKEN
    # Plaid answers a repeated exchange with the same Item: same connection.
    again = connector.link.exchange(user_id=USER, public_token=PUBLIC_TOKEN)
    assert not again.created and again.connection.id == first.connection.id
    assert len(connector.hub.list(user_id=USER, scope=PERSONAL)) == 1


def test_exchange_race_resolves_to_the_winner():
    fake = FakePlaid()
    connector = make_connector(fake)
    repo = connector.hub.connections
    winner = {}
    original = repo.create

    def racing_create(**kwargs):  # noqa: ANN003
        if not winner:
            winner["row"] = original(**{**kwargs, "connection_id": None})
        raise DuplicateConnection(winner["row"].id)

    repo.create = racing_create
    result = connector.link.exchange(user_id=USER, public_token=PUBLIC_TOKEN)
    assert not result.created and result.connection.id == winner["row"].id


def test_exchange_ends_the_item_when_the_connection_cannot_be_stored():
    fake = FakePlaid()
    connector = make_connector(fake)

    def broken_create(**kwargs):  # noqa: ANN003
        raise RuntimeError("database unavailable")

    connector.hub.connections.create = broken_create
    with pytest.raises(RuntimeError):
        connector.link.exchange(user_id=USER, public_token=PUBLIC_TOKEN)
    assert [b for p, b, _ in fake.calls if p == "/item/remove"] == [
        {"access_token": ACCESS_TOKEN}
    ]


def test_an_item_connected_by_someone_else_is_refused_without_revoking():
    fake = FakePlaid()
    connector = make_connector(fake)
    connector.link.exchange(user_id=OTHER, public_token=PUBLIC_TOKEN)
    with pytest.raises(PlaidItemOwnedElsewhere):
        connector.link.exchange(user_id=USER, public_token=PUBLIC_TOKEN)
    assert "/item/remove" not in fake.paths()


def test_exchange_label_is_optional_when_institution_lookup_fails():
    fake = FakePlaid(
        errors={
            "/institutions/get_by_id": [
                {
                    "status": 500,
                    "error": {
                        "error_type": "API_ERROR",
                        "error_code": "INTERNAL_SERVER_ERROR",
                    },
                }
            ]
        }
    )
    connector = make_connector(fake)
    assert (
        connector.link.exchange(user_id=USER, public_token=PUBLIC_TOKEN).connection.label
        is None
    )


def needs_reauth(fake: FakePlaid):
    fake.sync = {None: [page(added=[txn("t1", 4.5)], next_cursor="c1")]}
    connector = make_connector(fake, sink=RecordingSink())
    row = connector.link.exchange(user_id=USER, public_token=PUBLIC_TOKEN).connection
    connector.sync(row)
    fake.item_error = "ITEM_LOGIN_REQUIRED"
    connector.sync(row)
    row = connector.hub.connections.get(
        user_id=USER, connection_id=row.id, scope=PERSONAL
    )
    assert row.status == "needs_reauth"
    return connector, row


def test_update_mode_link_token_names_the_item_server_side():
    fake = FakePlaid()
    connector, row = needs_reauth(fake)
    token = connector.link.update_link_token(
        user_id=USER, connection_id=row.id, language="en"
    )
    assert token.link_token == "link-sandbox-update"
    body = [b for p, b, _ in fake.calls if p == "/link/token/create"][-1]
    assert body["access_token"] == ACCESS_TOKEN and "products" not in body


def test_update_mode_is_refused_for_healthy_or_foreign_connections():
    fake = FakePlaid()
    connector = make_connector(fake)
    row = connector.link.exchange(user_id=USER, public_token=PUBLIC_TOKEN).connection
    with pytest.raises(ConnectionNotReauthorizable):
        connector.link.update_link_token(
            user_id=USER, connection_id=row.id, language="en"
        )
    with pytest.raises(LookupError):
        connector.link.update_link_token(
            user_id=OTHER, connection_id=row.id, language="en"
        )


def test_reconnected_restores_active_and_keeps_cursor_and_freshness():
    fake = FakePlaid()
    connector, row = needs_reauth(fake)
    still_broken = connector.link.reconnected(user_id=USER, connection_id=row.id)
    assert still_broken.status == "needs_reauth"
    fake.item_error = None  # the person completed Link update mode
    restored = connector.link.reconnected(user_id=USER, connection_id=row.id)
    assert restored.status == "active" and restored.last_error_code is None
    assert restored.cursor == "c1" and restored.last_success_at == row.last_success_at
    assert connector.hub.credential(restored) == ACCESS_TOKEN


def test_disconnect_removes_the_item_at_plaid_and_deletes_the_credential():
    fake = FakePlaid()
    sink = RecordingSink()
    connector = make_connector(fake, sink=sink)
    row = connector.link.exchange(user_id=USER, public_token=PUBLIC_TOKEN).connection
    outcome = connector.hub.disconnect(user_id=USER, connection_id=row.id, scope=PERSONAL)
    assert outcome.provider_revocation == "revoked"
    remove = [b for p, b, _ in fake.calls if p == "/item/remove"]
    assert remove == [{"access_token": ACCESS_TOKEN}]
    assert (
        outcome.connection.secret is None and outcome.connection.status == "disconnected"
    )
    with pytest.raises(PlaidError) as gone:
        connector.client.item_get(ACCESS_TOKEN)
    assert gone.value.error_code == "ITEM_NOT_FOUND"


def test_revoke_of_an_item_plaid_no_longer_knows_counts_as_revoked():
    fake = FakePlaid()
    connector = make_connector(fake)
    row = connector.link.exchange(user_id=USER, public_token=PUBLIC_TOKEN).connection
    fake.removed_items.add(ITEM_ID)
    assert (
        connector.hub.disconnect(
            user_id=USER, connection_id=row.id, scope=PERSONAL
        ).provider_revocation
        == "revoked"
    )


def test_revoke_failure_is_reported_and_local_credential_still_deleted():
    fake = FakePlaid(
        errors={
            "/item/remove": [
                {
                    "status": 500,
                    "error": {
                        "error_type": "API_ERROR",
                        "error_code": "INTERNAL_SERVER_ERROR",
                    },
                }
            ]
        }
    )
    connector = make_connector(fake)
    row = connector.link.exchange(user_id=USER, public_token=PUBLIC_TOKEN).connection
    outcome = connector.hub.disconnect(user_id=USER, connection_id=row.id, scope=PERSONAL)
    assert outcome.provider_revocation == "failed" and outcome.connection.secret is None


@respx.mock
def test_client_sends_headers_once_without_redirects_or_retries():
    route = respx.post("https://sandbox.plaid.com/item/get").mock(
        return_value=httpx.Response(302, headers={"Location": "https://evil.example/"})
    )
    client = PlaidClient(PlaidConfig(client_id="cid", secret="sec"))
    with pytest.raises(PlaidError) as caught:
        client.item_get(ACCESS_TOKEN)
    assert caught.value.error_code == "HTTP_302" and route.call_count == 1
    sent = route.calls[0].request
    assert (
        sent.headers["PLAID-CLIENT-ID"] == "cid" and sent.headers["PLAID-SECRET"] == "sec"
    )
    assert ACCESS_TOKEN not in str(caught.value)
    respx.post("https://sandbox.plaid.com/item/remove").mock(
        side_effect=httpx.ConnectTimeout("t")
    )
    with pytest.raises(PlaidError) as down:
        client.item_remove(ACCESS_TOKEN)
    assert down.value.error_code == "PROVIDER_UNREACHABLE"
    assert client._http.timeout.read == 30.0


@respx.mock
def test_injected_credentials_send_no_auth_headers():
    route = respx.post("https://sandbox.plaid.com/item/remove").mock(
        return_value=httpx.Response(200, json={"request_id": "r"})
    )
    config = PlaidConfig(credentials_injected=True)
    assert config.configured and config.auth_headers() == {}
    PlaidClient(config).item_remove(ACCESS_TOKEN)
    assert "PLAID-SECRET" not in route.calls[0].request.headers


def test_config_seam_defaults_off_and_refuses_injection_in_production(monkeypatch):
    for key in (
        "PLAID_CLIENT_ID",
        "PLAID_SECRET",
        "PLAID_ENV",
        "PLAID_CREDENTIALS_INJECTED",
        "PLAID_WEBHOOK_URL",
        "PLAID_COUNTRY_CODES",
    ):
        monkeypatch.delenv(key, raising=False)
    config = plaid_config_from_env()
    assert (config.environment, config.configured, config.country_codes) == (
        "sandbox",
        False,
        ("US",),
    )
    monkeypatch.setenv("PLAID_ENV", "production")
    monkeypatch.setenv("PLAID_CREDENTIALS_INJECTED", "true")
    assert not plaid_config_from_env().configured
    assert plaid_config_from_env().base_url == "https://production.plaid.com"
    monkeypatch.setenv("PLAID_COUNTRY_CODES", "US,DO")
    with pytest.raises(ValueError):
        plaid_config_from_env()
    assert "plaid-secret-value" not in repr(
        PlaidConfig(client_id="c", secret="plaid-secret-value")
    )
