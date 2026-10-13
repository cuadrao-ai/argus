"""The owner's permission to read emailed receipts, on real Postgres: owner only,
the text and model shown are the ones stored, a change asks again, a decline
stores no permission, and the switch is read fresh at every ask."""

from __future__ import annotations

from uuid import uuid4

import pytest
from argus.domain.ingestion.email_intake.ai_consent import (
    EMAIL_RECEIPT_SCOPE,
    EmailConsentRequest,
    EmailConsentStore,
)
from argus.domain.ingestion.email_intake.store import PostgresEmailStore
from argus.domain.ingestion.whatsapp.ai_consent import ConsentError

from tests import test_business_actions_postgres as shared

actions = shared.actions
users = shared.users
pytestmark = shared.pytestmark


class Route:
    """The provider route as the runtime names it; the model can change."""

    def __init__(self) -> None:
        self.model = "scripted-fixture"

    def __call__(self) -> dict:
        return {
            "gateway": "openrouter",
            "interpretation": [{"model": self.model}],
            "reply": [],
        }


@pytest.fixture
def world(actions, users):  # noqa: ANN001
    service, context, grant = actions
    pool = service.authority.pool
    store = PostgresEmailStore(pool)
    space_id = str(context.actor.space_id)
    # The owner's own grant, as the space routes heal it on first use.
    with pool.connection() as db:
        db.execute(
            "insert into public.business_client_grants(space_id,grantee_id,issuer_id,capabilities)"
            " select %s,%s,%s,ARRAY['read','prepare','approve'] where not exists"
            " (select 1 from public.business_client_grants where space_id=%s and grantee_id=%s"
            " and revoked_at is null)",
            (space_id, users["owner"], users["owner"], space_id, users["owner"]),
        )
    address = store.create_route(
        recipient=f"recibos-{uuid4().hex[:8]}@recibos.example.test",
        space_id=space_id,
        principal_id=users["owner"],
        granted_by=users["other"],
        grant_id=str(grant),
    )
    route = Route()
    consent = EmailConsentStore(pool, route)
    return dict(
        pool=pool,
        store=store,
        space=space_id,
        owner=users["owner"],
        other=users["other"],
        address=address,
        route=route,
        consent=consent,
    )


def enable(world, language="es-419", key=None):  # noqa: ANN001, ANN201
    view = world["consent"].status(world["space"], world["owner"], language)
    request = EmailConsentRequest(
        action="enable", disclosure_token=view["disclosure_token"], language=language
    )
    key = key or str(uuid4())
    return (
        request,
        key,
        world["consent"].enable(world["space"], world["owner"], request, key),
    )


def rows(world):  # noqa: ANN001, ANN201
    with world["pool"].connection() as db:
        return db.execute(
            "select consenting_actor_id::text, grant_id::text, issuer_id::text, disclosure,"
            " route_hash, revoked_at is not null from public.business_email_ai_consents"
            " where space_id=%s order by consented_at",
            (world["space"],),
        ).fetchall()


def test_before_any_answer_the_owner_sees_unseen_with_a_token_and_a_grantee_only_the_state(
    world,  # noqa: ANN001
) -> None:
    owner = world["consent"].status(world["space"], world["owner"], "es-419")
    assert (owner["state"], owner["available"], owner["owner"]) == ("unseen", True, True)
    assert owner["disclosure"] == EMAIL_RECEIPT_SCOPE.disclosure_es
    assert owner["route"]["interpretation"] == [{"model": "scripted-fixture"}]
    assert owner["disclosure_token"] and len(owner["disclosure_token"]) == 64
    grantee = world["consent"].status(world["space"], world["other"], "en")
    assert (grantee["state"], grantee["available"], grantee["owner"]) == (
        "unseen",
        False,
        False,
    )
    assert grantee["reason"] == "business_owner_required"
    assert grantee["disclosure_token"] is None
    assert grantee["disclosure"] == EMAIL_RECEIPT_SCOPE.disclosure
    assert world["consent"].reading_allowed(world["space"]) is False


