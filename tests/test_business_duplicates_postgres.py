"""On real Postgres through the C0 bridge: a second draft whose read merchant,
date, amount and currency equal another draft's is flagged as a possible
duplicate, loses approval, and the first draft stays untouched."""

from __future__ import annotations

from uuid import UUID

import pytest
from argus.domain.business.actions.mutations import flag_duplicates
from argus.domain.business.contracts.actions import ApproveExpense, ProposeActivity
from argus.domain.business.contracts.facts import BusinessFactPatch
from argus.domain.business.transactions import transaction

from tests import test_business_actions_postgres as shared

actions = shared.actions
users = shared.users
pytestmark = shared.pytestmark

FACTS = {
    "kind": "expense",
    "amount": "850",
    "currency": "DOP",
    "occurred_on": "2026-10-01",
    "counterparty": "Ferretería El Tornillo",
    "business_share": {"kind": "all"},
}


def _draft(service, context, **overrides) -> tuple[UUID, int]:  # noqa: ANN001
    evidence = shared.source(service, context)
    patch = BusinessFactPatch.model_validate(
        {
            name: {"state": "known", "value": value}
            for name, value in {**FACTS, **overrides}.items()
        }
    )
    plan, lease = shared.prepare(
        service, context, [ProposeActivity(facts=patch, source_ids=(evidence,))]
    )
    result = service.execute(context, plan, 0, lease=lease)
    assert result.outcome == "applied", result
    return result.draft_id, result.version


def test_the_same_read_facts_flag_the_second_draft_and_block_its_approval(
    actions,
) -> None:  # noqa: ANN001
    service, context, _ = actions
    first, _ = _draft(service, context)
    second, version = _draft(service, context, counterparty="  FERRETERÍA EL TORNILLO ")
    other, _ = _draft(service, context, amount="851")
    with transaction(service.authority, context, "prepare") as tx:
        assert flag_duplicates(tx, second) == (str(first),)
        assert flag_duplicates(tx, other) == ()
        assert flag_duplicates(tx, first) == (str(second),)
    # The mark is the event's own attention: durable and visible to every reader.
    with service.authority.pool.connection() as db:
        assert db.execute(
            "select attention, possible_duplicates::text[], attention_detail->>'basis'"
            " from public.financial_import_events where id=%s",
            (second,),
        ).fetchone() == ("possible_duplicate", [str(first)], "read_facts")
    view = service.dossier(context, second)
    assert [b.code for b in view.blockers] == ["possible_duplicate"]
    assert view.approval_available is False
    assert view.facts.amount.value == "850.00" or view.facts.amount.value == "850"
    refused = service.approve(
        context, second, ApproveExpense(version=version, action="record_expense"), "dup"
    )
    assert (refused.outcome, refused.code) == ("invalid_input", "possible_duplicate")
    assert service.dossier(context, other).blockers == ()


def test_unknown_facts_never_match(actions) -> None:  # noqa: ANN001
    service, context, _ = actions
    _draft(service, context)
    second, _ = _draft(service, context)
    with transaction(service.authority, context, "prepare") as tx:
        tx.rows(
            "update public.financial_import_events set resolution ="
            ' jsonb_set(resolution, \'{business,facts,counterparty}\', \'{"state":"unknown","value":null,"origin":"extracted","verified":false,"source_ids":[]}\')'
            " where id=%s",
            (second,),
        )
        assert flag_duplicates(tx, second) == ()
    with pytest.raises(Exception):  # noqa: B017 - a draft with no Business facts is not a match either
        with transaction(service.authority, context, "prepare") as tx:
            flag_duplicates(tx, UUID(int=0))
