"""On real local Postgres: a receipt photo is read, bound, reviewed and
approved, and the approval writes the 606 declaration from the stored facts."""

import io
import json
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from uuid import UUID, uuid4
from zipfile import ZipFile

import pytest
from argus.domain.business.contracts.actions import (
    ApproveExpense,
    ReviewDraft,
    canonical_input_hash,
)
from argus.domain.business.contracts.dgii import FiscalReview
from argus.domain.business.contracts.facts import BusinessFactPatch
from argus.domain.business.export import ExportPeriod, export_package
from argus.domain.business.fiscal_profile import FiscalProfileChange, set_profile
from argus.domain.ingestion.contract import Attachment
from argus.domain.ingestion.documents.extractor import batch_from_result
from argus.domain.ingestion.documents.models import DocumentDraft, ExtractionResult
from argus.domain.ingestion.documents.objects import InMemorySourceObjects
from argus.domain.recording.repository import NewAccount
from faker import Faker
from psycopg.types.json import Jsonb

from tests import test_business_actions_postgres as shared
from tests.test_business_spaces_migration_postgres import connection

users = shared.users
shared_actions = shared.actions
pytestmark = [shared.pytestmark, pytest.mark.owner_acts]
FILER = "199990013"
SUPPLIER = "199990021"
EDITED_SUPPLIER = "199990048"
NCF = "B0100000001"
SEPTEMBER = ExportPeriod(date(2026, 9, 1), date(2026, 9, 30))
fake = Faker("es_MX")
Faker.seed(606)


@pytest.fixture
def actions(shared_actions):
    from argus.domain.business.spaces import PostgresSpaceStore

    service, context, grant = shared_actions
    name = fake.company()
    PostgresSpaceStore(service.authority.pool).rename(context.owner_id, name)
    set_profile(
        service.authority,
        context,
        FiscalProfileChange(
            name=name,
            previous_name=name,
            tax_id={"type": "rnc", "value": FILER},
            previous_tax_id=None,
        ),
        "rnc",
    )
    yield service, context


def colmado(**changes):
    """A local receipt: RNC, NCF and ITBIS printed, the supplier only in the header."""

    read = {
        "merchant": f"Colmado {fake.last_name()}",
        "total": "1180.00",
        "currency": "DOP",
        "rnc": SUPPLIER,
        "ncf": NCF,
        "itbis": "180.00",
        "occurred_on": "2026-09-05",
    }
    return {**read, **changes}


def receipt_draft(
    service, context, receipt: dict, currency: str | None, account: str | None = None
):
    """Prepare and bind one saved photo read. The purchase row leaves the supplier unknown."""

    content = f"{fake.uuid4()} {receipt['total']}".encode()
    digest = sha256(content).hexdigest()
    now = datetime.now(timezone.utc)
    holder = str(uuid4())
    result = ExtractionResult.model_validate(
        dict(
            complete=True,
            readable=True,
            pages_read=[1],
            observations=[
                dict(
                    page=1,
                    row=1,
                    evidence="transaction",
                    amount=receipt["total"],
                    currency=currency,
                    occurred_on=receipt["occurred_on"],
                    direction="outflow",
                    kind_hint="expense",
                    account={"currency": account},
                )
            ],
            receipt=receipt,
        )
    )
    with service.authority.pool.connection() as db:
        cid = connection(db, context.owner_id, context.actor.space_id)
        draft = DocumentDraft(
            connection_id=cid,
            filename="recibo.jpg",
            media_type="image/jpeg",
            sha256=digest,
            size_bytes=len(content),
            consent=True,
            created_at=now,
            updated_at=now,
        )
        batch = batch_from_result(result, digest, cid, now, 1)
        attachment = Attachment(
            external_id=digest,
            sha256=digest,
            media_type=draft.media_type,
            size_bytes=len(content),
            filename=draft.filename,
        )
        batch = batch.model_copy(
            update={
                "metadata": {"sha256": digest},
                "candidates": tuple(
                    c.model_copy(update={"attachments": (attachment,)})
                    for c in batch.candidates
                ),
            }
        )
        db.execute(
            "insert into public.financial_document_extractions"
            " (connection_id,user_id,draft,source_bytes,batch) values (%s,%s,%s,%s,%s)",
            (
                cid,
                context.owner_id,
                Jsonb(draft.model_dump(mode="json")),
                content,
                Jsonb(batch.model_dump(mode="json")),
            ),
        )
        db.execute(
            "update public.financial_source_connections set lease_holder=%s,"
            " lease_until=%s where id=%s",
            (holder, now + timedelta(minutes=3), cid),
        )
    service.capture_attachment_preparation(context, UUID(cid), target=None)
    prepared = service.prepare_attachment(
        user_id=context.owner_id,
        connection_id=cid,
        scope=context.scope,
        holder=holder,
        attempt_id=None,
        expected_batch_sha256=canonical_input_hash(batch),
    )
    assert prepared.outcome == "applied", prepared
    return prepared.draft_id, prepared.version


