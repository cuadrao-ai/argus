from __future__ import annotations

import pytest
from argus.domain.business.transactions import transaction
from faker import Faker

from tests import test_business_actions_postgres as shared

fake = Faker()
users = shared.users
actions = shared.actions
pytestmark = shared.pytestmark


@pytest.mark.parametrize("role", ["actor", "issuer"])
@pytest.mark.parametrize(
    "display_name,username",
    [
        (fake.name(), None),
        (fake.name(), fake.user_name()),
        (None, fake.user_name()),
        ("   ", None),
        (None, None),
    ],
)
def test_the_stored_actor_keeps_who_and_never_a_label(
    actions, role: str, display_name: str | None, username: str | None
) -> None:
    """Who acted is the id; readers name the person live (#2219)."""

    service, context, grant = actions
    with transaction(service.authority, context) as tx:
        before = tx.authorization
    user_id = (
        before.provenance.actor_id if role == "actor" else before.provenance.issuer_id
    )
    with service.authority.pool.connection() as db:
        db.execute(
            "update public.profiles set display_name=%s,username=%s where id=%s",
            (display_name, username, user_id),
        )
    with transaction(service.authority, context) as tx:
        after = tx.authorization
    assert after.context == before.context
    assert after.provenance == before.provenance
    assert after.provenance.grant_id == grant
    assert (after.provenance.display_name, after.provenance.issuer_display_name) == (
        "",
        "",
    )
