"""On real local Postgres: the 606 reads a record's evidence from the facts a
person approved. Every capture path approves facts that name their documents,
so a step that attaches no document (a note edit, a reopen, the approval's own
declaration and its undo after a failed money write) keeps the record on the
606. A record whose approved facts name no document stays held."""

from __future__ import annotations

import io
import json
from uuid import UUID, uuid4
from zipfile import ZipFile

import psycopg
import pytest
from argus.domain.business.annotations import EditCurrentNote, edit_note
from argus.domain.business.contracts.actions import (
    ApproveIncome,
    CaptureNote,
    ExistingDraft,
    ReopenDraft,
    ReviewDraft,
    TypedPurchase,
)
from argus.domain.business.contracts.dgii import FiscalReview, SalesDeclaration
from argus.domain.business.contracts.facts import (
    BusinessFactPatch,
    BusinessFacts,
    Known,
)
from argus.domain.business.export import export_package
from argus.domain.business.reporting_store import read_recorded
from argus.domain.ingestion.documents.objects import InMemorySourceObjects
from argus.domain.recording.errors import RecordingInputError
from psycopg.types.json import Jsonb

from tests import test_financial_accounts_postgres as accounts
from tests.test_business_approval_fiscal_postgres import (  # noqa: F401
    NCF,
    SEPTEMBER,
    SUPPLIER,
    actions,
    approve,
    colmado,
    dop_account,
    lines_606,
    pytestmark,  # noqa: F401
    receipt_draft,
    reviewed,
    saved_declaration,
    shared_actions,
    users,
)

MISSING = "fiscal_approval_evidence_missing"
#: Approval needs these known; the 606 line reads the fiscal three as well.
APPROVED = ("kind", "amount", "currency", "occurred_on")
FISCAL = ("rnc", "ncf", "itbis")


def approved_facts(service, context, draft) -> BusinessFacts:  # noqa: ANN001
    """The facts of the revision the dossier names as the approved one."""

    view = service.dossier(context, draft)
    assert view.approval_result.status == "recorded", view.approval_result
    with service.authority.pool.connection() as db:
        [(facts,)] = db.execute(
            "select after_facts from public.business_draft_revisions"
            " where draft_id=%s and version=%s",
            (draft, view.approval_result.approved_revision),
        ).fetchall()
    return BusinessFacts.model_validate(facts)


def linked_sources(service, draft) -> set[UUID]:  # noqa: ANN001
    with service.authority.pool.connection() as db:
        return {
            row[0]
            for row in db.execute(
                "select source_id from public.business_draft_sources where draft_id=%s",
                (draft,),
            ).fetchall()
        }


def assert_sourced(service, context, draft, fiscal: bool) -> None:  # noqa: ANN001
    """Each fact approval needs, and each fiscal fact the 606 reads, is known
    and names a document linked to the draft. Only a DOP currency may be a
    default with no document."""

    facts = approved_facts(service, context, draft)
    linked = linked_sources(service, draft)
    named = [(name, getattr(facts, name)) for name in APPROVED]
    if fiscal:
        named += [(name, getattr(facts.fiscal, name)) for name in FISCAL]
    for name, fact in named:
        assert isinstance(fact, Known), (name, fact)
        if name == "currency" and fact.origin == "default":
            assert (fact.value, fact.source_ids) == ("DOP", ())
            continue
        assert fact.source_ids, name
        assert set(fact.source_ids) <= linked, name


def exported(service, context) -> dict:  # noqa: ANN001
    """The DGII part of the export manifest."""

    blob = export_package(service.authority, context, SEPTEMBER, InMemorySourceObjects())
    with ZipFile(io.BytesIO(blob)) as archive:
        return json.loads(archive.read("manifest.json"))["dgii"]


def reconciled(service, context, activity: str) -> dict:  # noqa: ANN001
    [item] = [
        item
        for item in exported(service, context)["reconciliation"]
        if item["activity_id"] == activity
    ]
    return item


def shipped(service, context, draft) -> list[dict]:  # noqa: ANN001
    """The 606 issues for this draft's record, after the TXT carried its line.
    The dossier's approval receipt, the export manifest and the recorded
    snapshot name the same approved revision."""

    view = service.dossier(context, draft)
    activity = str(view.approval_result.activity_id)
    lines, issues = lines_606(service, context)
    mine = [issue for issue in issues if issue.get("activity_id") == activity]
    assert MISSING not in {issue["code"] for issue in mine}, mine
    assert [line for line in lines if NCF in line.split("|")], (lines, mine)
    [recorded] = [
        record
        for record in read_recorded(service.authority, context).records
        if str(record.row.activity_id) == activity
    ]
    assert (
        view.approval_result.approved_revision,
        reconciled(service, context, activity)["approved_revision"],
        recorded.approved.approved_revision,
    ) == (view.approval_result.approved_revision,) * 3
    return mine