def review(service, context, draft, version, *, funding=None, dgii=None):
    facts = BusinessFactPatch.model_validate(
        {
            name: {"state": "known", "value": value}
            for name, value in {
                "funding": funding or {"kind": "owner_funds"},
                "business_share": {"kind": "all"},
            }.items()
        }
    )
    return service.review(
        context,
        draft,
        ReviewDraft(
            version=version,
            facts=facts,
            dgii=FiscalReview.model_validate(dgii) if dgii else None,
        ),
        str(uuid4()),
    )


def reviewed(service, context, draft, version, **changes):
    result = review(service, context, draft, version, **changes)
    assert result.outcome == "applied", result
    return result.version


def approve(service, context, draft, version):
    return service.approve(
        context,
        draft,
        ApproveExpense(version=version, action="record_expense"),
        str(uuid4()),
    )


def revisions(service, draft) -> list[dict]:
    with service.authority.pool.connection() as db:
        rows = db.execute(
            "select version,after_facts,after_dgii from public.business_draft_revisions"
            " where draft_id=%s order by version",
            (draft,),
        ).fetchall()
    return [dict(zip(("version", "facts", "dgii"), row, strict=True)) for row in rows]


def dop_account(service, context, kind="cash"):
    return service.imports.money.repository.create(
        user_id=context.owner_id,
        idempotency_key=str(uuid4()),
        identity_hash=uuid4().hex,
        account=NewAccount(
            type=kind, currency="DOP", nickname="Caja", ownership_share_bps=10000
        ),
        opening=shared.shared._opening(1000000),
        scope=context.scope,
    ).stored.account.id


def booked(service, context) -> list[tuple]:
    with service.authority.pool.connection() as db:
        return db.execute(
            "select funding,currency from public.financial_records"
            " where user_id=%s and record_kind='expense'",
            (context.owner_id,),
        ).fetchall()


def lines_606(service, context) -> tuple[list[str], list[dict]]:
    blob = export_package(service.authority, context, SEPTEMBER, InMemorySourceObjects())
    with ZipFile(io.BytesIO(blob)) as archive:
        issues = json.loads(archive.read("manifest.json"))["dgii"]["issues"]
        name = f"dgii/DGII_F_606_{FILER}_202609.TXT"
        text = archive.read(name).decode() if name in archive.namelist() else ""
    return [line for line in text.split("\r\n")[1:] if line], issues


def saved_declaration(**changes):
    declaration = {
        "form": "606",
        "id_type": "1",
        "modified_ncf": None,
        "selective_tax": "0.00",
        "other_taxes": "0.00",
        "legal_tip": "0.00",
        "category": "02",
        "category_suggested": False,
        "paid_on": "2026-09-05",
        "services_amount": "1000.00",
        "goods_amount": "0.00",
        "itbis_withheld": "0.00",
        "itbis_proportionality": "0.00",
        "itbis_cost": "0.00",
        "itbis_perceived": "0.00",
        "income_withholding_type": None,
        "income_withheld": "0.00",
        "income_perceived": "0.00",
        "payment_method": "03",
        "actual_refund": False,
        "purchase_activity_id": None,
    }
    return {**declaration, **changes}


