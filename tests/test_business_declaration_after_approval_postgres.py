"""Over the actions service on Postgres: approval needs no 606 data, a saved
declaration keeps a person's values and takes only the Tipo Id and Forma de
Pago it left unknown from the account that paid, a person adds any 606 data on
the approved record and the export carries it, a line in a downloaded TXT
freezes that declaration with a clear code, and the export-line table is
server-only."""

from __future__ import annotations

import io
import json
from datetime import date
from unittest.mock import patch
from uuid import uuid4
from zipfile import ZipFile

import psycopg
import pytest
from argus.domain.business.contracts.actions import (
    ApproveExpense,
    ApproveIncome,
    CaptureNote,
    ReviewDraft,
)
from argus.domain.business.contracts.dgii import (
    FiscalReview,
    PurchaseDeclaration,
    PurchaseReview,
    SalesDeclaration,
)
from argus.domain.business.contracts.facts import BusinessFactPatch
from argus.domain.business.dgii_columns import PURCHASE_COLUMNS
from argus.domain.business.export import ExportPeriod, export_package
from argus.domain.business.fiscal_profile import set_profile
from argus.domain.ingestion.documents.objects import InMemorySourceObjects

from tests import test_business_actions_postgres as shared
from tests import test_business_dgii_postgres as dgii
from tests import test_financial_accounts_postgres as accounts
from tests.test_business_dgii_postgres import (
    business_account,
    cash_account,
    filer_change,
)

users = shared.users
shared_actions = shared.actions
actions = dgii.actions
pytestmark = [shared.pytestmark, pytest.mark.owner_acts]
PERIOD = ExportPeriod(date(2026, 9, 1), date(2026, 9, 30))
FILER = "199990013"
SUPPLIER = "199990021"
TXT_606 = f"dgii/DGII_F_606_{FILER}_202609.TXT"


def blank_declaration(**chosen) -> dict:
    return {
        **{name: None for name in PurchaseDeclaration.model_fields},
        "form": "606",
        "actual_refund": False,
        "category_suggested": False,
        **chosen,
    }


def captured(service, context, ncf, funding, declaration=None, amount="1180.00"):  # noqa: ANN001, ANN201
    """One reviewed expense: the amount in DOP on 2026-09-03, ITBIS 180.00,
    with a supplier RNC and the given NCF, and the declaration as saved."""

    capture = service.capture(
        context, CaptureNote(text=f"PRÁCTICA compra {ncf}"), str(uuid4())
    )
    facts = BusinessFactPatch.model_validate(
        {
            name: {"state": "known", "value": value}
            for name, value in {
                "kind": "expense",
                "amount": amount,
                "currency": "DOP",
                "occurred_on": "2026-09-03",
                "counterparty": f"PRÁCTICA {ncf}",
                "funding": funding,
                "business_share": {"kind": "all"},
                "receipt_state": "fiscal_receipt",
            }.items()
        }
    )
    reviewed = service.review(
        context,
        capture.draft_id,
        ReviewDraft(
            version=capture.version,
            facts=facts,
            dgii=FiscalReview.model_validate(
                {
                    "fiscal": {"rnc": SUPPLIER, "ncf": ncf, "itbis": "180.00"},
                    "declaration": declaration or blank_declaration(),
                }
            ),
        ),
        str(uuid4()),
    )
    assert reviewed.outcome == "applied", reviewed
    return reviewed.draft_id, reviewed.version


def approved(service, context, draft_id, version):  # noqa: ANN001, ANN201
    outcome = service.approve(
        context,
        draft_id,
        ApproveExpense(version=version, action="record_expense"),
        str(uuid4()),
    )
    assert outcome.outcome == "applied", outcome
    return service.dossier(context, draft_id)


