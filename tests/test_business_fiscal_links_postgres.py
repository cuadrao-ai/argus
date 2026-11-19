"""On real local Postgres: a fresh read opens with the whole 606 line, an
approval saves what the review showed, and a person's override holds until
they restore it."""

from datetime import date
from uuid import uuid4

from argus.domain.business.contracts.actions import (
    ApproveExpense,
    ApproveRefund,
    ReviewDraft,
)
from argus.domain.business.contracts.dgii import FiscalReview, PurchaseReview
from argus.domain.business.contracts.facts import MontosReview

from tests import test_business_approval_fiscal_postgres as fiscal
from tests import test_business_declaration_after_approval_postgres as recorded
from tests.test_business_dgii_postgres import cash_account

users = fiscal.users
shared_actions = fiscal.shared_actions
actions = fiscal.actions
pytestmark = fiscal.pytestmark
DAY = date(2026, 9, 5)
LINKED = {"id_type", "itbis", "legal_tip", "goods_amount", "services_amount", "paid_on"}


def _receipt(service, context, number: int, **read) -> tuple:  # noqa: ANN001, ANN003
    """An unreviewed receipt of the one supplier: 1,000 before ITBIS, dated DAY."""

    return fiscal.receipt_draft(
        service, context, fiscal.colmado(ncf=f"B01000004{number:02d}", **read), "DOP"
    )


def _review(service, context, draft, **change) -> None:  # noqa: ANN001, ANN003
    result = service.review(
        context,
        draft,
        ReviewDraft(version=service.dossier(context, draft).version, **change),
        str(uuid4()),
    )
    assert result.outcome == "applied", result


def _remembered(service, context, **purchase) -> None:  # noqa: ANN001, ANN003
    """A person answered for this supplier on an earlier receipt."""

    earlier, _ = _receipt(service, context, 1)
    _review(service, context, earlier, purchase=PurchaseReview(**purchase))


def _fresh(service, context, number: int = 2, **read):  # noqa: ANN001, ANN003, ANN202
    """A receipt reviewed to approvable with no fiscal answer given, and its dossier."""

    draft, version = _receipt(service, context, number, **read)
    fiscal.reviewed(service, context, draft, version)
    return draft, service.dossier(context, draft)


def test_a_fresh_read_opens_with_the_whole_606_line(actions):  # noqa: ANN001
    service, context = actions
    _remembered(service, context, category="02", payment_method="03")

    draft, _ = _receipt(service, context, 2)
    shown = service.dossier(context, draft)

    assert shown.dgii is not None
    line = shown.dgii
    assert (line.id_type, line.itbis, line.paid_on) == ("1", "180.00", DAY)
    assert (line.services_amount, line.goods_amount) == ("1000.00", None)
    # The two answers stay suggestions until a person confirms or approves.
    assert (line.category, line.payment_method) == (None, None)
    assert shown.declaration_suggestions.category.value == "02"
    assert shown.declaration_suggestions.payment_method.value == "03"
    assert {name for name, link in shown.inheritance.items() if link.inherited} == LINKED
    assert shown.inheritance["id_type"].field == "rnc"
    # Showing it saves nothing.
    assert fiscal.revisions(service, draft)[-1]["dgii"] is None


def test_a_fresh_read_with_no_suggestion_leaves_only_the_persons_fields_blank(actions):  # noqa: ANN001
    service, context = actions

    draft, _ = _receipt(service, context, 2)
    line = service.dossier(context, draft).dgii

    assert (line.id_type, line.itbis) == ("1", "180.00")
    assert (line.category, line.payment_method, line.paid_on) == (None, None, None)
    assert (line.services_amount, line.goods_amount) == (None, None)


