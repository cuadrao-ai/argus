import pytest
from argus.api.business_drafts import receipt_detail, receipt_summaries, scoped_legacy
from argus.api.business_receipt_activity import project
from argus.domain.business.contracts.actions import ReviewDraft
from argus.domain.business.contracts.facts import BusinessFactPatch
from argus.domain.business.receipt_consent import BusinessReceiptConsentStore
from argus.domain.business.scope import BusinessScope
from fastapi import FastAPI
from starlette.requests import Request

from tests import test_business_attachment_preparation_postgres as bridge
from tests import test_business_receipt_views_postgres as views
from tests import test_business_single_candidate_postgres as single

actions = bridge.actions
users = bridge.users
pytestmark = bridge.pytestmark


def ready(actions):
    saved = single._saved(actions, "expense")
    bridge.bind(saved)
    result = bridge.finish(saved)
    assert result.outcome == "applied"
    service, context, _, cid, _, _ = saved
    web = views._web(service, context)
    draft = web.service.documents.store.draft(user_id=context.owner_id, connection_id=cid)
    web.service.documents._update(
        context.owner_id, draft, holder=saved[4], status="review_ready", error_code=None
    )
    return service, context, cid, result.draft_id, web


@pytest.mark.owner_acts
def test_cursor_tracks_canonical_revision_and_stale_ack_preserves_new_content(actions):
    service, context, cid, draft_id, web = ready(actions)
    before = receipt_detail(web, web.service.receipt(web.scope, cid))
    listed = next(row for row in receipt_summaries(web, "inbox") if row["id"] == cid)
    assert listed["activity"] == before["activity"]
    assert before["activity"]["unread"] is True, (
        before["activity"],
        before["status"],
        before["read_pending"],
        web.service.receipt(web.scope, cid).draft.updated_at,
    )
    first = project(
        web, [before], acknowledge_id=cid, cursor=before["activity"]["completion_cursor"]
    )[0]
    assert first["activity"]["unread"] is False
    outcome = service.review(
        context,
        draft_id,
        ReviewDraft(
            version=before["version"],
            facts=BusinessFactPatch.model_validate(
                {"counterparty": {"state": "known", "value": "Reviewed shop"}}
            ),
        ),
        "activity-test-review",
    )
    assert outcome.outcome == "applied"
    newer = receipt_detail(web, web.service.receipt(web.scope, cid))
    assert (
        newer["activity"]["completion_cursor"] != before["activity"]["completion_cursor"]
    )
    assert newer["activity"]["unread"] is True
    assert (
        project(
            web,
            [before],
            acknowledge_id=cid,
            cursor=before["activity"]["completion_cursor"],
        )[0]["activity"]["unread"]
        is True
    )
    assert (
        project(
            web,
            [newer],
            acknowledge_id=cid,
            cursor=newer["activity"]["completion_cursor"],
        )[0]["activity"]["unread"]
        is False
    )
    assert service.dossier(context, draft_id).version == newer["version"]


@pytest.mark.owner_acts
def test_read_only_viewer_boundary_is_isolated_from_owner_and_no_financial_write(
    actions, users
):
    service, context, cid, draft_id, owner = ready(actions)
    with service.authority.pool.connection() as db:
        grant = db.execute(
            "insert into public.business_client_grants(space_id,grantee_id,issuer_id,capabilities) values (%s,%s,%s,ARRAY['read']) returning id",
            (context.actor.space_id, users["other"], context.owner_id),
        ).fetchone()[0]
        before = db.execute(
            "select version,state,resolution,updated_at from public.financial_import_events where id=%s",
            (draft_id,),
        ).fetchone()
    app = FastAPI()
    app.state.financial_accounts_pool = service.authority.pool
    request = Request(
        {
            "type": "http",
            "app": app,
            "method": "POST",
            "path": f"/api/v1/business/receipts/{cid}/read",
            "path_params": {"receipt_id": cid},
            "headers": [],
            "state": {},
        }
    )
    scope = BusinessScope(
        person_id=str(context.owner_id),
        owner=context.scope,
        actor_id=str(users["other"]),
        grant_id=str(grant),
        role="accountant",
    )
    reader = scoped_legacy(
        request,
        owner.service.documents,
        owner.service.documents.hub,
        str(users["other"]),
        scope,
    )
    detail = receipt_detail(reader, reader.service.receipt(reader.scope, cid))
    assert reader.record_context.capabilities == {"read"}
    assert (
        project(
            reader,
            [detail],
            acknowledge_id=cid,
            cursor=detail["activity"]["completion_cursor"],
        )[0]["activity"]["unread"]
        is False
    )
    assert (
        receipt_detail(owner, owner.service.receipt(owner.scope, cid))["activity"][
            "unread"
        ]
        is True
    )
    with service.authority.pool.connection() as db:
        assert (
            db.execute(
                "select version,state,resolution,updated_at from public.financial_import_events where id=%s",
                (draft_id,),
            ).fetchone()
            == before
        )
        assert (
            db.execute(
                "select count(*) from public.business_receipt_read_states where space_id=%s and connection_id=%s",
                (context.actor.space_id, cid),
            ).fetchone()[0]
            == 1
        )


