"""Which receipt a row of the legacy receipt surface leads to, read against
real records."""

from __future__ import annotations

from uuid import uuid4

import pytest
from argus.domain.business.activity.queries import read_activity
from argus.domain.business.authority import authorize
from argus.domain.business.contracts.activity import ActivityFilters
from argus.domain.business.transactions import LegacyAction, record_legacy_action

from tests import test_business_actions_postgres as shared
from tests.test_business_single_candidate_postgres import _saved

users = shared.users
actions = shared.actions
pytestmark = [shared.pytestmark, pytest.mark.owner_acts]


def _record(service, context, action: LegacyAction, subjects: list[str]) -> None:
    with service.authority.pool.connection() as db:
        live = authorize(db, context.actor, context.grant_id)
        record_legacy_action(db, live, action, subjects, str(uuid4()))


def _named(service, context, filters: ActivityFilters | None = None) -> list:
    feed = read_activity(service.authority, context, limit=25, filters=filters)
    return sorted(
        (
            item.action,
            None
            if item.object is None
            else (item.object.kind, str(item.object.id), item.object.label),
        )
        for item in feed.items
        if item.action.startswith("receipt_")
    )


def test_a_legacy_row_leads_to_the_one_receipt_its_subject_answers_to(actions):
    service, context, _, cid, _, batch = _saved(actions, "expense")
    service.imports.submit(
        user_id=context.owner_id,
        connection_id=cid,
        candidates=batch.candidates,
        scope=context.scope,
    )
    with service.authority.pool.connection() as db:
        [(event_id,)] = db.execute(
            "select distinct event_id from public.financial_import_observations"
            " where connection_id=%s",
            (cid,),
        ).fetchall()
    _record(service, context, "receipt_upload", [str(cid)])
    _record(service, context, "receipt_review", [str(event_id)])
    _record(service, context, "receipt_confirm", [str(event_id), str(cid)])

    receipt = ("receipt", str(cid), "image.png")
    assert _named(service, context) == [
        ("receipt_confirm", receipt),
        ("receipt_review", receipt),
        ("receipt_upload", receipt),
    ]
    assert _named(service, context, ActivityFilters(q="image")) == [
        ("receipt_confirm", receipt),
        ("receipt_review", receipt),
        ("receipt_upload", receipt),
    ]


def test_a_legacy_subject_that_is_no_receipt_of_the_business_names_nothing(actions):
    service, context, _ = actions
    _record(service, context, "receipt_upload", [str(uuid4())])
    _record(service, context, "receipt_confirm", [str(uuid4()), str(uuid4())])

    assert _named(service, context) == [
        ("receipt_confirm", None),
        ("receipt_upload", None),
    ]