def captured_income(service, context, checking, declaration=None):  # noqa: ANN001, ANN201
    """One reviewed sale: 2000.00 DOP on 2026-09-03 into the checking account,
    with the 607 declaration as saved, or with no declaration at all."""

    capture = service.capture(context, CaptureNote(text="PRÁCTICA venta"), str(uuid4()))
    facts = BusinessFactPatch.model_validate(
        {
            name: {"state": "known", "value": value}
            for name, value in {
                "kind": "income",
                "amount": "2000.00",
                "currency": "DOP",
                "occurred_on": "2026-09-03",
                "counterparty": "PRÁCTICA cliente",
                "funding": account_funding(checking),
                "business_share": {"kind": "all"},
            }.items()
        }
    )
    dgii = (
        FiscalReview.model_validate(
            {
                "fiscal": {"rnc": SUPPLIER, "ncf": "B0100000901", "itbis": "180.00"},
                "declaration": declaration,
            }
        )
        if declaration
        else None
    )
    reviewed = service.review(
        context,
        capture.draft_id,
        ReviewDraft(version=capture.version, facts=facts, dgii=dgii),
        str(uuid4()),
    )
    assert reviewed.outcome == "applied", reviewed
    return reviewed.draft_id, reviewed.version


def declared(service, context, draft_id, version, **review):  # noqa: ANN001, ANN201
    return service.review(
        context,
        draft_id,
        ReviewDraft(version=version, purchase=PurchaseReview(**review)),
        str(uuid4()),
    )


def export_lines(service, context):  # noqa: ANN001, ANN201
    with service.authority.pool.connection() as connection:
        return connection.execute(
            "select activity_id::text,form,period from public.business_dgii_export_lines"
            " where space_id=%s order by exported_at,id",
            (context.actor.space_id,),
        ).fetchall()


def account_funding(account) -> dict:  # noqa: ANN001
    return {"kind": "business_account", "account_id": str(account)}


def txt_606(service, context):  # noqa: ANN001, ANN201
    """The packet's DGII manifest and its one 606 TXT line by column name,
    None when no 606 TXT shipped."""

    blob = export_package(service.authority, context, PERIOD, InMemorySourceObjects())
    with ZipFile(io.BytesIO(blob)) as archive:
        manifest = json.loads(archive.read("manifest.json"))["dgii"]
        if TXT_606 not in archive.namelist():
            return manifest, None
        line = archive.read(TXT_606).split(b"\r\n")[1].decode()
    names = [name for name, _ in PURCHASE_COLUMNS]
    return manifest, dict(zip(names, line.split("|"), strict=True))


def test_approval_fills_only_what_a_saved_declaration_left_unknown(actions):  # noqa: ANN001
    service, context, _ = actions
    cash = account_funding(cash_account(service, context))

    blank = approved(service, context, *captured(service, context, "B0100000021", cash))
    assert blank.review_state == "accepted"
    assert (blank.dgii.id_type, blank.dgii.payment_method) == ("1", "01")
    assert blank.dgii.category is None
    assert blank.history[-1].after_dgii.payment_method == "01"
    assert blank.approval_result.approved_revision < blank.history[-1].version

    chosen = approved(
        service,
        context,
        *captured(
            service,
            context,
            "B0100000022",
            cash,
            blank_declaration(payment_method="04"),
        ),
    )
    assert (chosen.dgii.id_type, chosen.dgii.payment_method) == ("1", "04")

    # Owner funds imply no payment form; the approval still goes through.
    owner = approved(
        service,
        context,
        *captured(service, context, "B0100000023", {"kind": "owner_funds"}),
    )
    assert owner.review_state == "accepted"
    assert (owner.dgii.id_type, owner.dgii.payment_method) == ("1", None)
    assert owner.dgii.category is None