def partial_declaration() -> dict:
    """A saved 606 the approval completes: it fills the Tipo Id, so the
    approval writes a revision of its own that attaches no document."""

    return {
        "fiscal": {"rnc": SUPPLIER, "ncf": NCF, "itbis": "180.00"},
        "declaration": saved_declaration(id_type=None),
    }


def refuse_once(service, monkeypatch) -> None:  # noqa: ANN001
    money = service.imports.money
    write = money.write

    def refuse(**kwargs):  # noqa: ANN003, ANN202
        monkeypatch.setattr(money, "write", write)
        raise RecordingInputError("activity_invalid", "synthetic refusal")

    monkeypatch.setattr(money, "write", refuse)


def review_facts(service, context, draft, version, facts, dgii=None) -> int:  # noqa: ANN001
    result = service.review(
        context,
        draft,
        ReviewDraft(
            version=version,
            facts=BusinessFactPatch.model_validate(
                {
                    name: {"state": "known", "value": value}
                    for name, value in facts.items()
                }
            ),
            dgii=FiscalReview.model_validate(dgii) if dgii else None,
        ),
        str(uuid4()),
    )
    assert result.outcome == "applied", result
    return result.version


# The premise: every capture path approves facts that name their documents.


def test_an_uploaded_read_approves_sourced_facts(actions) -> None:  # noqa: ANN001, F811
    service, context = actions
    draft, version = receipt_draft(service, context, colmado(), "DOP")
    outcome = approve(service, context, draft, reviewed(service, context, draft, version))
    assert outcome.outcome == "applied", outcome
    assert_sourced(service, context, draft, fiscal=True)


@pytest.mark.parametrize("document_type", [None, "recibo"])
def test_a_typed_purchase_note_approves_sourced_facts(actions, document_type) -> None:  # noqa: ANN001, F811
    service, context = actions
    capture = service.capture(
        context,
        CaptureNote(text="PRÁCTICA compra a mano", document_type=document_type),
        str(uuid4()),
    )
    assert capture.outcome == "applied", capture
    version = review_facts(
        service,
        context,
        capture.draft_id,
        capture.version,
        {
            "kind": "expense",
            "amount": "1180.00",
            "currency": "DOP",
            "occurred_on": "2026-09-05",
            "counterparty": "PRÁCTICA Ferretería",
            "funding": {"kind": "owner_funds"},
            "business_share": {"kind": "all"},
            "receipt_state": "fiscal_receipt",
        },
        {
            "fiscal": {"rnc": SUPPLIER, "ncf": NCF, "itbis": "180.00"},
            "declaration": saved_declaration(),
        },
    )
    outcome = approve(service, context, capture.draft_id, version)
    assert outcome.outcome == "applied", outcome
    assert_sourced(service, context, capture.draft_id, fiscal=True)


def test_a_typed_sale_approves_sourced_facts(actions) -> None:  # noqa: ANN001, F811
    service, context = actions
    checking = dop_account(service, context, "checking")
    capture = service.capture(
        context,
        CaptureNote(text="PRÁCTICA venta a mano", document_type="venta"),
        str(uuid4()),
    )
    assert capture.outcome == "applied", capture
    # The type names the kind; the person types the rest.
    assert approved_kind_is_sourced(service, capture.draft_id)
    version = review_facts(
        service,
        context,
        capture.draft_id,
        capture.version,
        {
            "amount": "2360.00",
            "currency": "DOP",
            "occurred_on": "2026-09-06",
            "counterparty": "PRÁCTICA Cliente",
            "funding": {"kind": "business_account", "account_id": str(checking)},
            "business_share": {"kind": "all"},
        },
        {
            "fiscal": {"rnc": SUPPLIER, "ncf": "B0100000777", "itbis": "360.00"},
            "declaration": {
                **{name: None for name in SalesDeclaration.model_fields},
                "form": "607",
            },
        },
    )
    outcome = service.approve_income(
        context,
        capture.draft_id,
        ApproveIncome(version=version, action="record_income"),
        str(uuid4()),
    )
    assert outcome.outcome == "applied", outcome
    assert_sourced(service, context, capture.draft_id, fiscal=True)


def approved_kind_is_sourced(service, draft) -> bool:  # noqa: ANN001
    with service.authority.pool.connection() as db:
        [(facts,)] = db.execute(
            "select after_facts from public.business_draft_revisions"
            " where draft_id=%s order by version desc limit 1",
            (draft,),
        ).fetchall()
    kind = BusinessFacts.model_validate(facts).kind
    return isinstance(kind, Known) and kind.value == "income" and bool(kind.source_ids)