def test_owner_funded_receipt_declares_no_expense_type_or_payment_form(actions):
    service, context = actions
    read = colmado()
    draft, version = receipt_draft(service, context, read, "DOP")
    approved = reviewed(service, context, draft, version)

    outcome = approve(service, context, draft, approved)

    assert outcome.outcome == "applied", outcome
    *reviewing, declared = revisions(service, draft)
    assert all(row["dgii"] is None for row in reviewing)
    assert declared["version"] == approved + 1
    assert declared["facts"] == reviewing[-1]["facts"]
    assert declared["facts"]["counterparty"]["value"] == read["merchant"]
    assert {
        name: declared["dgii"][name]
        for name in (
            "form",
            "id_type",
            "category",
            "category_suggested",
            "payment_method",
            "goods_amount",
            "services_amount",
        )
    } == {
        "form": "606",
        "id_type": "1",
        "category": None,
        "category_suggested": False,
        "payment_method": None,
        "goods_amount": None,
        "services_amount": None,
    }
    lines, issues = lines_606(service, context)
    assert lines == []
    activity = outcome.activity_id
    blocking = {
        issue["field"]
        for issue in issues
        if issue["code"] == "fiscal_fact_required"
        and issue["activity_id"] == str(activity)
    }
    assert {"category", "payment_method"} <= blocking
    assert booked(service, context) == [("owner_funds", "DOP")]
    assert service.dossier(context, draft).approval_result.approved_revision == approved


def test_usd_owner_funded_receipt_stays_usd_after_approval(actions):
    service, context = actions
    draft, version = receipt_draft(
        service,
        context,
        colmado(currency="USD", total="59.00", itbis=None, rnc=None, ncf=None),
        None,
    )
    approved = reviewed(service, context, draft, version)

    outcome = approve(service, context, draft, approved)

    assert outcome.outcome == "applied", outcome
    history = revisions(service, draft)
    assert history[-1]["version"] == approved
    assert history[-1]["facts"]["currency"]["value"] == "USD"
    assert history[-1]["dgii"] is None
    assert booked(service, context) == [("owner_funds", "USD")]


def test_a_printed_currency_symbol_stays_unknown(actions):
    service, context = actions

    draft, _ = receipt_draft(service, context, colmado(currency="RD$"), None)

    assert revisions(service, draft)[-1]["facts"]["currency"]["state"] == "unknown"


@pytest.mark.parametrize("ncf", ["B0200000001", "E320000000001"])
def test_consumer_receipt_gets_no_declaration(actions, ncf):
    service, context = actions
    draft, version = receipt_draft(service, context, colmado(ncf=ncf), "DOP")
    approved = reviewed(service, context, draft, version)

    outcome = approve(service, context, draft, approved)

    assert outcome.outcome == "applied", outcome
    history = revisions(service, draft)
    assert history[-1]["version"] == approved
    assert history[-1]["dgii"] is None


def test_receipt_without_rnc_gets_no_declaration(actions):
    service, context = actions
    draft, version = receipt_draft(service, context, colmado(rnc=None), "DOP")
    approved = reviewed(service, context, draft, version)

    outcome = approve(service, context, draft, approved)

    assert outcome.outcome == "applied", outcome
    history = revisions(service, draft)
    assert history[-1]["facts"]["fiscal"]["rnc"]["state"] == "unknown"
    assert history[-1]["version"] == approved
    assert history[-1]["dgii"] is None


def test_a_read_naming_two_currencies_leaves_the_currency_unknown(actions):
    service, context = actions

    draft, _ = receipt_draft(
        service, context, colmado(currency="USD"), None, account="DOP"
    )

    assert revisions(service, draft)[-1]["facts"]["currency"]["state"] == "unknown"


