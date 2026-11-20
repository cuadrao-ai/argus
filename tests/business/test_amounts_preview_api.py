from types import SimpleNamespace
from uuid import uuid4

import pytest
from argus.api.business_drafts import require_drafts
from argus.api.routers.business_drafts import router
from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.amounts import AmountsPreview
from argus.domain.business.contracts.dossier import ReviewFlag
from argus.domain.business.contracts.facts import InheritedValue, NetAmount
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.business import test_fiscal_links as links

DECLARATION = links.fresh(links.read()).model_dump(mode="json")


@pytest.mark.parametrize(("outcome", "code", "status"), [
    (None, None, 200),
    ("permission_denied", "business_permission_denied", 403),
    ("not_found", "business_record_not_found", 404),
    ("stale_version", "stale_version", 409),
])
def test_preview_uses_scoped_draft_context_and_no_store(outcome, code, status):
    calls = []
    draft_id = uuid4()
    actor = object()

    def scoped(draft):
        assert draft == draft_id
        calls.append("scope")
        if outcome:
            raise ActionError(outcome, code)
        return actor

    def preview(context, draft, body):
        assert context is actor and draft == draft_id
        assert body.version == 3 and body.amount.value == "1200"
        assert body.declaration.goods_amount == "400.00"
        assert (body.override_inherited, body.restore_inherited) == (("goods_amount",), ("paid_on",))
        calls.append("preview")
        return AmountsPreview(
            net_amount=NetAmount(amount="1000", source="read"),
            mismatch=ReviewFlag(code="amounts_mismatch", field="amount", confirm=False, difference="20.00"),
            inheritance={"goods_amount": InheritedValue(field="net_amount", value="1000.00", inherited=False, paired_with=("services_amount",))},
        )

    app = FastAPI()
    @app.middleware("http")
    async def request_id(request, call_next):
        request.state.request_id = "preview-test"
        return await call_next(request)

    app.include_router(router)
    app.dependency_overrides[require_drafts] = lambda: SimpleNamespace(for_draft=scoped, service=SimpleNamespace(preview_amounts=preview))
    with TestClient(app) as client:
        response = client.post(f"/business/drafts/{draft_id}/amounts-preview", json={
            "version": 3,
            "amount": {"state": "known", "value": "1200"},
            "declaration": {**DECLARATION, "goods_amount": "400.00"},
            "override_inherited": ["goods_amount"],
            "restore_inherited": ["paid_on"],
        })
    assert response.status_code == status
    assert "no-store" in response.headers["cache-control"]
    assert calls == (["scope", "preview"] if status == 200 else ["scope"])
    if status == 200:
        assert response.json()["mismatch"]["difference"] == "20.00"
        assert response.json()["inheritance"] == {"goods_amount": {"field": "net_amount", "value": "1000.00", "inherited": False, "paired_with": ["services_amount"]}}


def test_preview_refuses_a_link_overridden_and_restored_together():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[require_drafts] = lambda: SimpleNamespace()
    with TestClient(app) as client:
        response = client.post(
            f"/business/drafts/{uuid4()}/amounts-preview",
            json={"version": 1, "override_inherited": ["paid_on"], "restore_inherited": ["paid_on"]},
        )
    assert response.status_code == 422
