"""New fiscal rows use the existing actual deletion and purge orchestration."""

from uuid import UUID

import pytest
from argus.domain.business.authority import ActionError
from argus.domain.business.fiscal_sandbox.contracts import Observation
from argus.domain.business.fiscal_sandbox.store import Store

from tests import test_business_account_deletion_postgres as deletion
from tests import test_business_custody_graph_postgres as graph
from tests import test_business_purge_postgres as purge
from tests.fiscal import conftest as fixtures

case_factory = fixtures.case_factory

users = graph.users
actions = graph.actions
prepared = graph.prepared
custody = graph.custody
pytestmark = [graph.pytestmark, pytest.mark.owner_acts]


@pytest.mark.parametrize("phase", ["prepared", "contacted", "unknown"])
def test_actor_deletion_retains_contact_identity_and_purge_cascades(
    custody, case_factory, monkeypatch, phase
):
    w = custody
    store = Store(w["pool"])
    actor = w["context"].actor
    case = case_factory(UUID(w["space"]))
    operation = store.prepare(actor, None, case)
    if phase != "prepared":
        _, permit = store.claim(actor, None, operation.id, operation.payload_digest)
        assert permit is not None
    if phase == "unknown":
        store.record(
            operation.id, Observation(source="unknown", code="contact_uncertain")
        )
    with w["pool"].connection() as db:
        before = db.execute(
            "select contact_token,case_data,payload_digest,space_id from public.business_fiscal_operations where id=%s",
            (operation.id,),
        ).fetchone()
    deletion.close(w)
    assert deletion.command(w).delete_account(user_id=w["old"]).status == "done"
    with w["pool"].connection() as db:
        after = db.execute(
            "select contact_token,case_data,payload_digest,space_id from public.business_fiscal_operations where id=%s",
            (operation.id,),
        ).fetchone()
        assert after == before
        provenance = db.execute(
            "select prepared_actor,approved_actor from public.business_fiscal_operations where id=%s",
            (operation.id,),
        ).fetchone()
        assert str(actor.actor_id) not in str(provenance)
    with pytest.raises(ActionError):
        store.claim(actor, None, operation.id, operation.payload_digest)
    if phase != "prepared":
        # Retained commitment may settle after authority deletion, with no send permit.
        store.callback(
            case,
            Observation(
                source="callback",
                provider_id="01J00000000000000000000000",
                issuer=case.issuer,
                number=case.number,
                processing="FINISHED",
                legal="ACCEPTED",
            ),
        )
    purge.remover(w, monkeypatch)
    purge.expiry(w)
    assert deletion.command(w).resume_pending(idle_seconds=0)["done"] == 1
    with w["pool"].connection() as db:
        assert (
            db.execute(
                "select 1 from public.business_fiscal_operations where id=%s",
                (operation.id,),
            ).fetchone()
            is None
        )
        assert (
            db.execute(
                "select 1 from public.business_fiscal_observations where operation_id=%s",
                (operation.id,),
            ).fetchone()
            is None
        )
        db.execute(
            "delete from argus_private.business_purge_runs where space_id=%s",
            (w["space"],),
        )
    if phase != "prepared":
        store.callback(
            case,
            Observation(
                source="callback",
                provider_id="01J00000000000000000000000",
                issuer=case.issuer,
                number=case.number,
                processing="FINISHED",
                legal="ACCEPTED",
            ),
        )
        with w["pool"].connection() as db:
            assert db.execute(
                "select 1 from public.business_fiscal_observations where operation_id is null and evidence->>'number'=%s",
                (case.number,),
            ).fetchone()


@pytest.mark.parametrize("contacted", [False, True])
def test_ownership_transfer_never_reopens_contact(custody, case_factory, contacted):
    w = custody
    store = Store(w["pool"])
    actor = w["context"].actor
    case = case_factory(UUID(w["space"]))
    operation = store.prepare(actor, None, case)
    if contacted:
        store.claim(actor, None, operation.id, operation.payload_digest)
        store.record(
            operation.id, Observation(source="unknown", code="contact_uncertain")
        )
    deletion.transfer(w)
    with pytest.raises(ActionError):
        store.claim(actor, None, operation.id, operation.payload_digest)
    from argus.domain.business.contracts.authority import TrustedActor

    new_owner = TrustedActor(
        actor_id=w["users"]["other"], actor_kind="member", space_id=case.business_id
    )
    _, permit = store.claim(new_owner, None, operation.id, operation.payload_digest)
    assert (permit is None) == contacted
