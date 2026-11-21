"""On real local Postgres: a fresh read opens with the whole 606 line, an
approval saves what the review showed, and a person's override holds until
they restore it."""

from datetime import date
from uuid import uuid4

import pytest
from argus.domain.business.contracts.actions import (
    ApproveExpense,
    ApproveRefund,
    MarkPersonal,
    ReviewDraft,
)
from argus.domain.business.contracts.dgii import FiscalReview, PurchaseReview
from argus.domain.business.contracts.facts import MontosReview
from argus.domain.business.dgii_columns import PURCHASE_COLUMNS
from argus.domain.business.dgii_export import line_values
from argus.domain.business.reporting_store import read_export_source
from psycopg.types.json import Jsonb

from tests import test_business_approval_fiscal_postgres as fiscal
from tests import test_business_declaration_after_approval_postgres as recorded
from tests.business.receipt_stub import receipt_date, receipt_day
from tests.business.test_approved_export_unchanged import CASES, PURCHASE
from tests.test_business_dgii_postgres import cash_account

users = fiscal.users
shared_actions = fiscal.shared_actions
actions = fiscal.actions
pytestmark = fiscal.pytestmark
LINKED = {"id_type", "itbis", "legal_tip", "goods_amount", "services_amount", "paid_on"}


def _receipt(service, context, number: int, **read) -> tuple:  # noqa: ANN001, ANN003
    """An unreviewed receipt of the one supplier: 1,000 before ITBIS, dated the receipt day."""

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
    assert (line.id_type, line.itbis, line.paid_on) == ("1", "180.00", receipt_day())
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
    assert (written["goods_amount"], written["paid_on"]) == ("1000.00", receipt_date())


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
    assert service.dossier(context, draft).dgii.paid_on == receipt_day()

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


def _saved_before_the_links(  # noqa: ANN202
    service, context, draft, overrides=(), /, **declared  # noqa: ANN001, ANN003
) -> dict:
    """Leave the record as a save before #2307 left it: these declared
    values, and no override recorded for a field it did not link. ``overrides``
    None is a save from before any override was recorded, with what else the
    draft then held beside its declaration under ``draft``."""

    held = {
        "fiscal_overrides": None if overrides is None else list(overrides),
        **declared.pop("draft", {}),
    }
    with service.authority.pool.connection() as db:
        db.execute("set local session_replication_role=replica")
        db.execute(
            "update public.financial_import_events set resolution=jsonb_set(resolution,"
            "'{business}',(resolution->'business') || %s || jsonb_build_object("
            "'dgii',(resolution->'business'->'dgii') || %s))"
            " where id=%s and owner_space_id=%s",
            (Jsonb(held), Jsonb(declared), draft, context.actor.space_id),
        )
        [saved] = db.execute(
            "update public.business_draft_revisions set after_dgii=after_dgii || %s"
            " where draft_id=%s and space_id=%s and version=(select max(version)"
            " from public.business_draft_revisions where draft_id=%s) returning after_dgii",
            (Jsonb(declared), draft, context.actor.space_id, draft),
        ).fetchall()
    return saved[0]


@pytest.mark.parametrize(
    ("overrides", "declared", "exported"),
    [
        pytest.param(
            (),
            {"payment_method": "01", "paid_on": None},
            {"id_type": "1", "paid_on": "", "itbis": "180.00", "payment_method": "01"},
            id="efectivo with no fecha pago",
        ),
        pytest.param(
            (),
            {"payment_method": "04", "paid_on": "2026-09-03"},
            {"id_type": "1", "paid_on": "20260903", "itbis": "180.00", "payment_method": "04"},
            id="credito approved while marked paid",
        ),
        pytest.param(
            (),
            {"payment_method": "04", "paid_on": None, "id_type": "2"},
            {"id_type": "2", "paid_on": "", "itbis": "180.00", "payment_method": "04"},
            id="tipo id chosen against the rnc",
        ),
        pytest.param(
            ("itbis", "paid_on"),
            {"payment_method": "02", "paid_on": "2026-09-20", "itbis": "150.00"},
            {"id_type": "1", "paid_on": "20260920", "itbis": "150.00", "payment_method": "02"},
            id="itbis and fecha pago overridden",
        ),
    ],
)
def test_an_approved_record_keeps_its_saved_606_line(actions, overrides, declared, exported):  # noqa: ANN001
    service, context = actions
    cash = recorded.account_funding(cash_account(service, context))
    draft, version = recorded.captured(
        service, context, "B0100002401", cash, recorded.blank_declaration(category="09")
    )
    recorded.approved(service, context, draft, version)
    saved = _saved_before_the_links(service, context, draft, overrides, **declared)

    activity = str(service.dossier(context, draft).approval_result.activity_id)

    def line() -> dict:
        """The record's 606 line as the export snapshot reads it."""

        exported = read_export_source(service.authority, context).approved[activity]
        names = [name for name, _ in PURCHASE_COLUMNS]
        return dict(zip(names, line_values(exported), strict=True))

    before = line()
    assert {name: before[name] for name in exported} == exported
    shown = service.dossier(context, draft)
    assert shown.dgii.model_dump(mode="json") == saved
    assert not {"id_type", "paid_on", "modified_ncf"} & set(shown.inheritance)

    # A later answer changes its own cell and no other.
    added = recorded.declared(service, context, draft, shown.version, category="02")
    assert added.outcome == "applied", added
    after = line()
    assert after["category"] == "02"
    moved = {"category", "goods_amount", "services_amount"}
    assert {k: v for k, v in after.items() if k not in moved} == {
        k: v for k, v in before.items() if k not in moved
    }