@pytest.mark.parametrize(
    "kind,form",
    [("cash", "01"), ("checking", "02"), ("savings", "02"), ("credit_card", "03")],
)
def test_payment_form_follows_the_account_that_paid(actions, kind, form):
    service, context = actions
    account = dop_account(service, context, kind)
    draft, version = receipt_draft(service, context, colmado(), "DOP")
    approved = reviewed(
        service,
        context,
        draft,
        version,
        funding={"kind": "business_account", "account_id": str(account)},
    )

    outcome = approve(service, context, draft, approved)

    assert outcome.outcome == "applied", outcome
    assert revisions(service, draft)[-1]["dgii"]["payment_method"] == form


def test_usd_receipt_on_a_dop_account_is_refused_without_money(actions):
    service, context = actions
    account = dop_account(service, context)
    draft, version = receipt_draft(
        service, context, colmado(currency="USD", total="59.00"), "USD"
    )
    funding = {"kind": "business_account", "account_id": str(account)}

    refused = review(service, context, draft, version, funding=funding)
    outcome = approve(service, context, draft, version)

    assert (refused.outcome, refused.code) == (
        "invalid_input",
        "import_currency_mismatch",
    )
    assert outcome.outcome == "invalid_input", outcome
    assert booked(service, context) == []
    assert [row["version"] for row in revisions(service, draft)] == [version]


def test_account_funded_receipt_without_currency_is_refused_without_money(actions):
    service, context = actions
    account = dop_account(service, context)
    draft, version = receipt_draft(
        service, context, colmado(currency=None, total="59.00"), None
    )
    funding = {"kind": "business_account", "account_id": str(account)}
    approved = reviewed(service, context, draft, version, funding=funding)

    outcome = approve(service, context, draft, approved)

    assert (outcome.outcome, outcome.code) == ("invalid_input", "fact_required")
    assert booked(service, context) == []


def test_rnc_edited_before_approval_is_the_one_declared(actions):
    service, context = actions
    draft, version = receipt_draft(service, context, colmado(), "DOP")
    approved = reviewed(
        service,
        context,
        draft,
        version,
        dgii={
            "fiscal": {"rnc": EDITED_SUPPLIER, "ncf": NCF, "itbis": "180.00"},
            "declaration": saved_declaration(
                category="09", services_amount="0.00", goods_amount="1000.00"
            ),
        },
    )

    outcome = approve(service, context, draft, approved)

    assert outcome.outcome == "applied", outcome
    assert (
        revisions(service, draft)[-1]["facts"]["fiscal"]["rnc"]["value"]
        == EDITED_SUPPLIER
    )
    lines, issues = lines_606(service, context)
    assert issues == []
    [line] = lines
    assert line.split("|")[0] == EDITED_SUPPLIER


def test_declaration_saved_before_approval_is_kept(actions):
    service, context = actions
    draft, version = receipt_draft(service, context, colmado(), "DOP")
    saved = saved_declaration()
    approved = reviewed(
        service,
        context,
        draft,
        version,
        dgii={
            "fiscal": {"rnc": SUPPLIER, "ncf": NCF, "itbis": "180.00"},
            "declaration": saved,
        },
    )

    outcome = approve(service, context, draft, approved)

    assert outcome.outcome == "applied", outcome
    history = revisions(service, draft)
    assert history[-1]["version"] == approved
    assert history[-1]["dgii"] == saved
    lines, issues = lines_606(service, context)
    assert issues == []
    [line] = lines
    assert line.split("|")[:4] == [SUPPLIER, "1", "02", NCF]


def drafts_client(service, context):
    from argus.api.app_setup import http_exception_handler
    from argus.api.business_drafts import DraftContext, require_drafts
    from argus.api.routers.business_drafts import router
    from fastapi import FastAPI, HTTPException
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.include_router(router)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.dependency_overrides[require_drafts] = lambda: DraftContext(
        service, context.actor.actor_id, str(context.actor.space_id), context.grant_id
    )

    @app.middleware("http")
    async def request_id(request, call_next):
        request.state.request_id = "duplicate-comprobante"
        return await call_next(request)

    return TestClient(app)


