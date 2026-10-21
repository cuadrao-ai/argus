"""The readings every view shares: what is personal, what carries a fiscal
number, what the accountant answered; approval admits a personal receipt and
still refuses a partial share; the export's words for the marks; a read-only
grant's refusal is a 403."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from argus.domain.business.actions.dossier import blockers
from argus.domain.business.actions.marks import fiscal_inclusion_available
from argus.domain.business.contracts.facts import (
    BusinessFacts,
    FiscalFacts,
    Known,
    OwnerFunding,
    Unknown,
    WholeBusinessShare,
    fiscal_inclusion,
    fiscal_value,
    is_personal,
)
from argus.domain.business.export import _marks

SOURCE = uuid4()


def known(value, origin="owner_stated", verified=True):  # noqa: ANN001, ANN201
    return Known(value=value, origin=origin, verified=verified, source_ids=(SOURCE,))


def facts(**over) -> BusinessFacts:  # noqa: ANN003
    base = dict(
        kind=known("expense"),
        amount=known("850.00"),
        currency=known("DOP"),
        occurred_on=known("2026-10-09"),
        funding=known(OwnerFunding()),
        business_share=known(WholeBusinessShare(kind="all")),
    )
    base.update(over)
    return BusinessFacts.model_validate(
        {
            key: (value.model_dump() if hasattr(value, "model_dump") else value)
            for key, value in base.items()
        }
    )


def test_personal_is_a_persons_none_and_nothing_else():
    assert (
        is_personal(facts(business_share=known(WholeBusinessShare(kind="none")))) is True
    )
    # The owner's mark and a prepare-holder's mark are both a person's statement.
    assert (
        is_personal(
            facts(
                business_share=known(WholeBusinessShare(kind="none"), origin="member_set")
            )
        )
        is True
    )
    # A none the model read or matched is not a mark.
    assert (
        is_personal(
            facts(
                business_share=known(
                    WholeBusinessShare(kind="none"), origin="extracted", verified=False
                )
            )
        )
        is False
    )
    assert (
        is_personal(
            facts(
                business_share=known(
                    WholeBusinessShare(kind="none"), origin="matched", verified=False
                )
            )
        )
        is False
    )
    assert (
        is_personal(facts(business_share=known(WholeBusinessShare(kind="all")))) is False
    )
    assert is_personal(facts(business_share=Unknown())) is False


def test_fiscal_value_is_an_ncf_or_an_ecf_the_draft_knows_of_any_origin():
    assert fiscal_value(facts()) is None
    assert fiscal_value(facts(fiscal=FiscalFacts())) is None
    assert (
        fiscal_value(
            facts(
                fiscal=FiscalFacts(
                    ncf=known("B0100000001", origin="extracted", verified=False)
                )
            )
        )
        == "ncf"
    )
    assert (
        fiscal_value(
            facts(
                fiscal=FiscalFacts(
                    ecf=known("E310000000001", origin="qr_decoded", verified=False)
                )
            )
        )
        == "ecf"
    )
    assert (
        fiscal_value(facts(fiscal=FiscalFacts(ncf=known("B01"), ecf=known("E31"))))
        == "ecf"
    )


def test_the_606_answer_applies_only_to_a_personal_receipt_with_a_fiscal_number():
    answered = FiscalFacts(
        ncf=known("B0100000001"), include_606=known(True, origin="member_set")
    )
    assert (
        fiscal_inclusion(
            facts(business_share=known(WholeBusinessShare(kind="none")), fiscal=answered)
        )
        is True
    )
    assert (
        fiscal_inclusion(
            facts(
                business_share=known(WholeBusinessShare(kind="none")),
                fiscal=FiscalFacts(ncf=known("B01")),
            )
        )
        is None
    )
    # Not personal, or no fiscal number: the answer, if any, does not apply.
    assert fiscal_inclusion(facts(fiscal=answered)) is None
    assert (
        fiscal_inclusion(
            facts(
                business_share=known(WholeBusinessShare(kind="none")),
                fiscal=FiscalFacts(include_606=known(False, origin="member_set")),
            )
        )
        is None
    )


def _tx(actor_id, owner_id, kind="member", capabilities=("read", "prepare")):  # noqa: ANN001
    return SimpleNamespace(
        context=SimpleNamespace(
            actor=SimpleNamespace(actor_id=actor_id, actor_kind=kind), owner_id=owner_id
        ),
        authorization=SimpleNamespace(capabilities=frozenset(capabilities)),
    )


@pytest.mark.parametrize(
    ("state", "open_to_the_accountant"),
    [("open", True), ("accepted", True), ("accepting", False), ("dismissed", False)],
)
def test_the_606_gate_opens_only_on_an_open_or_accepted_draft(
    state: str, open_to_the_accountant: bool
):
    """``fiscal_inclusion_available`` reads the gate ``decide_606`` enforces:
    the accountant, on an open or accepted draft whose question applies."""

    owner, accountant = uuid4(), uuid4()
    personal = facts(
        business_share=known(WholeBusinessShare(kind="none")),
        fiscal=FiscalFacts(ncf=known("B0100000001")),
    )
    accountant_tx = _tx(accountant, owner)
    assert fiscal_inclusion_available(accountant_tx, personal, state) is (
        open_to_the_accountant
    )
    # The owner, a non-member, a read-only grant, or a draft the question
    # does not apply to: closed whatever the state.
    assert fiscal_inclusion_available(_tx(owner, owner), personal, state) is False
    assert (
        fiscal_inclusion_available(
            _tx(accountant, owner, kind="extractor"), personal, state
        )
        is False
    )
    assert (
        fiscal_inclusion_available(
            _tx(accountant, owner, capabilities=("read",)), personal, state
        )
        is False
    )
    assert fiscal_inclusion_available(accountant_tx, facts(), state) is False


def test_approval_admits_a_personal_receipt_and_still_refuses_a_partial_share():
    assert [
        b.code
        for b in blockers(
            facts(business_share=known(WholeBusinessShare(kind="none"))), ()
        )
    ] == []
    assert [b.code for b in blockers(facts(), ())] == []
    partial = BusinessFacts.model_validate(
        {
            **facts().model_dump(),
            "business_share": {
                "state": "known",
                "value": {"kind": "partial", "amount": "100.00"},
                "origin": "owner_stated",
                "verified": True,
                "source_ids": [str(SOURCE)],
            },
        }
    )
    assert [b.code for b in blockers(partial, ())] == ["business_allocation_unsupported"]


def test_the_export_says_the_marks_in_its_own_words_and_never_drops_a_personal_row():
    def draft(f: BusinessFacts) -> dict:
        return {"resolution": {"business": {"facts": f.model_dump(mode="json")}}}

    assert _marks([]) == {"personal": "no", "fiscal_value": "", "include_606": ""}
    assert _marks([draft(facts())]) == {
        "personal": "no",
        "fiscal_value": "",
        "include_606": "",
    }
    personal = facts(
        business_share=known(WholeBusinessShare(kind="none")),
        fiscal=FiscalFacts(
            ncf=known("B01"), include_606=known(False, origin="member_set")
        ),
    )
    assert _marks([draft(personal)]) == {
        "personal": "yes",
        "fiscal_value": "ncf",
        "include_606": "no",
    }
    undecided = facts(
        business_share=known(WholeBusinessShare(kind="none")),
        fiscal=FiscalFacts(ecf=known("E31")),
    )
    assert _marks([draft(undecided)]) == {
        "personal": "yes",
        "fiscal_value": "ecf",
        "include_606": "",
    }


def test_a_refused_mark_answers_403_business_permission_denied():
    from argus.api.business_drafts import action_problem
    from argus.domain.business.contracts.actions import Refused
    from starlette.requests import Request

    request = Request({"type": "http", "method": "POST", "path": "/", "headers": []})
    request.state.request_id = "req"
    problem = action_problem(
        request,
        Refused(outcome="permission_denied", code="business_permission_denied"),
    )
    assert problem.status_code == 403


def test_a_receipt_says_no_fiscal_number_only_once_its_facts_exist():
    """fiscal_known comes from the server: a receipt one draft owns has read
    facts, so no NCF or e-CF means none; one nobody read yet says nothing."""

    from argus.api.business_drafts import draft_overlay
    from argus.domain.business.actions.marks import record_marks

    summary = {
        "id": str(uuid4()),
        "status": "needs_attention",
        "attention": "unreadable",
        "error_code": "receipt_unreadable",
        "merchant": None,
    }
    assert "fiscal_known" not in draft_overlay(summary, [])
    read = facts()
    row = {
        "id": uuid4(),
        "state": "open",
        "version": 2,
        "activity_id": None,
        "attention": None,
        "resolution": {"business": {"facts": read.model_dump(mode="json")}},
        "marks": record_marks(read, {}, str(uuid4())),
    }
    overlaid = draft_overlay({**summary, "status": "review_ready"}, [row])
    assert overlaid["fiscal_known"] is True and overlaid["fiscal_value"] is None


def test_every_wire_that_carries_marks_declares_every_mark_and_answers_200():
    """The marks one server function returns are spread into receipt, expense,
    search and dossier payloads whose models forbid unknown keys: each must
    declare every mark, or the route answers 500. Checked through FastAPI's own
    response validation with the real schemas."""

    from argus.api.business_schemas import (
        BusinessExpense,
        BusinessSearch,
        ExpenseDetail,
        ExpensePage,
        ReceiptDetail,
        ReceiptPage,
        ReceiptSummary,
    )
    from argus.domain.business.actions.marks import record_marks
    from argus.domain.business.contracts.dossier import BusinessDossier
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    marked = facts(
        business_share=known(WholeBusinessShare(kind="none"), origin="member_set"),
        fiscal=FiscalFacts(
            ncf=known("B01"), include_606=known(False, origin="member_set")
        ),
    )
    marks = record_marks(
        marked,
        {"marker_id": str(uuid4()), "marker_name": "Lía", "answer_name": "Lía"},
        str(uuid4()),
    )
    assert marks["fiscal_known"] and marks["personal_marked_by"] == "Lía"
    for model in (
        ReceiptSummary,
        ReceiptDetail,
        BusinessExpense,
        ExpenseDetail,
        BusinessDossier,
    ):
        assert set(marks) <= set(model.model_fields), model.__name__

    expense = {
        "id": str(uuid4()),
        "merchant": "Ferretería",
        "amount": "850.00",
        "currency": "DOP",
        "category_id": None,
        "account_id": None,
        "occurred_on": "2026-10-09",
        "receipt_id": None,
        "draft_id": str(uuid4()),
        **marks,
    }
    receipt = {
        "id": str(uuid4()),
        "channel": "web",
        "filename": "recibo.png",
        "media_type": "image/png",
        "size_bytes": 10,
        "received_at": "2026-10-09T12:00:00Z",
        "status": "review_ready",
        "error_code": None,
        "attention": None,
        "preparable": False,
        "enterable": False,
        "expense_id": None,
        "merchant": "Ferretería",
        "occurred_on": "2026-10-09",
        "amount": "850.00",
        "currency": "DOP",
        "category_id": None,
        "account_id": None,
        "personal_editable": True,
        **marks,
    }
    app = FastAPI()

    @app.get("/expenses", response_model=ExpensePage)
    def expenses():  # noqa: ANN202
        return {"items": [expense]}

    @app.get("/expense", response_model=ExpenseDetail)
    def detail():  # noqa: ANN202
        return {**expense, "recorded_at": None, "revision": None}

    @app.get("/search", response_model=BusinessSearch)
    def search():  # noqa: ANN202
        lists = ("ventas", "accounts", "email_deliveries", "email_senders")
        return {
            **dict.fromkeys(lists, []),
            "expenses": [expense],
            "ventas": [expense],
            "receipts": [receipt],
            "next_cursors": dict.fromkeys((*lists, "expenses", "receipts")),
        }

    @app.get("/receipts", response_model=ReceiptPage)
    def receipts():  # noqa: ANN202
        return {"items": [receipt]}

    client = TestClient(app)
    for path in ("/expenses", "/expense", "/search", "/receipts"):
        answer = client.get(path)
        assert answer.status_code == 200, (path, answer.text)
    body = client.get("/expenses").json()["items"][0]
    assert (body["fiscal_known"], body["personal"], body["include_606_by"]) == (
        True,
        True,
        "Lía",
    )
