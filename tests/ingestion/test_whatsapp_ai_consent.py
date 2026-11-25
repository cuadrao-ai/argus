from dataclasses import replace
from uuid import uuid4

import pytest
from argus.domain.ingestion.whatsapp.ai_consent import (
    AIConsentStore,
    ConsentError,
    EnableAIConsent,
    digest,
)
from pydantic import ValidationError


@pytest.mark.parametrize(
    "extra", ["owner_id", "space_id", "sender_link_id", "grant_id", "route"]
)
def test_owner_command_cannot_supply_authority_or_route(extra):
    with pytest.raises(ValidationError):
        EnableAIConsent.model_validate(
            {
                "action": "enable",
                "disclosure_token": "a" * 64,
                extra: str(uuid4()),
            }
        )


@pytest.mark.parametrize("token", ["", "a" * 63, "A" * 64, None, 1])
def test_disclosure_token_requires_exact_digest(token):
    with pytest.raises(ValidationError):
        EnableAIConsent(action="enable", disclosure_token=token)


def test_undisclosed_route_is_unavailable_without_database_access():
    store = AIConsentStore(None, lambda: {})
    with pytest.raises(ConsentError, match="route_unavailable"):
        store._route()


def test_disclosure_token_binds_link_generation_and_actual_route():
    store = AIConsentStore(None, lambda: {})
    owner, space = uuid4(), uuid4()
    link = (uuid4(), space, owner, b"s" * 32, "1234")
    route = {
        "gateway": "openrouter",
        "interpretation": [{"model": "fixture", "provider": None}],
    }
    view = store._view(link, None, route)
    assert not view["enabled"]
    assert (
        view["disclosure_token"]
        != store._view((uuid4(), *link[1:]), None, route)["disclosure_token"]
    )
    assert (
        view["disclosure_token"]
        != store._view(link, None, {**route, "reply": []})["disclosure_token"]
    )
    assert digest(route) == digest(dict(reversed(list(route.items()))))


@pytest.mark.parametrize("suffix", [" Updated scope.", "\n"])
def test_exact_disclosure_drift_invalidates_token_and_receipt(monkeypatch, suffix):
    route = {"gateway": "synthetic-fixture"}
    store = AIConsentStore(None, lambda: route)
    link = (uuid4(), uuid4(), uuid4(), b"s" * 32, "1234")
    receipt = {
        "id": uuid4(),
        "scope_version": store.scope.version,
        "disclosure": store.scope.disclosure,
        "route_hash": digest(route),
        "consented_at": None,
        "revoked_at": None,
    }
    original = store._view(link, receipt, route)
    assert original["enabled"]
    monkeypatch.setattr(
        store,
        "scope",
        replace(store.scope, disclosure=store.scope.disclosure + suffix),
    )
    changed = store._view(link, receipt, route)
    assert changed["disclosure_token"] != original["disclosure_token"]
    assert not changed["enabled"]
    assert receipt["disclosure"] + suffix == changed["disclosure"]