def test_same_rnc_and_ncf_already_approved_is_refused_with_its_record(actions):
    service, context = actions
    first, version = receipt_draft(service, context, colmado(), "DOP")
    assert approve(
        service, context, first, reviewed(service, context, first, version)
    ).outcome == ("applied")
    second, version = receipt_draft(service, context, colmado(), "DOP")
    approved = reviewed(service, context, second, version)

    key = str(uuid4())
    with drafts_client(service, context) as client:
        refused, replayed = (
            client.post(
                f"/business/drafts/{second}/approve",
                json={"version": approved, "action": "record_expense"},
                headers={"Idempotency-Key": key},
            )
            for _ in range(2)
        )

    for response in (refused, replayed):
        assert response.status_code == 422, response.json()
        assert response.json()["code"] == "duplicate_comprobante"
        assert response.json()["context"] == {"existing_record_id": str(first)}
    assert booked(service, context) == [("owner_funds", "DOP")]


@pytest.mark.parametrize(
    "first_read,second_read",
    [
        (colmado(), colmado(rnc=EDITED_SUPPLIER)),
        (colmado(rnc=None), colmado(rnc=None)),
    ],
    ids=["other_supplier", "no_rnc"],
)
def test_short_of_an_rnc_and_ncf_match_approval_goes_through(
    actions, first_read, second_read
):
    service, context = actions
    for read in (first_read, second_read):
        draft, version = receipt_draft(service, context, read, "DOP")
        outcome = approve(
            service, context, draft, reviewed(service, context, draft, version)
        )
        assert outcome.outcome == "applied", outcome
    assert len(booked(service, context)) == 2


def test_failed_money_write_clears_the_approval_declaration(actions, monkeypatch):
    from argus.domain.recording.errors import RecordingInputError

    service, context = actions
    checking = dop_account(service, context, "checking")
    draft, version = receipt_draft(service, context, colmado(), "DOP")
    approved = reviewed(service, context, draft, version)
    money = service.imports.money
    write = money.write

    def refuse_once(**kwargs):
        monkeypatch.setattr(money, "write", write)
        raise RecordingInputError("activity_invalid", "synthetic refusal")

    monkeypatch.setattr(money, "write", refuse_once)

    failed = approve(service, context, draft, approved)

    assert (failed.outcome, failed.code) == ("invalid_input", "activity_invalid")
    reopened = service.dossier(context, draft)
    assert reopened.dgii is None
    cleared = revisions(service, draft)[-1]
    assert (cleared["version"], cleared["dgii"]) == (reopened.version, None)
    funded = reviewed(
        service,
        context,
        draft,
        reopened.version,
        funding={"kind": "business_account", "account_id": str(checking)},
    )

    outcome = approve(service, context, draft, funded)

    assert outcome.outcome == "applied", outcome
    assert revisions(service, draft)[-1]["dgii"]["payment_method"] == "02"
    assert len(booked(service, context)) == 1


def test_failed_money_write_keeps_the_saved_declaration(actions, monkeypatch):
    from argus.domain.recording.errors import RecordingInputError

    service, context = actions
    draft, version = receipt_draft(service, context, colmado(), "DOP")
    saved = saved_declaration()
    approved = reviewed(
        service,
        context,
        draft,
        version,
        dgii={
            "fiscal": {"rnc": SUPPLIER, "ncf": NCF, "itbis": "180.00"},
            "declaration": saved,
        },
    )

    def refuse(**kwargs):
        raise RecordingInputError("activity_invalid", "synthetic refusal")

    monkeypatch.setattr(service.imports.money, "write", refuse)

    failed = approve(service, context, draft, approved)

    assert failed.outcome == "invalid_input", failed
    assert service.dossier(context, draft).dgii.model_dump(mode="json") == saved
    assert revisions(service, draft)[-1]["version"] == approved


