"""The list, dossier, and approval use the same decision about a draft's sender."""

from __future__ import annotations

import pytest
from argus.domain.ingestion.email_intake import sender_policy

from tests import test_business_listos_postgres as listos
from tests.business.test_business_api import RECEIPT
from tests.test_business_dossier_standing_postgres import _same_as_the_list

pytestmark = listos.pytestmark
people = listos.people
rig = listos.rig


@pytest.mark.parametrize(
    ("standing", "refused"),
    [
        (None, False),
        ("authorized", False),
        ("new", True),
        ("pending", True),
        ("blocked", True),
    ],
)
def test_each_sender_standing_agrees_on_the_list_dossier_and_approval(
    rig,  # noqa: ANN001
    monkeypatch: pytest.MonkeyPatch,
    standing: str | None,
    refused: bool,
) -> None:
    if standing is None:
        receipt = listos._read(rig)
    else:
        runtime, receipt, _ = listos._delivered(rig, monkeypatch, RECEIPT)
        [rule] = runtime.store.list_senders(rig.alice.space_id)
        if standing == "new":
            runtime.store.remove_sender(rig.alice.space_id, rule.id)
        elif standing != "authorized":
            runtime.store.upsert_sender(
                rig.alice.space_id, "address", rule.value, standing
            )

    _assert_sender_decision(rig, receipt, refused)


def _assert_sender_decision(rig, receipt: str, refused: bool) -> None:  # noqa: ANN001
    dossier = _same_as_the_list(rig, receipt)
    assert dossier["listo_gaps"] == (["unverified_sender"] if refused else [])
    answer = listos._approve_alone(rig, listos._named(rig, receipt))
    if refused:
        assert (answer.status_code, answer.json()["code"]) == (
            403,
            "email_sender_unauthorized",
        )
    else:
        assert answer.status_code == 200, answer.text


def test_the_list_dossier_and_approve_route_consume_the_sender_decision(
    rig,  # noqa: ANN001
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, receipt, _ = listos._delivered(rig, monkeypatch, RECEIPT)
    monkeypatch.setattr(
        sender_policy,
        "sender_refusal",
        lambda standing: "email_sender_unauthorized"
        if standing == "authorized"
        else None,
    )
    _assert_sender_decision(rig, receipt, refused=True)