def _line(service, context, draft) -> dict:  # noqa: ANN001
    """The approved record's 606 line as the export snapshot reads it."""

    activity = str(service.dossier(context, draft).approval_result.activity_id)
    exported = read_export_source(service.authority, context).approved[activity]
    return dict(zip([name for name, _ in PURCHASE_COLUMNS], line_values(exported), strict=True))


def _shown(dossier) -> dict:  # noqa: ANN001
    return dossier.dgii.model_dump(mode="json", exclude={"suggestion_sources"})


@pytest.mark.parametrize("overrides", [None, ()], ids=["no overrides recorded", "none overridden"])
def test_approval_saves_the_fecha_pago_shown_on_a_draft_saved_before_the_links(actions, overrides):  # noqa: ANN001
    service, context = actions
    draft, _ = _fresh(service, context)
    _review(service, context, draft, purchase=PurchaseReview(category="09", payment_method="01"))
    _saved_before_the_links(service, context, draft, overrides, paid_on=None)

    shown = service.dossier(context, draft)
    assert shown.dgii.paid_on == receipt_day()
    outcome = service.approve(
        context,
        draft,
        ApproveExpense(version=shown.version, action="record_expense"),
        str(uuid4()),
    )

    assert outcome.outcome == "applied", outcome
    written = fiscal.revisions(service, draft)[-1]["dgii"]
    assert {k: v for k, v in written.items() if k != "suggestion_sources"} == _shown(shown)
    assert _shown(service.dossier(context, draft)) == _shown(shown)
    assert _line(service, context, draft)["paid_on"] == receipt_day().strftime("%Y%m%d")


@pytest.mark.parametrize("overrides", [None, ()], ids=["no overrides recorded", "none overridden"])
def test_a_credit_note_approval_saves_the_ncf_modificado_shown(actions, overrides):  # noqa: ANN001
    service, context = actions
    cash = recorded.account_funding(cash_account(service, context))
    purchase, version = recorded.captured(service, context, "B0100002501", cash)
    activity = str(recorded.approved(service, context, purchase, version).approval_result.activity_id)
    credit, version = recorded.captured(
        service,
        context,
        "B0400000021",
        cash,
        recorded.blank_declaration(
            category="09", payment_method="06", actual_refund=True, purchase_activity_id=activity
        ),
        amount="118.00",
        itbis="18.00",
        kind="refund",
        occurred_on="2026-09-10",
    )
    _saved_before_the_links(service, context, credit, overrides, modified_ncf=None, id_type=None)

    shown = service.dossier(context, credit)
    assert (shown.dgii.modified_ncf, shown.dgii.id_type) == ("B0100002501", "1")
    outcome = service.approve_refund(
        context, credit, ApproveRefund(version=version, action="record_refund"), str(uuid4())
    )

    assert outcome.outcome == "applied", outcome
    assert _shown(service.dossier(context, credit)) == _shown(shown)
    line = _line(service, context, credit)
    assert (line["modified_ncf"], line["id_type"]) == ("B0100002501", "1")


def _category(service, context, draft) -> set:  # noqa: ANN001
    version = service.dossier(context, draft).version
    result = recorded.declared(service, context, draft, version, category="02")
    assert result.outcome == "applied", result
    return {"category", "goods_amount", "services_amount"}


def _forma_de_pago(service, context, draft) -> set:  # noqa: ANN001
    version = service.dossier(context, draft).version
    result = recorded.declared(service, context, draft, version, payment_method="03")
    assert result.outcome == "applied", result
    return {"payment_method"}