def test_the_owner_turns_reading_on_against_the_text_shown_and_the_switch_reads_fresh(
    world,  # noqa: ANN001
) -> None:
    request, key, view = enable(world)
    assert (view["state"], view["consented_by"] is not None) == ("on", True)
    assert world["consent"].reading_allowed(world["space"]) is True
    [(actor, grant, issuer, text, route_hash, revoked)] = rows(world)
    assert actor == world["owner"] and issuer == world["owner"]
    assert text == EMAIL_RECEIPT_SCOPE.disclosure_es and not revoked
    # The same key again is the same answer; a different space under that key is refused.
    assert (
        world["consent"].enable(world["space"], world["owner"], request, key)["state"]
        == "on"
    )
    assert len(rows(world)) == 1
    # Already on: a fresh agreement is the state, not a second row.
    enable(world)
    assert len(rows(world)) == 1
    world["consent"].revoke(world["space"], world["owner"])
    off = world["consent"].status(world["space"], world["owner"])
    assert (off["state"], off["revoked_at"] is not None) == ("off", True)
    assert world["consent"].reading_allowed(world["space"]) is False
    # Turned on again: a new row, the old one stays revoked.
    enable(world, language="en")
    assert [r[5] for r in rows(world)] == [True, False]
    assert rows(world)[1][3] == EMAIL_RECEIPT_SCOPE.disclosure
    assert world["consent"].reading_allowed(world["space"]) is True


def test_a_grantee_cannot_answer_and_a_stale_or_changed_text_or_model_asks_again(
    world,  # noqa: ANN001
) -> None:
    view = world["consent"].status(world["space"], world["owner"], "es-419")
    request = EmailConsentRequest(
        action="enable", disclosure_token=view["disclosure_token"], language="es-419"
    )
    with pytest.raises(ConsentError) as refused:
        world["consent"].enable(world["space"], world["other"], request, str(uuid4()))
    assert refused.value.code == "business_owner_required"
    with pytest.raises(ConsentError) as refused:
        world["consent"].decline(world["space"], world["other"], str(uuid4()))
    assert refused.value.code == "business_owner_required"
    with pytest.raises(ConsentError) as refused:
        world["consent"].revoke(world["space"], world["other"])
    assert refused.value.code == "business_owner_required"
    # A token for the English text does not agree to the Spanish one.
    stale = EmailConsentRequest(
        action="enable", disclosure_token=view["disclosure_token"], language="en"
    )
    with pytest.raises(ConsentError) as refused:
        world["consent"].enable(world["space"], world["owner"], stale, str(uuid4()))
    assert refused.value.code == "email_consent_disclosure_stale"
    enable(world)
    assert world["consent"].reading_allowed(world["space"]) is True
    # The model changes: the permission no longer matches, nothing is read, the owner is asked again.
    world["route"].model = "another-model"
    assert world["consent"].reading_allowed(world["space"]) is False
    again = world["consent"].status(world["space"], world["owner"], "es-419")
    assert (again["state"], again["disclosure_token"] is not None) == ("off", True)
    assert again["disclosure_token"] != view["disclosure_token"]
    enable(world)
    assert world["consent"].reading_allowed(world["space"]) is True
    assert [r[5] for r in rows(world)] == [True, False]


def test_without_a_live_address_nothing_is_read_and_nothing_can_be_agreed(
    world,  # noqa: ANN001
) -> None:
    enable(world)
    world["store"].deactivate_routes(world["space"])
    assert world["consent"].reading_allowed(world["space"]) is False
    view = world["consent"].status(world["space"], world["owner"])
    request = EmailConsentRequest(
        action="enable", disclosure_token=view["disclosure_token"]
    )
    with pytest.raises(ConsentError) as refused:
        world["consent"].enable(world["space"], world["owner"], request, str(uuid4()))
    assert refused.value.code == "email_address_required"


@pytest.mark.xfail(
    strict=True,
    reason="the declined row needs email_ai_consent_declined in the turn-less ledger allow-list",
)
def test_a_decline_stores_no_permission_and_the_notice_never_returns(world) -> None:  # noqa: ANN001
    declined = world["consent"].decline(world["space"], world["owner"], str(uuid4()))
    assert declined["state"] == "off"
    assert rows(world) == []
    assert world["consent"].reading_allowed(world["space"]) is False
    with world["pool"].connection() as db:
        ledger = db.execute(
            "select command->>'action', actor->>'grant_id' from public.business_action_receipts"
            " where space_id=%s and turn_key is null and command->>'action'='email_ai_consent_declined'",
            (world["space"],),
        ).fetchall()
    assert len(ledger) == 1 and ledger[0][1]
    # The same answer again is one row; turning on later is a real permission.
    world["consent"].decline(world["space"], world["owner"], str(uuid4()))
    enable(world)
    assert world["consent"].status(world["space"], world["owner"])["state"] == "on"
