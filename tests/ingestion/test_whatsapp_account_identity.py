"""Channel account authority belongs to the caller across Business ownership changes."""


from types import SimpleNamespace

import pytest
from argus.api.business_spaces import business_access, business_spaces
from argus.api.documents import documents_service
from argus.api.whatsapp import whatsapp_runtime
from argus.domain.business.roles import BusinessRole
from faker import Faker

from tests.ingestion.conftest import ALICE, BOB, bearer
from tests.ingestion.test_whatsapp_api import (  # noqa: F401
    CODES,
    LINK,
    LINK_BODY,
    graph,
    link_alice,
    wa_client,
)


@pytest.mark.parametrize("is_default_destination,selected", [(False, True), (True, True), (True, False)])
def test_transferred_business_never_uses_creators_channel_account(
    wa_client, identities, is_default_destination, selected, monkeypatch  # noqa: F811
):
    fake = Faker()
    creator, caller = identities[ALICE]["id"], identities[BOB]["id"]
    spaces, access = business_spaces(), business_access()
    transferred, _ = spaces.create_additional(creator, fake.company(), "DO", fake.uuid4())
    # Model the persisted transfer: the creator stays on the space, the live
    # Owner membership belongs to the recipient.
    access._live(transferred.id, creator)["revoked_at"] = access._now()
    grant = access._insert_grant(transferred.id, caller, caller, BusinessRole.OWNER)
    reading = documents_service().business_receipt_consent
    status = reading.status(transferred.id, creator)
    reading.set(
        transferred.id, creator, actor_id=caller, enabled=True,
        version=status["scope_version"], disclosure_token=status["disclosure_token"],
    )
    if is_default_destination:
        spaces._defaults[caller] = transferred.id
    link_alice(wa_client)
    runtime = whatsapp_runtime()
    store = runtime.intake.store
    creator_link = store.destination_link(destination_owner_id=creator)
    assert creator_link is not None
    headers = {**bearer(BOB), **({"X-Business-Grant": grant["id"]} if selected else {})}
    availability = wa_client.get("/api/v1/business/workspace", headers=headers)
    assert availability.status_code == 200, availability.text
    assert availability.json()["receiving_channels"]["whatsapp"]["available"] is True
    responses = [
        wa_client.get(LINK, headers=headers),
        wa_client.post(CODES, json=LINK_BODY, headers=headers),
    ]
    assert [r.status_code for r in responses] == [200, 201]
    assert responses[0].json()["linked"] is False
    assert responses[0].json()["last4"] is None
    assert {code.owner for code in store._codes.values()} == {caller}

    from argus.api.routers import whatsapp as routes

    revoked = []
    monkeypatch.setenv("CUADRAO_WHATSAPP_INTAKE_ENABLED", "false")
    monkeypatch.setattr(routes, "_consent_pool", lambda request: object())
    monkeypatch.setattr(routes, "AIConsentStore", lambda *args: SimpleNamespace(revoke=revoked.append))
    assert wa_client.delete(LINK, headers=headers).status_code == 204
    assert wa_client.delete("/api/v1/whatsapp/ai-consent", headers=headers).status_code == 204
    assert [str(owner) for owner in revoked] == [caller]
    assert store.destination_link(destination_owner_id=creator) == creator_link