def _restored_itbis(service, context, draft) -> set:  # noqa: ANN001
    _review(service, context, draft, montos=MontosReview(restore_inherited=("itbis",)))
    return set()


def _personal_and_back(service, context, draft) -> set:  # noqa: ANN001
    for personal in (True, False):
        version = service.dossier(context, draft).version
        result = service.mark_personal(
            context, draft, MarkPersonal(version=version, personal=personal), str(uuid4())
        )
        assert result.outcome == "applied", result
    return set()


PAID_BILL = {"bill_mark": "Factura pagada"}
LEGACY_SAVES = {
    "paid bill with no fecha pago": {
        "draft": PAID_BILL,
        "payment_method": "04",
        "paid_on": None,
    },
    "amount typed against its tipo de gasto": {
        "draft": {**PAID_BILL, "amount_derived": False},
        "category": "02",
        "payment_method": "04",
        "paid_on": None,
        "goods_amount": "500.00",
        "services_amount": None,
    },
}


@pytest.mark.parametrize("declared", LEGACY_SAVES.values(), ids=LEGACY_SAVES.keys())
@pytest.mark.parametrize(
    "write",
    [_category, _forma_de_pago, _restored_itbis, _personal_and_back],
    ids=["tipo de gasto", "forma de pago", "montos restore", "personal and back"],
)
def test_a_write_keeps_the_export_of_a_save_from_before_overrides(actions, write, declared):  # noqa: ANN001
    service, context = actions
    cash = recorded.account_funding(cash_account(service, context))
    draft, version = recorded.captured(
        service, context, "B0100002601", cash, recorded.blank_declaration(category="09")
    )
    recorded.approved(service, context, draft, version)
    _saved_before_the_links(service, context, draft, None, **declared)
    before = _line(service, context, draft)
    assert before["paid_on"] == "20260903"

    moved = write(service, context, draft)

    after = _line(service, context, draft)
    assert {k: v for k, v in after.items() if k not in moved} == {
        k: v for k, v in before.items() if k not in moved
    }


def _json(saved: dict) -> dict:
    return {k: v.isoformat() if isinstance(v, date) else v for k, v in saved.items()}


def _exported(service, context, draft):  # noqa: ANN001, ANN202
    """The approved record's declaration as the export snapshot reads it."""

    activity = str(service.dossier(context, draft).approval_result.activity_id)
    return read_export_source(service.authority, context).approved[activity].declaration


@pytest.mark.parametrize(
    ("saved", "overrides", "bill_mark"),
    [pytest.param(*case.values[1:4], id=case.id) for case in CASES if case.values[0] is PURCHASE],
)
def test_the_dossier_of_an_approved_record_shows_the_line_it_exports(  # noqa: ANN201
    actions, saved, overrides, bill_mark  # noqa: ANN001
):
    service, context = actions
    cash = recorded.account_funding(cash_account(service, context))
    draft, version = recorded.captured(
        service, context, "B0100000001", cash, recorded.blank_declaration(category="09")
    )
    recorded.approved(service, context, draft, version)
    _saved_before_the_links(
        service, context, draft, overrides, draft={"bill_mark": bill_mark}, **_json(saved)
    )

    exported = _exported(service, context, draft)
    shown = service.dossier(context, draft)

    assert _shown(shown) == exported.model_dump(mode="json", exclude={"suggestion_sources"})
    assert not {"id_type", "paid_on", "modified_ncf"} & set(shown.inheritance)


def test_the_dossier_of_an_approved_credit_note_shows_the_line_it_exports(actions):  # noqa: ANN001
    service, context = actions
    cash = recorded.account_funding(cash_account(service, context))
    purchase, version = recorded.captured(service, context, "B0100002701", cash)
    activity = str(recorded.approved(service, context, purchase, version).approval_result.activity_id)
    credit, version = recorded.captured(
        service,
        context,
        "B0400000027",
        cash,
        recorded.blank_declaration(
            category="09", payment_method="04", actual_refund=True, purchase_activity_id=activity
        ),
        amount="118.00",
        itbis="18.00",
        kind="refund",
        occurred_on="2026-09-12",
    )
    outcome = service.approve_refund(
        context, credit, ApproveRefund(version=version, action="record_refund"), str(uuid4())
    )
    assert outcome.outcome == "applied", outcome
    _saved_before_the_links(service, context, credit, (), modified_ncf="B0100000009")

    exported = _exported(service, context, credit)

    assert exported.modified_ncf == "B0100000009"
    assert _shown(service.dossier(context, credit)) == exported.model_dump(
        mode="json", exclude={"suggestion_sources"}
    )
