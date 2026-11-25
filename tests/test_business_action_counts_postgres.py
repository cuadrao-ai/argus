"""Over HTTP, on the real app, Auth and Postgres: each action that moves a row
of the Bandeja answers with the counts a fresh read gives right after it."""

from __future__ import annotations

from uuid import uuid4

import pytest

from tests import test_business_listos_postgres as listos
from tests.test_business_listos_postgres import (
    _approve_alone,
    _approve_many,
    _get,
    _named,
    _read,
)
from tests.test_business_scope_switch_routes_postgres import API

pytestmark = listos.pytestmark
people = listos.people
rig = listos.rig


def _document(rig, receipt_id: str, action: str):  # noqa: ANN001, ANN202
    draft_id = _get(rig, f"/business/receipts/{receipt_id}")["draft_id"]
    return rig.client.post(
        f"{API}/business/drafts/{draft_id}/{action}",
        headers={**rig.alice.headers, "Idempotency-Key": str(uuid4())},
    )


def _delete(rig, receipts: list[str]):  # noqa: ANN001, ANN202
    return _document(rig, receipts[0], "delete")


def _restore(rig, receipts: list[str]):  # noqa: ANN001, ANN202
    assert _delete(rig, receipts).status_code == 200
    return _document(rig, receipts[0], "restore")


def _purge(rig, receipts: list[str]):  # noqa: ANN001, ANN202
    assert _delete(rig, receipts).status_code == 200
    return _document(rig, receipts[0], "purge")


def _accept(rig, receipts: list[str]):  # noqa: ANN001, ANN202
    return _approve_alone(rig, _named(rig, receipts[0]))


def _accept_all(rig, receipts: list[str]):  # noqa: ANN001, ANN202
    return _approve_many(rig, [_named(rig, receipt) for receipt in receipts])


@pytest.mark.parametrize(
    "act", [_delete, _restore, _purge, _accept, _accept_all], ids=lambda act: act.__name__
)
def test_an_action_answers_with_the_counts_a_fresh_read_gives(rig, act) -> None:  # noqa: ANN001
    receipts = [_read(rig), _read(rig), _read(rig, {"total": None})]
    answer = act(rig, receipts[:2])

    assert answer.status_code == 200, answer.text
    assert answer.json()["inbox_counts"] == _get(rig, "/business/receipt-activity")
