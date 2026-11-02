"""Over the actions service on Postgres: the services or goods amount a Tipo de
gasto pick worked out moves with every later change to what it was worked out
from, in either order, so the 606 line agrees with the total. An amount a
person typed never moves, and a real conflict still holds the line."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from uuid import uuid4

import pytest
from argus.domain.business.contracts.actions import ReviewDraft
from argus.domain.business.contracts.dgii import FiscalReview, PurchaseReview
from argus.domain.business.contracts.facts import BusinessFactPatch
from argus.domain.business.fiscal_profile import set_profile

from tests import test_business_actions_postgres as shared
from tests import test_business_declaration_after_approval_postgres as records
from tests import test_business_dgii_postgres as dgii

users = shared.users
shared_actions = shared.actions
actions = dgii.actions
pytestmark = [shared.pytestmark, pytest.mark.owner_acts]
FILER = "199990013"
CONFLICT = ("fiscal_invoice_total_conflict", "amount")


@dataclass(frozen=True)
class Draft:
    service: object
    context: object
    id: object

    @property
    def view(self):  # noqa: ANN201
        return self.service.dossier(self.context, self.id)

    def write(self, key: str | None = None, **review):  # noqa: ANN003, ANN201
        written = self.service.review(
            self.context,
            self.id,
            ReviewDraft(version=self.view.version, **review),
            key or str(uuid4()),
        )
        assert written.outcome == "applied", written
        return written

    def fact(self, name: str, state: str = "known", value: object = None) -> None:
        self.write(
            facts=BusinessFactPatch.model_validate(
                {name: {"state": state, "value": value}}
            )
        )

    def total(self, value: str) -> None:
        self.fact("amount", value=value)

    def itbis(self, value: str | None) -> None:
        """The ITBIS row: the stored declaration goes back as it stands."""

        view = self.view
        fiscal = view.facts.fiscal
        self.write(
            dgii=FiscalReview.model_validate(
                {
                    "fiscal": {
                        "rnc": fiscal.rnc.value,
                        "ncf": fiscal.ncf.value,
                        "itbis": value,
                    },
                    "declaration": view.dgii.model_dump(mode="json"),
                }
            )
        )

    def pick(self, category: str | None) -> None:
        self.write(purchase=PurchaseReview(category=category))

    def typed(self, **amounts: str | None) -> None:
        """Más datos fiscales: the whole declaration, a person's amounts on it."""

        view = self.view
        fiscal = view.facts.fiscal
        self.write(
            dgii=FiscalReview.model_validate(
                {
                    "fiscal": {
                        "rnc": fiscal.rnc.value,
                        "ncf": fiscal.ncf.value,
                        "itbis": fiscal.itbis.value,
                    },
                    "declaration": {**view.dgii.model_dump(mode="json"), **amounts},
                }
            )
        )

    def settled(self, **written: str | None) -> None:
        self.write(purchase=PurchaseReview(**written))

    @property
    def split(self) -> tuple[str | None, str | None]:
        view = self.view
        return view.dgii.services_amount, view.dgii.goods_amount


def drafted(service, context, ncf="B0100000061", **money) -> Draft:  # noqa: ANN001, ANN003
    """A reviewed draft, 300.00 DOP and ITBIS 0.00 unless told otherwise, on a
    business account, with a blank declaration."""

    set_profile(service.authority, context, dgii.filer_change(FILER), "rnc")
    funding = records.account_funding(dgii.cash_account(service, context))
    draft_id, _ = records.captured(
        service,
        context,
        ncf,
        funding,
        **{"amount": "300.00", "itbis": "0.00", **money},
    )
    return Draft(service, context, draft_id)


def closed(draft: Draft) -> tuple[dict | None, list[tuple[str, str]]]:
    """Approves the draft and answers its 606 line and the issues that hold it."""

    view = draft.view
    records.approved(draft.service, draft.context, draft.id, view.version)
    manifest, rows = records.txt_606_rows(draft.service, draft.context)
    return (
        rows[0] if rows else None,
        sorted((issue["code"], issue["field"]) for issue in manifest["issues"]),
    )