def test_records_sheet_has_the_accountant_columns(actions):
    from tests.business.test_business_export import sheet_rows

    service, context = actions
    read = colmado()
    draft, version = receipt_draft(service, context, read, "DOP")
    approved = reviewed(
        service,
        context,
        draft,
        version,
        dgii={
            "fiscal": {"rnc": SUPPLIER, "ncf": NCF, "itbis": "180.00"},
            "declaration": saved_declaration(),
        },
    )
    outcome = approve(service, context, draft, approved)
    assert outcome.outcome == "applied", outcome

    blob = export_package(service.authority, context, SEPTEMBER, InMemorySourceObjects())

    with ZipFile(io.BytesIO(blob)) as archive:
        text = archive.read("records.csv").decode("utf-8-sig")
        workbook = archive.read("records.xlsx")
    rows = [line.split(",") for line in text.strip().split("\r\n")]
    assert rows == [
        [
            "Fecha",
            "Proveedor",
            "RNC",
            "NCF",
            "Tipo de gasto",
            "Forma de pago",
            "Subtotal",
            "ITBIS",
            "Total",
            "Moneda",
            "Estado",
        ],
        [
            "2026-09-05",
            read["merchant"],
            SUPPLIER,
            NCF,
            "02",
            "03",
            "1000.00",
            "180.00",
            "1180.00",
            "DOP",
            "606",
        ],
    ]
    assert sheet_rows(workbook) == rows
    ids = sheet_rows(workbook, 2)
    assert ids[1][ids[0].index("activity_id")] == str(outcome.activity_id)
    assert ids[1][ids[0].index("draft_ids")] == str(draft)
    assert "note" not in ids[0]


def test_reapproval_rebuilds_a_declaration_the_clear_missed(actions, monkeypatch):
    from argus.domain.business.actions import approval
    from argus.domain.recording.errors import RecordingInputError

    service, context = actions
    checking = dop_account(service, context, "checking")
    draft, version = receipt_draft(service, context, colmado(), "DOP")
    approved = reviewed(service, context, draft, version)
    money = service.imports.money
    write = money.write

    def refuse_once(**kwargs):
        monkeypatch.setattr(money, "write", write)
        raise RecordingInputError("activity_invalid", "synthetic refusal")

    monkeypatch.setattr(money, "write", refuse_once)
    monkeypatch.setattr(approval, "_clear_approval_declaration", lambda *_: None)
    assert approve(service, context, draft, approved).outcome == "invalid_input"
    reopened = service.dossier(context, draft)
    assert reopened.dgii is not None
    funded = reviewed(
        service,
        context,
        draft,
        reopened.version,
        funding={"kind": "business_account", "account_id": str(checking)},
    )

    outcome = approve(service, context, draft, funded)

    assert outcome.outcome == "applied", outcome
    assert revisions(service, draft)[-1]["dgii"]["payment_method"] == "02"


def test_a_failed_clear_still_stores_the_refusal(actions, monkeypatch):
    from argus.domain.business.actions import approval
    from argus.domain.business.authority import ActionError
    from argus.domain.recording.errors import RecordingInputError

    service, context = actions
    draft, version = receipt_draft(service, context, colmado(), "DOP")
    approved = reviewed(service, context, draft, version)

    def refuse(**kwargs):
        raise RecordingInputError("activity_invalid", "synthetic refusal")

    def unreadable(event):
        raise ActionError("not_found", "business_record_not_found")

    monkeypatch.setattr(service.imports.money, "write", refuse)
    monkeypatch.setattr(approval, "facts_of", unreadable)
    key = str(uuid4())
    command = ApproveExpense(version=approved, action="record_expense")

    failed, replayed = (service.approve(context, draft, command, key) for _ in range(2))

    assert (failed.outcome, failed.code) == ("invalid_input", "activity_invalid")
    assert replayed == failed