def test_606_data_is_added_after_approval_until_the_line_is_exported(actions):  # noqa: ANN001
    service, context, _ = actions
    set_profile(service.authority, context, filer_change(FILER), "rnc")
    cash = account_funding(cash_account(service, context))
    draft_id, version = captured(service, context, "B0100000031", cash)
    view = approved(service, context, draft_id, version)
    assert view.declaration_editable is True
    assert view.dgii.category is None
    revisions = len(view.history)

    added = declared(service, context, draft_id, view.version, category="02")
    assert added.outcome == "applied", added
    view = service.dossier(context, draft_id)
    assert view.review_state == "accepted"
    assert (view.dgii.category, view.dgii.services_amount) == ("02", "1000.00")
    assert view.dgii.payment_method == "01"
    assert len(view.history) == revisions + 1
    assert view.history[-1].after_dgii.category == "02"
    assert view.history[-1].actor.actor_id == context.actor.actor_id
    assert view.approval_result.approved_revision < view.history[-1].version

    # The recorded facts stay locked; only the declaration moved.
    facts = service.review(
        context,
        draft_id,
        ReviewDraft(
            version=view.version,
            facts=BusinessFactPatch.model_validate(
                {"counterparty": {"state": "known", "value": "Otro"}}
            ),
        ),
        str(uuid4()),
    )
    assert facts.code == "recorded_correction_unsupported"
    assert export_lines(service, context) == []

    blob = export_package(service.authority, context, PERIOD, InMemorySourceObjects())
    with ZipFile(io.BytesIO(blob)) as archive:
        manifest = json.loads(archive.read("manifest.json"))["dgii"]
        assert TXT_606 in archive.namelist()
        line = archive.read(TXT_606).split(b"\r\n")[1].decode()
    assert line.split("|")[2] == "02"
    [placed] = [
        item for item in manifest["reconciliation"] if item["draft_id"] == str(draft_id)
    ]
    assert placed["disposition"] == "606"
    assert export_lines(service, context) == [(placed["activity_id"], "606", "202609")]

    view = service.dossier(context, draft_id)
    assert view.declaration_editable is False
    frozen = declared(service, context, draft_id, view.version, payment_method="04")
    assert frozen.code == "fiscal_declaration_exported"
    after = service.dossier(context, draft_id)
    assert after.dgii.payment_method == "01"
    assert len(after.history) == len(view.history)


def test_a_record_the_old_approval_left_blank_takes_the_whole_606(actions):  # noqa: ANN001
    """The approval before this slice saved the blank form and filled nothing.
    Every 606 field a person then supplies lands on the approved record in one
    write, and the TXT carries each one."""

    service, context, _ = actions
    set_profile(service.authority, context, filer_change(FILER), "rnc")
    cash = account_funding(cash_account(service, context))
    with patch(
        "argus.domain.business.actions.approval._approval_declaration",
        return_value=None,
    ):
        draft_id, version = captured(service, context, "B0100000041", cash)
        view = approved(service, context, draft_id, version)
    assert (view.dgii.id_type, view.dgii.payment_method) == (None, None)

    chosen = {
        "id_type": "1",
        "category": "02",
        "payment_method": "01",
        "services_amount": "880.00",
        "itbis_proportionality": "30.00",
        "itbis_cost": "20.00",
        "selective_tax": "10.00",
        "other_taxes": "10.00",
        "legal_tip": "100.00",
    }
    added = declared(service, context, draft_id, view.version, **chosen)
    assert added.outcome == "applied", added
    view = service.dossier(context, draft_id)
    assert {name: getattr(view.dgii, name) for name in chosen} == chosen
    assert view.review_state == "accepted"

    manifest, row = txt_606(service, context)
    assert manifest["forms"]["606"]["status"] == "prepared_candidate", manifest["issues"]
    assert {name: row[name] for name in chosen} == chosen


def test_a_restaurant_receipt_ships_its_base_itbis_and_tip(actions):  # noqa: ANN001
    """1000.00 base, 180.00 ITBIS, 100.00 propina legal: 1280.00 on the receipt.
    Approved with no 606 data. The tip comes after, with the expense type, and
    the base is the total less ITBIS and tip."""

    service, context, _ = actions
    set_profile(service.authority, context, filer_change(FILER), "rnc")
    cash = account_funding(cash_account(service, context))
    draft_id, version = captured(service, context, "B0100000042", cash, amount="1280.00")
    view = approved(service, context, draft_id, version)
    added = declared(
        service,
        context,
        draft_id,
        view.version,
        category="02",
        payment_method="01",
        legal_tip="100.00",
    )
    assert added.outcome == "applied", added
    view = service.dossier(context, draft_id)
    assert (view.dgii.services_amount, view.dgii.legal_tip) == ("1000.00", "100.00")

    manifest, row = txt_606(service, context)
    assert manifest["forms"]["606"]["status"] == "prepared_candidate", manifest["issues"]
    assert (
        row["services_amount"],
        row["billed_amount"],
        row["itbis"],
        row["legal_tip"],
    ) == ("1000.00", "1000.00", "180.00", "100.00")