@pytest.mark.owner_acts
def test_consent_generations_revoke_without_adopting_old_permission(actions):
    service, context, _ = actions
    store = BusinessReceiptConsentStore(
        service.authority.pool,
        lambda: {
            "gateway": "fixture",
            "interpretation": [{"model": "fixture-reader"}],
            "reply": [],
        },
    )
    space, owner = str(context.actor.space_id), str(context.owner_id)
    shown = store.status(space, owner)
    assert shown["enabled"] is False
    accepted = store.set(
        space, owner, enabled=True, version=1, disclosure_token=shown["disclosure_token"]
    )
    assert store.enabled(space, owner, accepted["consent_id"])
    store.set(space, owner, enabled=False, version=1)
    assert not store.enabled(space, owner, accepted["consent_id"])
    again = store.set(
        space, owner, enabled=True, version=1, disclosure_token=shown["disclosure_token"]
    )
    assert again["consent_id"] != accepted["consent_id"]
    assert not store.enabled(space, owner, accepted["consent_id"])


@pytest.mark.owner_acts
def test_delayed_consent_commands_cannot_reverse_a_later_choice(actions):
    service, context, _ = actions
    store = BusinessReceiptConsentStore(
        service.authority.pool,
        lambda: {
            "gateway": "fixture",
            "interpretation": [{"model": "fixture-reader"}],
            "reply": [],
        },
    )
    space, owner = str(context.actor.space_id), str(context.owner_id)
    token = store.status(space, owner)["disclosure_token"]
    first = store.set(
        space,
        owner,
        enabled=True,
        version=1,
        disclosure_token=token,
        idempotency_key="first-enable",
    )
    store.set(
        space,
        owner,
        enabled=True,
        version=1,
        disclosure_token=token,
        idempotency_key="noop-enable",
    )
    store.set(space, owner, enabled=False, version=1, idempotency_key="turn-off")
    assert not store.set(
        space,
        owner,
        enabled=True,
        version=1,
        disclosure_token=token,
        idempotency_key="first-enable",
    )["enabled"]
    assert not store.set(
        space,
        owner,
        enabled=True,
        version=1,
        disclosure_token=token,
        idempotency_key="noop-enable",
    )["enabled"]
    current = store.set(
        space,
        owner,
        enabled=True,
        version=1,
        disclosure_token=token,
        idempotency_key="second-enable",
    )
    assert current["consent_id"] != first["consent_id"]
    assert store.set(space, owner, enabled=False, version=1, idempotency_key="turn-off")[
        "enabled"
    ]
    assert store.enabled(space, owner, current["consent_id"])


@pytest.mark.owner_acts
def test_concurrent_enable_commands_create_one_current_generation(actions):
    from concurrent.futures import ThreadPoolExecutor

    service, context, _ = actions
    store = BusinessReceiptConsentStore(
        service.authority.pool,
        lambda: {
            "gateway": "fixture",
            "interpretation": [{"model": "fixture-reader"}],
            "reply": [],
        },
    )
    space, owner = str(context.actor.space_id), str(context.owner_id)
    token = store.status(space, owner)["disclosure_token"]

    def accept(key):
        return store.set(
            space,
            owner,
            enabled=True,
            version=1,
            disclosure_token=token,
            idempotency_key=key,
        )

    with ThreadPoolExecutor(max_workers=2) as workers:
        result = list(workers.map(accept, ["enable-a", "enable-b"]))
    assert result[0]["consent_id"] == result[1]["consent_id"]
    with service.authority.pool.connection() as db:
        assert (
            db.execute(
                "select count(*) from public.business_receipt_consent_commands where space_id=%s",
                (space,),
            ).fetchone()[0]
            == 2
        )
        assert (
            db.execute(
                "select count(*) from public.business_receipt_reading_consents where space_id=%s",
                (space,),
            ).fetchone()[0]
            == 1
        )