@dataclass(frozen=True)
class Case:
    steps: tuple[Callable[[Draft], None], ...]
    #: The 606 line's services and goods amounts and its ITBIS; None when held.
    line: tuple[str, str, str] | None
    issues: tuple[tuple[str, str], ...] = ()


def step(name: str, *args: object, **kwargs: object) -> Callable[[Draft], None]:
    return lambda draft: getattr(draft, name)(*args, **kwargs)


CASES = {
    "services_pick_then_total_and_itbis": Case(
        (step("pick", "02"), step("total", "700.00"), step("itbis", "100.00")),
        ("600.00", "", "100.00"),
    ),
    "goods_pick_then_total_and_itbis": Case(
        (step("pick", "09"), step("total", "700.00"), step("itbis", "100.00")),
        ("", "600.00", "100.00"),
    ),
    "goods_pick_then_itbis_then_total": Case(
        (step("pick", "09"), step("itbis", "100.00"), step("total", "700.00")),
        ("", "600.00", "100.00"),
    ),
    "total_and_itbis_then_pick": Case(
        (step("total", "700.00"), step("itbis", "100.00"), step("pick", "09")),
        ("", "600.00", "100.00"),
    ),
    "total_changed_back": Case(
        (step("pick", "09"), step("total", "700.00"), step("total", "300.00")),
        ("", "300.00", "0.00"),
    ),
    "itbis_changed_back": Case(
        (step("pick", "02"), step("itbis", "50.00"), step("itbis", "0.00")),
        ("300.00", "", "0.00"),
    ),
    "tipo_changed_moves_the_side": Case(
        (step("pick", "09"), step("pick", "02")),
        ("300.00", "", "0.00"),
    ),
    "tipo_changed_back": Case(
        (step("pick", "09"), step("pick", "02"), step("pick", "09")),
        ("", "300.00", "0.00"),
    ),
    "zero_itbis": Case(
        (step("pick", "09"), step("total", "700.00")),
        ("", "700.00", "0.00"),
    ),
    "itbis_taken_back_to_unknown": Case(
        (step("pick", "09"), step("itbis", "50.00"), step("itbis", None)),
        None,
        (("fiscal_fact_required", "itbis"),),
    ),
    "itbis_above_the_total_for_a_moment": Case(
        (step("pick", "09"), step("itbis", "700.00"), step("total", "800.00")),
        ("", "100.00", "700.00"),
    ),
    "tip_written_after_the_pick": Case(
        (step("pick", "02"), step("settled", legal_tip="30.00")),
        ("270.00", "", "0.00"),
    ),
    "mixed_split_a_person_typed_agrees": Case(
        (step("typed", services_amount="100.00", goods_amount="200.00"), step("pick", "09")),
        ("100.00", "200.00", "0.00"),
    ),
    "mixed_split_a_person_typed_stays": Case(
        (
            step("typed", services_amount="100.00", goods_amount="200.00"),
            step("pick", "09"),
            step("total", "700.00"),
        ),
        None,
        (CONFLICT,),
    ),
    "a_typed_amount_the_rule_would_also_give_stays": Case(
        (step("typed", goods_amount="300.00"), step("pick", "09"), step("total", "700.00")),
        None,
        (CONFLICT,),
    ),
    "a_person_retypes_over_the_pick": Case(
        (
            step("pick", "09"),
            step("typed", services_amount="50.00", goods_amount="250.00"),
            step("total", "700.00"),
        ),
        None,
        (CONFLICT,),
    ),
    "a_typed_amount_stays_when_the_tipo_changes": Case(
        (step("pick", "09"), step("settled", goods_amount="300.00"), step("pick", "02")),
        ("", "300.00", "0.00"),
    ),
}


@pytest.mark.parametrize("name", CASES)
def test_the_606_line_after_each_order_of_edits(actions, name):  # noqa: ANN001
    service, context, _ = actions
    case = CASES[name]
    draft = drafted(service, context)
    for edit in case.steps:
        edit(draft)
    draft.settled(payment_method="01")

    row, issues = closed(draft)

    assert tuple(issues) == case.issues
    assert (
        None
        if row is None
        else (row["services_amount"], row["goods_amount"], row["itbis"])
    ) == case.line