def test_a_debit_note_names_the_comprobante_it_modifies_after_approval(actions):  # noqa: ANN001
    """A B03 debit note is approved like any purchase. The comprobante it
    modifies is 606 data, written after approval, and the TXT carries it."""

    service, context, _ = actions
    set_profile(service.authority, context, filer_change(FILER), "rnc")
    cash = account_funding(cash_account(service, context))
    draft_id, version = captured(service, context, "B0300000011", cash)
    view = approved(service, context, draft_id, version)
    assert view.dgii.modified_ncf is None
    added = declared(
        service,
        context,
        draft_id,
        view.version,
        category="02",
        payment_method="01",
        modified_ncf="B0100000001",
    )
    assert added.outcome == "applied", added
    assert service.dossier(context, draft_id).dgii.modified_ncf == "B0100000001"

    manifest, row = txt_606(service, context)
    assert manifest["forms"]["606"]["status"] == "prepared_candidate", manifest["issues"]
    assert (row["ncf"], row["modified_ncf"]) == ("B0300000011", "B0100000001")


def test_a_record_that_takes_no_606_refuses_the_606_write(actions):  # noqa: ANN001
    """An income carries a 607 or nothing. It reads declaration_editable false,
    open or approved, and a 606 write on it is refused with a clear code
    instead of answering applied and saving nothing."""

    service, context, _ = actions
    checking = business_account(service, context, "checking", "PRÁCTICA banco")
    draft_id, version = captured_income(service, context, checking)
    assert service.dossier(context, draft_id).declaration_editable is False
    refused = declared(service, context, draft_id, version, category="02")
    assert refused.code == "fiscal_direction_unsupported", refused
    view = service.dossier(context, draft_id)
    assert (view.version, view.dgii) == (version, None)

    recorded = service.approve_income(
        context,
        draft_id,
        ApproveIncome(version=version, action="record_income"),
        str(uuid4()),
    )
    assert recorded.outcome == "applied", recorded
    view = service.dossier(context, draft_id)
    assert (view.review_state, view.declaration_editable) == ("accepted", False)
    refused = declared(
        service, context, draft_id, view.version, category="02", payment_method="01"
    )
    assert refused.code == "fiscal_direction_unsupported", refused
    after = service.dossier(context, draft_id)
    assert (after.version, after.dgii, len(after.history)) == (
        view.version,
        None,
        len(view.history),
    )

    # A sale with its 607 saved: that declaration is not a 606 either.
    sale = {**{name: None for name in SalesDeclaration.model_fields}, "form": "607"}
    draft_id, version = captured_income(service, context, checking, declaration=sale)
    assert service.dossier(context, draft_id).declaration_editable is False
    refused = declared(service, context, draft_id, version, category="02")
    assert refused.code == "fiscal_direction_unsupported", refused
    assert service.dossier(context, draft_id).dgii.form == "607"


def test_export_lines_are_server_only_and_append_only(actions):  # noqa: ANN001
    """A signed-in person cannot read the table. The service role reads and
    inserts and can neither update nor delete: a downloaded line stays."""

    service, context, _ = actions
    with psycopg.connect(accounts.DSN) as connection, connection.cursor() as cursor:
        cursor.execute(
            "select has_table_privilege('service_role',"
            " 'public.business_dgii_export_lines', 'SELECT'),"
            " has_table_privilege('service_role',"
            " 'public.business_dgii_export_lines', 'INSERT'),"
            " has_table_privilege('service_role',"
            " 'public.business_dgii_export_lines', 'UPDATE'),"
            " has_table_privilege('service_role',"
            " 'public.business_dgii_export_lines', 'DELETE')"
        )
        assert cursor.fetchone() == (True, True, False, False)
        for statement in (
            "update public.business_dgii_export_lines set form = form",
            "delete from public.business_dgii_export_lines",
        ):
            with pytest.raises(psycopg.errors.InsufficientPrivilege):
                with connection.transaction():
                    cursor.execute("set local role service_role")
                    cursor.execute(statement)
        cursor.execute("set local role authenticated")
        cursor.execute(
            "select set_config('request.jwt.claims', %s, true)",
            (
                json.dumps(
                    {
                        "sub": str(context.actor.actor_id),
                        "role": "authenticated",
                        "is_anonymous": False,
                    }
                ),
            ),
        )
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            cursor.execute("select 1 from public.business_dgii_export_lines limit 1")