def test_approval_saves_what_the_review_showed(actions):  # noqa: ANN001
    service, context = actions
    _remembered(service, context, category="09", payment_method="01")
    draft, shown = _fresh(service, context)

    outcome = service.approve(
        context,
        draft,
        ApproveExpense(
            version=shown.version,
            action="record_expense",
            suggestions=shown.declaration_suggestions,
        ),
        str(uuid4()),
    )

    assert outcome.outcome == "applied", outcome
    written = fiscal.revisions(service, draft)[-1]["dgii"]
    answers = {"category": "09", "payment_method": "01"}
    assert {k: v for k, v in written.items() if k != "suggestion_sources"} == {
        **shown.dgii.model_dump(mode="json", exclude={"suggestion_sources"}),
        **answers,
    }
    assert (written["goods_amount"], written["paid_on"]) == ("1000.00", DAY.isoformat())


def test_saving_the_pane_as_shown_overrides_nothing(actions):  # noqa: ANN001
    service, context = actions
    _remembered(service, context, category="02", payment_method="03")
    draft, shown = _fresh(service, context)

    _review(
        service,
        context,
        draft,
        dgii=FiscalReview.model_validate(
            {
                "fiscal": {"rnc": fiscal.SUPPLIER, "ncf": "B0100000402", "itbis": "180.00"},
                "declaration": shown.dgii.model_dump(mode="json"),
            }
        ),
    )

    saved = service.dossier(context, draft)
    assert {name for name, link in saved.inheritance.items() if link.inherited} == LINKED
    assert saved.dgii == shown.dgii
    # A suggestion is shown, never stored: export still reads no tipo de gasto.
    stored = fiscal.revisions(service, draft)[-1]["dgii"]
    assert (stored["category"], stored["services_amount"], stored["goods_amount"]) == (
        None,
        None,
        None,
    )


def test_an_overridden_tipo_id_holds_until_it_is_restored(actions):  # noqa: ANN001
    service, context = actions
    draft, _ = _fresh(service, context)

    _review(service, context, draft, purchase=PurchaseReview(id_type="2"))
    overridden = service.dossier(context, draft)
    assert overridden.dgii.id_type == "2"
    assert overridden.inheritance["id_type"].inherited is False
    assert overridden.inheritance["id_type"].value == "1"

    _review(service, context, draft, montos=MontosReview(restore_inherited=("id_type",)))
    restored = service.dossier(context, draft)
    assert restored.dgii.id_type == "1"
    assert restored.inheritance["id_type"].inherited is True


def test_fecha_pago_follows_the_chosen_forma_de_pago(actions):  # noqa: ANN001
    service, context = actions
    draft, _ = _fresh(service, context)

    _review(service, context, draft, purchase=PurchaseReview(payment_method="04"))
    assert service.dossier(context, draft).dgii.paid_on is None

    _review(service, context, draft, purchase=PurchaseReview(payment_method="02"))
    assert service.dossier(context, draft).dgii.paid_on == DAY

    _review(service, context, draft, purchase=PurchaseReview(paid_on=date(2026, 9, 20)))
    _review(service, context, draft, purchase=PurchaseReview(payment_method="04"))
    assert service.dossier(context, draft).dgii.paid_on == date(2026, 9, 20)


def test_a_linked_credit_note_carries_its_purchases_number(actions):  # noqa: ANN001
    service, context = actions
    cash = recorded.account_funding(cash_account(service, context))
    purchase, version = recorded.captured(service, context, "B0100002301", cash)
    activity = str(recorded.approved(service, context, purchase, version).approval_result.activity_id)

    credit, version = recorded.captured(
        service,
        context,
        "B0400000011",
        cash,
        recorded.blank_declaration(
            category="09", payment_method="06", actual_refund=True, purchase_activity_id=activity
        ),
        amount="118.00",
        itbis="18.00",
        kind="refund",
        occurred_on="2026-09-10",
    )

    shown = service.dossier(context, credit)
    assert shown.dgii.modified_ncf == "B0100002301"
    link = shown.inheritance["modified_ncf"]
    assert (link.field, link.value, link.inherited) == ("original_ncf", "B0100002301", True)

    outcome = service.approve_refund(
        context, credit, ApproveRefund(version=version, action="record_refund"), str(uuid4())
    )
    assert outcome.outcome == "applied", outcome
    assert service.dossier(context, credit).dgii.modified_ncf == "B0100002301"
