from __future__ import annotations

import pytest
from argus.domain.business.contracts.actions import ApproveExpense
from argus.domain.business.transactions import transaction
from faker import Faker

from tests import test_business_actions_postgres as shared

fake = Faker()
users = shared.users
actions = shared.actions
pytestmark = shared.pytestmark


@pytest.mark.parametrize("role", ["actor", "issuer"])
@pytest.mark.parametrize(
    "display_name,username,expected",
    [
        ("  María 李  ", None, "María 李"),
        ("Contadora de prueba", "accountant_handle", "Contadora de prueba"),
        (None, "  existing_handle  ", "existing_handle"),
        ("   ", "existing_handle", "existing_handle"),
        (None, None, "Member"),
        ("   ", "   ", "Member"),
        ("\t", None, "Member"),
        ("\n", "existing_handle", "existing_handle"),
        ("\t\n\r\f\v ", "\nexisting_handle\t", "existing_handle"),
        (None, "\t\n\r\f\v ", "Member"),
        ("\t María 李 \n\r\f\v", None, "María 李"),
        ("\u00a0María 李\u2003", None, "María 李"),
        ("\u00a0\u2003", "existing_handle", "existing_handle"),
    ],
)
def test_actor_and_issuer_labels_use_existing_profile_identity(
    actions, role: str, display_name: str | None, username: str | None, expected: str
) -> None:
    service, context, grant = actions
    with transaction(service.authority, context) as tx:
        before = tx.authorization
    user_id = (
        before.provenance.actor_id if role == "actor" else before.provenance.issuer_id
    )
    with service.authority.pool.connection() as db:
        db.execute(
            "update public.profiles set display_name=%s,username=%s,preferred_name=%s"
            " where id=%s",
            (display_name, username, "Greeting only", user_id),
        )
    with transaction(service.authority, context) as tx:
        after = tx.authorization
    assert after.context == before.context
    assert after.capabilities == before.capabilities
    assert after.provenance.actor_id == before.provenance.actor_id
    assert after.provenance.issuer_id == before.provenance.issuer_id
    assert after.provenance.grant_id == grant
    assert after.provenance.actor_kind == before.provenance.actor_kind
    if role == "actor":
        assert after.provenance.display_name == expected
        assert (
            after.provenance.issuer_display_name == before.provenance.issuer_display_name
        )
    else:
        assert after.provenance.issuer_display_name == expected
        assert after.provenance.display_name == before.provenance.display_name
    with service.authority.pool.connection() as db:
        assert db.execute(
            "select display_name,username from public.profiles where id=%s", (user_id,)
        ).fetchone() == (display_name, username)


@pytest.mark.parametrize("named", [False, True])
def test_profile_rename_preserves_original_approval_and_revision_labels(
    actions, named: bool
) -> None:
    service, context, grant = actions
    actor_name = "Contadora de prueba" if named else None
    issuer_name = "Dueña de prueba" if named else None
    with transaction(service.authority, context) as tx:
        actor = tx.authorization.provenance
    with service.authority.pool.connection() as db:
        db.execute(
            "update public.profiles set display_name=%s,username=null where id=%s",
            (actor_name, actor.actor_id),
        )
        db.execute(
            "update public.profiles set display_name=%s,username=null where id=%s",
            (issuer_name, actor.issuer_id),
        )
    draft = shared.ready(service, context, owner_funds=True)
    request = ApproveExpense(version=1, action="record_expense")
    key = fake.uuid4()
    result = service.approve(context, draft, request, key)
    assert result.outcome == "applied"
    original = service.dossier(context, draft)
    saved_actor = original.approval_result.actor
    assert saved_actor.display_name == (actor_name if named else "Member")
    assert saved_actor.issuer_display_name == (issuer_name if named else "Member")
    assert saved_actor.actor_id == actor.actor_id
    assert saved_actor.issuer_id == actor.issuer_id
    assert saved_actor.grant_id == grant
    assert original.approval_result.reviewed_version == 1
    assert all(revision.actor == saved_actor for revision in original.history)
    renamed_actor, renamed_issuer = fake.name(), fake.name()
    with service.authority.pool.connection() as db:
        db.execute(
            "update public.profiles set display_name=%s where id=%s",
            (renamed_actor, actor.actor_id),
        )
        db.execute(
            "update public.profiles set display_name=%s where id=%s",
            (renamed_issuer, actor.issuer_id),
        )
    with transaction(service.authority, context) as tx:
        assert tx.authorization.provenance.display_name == renamed_actor
        assert tx.authorization.provenance.issuer_display_name == renamed_issuer
    assert service.approve(context, draft, request, key) == result
    reread = service.dossier(context, draft)
    assert reread.approval_result == original.approval_result
    assert reread.history == original.history
