"""On real local Postgres: whatever shape an open expense is in, its approval
saves the 606 line its review showed, and the export reads that same line."""

from dataclasses import dataclass
from itertools import product
from uuid import uuid4

import pytest
from argus.domain.business.contracts.actions import ApproveExpense
from argus.domain.business.contracts.dgii import PurchaseReview
from psycopg.types.json import Jsonb

from tests import test_business_approval_fiscal_postgres as fiscal
from tests import test_business_declaration_after_approval_postgres as recorded
from tests import test_business_fiscal_links_postgres as links
from tests.business.receipt_stub import receipt_day
from tests.business_accept_support import seen_gaps

users = fiscal.users
shared_actions = fiscal.shared_actions
actions = fiscal.actions
pytestmark = fiscal.pytestmark
FORMS = ("01", "02", "03", "04", "05", "06", "07")
ANSWERS = ("category", "payment_method")
#: The server's suggestion for each answer. Compra a crédito pays later, so a
#: Fecha pago that follows the account instead of the suggestion shows.
SUGGESTED = {"category": "09", "payment_method": "04"}


@dataclass(frozen=True)
class Shape:
    """An open expense before its approval. ``saved`` is whether a person
    saved a declaration: with its overrides recorded, or as a save from before
    any were. ``payment`` is the Forma de pago saved, ``cleared`` a linked
    field the person left blank, ``account`` the type of the account that
    paid, and ``paid`` a due notice the read marked as paid."""

    saved: str = "no"
    payment: str | None = None
    cleared: str | None = None
    suggested: bool = False
    account: str | None = None
    paid: bool = False

    @property
    def id(self) -> str:
        parts = [
            {"no": "nothing saved", "yes": "saved", "old": "saved before overrides"}[self.saved],
            f"forma {self.payment or 'blank'}" if self.saved != "no" else None,
            f"{self.cleared} cleared" if self.cleared else None,
            "suggested" if self.suggested else None,
            f"paid from {self.account}" if self.account else None,
            "marked paid" if self.paid else None,
        ]
        return ", ".join(part for part in parts if part)


SOURCES = tuple(product((False, True), (None, "checking")))
SHAPES = (
    *(
        Shape(suggested=suggested, account=account)
        for suggested in (False, True)
        for account in (None, "cash", "checking", "credit_card")
    ),
    *(
        Shape(saved, None, None, suggested, account)
        for saved in ("yes", "old")
        for suggested, account in SOURCES
    ),
    *(
        Shape(saved, payment, None, suggested, account)
        for saved in ("yes", "old")
        for payment in FORMS
        for suggested, account in ((False, None), (True, "checking"))
    ),
    *(
        Shape("yes", payment, cleared, suggested, account)
        for cleared in ("id_type", "paid_on")
        for payment in (None, "01", "04")
        for suggested, account in SOURCES
    ),
    *(
        Shape(saved, payment, paid=True)
        for saved in ("no", "yes", "old")
        for payment in ((None,) if saved == "no" else (None, "01", "04"))
    ),
)


def _open(service, context, shape: Shape):  # noqa: ANN001, ANN202
    if shape.suggested:
        links._remembered(service, context, **SUGGESTED)
    draft, version = links._receipt(service, context, 2)
    funding = (
        recorded.account_funding(fiscal.dop_account(service, context, shape.account))
        if shape.account
        else None
    )
    fiscal.reviewed(service, context, draft, version, funding=funding)
    if shape.saved != "no":
        links._review(
            service, context, draft, purchase=PurchaseReview(payment_method=shape.payment)
        )
    if shape.cleared:
        links._review(service, context, draft, purchase=PurchaseReview(**{shape.cleared: None}))
    mark = {"draft": links.PAID_BILL} if shape.paid else {}
    if shape.saved == "old":
        links._saved_before_the_links(service, context, draft, None, paid_on=None, **mark)
    elif shape.paid:
        _mark_paid(service, context, draft)
    return draft


def _mark_paid(service, context, draft) -> None:  # noqa: ANN001
    with service.authority.pool.connection() as db:
        db.execute("set local session_replication_role=replica")
        db.execute(
            "update public.financial_import_events set resolution=jsonb_set(resolution,"
            "'{business,bill_mark}',%s) where id=%s and owner_space_id=%s",
            (Jsonb(links.PAID_BILL["bill_mark"]), draft, context.actor.space_id),
        )


def _approve(service, context, draft, shown) -> None:  # noqa: ANN001
    outcome = service.approve(
        context,
        draft,
        ApproveExpense(
            version=shown.version,
            action="record_expense",
            suggestions=shown.declaration_suggestions,
            accept_gaps=seen_gaps(service, context, draft),
        ),
        str(uuid4()),
    )
    assert outcome.outcome == "applied", outcome


def _reviewed(shown) -> dict:  # noqa: ANN001
    """The 606 line a person reads in the review: each field as shown, and a
    blank answer at the suggestion shown in its place."""

    line = links._shown(shown)
    for answer in ANSWERS:
        suggestion = getattr(shown.declaration_suggestions, answer)
        if line[answer] is None and suggestion is not None:
            line[answer] = suggestion.value
    return line


@pytest.mark.parametrize("shape", SHAPES, ids=[shape.id for shape in SHAPES])
def test_an_approval_saves_and_exports_the_line_its_review_showed(actions, shape):  # noqa: ANN001
    service, context = actions
    draft = _open(service, context, shape)
    shown = service.dossier(context, draft)
    reviewed = _reviewed(shown)

    _approve(service, context, draft, shown)

    saved = fiscal.revisions(service, draft)[-1]["dgii"]
    assert {k: v for k, v in saved.items() if k != "suggestion_sources"} == reviewed
    assert links._shown(service.dossier(context, draft)) == reviewed
    exported = links._exported(service, context, draft)
    assert exported.model_dump(mode="json", exclude={"suggestion_sources"}) == reviewed


@pytest.mark.parametrize("account", [None, "checking"], ids=["owner funds", "checking"])
def test_a_tipo_id_a_person_cleared_still_follows_the_rnc(actions, account):  # noqa: ANN001
    service, context = actions
    draft = _open(service, context, Shape("yes", "01", "id_type", account=account))
    shown = service.dossier(context, draft)
    assert shown.dgii.id_type == "1"
    assert shown.inheritance["id_type"].inherited is True

    _approve(service, context, draft, shown)

    assert fiscal.revisions(service, draft)[-1]["dgii"]["id_type"] == "1"
    assert links._line(service, context, draft)["id_type"] == "1"


def test_a_saved_blank_forma_de_pago_shows_the_account_that_paid(actions):  # noqa: ANN001
    service, context = actions
    draft = _open(service, context, Shape("yes", account="checking"))

    shown = service.dossier(context, draft)

    assert (shown.dgii.payment_method, shown.dgii.paid_on) == ("02", receipt_day())
    assert shown.inheritance["paid_on"].inherited is True
    _approve(service, context, draft, shown)
    line = links._line(service, context, draft)
    assert (line["payment_method"], line["paid_on"]) == ("02", receipt_day().strftime("%Y%m%d"))


def test_a_suggested_forma_de_pago_comes_before_the_account_that_paid(actions):  # noqa: ANN001
    service, context = actions
    draft = _open(service, context, Shape("yes", suggested=True, account="checking"))

    shown = service.dossier(context, draft)

    assert shown.declaration_suggestions.payment_method.value == "04"
    assert (shown.dgii.payment_method, shown.dgii.paid_on) == (None, None)
    _approve(service, context, draft, shown)
    line = links._line(service, context, draft)
    assert (line["payment_method"], line["paid_on"]) == ("04", "")
