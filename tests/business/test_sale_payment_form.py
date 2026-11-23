"""A sale paid one way: a person picks the payment form and the server puts
the record's whole total in that bucket of the 607 payment split. The pick
carries no amount, and the bucket follows the total when the total changes."""

from __future__ import annotations

from typing import get_args
from uuid import uuid4

import pytest
from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.actions import ReviewDraft
from argus.domain.business.contracts.dgii import (
    SalePayment,
    SalePaymentForm,
    SalePaymentSplit,
    SalesDeclaration,
)
from argus.domain.business.contracts.dossier import _unmeasured_removed
from argus.domain.business.contracts.facts import BusinessFacts, Known
from argus.domain.business.dgii_columns import PAYMENT_BUCKETS
from argus.domain.business.purchase_review import (
    apply_payment_split,
    sale_payment,
    whole_payment,
)
from pydantic import ValidationError

from tests.business.test_document_type_direction import _event, _review

FORMS = get_args(SalePaymentForm)


def _facts(total: str | None, kind: str = "income") -> BusinessFacts:
    source = uuid4()

    def known(value: str) -> Known:
        return Known(value=value, origin="extracted", source_ids=(source,))

    data = {"kind": known(kind), "currency": known("DOP")}
    if total is not None:
        data["amount"] = known(total)
    return BusinessFacts.model_validate(data)


def _sale(total: str | None = "1180.00", **declared: str):  # noqa: ANN202
    event = _event("venta", _facts(total))
    if declared:
        split = {name: declared.pop(name) for name in list(declared) if name in FORMS}
        saved = apply_payment_split(None, SalePaymentSplit(**split))
        event.resolution["business"]["dgii"] = saved.model_copy(
            update=declared
        ).model_dump(mode="json")
    return event


def _buckets(dgii: dict) -> dict[str, str]:
    return {name: dgii[name] for name in FORMS if dgii[name] is not None}


def test_the_forms_a_person_picks_are_the_buckets_of_the_split():
    assert FORMS == PAYMENT_BUCKETS == tuple(SalePaymentSplit.model_fields)


@pytest.mark.parametrize("form", FORMS)
def test_one_pick_puts_the_whole_total_in_its_bucket_and_no_other(monkeypatch, form):
    saved = _review(
        monkeypatch, _sale(cash="500.00", bank="680.00"), None, sale_payment_form=form
    )
    assert saved["dgii"]["form"] == "607"
    assert _buckets(saved["dgii"]) == {form: "1180.00"}


def test_a_sale_with_no_declaration_starts_its_607_with_the_pick(monkeypatch):
    saved = _review(monkeypatch, _sale("118"), None, sale_payment_form="card")
    assert _buckets(saved["dgii"]) == {"card": "118.00"}
    assert saved["dgii"]["income_type"] is None


def test_a_pick_keeps_the_other_607_answers(monkeypatch):
    saved = _review(
        monkeypatch,
        _sale(cash="1180.00", income_type="4"),
        None,
        sale_payment_form="credit",
    )
    assert saved["dgii"]["income_type"] == "4"
    assert _buckets(saved["dgii"]) == {"credit": "1180.00"}


def test_a_purchase_takes_no_payment_form(monkeypatch):
    event = _event("recibo", _facts("1180.00", kind="expense"))
    with pytest.raises(ActionError) as refused:
        _review(monkeypatch, event, None, sale_payment_form="cash")
    assert refused.value.result.code == "fiscal_direction_unsupported"


@pytest.mark.parametrize(
    "total,code",
    [(None, "fact_required"), ("118.005", "fiscal_amount_precision_or_limit")],
)
def test_a_total_the_bucket_cannot_hold_refuses_the_pick(monkeypatch, total, code):
    with pytest.raises(ActionError) as refused:
        _review(monkeypatch, _sale(total), None, sale_payment_form="cash")
    assert refused.value.result.code == code


def _retotal(monkeypatch, event, total: str) -> dict:  # noqa: ANN001
    return _review(
        monkeypatch, event, None, {"amount": {"state": "known", "value": total}}
    )


def test_the_one_bucket_follows_a_corrected_total(monkeypatch):
    saved = _retotal(monkeypatch, _sale(bank="1180.00"), "1200.50")
    assert _buckets(saved["dgii"]) == {"bank": "1200.50"}


@pytest.mark.parametrize(
    "split",
    [{"cash": "500.00", "bank": "680.00"}, {"cash": "1000.00"}],
    ids=["several_buckets", "one_bucket_that_was_not_the_total"],
)
def test_a_split_a_person_wrote_by_amount_is_never_moved(monkeypatch, split):
    saved = _retotal(monkeypatch, _sale(**split), "1200.50")
    assert _buckets(saved["dgii"]) == split


def test_a_pick_and_a_new_total_in_one_write_use_the_new_total(monkeypatch):
    saved = _review(
        monkeypatch,
        _sale(cash="1180.00"),
        None,
        {"amount": {"state": "known", "value": "900.00"}},
        sale_payment_form="card",
    )
    assert _buckets(saved["dgii"]) == {"card": "900.00"}


def _declared(**split: str) -> SalesDeclaration:
    return apply_payment_split(None, SalePaymentSplit(**split))


@pytest.mark.parametrize(
    "split,form",
    [
        ({}, None),
        ({"gift": "1180.00"}, "gift"),
        ({"gift": "1180.00", "cash": "0.00"}, "gift"),
        ({"cash": "500.00", "bank": "680.00"}, None),
    ],
)
def test_the_dossier_says_the_one_form_and_the_forms_to_pick(split, form):
    assert sale_payment("venta", _declared(**split)) == SalePayment(
        form=form, options=FORMS
    )


def test_only_a_sale_has_a_payment_form():
    assert sale_payment("recibo", None) is None
    assert sale_payment("venta", None) == SalePayment(form=None, options=FORMS)


def test_the_whole_payment_is_exact():
    assert whole_payment(None, "barter", "118").barter == "118.00"


def test_the_review_takes_the_pick_alone_and_only_a_known_form():
    assert ReviewDraft(version=1, sale_payment_form="cash").sale_payment_form == "cash"
    with pytest.raises(ValidationError):
        ReviewDraft(version=1, sale_payment_form="cheque")
    with pytest.raises(ValidationError):
        ReviewDraft(version=1)


def test_no_model_reads_the_pick():
    source = {
        "kind": "web_action",
        "text": '{"request": {"version": 2, "sale_payment_form": "cash"}}',
    }
    assert "sale_payment_form" not in _unmeasured_removed(source)["text"]
