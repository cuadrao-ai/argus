"""A person's same-Business duplicate decision opens only the named pair."""
from __future__ import annotations

from uuid import uuid4

import pytest

from tests import test_business_duplicates_postgres as receipts
from tests import test_business_attachment_preparation_postgres as preparation


actions = receipts.actions
users = receipts.users
pytestmark = receipts.pytestmark


def pair(actions):
    prepared = []
    for content in (b"Synthetic purchase one", b"Synthetic purchase two"):
        receipt = receipts._receipt(actions, content)
        preparation.bind(receipt)
        prepared.append(preparation.finish(receipt).draft_id)
    return prepared


def request_for(service, context, draft_id, other_id):
    from argus.domain.business.contracts.actions import ResolveDuplicate

    return ResolveDuplicate(
        version=service.dossier(context, draft_id).version,
        other_draft_id=other_id,
        other_version=service.dossier(context, other_id).version,
        decision="different_purchase",
    )


@pytest.mark.owner_acts
def test_explicit_decision_clears_duplicate_only_and_is_durable(actions):
    service, context, _ = actions
    first, second = pair(actions)
    before = service.dossier(context, second)
    assert "possible_duplicate" in {b.code for b in before.blockers}
    request = request_for(service, context, second, first)
    key = str(uuid4())
    decided = service.resolve_duplicate(context, second, request, key)
    assert decided.outcome == "applied", decided
    after = service.dossier(context, second)
    assert "possible_duplicate" not in {b.code for b in after.blockers}
    assert after.version == before.version + 1
    assert len(after.history) == len(before.history) + 1
    assert "fact_required" in {b.code for b in after.blockers}
    assert after.approval_available is False
    assert service.resolve_duplicate(context, second, request, key) == decided
    with service.authority.pool.connection() as db:
        assert db.execute(
            "select count(*) from public.financial_records where owner_space_id=%s",
            (context.actor.space_id,),
        ).fetchone() == (0,)
