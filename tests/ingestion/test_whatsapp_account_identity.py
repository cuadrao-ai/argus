"""Channel account authority belongs to the caller across Business ownership changes."""

from dataclasses import replace
from types import SimpleNamespace

import pytest
from argus.api.business_spaces import business_access, business_spaces
from argus.api.whatsapp import configure_whatsapp, whatsapp_runtime
from argus.domain.business.roles import BusinessRole
from faker import Faker

from tests.ingestion.conftest import ALICE, BOB, bearer
from tests.ingestion.test_whatsapp_api import (  # noqa: F401
    CODES,
    LINK,
    consent_reads,
    graph,
    link_alice,
    wa_client,
)


@pytest.mark.parametrize("supported_destination,selected", [(False, True), (True, True), (True, False)])
def test_transferred_business_never_uses_creators_channel_account(
    wa_client, consent_reads, identities, supported_destination, selected
):
    fake = Faker()
    creator, caller = identities[ALICE]["id"], identities[BOB]["id"]
    spaces, access = business_spaces(), business_access()
    transferred, _ = spaces.create_additional(creator, fake.company(), "DO", fake.uuid4())
    # Model the persisted transfer: the creator stays on the space, the live
    # Owner membership belongs to the recipient.
    access._live(transferred.id, creator)["revoked_at"] = access._now()
    grant = access._insert_grant(transferred.id, caller, caller, BusinessRole.OWNER)
    if supported_destination:
        spaces._defaults[caller] = transferred.id
    link_alice(wa_client)
    runtime = whatsapp_runtime()
    store = runtime.intake.store
    creator_link = store.destination_link(destination_owner_id=creator)
    assert creator_link is not None
    status = runtime.receipts.status
    configure_whatsapp(replace(runtime, receipts=SimpleNamespace(
        status=status, enable=lambda owner, body, key: status(owner, None)
    )))
    headers = {**bearer(BOB), **({"X-Business-Grant": grant["id"]} if selected else {})}
    availability = wa_client.get("/api/v1/business/workspace", headers=headers)
    assert availability.status_code == 200, availability.text
    assert availability.json()["receiving_channels"]["whatsapp"]["available"] is supported_destination
    responses = [
        wa_client.get(LINK, headers=headers),
        wa_client.post(CODES, headers=headers),
        wa_client.get("/api/v1/whatsapp/ai-consent", headers=headers),
        wa_client.post("/api/v1/whatsapp/ai-consent", headers={**headers, "Idempotency-Key": fake.uuid4()},
                       json={"action": "enable", "disclosure_token": "a" * 64}),
    ]
    if supported_destination:
        assert [r.status_code for r in responses] == [200, 201, 200, 200]
        assert responses[0].json() == {"linked": False, "last4": None, "linked_at": None, "reply_language": None}
        assert [str(owner) for owner, _ in consent_reads] == [caller, caller]
        assert {code.owner for code in store._codes.values() if not code.consumed} == {caller}
    else:
        assert [r.status_code for r in responses] == [404] * 4
        assert consent_reads == []
    assert store.destination_link(destination_owner_id=creator) == creator_link
