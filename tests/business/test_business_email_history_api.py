"""Receiving availability cannot erase past deliveries or receipt provenance."""

from dataclasses import replace
from types import SimpleNamespace

import pytest
from argus.api import email_intake as intake
from argus.domain.ingestion.email_intake.models import EmailDeliveryPart
from faker import Faker

from tests.business.test_business_api import BASE, Owner, alice, bob  # noqa: F401
from tests.business.test_business_email_api import runtime  # noqa: F401
from tests.business.test_business_review_counts import PERIOD, _email


@pytest.mark.parametrize("runtime_present", [True, False])
def test_history_counts_and_provenance_survive_receiving_off(
    alice: Owner, bob: Owner, runtime, monkeypatch, runtime_present  # noqa: F811
):
    fake = Faker()
    original, attachment = _email(alice, runtime)
    space = alice.scope().owner.space_id
    route = runtime.store.route_for_space(space)
    waiting = runtime.store.enqueue(
        runtime.store.list(space)[0].provider, fake.uuid4(), (route.recipient,), route_id=route.id,
        space_id=space, principal_id=route.principal_id,
    )
    claimed = runtime.store.claim(delivery_id=waiting.id)
    runtime.store.update(claimed, subject=fake.sentence())
    runtime.store.put_part(
        claimed, EmailDeliveryPart("1", "file.bin", "application/octet-stream", "rejected", None, "email_part_unsupported")
    )
    runtime.store.finish(claimed, "rejected", "email_parts_rejected")
    runtime.store._deliveries[waiting.id] = replace(
        runtime.store.get(waiting.id, space), inbox_group="bandeja"
    )
    before = {
        path: alice.get(path, **params).json()
        for path, params in (("/email/deliveries", {}), ("/email/inbox", {}),
                             ("/receipt-activity", {}), ("/overview", PERIOD))
    }
    assert any(row["id"] == waiting.id for row in before["/email/deliveries"]["items"])
    assert before["/receipt-activity"]["needs_attention_count"] == 1
    monkeypatch.setattr(intake, "webhook_enabled", lambda: False)
    if not runtime_present:
        pool = object()
        documents = SimpleNamespace(
            store=runtime.documents.store,
            business_actions=SimpleNamespace(authority=SimpleNamespace(pool=pool)),
        )
        monkeypatch.setattr(intake, "documents_service", lambda: documents)
        monkeypatch.setattr(intake, "PostgresEmailStore", lambda selected: runtime.store if selected is pool else None)
        intake.configure_email_intake(None)
    assert alice.get("/workspace").json()["receiving_channels"]["email"] == {"available": False}
    for path, params in (("/email/deliveries", {}), ("/email/inbox", {}),
                         ("/receipt-activity", {}), ("/overview", PERIOD)):
        response = alice.get(path, **params)
        assert response.status_code == 200, response.text
        assert response.json() == before[path]
    detail = alice.get(f"/email/deliveries/{waiting.id}")
    assert detail.status_code == 200, detail.text
    assert detail.json()["standing"] == "no_receipt"
    assert len(detail.json()["parts"]) == 1
    assert detail.json()["retryable"] is False
    assert alice.post(f"/email/deliveries/{waiting.id}/retry").status_code == 404
    receipts = {row["id"]: row for row in alice.get("/receipts", view="all").json()["items"]}
    assert receipts[attachment]["channel"] == receipts[original]["channel"] == "email"
    assert receipts[original]["email_original"] is True
    assert receipts[attachment]["email_delivery_ids"] == receipts[original]["email_delivery_ids"]
    assert alice.get(f"/receipts/{original}/source").status_code == 200
    assert len(alice.get("/search", q="Factura 0113").json()["email_deliveries"]) == 1
    assert bob.get("/email/deliveries").json() == {"items": []}
    assert bob.get(f"/email/deliveries/{waiting.id}").status_code == 404
    assert alice.client.get(BASE + "/email/deliveries").status_code == 401