def test_a_typed_purchase_with_no_paper_approves_sourced_facts(actions) -> None:  # noqa: ANN001, F811
    service, context = actions
    capture = service.capture(
        context,
        CaptureNote(
            text="PRÁCTICA Colmado",
            purchase=TypedPurchase(amount="350.00", occurred_on="2026-09-07"),
        ),
        str(uuid4()),
    )
    assert capture.outcome == "applied", capture
    version = review_facts(
        service,
        context,
        capture.draft_id,
        capture.version,
        {"funding": {"kind": "owner_funds"}, "business_share": {"kind": "all"}},
    )
    outcome = approve(service, context, capture.draft_id, version)
    assert outcome.outcome == "applied", outcome
    # Sin comprobante: no fiscal facts, and the currency is the DOP default.
    assert_sourced(service, context, capture.draft_id, fiscal=False)


def test_a_note_added_to_a_draft_keeps_its_sourced_facts(actions) -> None:  # noqa: ANN001, F811
    service, context = actions
    draft, version = receipt_draft(service, context, colmado(), "DOP")
    version = reviewed(service, context, draft, version)
    added = service.capture(
        context,
        CaptureNote(
            text="PRÁCTICA nota del dueño",
            draft=ExistingDraft(draft_id=draft, version=version),
        ),
        str(uuid4()),
    )
    assert added.outcome == "applied", added
    outcome = approve(service, context, draft, added.version)
    assert outcome.outcome == "applied", outcome
    assert_sourced(service, context, draft, fiscal=True)


# The bug: a step that attaches no document left the record off the 606.


def test_approval_after_a_note_edit_ships_the_606_line(actions) -> None:  # noqa: ANN001, F811
    service, context = actions
    draft, version = receipt_draft(service, context, colmado(), "DOP")
    version = reviewed(service, context, draft, version, dgii=partial_declaration())
    noted = edit_note(
        service.authority,
        context,
        draft,
        EditCurrentNote(expected_version=version, note="PRÁCTICA almuerzo"),
        str(uuid4()),
    )
    outcome = approve(service, context, draft, noted.version)
    assert outcome.outcome == "applied", outcome
    shipped(service, context, draft)


def test_reopen_then_approval_with_no_edits_ships_the_606_line(actions) -> None:  # noqa: ANN001, F811
    service, context = actions
    draft, version = receipt_draft(service, context, colmado(), "DOP")
    version = reviewed(service, context, draft, version, dgii=partial_declaration())
    assert approve(service, context, draft, version).outcome == "applied"
    reopened = service.reopen(
        context,
        draft,
        ReopenDraft(version=service.dossier(context, draft).version),
        str(uuid4()),
    )
    assert reopened.outcome == "applied", reopened
    outcome = approve(service, context, draft, reopened.version)
    assert outcome.outcome == "applied", outcome
    shipped(service, context, draft)


@pytest.mark.parametrize("undone", [True, False], ids=["undo_ran", "undo_missed"])
def test_a_retried_approval_ships_the_606_line(actions, monkeypatch, undone) -> None:  # noqa: ANN001, F811
    from argus.domain.business.actions import approval

    service, context = actions
    draft, version = receipt_draft(service, context, colmado(), "DOP")
    version = reviewed(service, context, draft, version, dgii=partial_declaration())
    refuse_once(service, monkeypatch)
    if not undone:
        monkeypatch.setattr(approval, "_clear_approval_declaration", lambda *_: None)
    failed = approve(service, context, draft, version)
    assert (failed.outcome, failed.code) == ("invalid_input", "activity_invalid")

    outcome = approve(service, context, draft, service.dossier(context, draft).version)
    assert outcome.outcome == "applied", outcome
    shipped(service, context, draft)


def test_approved_facts_that_name_no_document_stay_held(actions) -> None:  # noqa: ANN001, F811
    """The control: strip every document from the approved revision's facts,
    as no capture path can, and the record is held off the 606. With no
    document a fact cannot be known, so the record has no NCF either."""

    service, context = actions
    draft, version = receipt_draft(service, context, colmado(), "DOP")
    version = reviewed(service, context, draft, version, dgii=partial_declaration())
    outcome = approve(service, context, draft, version)
    assert outcome.outcome == "applied", outcome
    revision = service.dossier(context, draft).approval_result.approved_revision
    bare = BusinessFacts(currency=Known(value="DOP", origin="default", source_ids=()))
    with psycopg.connect(accounts.DSN) as db, db.transaction():
        # Revisions are immutable by trigger; the disposable database lets the
        # test bypass it to build a record no capture path can.
        db.execute("set local session_replication_role = replica")
        db.execute(
            "update public.business_draft_revisions set after_facts=%s"
            " where draft_id=%s and version=%s",
            (Jsonb(bare.model_dump(mode="json")), draft, revision),
        )

    held = reconciled(service, context, str(outcome.activity_id))
    assert (held["disposition"], held["source_ids"]) == ("needs_review", [])
    assert exported(service, context)["forms"]["606"]["status"] == "needs_review"
    assert not [line for line in lines_606(service, context)[0] if NCF in line]
