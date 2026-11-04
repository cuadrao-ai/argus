"""The document type is the one owner of purchase or sale. The Bandeja's
editors, Registros' family, the projection and the 606/607 export read it
through ``direction``; typed entry and the read set it through one rule,
``resolved_document_type``, and a default is never marked detected."""

from __future__ import annotations

import json
from contextlib import contextmanager, nullcontext
from dataclasses import replace
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from argus.domain.business import document_type as types
from argus.domain.business.actions import captures, mutations, sources
from argus.domain.business.contracts.actions import CaptureNote
from argus.domain.business.contracts.facts import BusinessFacts, Known
from argus.domain.business.dgii_export import fiscal_manifest
from argus.domain.business.dgii_validation import FiscalRecord
from argus.domain.business.month_close import project_documents
from argus.domain.business.purchase_review import (
    takes_payment_split,
    takes_purchase_declaration,
)
from argus.domain.business.reporting import ReportRow
from argus.domain.business.reporting_projection import DraftState, project
from argus.domain.business.reporting_store import RecordedRecord
from argus.domain.ingestion.contract import ImportCandidate, SourceRef
from argus.domain.ingestion.documents.dgii_qr import parse_dgii_url
from argus.domain.ingestion.documents.models import ExtractionBatch, ReceiptDetails
from argus.domain.ingestion.reconcile.model import ImportEvent

from tests.business.test_venta import _actor, _draft
from tests.dgii.test_packet import practice_records
from tests.dgii_qr_support import RNC as QR_ISSUER
from tests.dgii_qr_support import URL

OWN = "131000002"
OTHER = "101000007"
DAY = date(2026, 9, 3)
PERIOD = dict(start=date(2026, 9, 1), end=date(2026, 9, 30), captured_on=date(2026, 10, 18))


@pytest.mark.parametrize(
    "named,issuer,own,expected",
    [
        ("recibo", OWN, OWN, ("recibo", False)),
        ("venta", OTHER, OWN, ("venta", False)),
        (None, OWN, OWN, ("venta", True)),
        (None, "1-31-00000-2", OWN, ("venta", True)),
        (None, OTHER, OWN, ("recibo", True)),
        # A typed note prints no issuer: a receipt by default.
        (None, None, OWN, ("recibo", False)),
        # No Business RNC to compare with: a receipt by default.
        (None, OTHER, None, ("recibo", False)),
        (None, "RNC 131000002", OWN, ("recibo", False)),
        (None, None, None, ("recibo", False)),
    ],
)
def test_one_rule_names_the_type_and_whether_the_read_chose_it(
    named, issuer, own, expected
):
    assert types.resolved_document_type(named, issuer, own) == expected


@pytest.mark.parametrize(
    "document_type,family,form", [("recibo", "purchase", "606"), ("venta", "sale", "607")]
)
def test_each_type_is_one_family_on_one_form(document_type, family, form):
    found = types.direction(document_type)
    assert (found.family, found.form) == (family, form)


@pytest.mark.parametrize(
    "kind,document_type",
    [("expense", "recibo"), ("refund", "recibo"), ("income", "venta"), ("transfer", None)],
)
def test_money_with_no_document_stands_under_the_type_whose_kinds_include_it(
    kind, document_type
):
    assert types.money_document_type(kind) == document_type
    assert types.direction(None) is None


def _tx(own: str | None) -> SimpleNamespace:
    return SimpleNamespace(
        context=SimpleNamespace(
            owner_id=str(uuid4()), actor=SimpleNamespace(space_id=uuid4())
        ),
        imports=SimpleNamespace(put_event=Mock()),
        rows=Mock(
            side_effect=lambda sql, *args: [{"business_rnc": own}]
            if "business_rnc" in sql
            else []
        ),
    )


def _read(monkeypatch, *, named, printed, own, qr=False) -> dict:  # noqa: ANN001
    """One upload read on a Business whose RNC is ``own``: ``printed`` is the
    RNC the read found, ``qr`` adds a DGII QR whose issuer is ``QR_ISSUER``."""

    draft = _draft(document_type=named)
    candidate = ImportCandidate(
        source=SourceRef(
            source="statement",
            connection_id=draft.connection_id,
            external_id=draft.sha256,
            observed_at=draft.created_at,
        ),
        evidence="transaction",
        direction="outflow",
        amount="118.00",
        currency="DOP",
        kind_hint="expense",
        merchant="PRÁCTICA Ferretería",
    )
    batch = ExtractionBatch(
        complete=True,
        readable=True,
        candidates=(candidate,),
        receipt=ReceiptDetails(
            total="118.00", currency="DOP", rnc=printed, ncf="B0100000001"
        ),
        dgii_qr=parse_dgii_url(URL) if qr else None,
    )
    tx = _tx(own)
    monkeypatch.setattr(sources, "record_source", lambda *args: uuid4())
    monkeypatch.setattr(sources, "attach", lambda *args: None)
    mutations.prepare_attachment(tx, None, batch, draft, _actor())
    return tx.imports.put_event.call_args.args[0].resolution["business"]


def _typed(monkeypatch, request: CaptureNote, own: str | None) -> tuple[dict, SimpleNamespace]:  # noqa: ANN001
    """One typed note on a Business whose RNC is ``own``; the saved resolution
    and the transaction it ran in."""

    tx = _tx(own)
    tx.connection = SimpleNamespace(transaction=nullcontext)
    tx.authorization = SimpleNamespace(
        provenance=_actor().model_copy(update={"actor_kind": "member"})
    )

    @contextmanager
    def opened(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        yield tx

    monkeypatch.setattr(captures, "transaction", opened)
    monkeypatch.setattr(captures.plans, "receipt", lambda *args: None)
    monkeypatch.setattr(captures.plans, "start_receipt", lambda *args: None)
    monkeypatch.setattr(captures.plans, "finish_receipt", lambda tx, key, result: result)
    monkeypatch.setattr(sources, "record_source", lambda *args: uuid4())
    monkeypatch.setattr(sources, "attach", lambda *args: None)
    monkeypatch.setattr(mutations, "validate_facts", lambda *args: None)
    context = SimpleNamespace(
        owner_id=tx.context.owner_id,
        actor=SimpleNamespace(
            actor_kind="member", actor_id=uuid4(), space_id=tx.context.actor.space_id
        ),
    )
    outcome = captures.capture(SimpleNamespace(authority=None), context, request, "key")
    assert outcome.outcome == "applied", outcome
    return tx.imports.put_event.call_args.args[0].resolution["business"], tx


CASES = {
    "named_recibo": (
        lambda m: _read(m, named="recibo", printed=OWN, own=OWN),
        ("recibo", False),
    ),
    "named_venta": (
        lambda m: _read(m, named="venta", printed=OTHER, own=OWN),
        ("venta", False),
    ),
    "issuer_is_the_business": (
        lambda m: _read(m, named=None, printed=OWN, own=OWN),
        ("venta", True),
    ),
    "issuer_differs": (
        lambda m: _read(m, named=None, printed=OTHER, own=OWN),
        ("recibo", True),
    ),
    "qr_issuer_is_the_business": (
        lambda m: _read(m, named=None, printed=OTHER, own=QR_ISSUER, qr=True),
        ("venta", True),
    ),
    "qr_issuer_outranks_a_printed_own_rnc": (
        lambda m: _read(m, named=None, printed=OWN, own=OWN, qr=True),
        ("recibo", True),
    ),
    "typed_note": (
        lambda m: _typed(m, CaptureNote(text="Compra de clavos"), OWN)[0],
        ("recibo", False),
    ),
    "typed_venta": (
        lambda m: _typed(
            m, CaptureNote(text="Factura a cliente", document_type="venta"), OWN
        )[0],
        ("venta", False),
    ),
}


def _approved(saved: dict) -> FiscalRecord:
    """The draft as an approval records it: a kind the type admits."""

    facts = BusinessFacts.model_validate(saved["facts"])
    document_type = saved["document_type"]
    kind = (
        facts.kind.value
        if isinstance(facts.kind, Known)
        else types.TYPE_KINDS[document_type][0]
    )
    return FiscalRecord(
        str(uuid4()),
        1,
        str(uuid4()),
        2,
        DAY,
        "118.00",
        "DOP",
        kind,
        document_type,
        facts,
        None,
        (str(uuid4()),),
    )


def _recorded(record: FiscalRecord) -> RecordedRecord:
    return RecordedRecord(
        row=ReportRow(
            activity_id=record.activity_id,
            revision=1,
            occurred_on=DAY,
            kind=record.kind,
            currency="DOP",
            amount_minor=11800,
            effect="known",
            dependency_fingerprints=("approved",),
        ),
        activity_json=json.dumps(
            {"kind": record.kind, "amount": "118.00", "legs": [], "source_id": None}
        ),
        approved=record,
        settlement=None,
        sources=(),
    )


def _draft_state(saved: dict, record: FiscalRecord) -> DraftState:
    now = datetime.now(timezone.utc)
    event = ImportEvent(
        record.draft_id,
        str(uuid4()),
        "accepted",
        "transaction",
        None,
        None,
        None,
        (),
        {"business": saved},
        record.activity_id,
        "accepted-key",
        now,
        now,
        2,
    )
    return DraftState(event, record.facts, record, (), None, (), "fingerprint")


def _export_form(record: FiscalRecord) -> str | None:
    """The one form the export puts the record on: as a line, or as the form
    whose issues hold it."""

    manifest, _rows = fiscal_manifest(
        (record,), rnc=OWN, business_name="PRÁCTICA Taller", **PERIOD
    )
    [item] = manifest["reconciliation"]
    if item["disposition"] in ("606", "607"):
        return item["disposition"]
    holding = [
        form
        for form in ("606", "607")
        if any(
            issue["activity_id"] == record.activity_id
            for issue in manifest["forms"][form]["issues"]
        )
    ]
    assert len(holding) <= 1, (item, holding)
    return holding[0] if holding else None


@pytest.mark.parametrize("name", list(CASES))
def test_every_reader_takes_the_direction_from_the_type(monkeypatch, name):
    """Bandeja (which declaration the dossier offers), Registros' family, the
    projection and the export agree on the form, from the type alone."""

    make, expected = CASES[name]
    saved = make(monkeypatch)
    assert (saved["document_type"], saved.get("document_type_detected", False)) == expected
    found = types.direction(saved["document_type"])
    facts = BusinessFacts.model_validate(saved["facts"])
    assert (
        takes_purchase_declaration(saved["document_type"], facts),
        takes_payment_split(saved["document_type"]),
    ) == (found.family == "purchase", found.family == "sale")
    record = _approved(saved)
    row = project(_recorded(record), _draft_state(saved, record), {}, OWN)
    assert row.family == found.family
    assert _export_form(record) == found.form


@pytest.mark.parametrize(
    "name",
    ["issuer_is_the_business", "issuer_differs", "typed_note", "typed_venta"],
)
def test_an_approved_record_routes_by_its_type_with_no_draft_in_hand(monkeypatch, name):
    make, (document_type, _detected) = CASES[name]
    record = _approved(make(monkeypatch))
    assert project(_recorded(record), None, {}, OWN).family == types.direction(
        document_type
    ).family


@pytest.mark.parametrize(
    "make",
    [
        lambda m: _read(m, named=None, printed=None, own=OWN),
        lambda m: _read(m, named=None, printed=OTHER, own=None),
        lambda m: _typed(m, CaptureNote(text="Compra de clavos"), None)[0],
    ],
)
def test_a_defaulted_type_is_never_marked_detected(monkeypatch, make):
    saved = make(monkeypatch)
    assert (saved["document_type"], saved.get("document_type_detected", False)) == (
        "recibo",
        False,
    )


def test_typed_entry_reads_the_business_rnc(monkeypatch):
    """A typed Venta gets the same meaning an upload typed Venta gets: its
    facts pass through ``typed_facts`` with the Business's own number."""

    seen = []
    real = captures.typed_facts

    def spy(facts, document_type, source_ids, origin, business_tax_id):  # noqa: ANN001, ANN202
        seen.append(business_tax_id)
        return real(facts, document_type, source_ids, origin, business_tax_id)

    monkeypatch.setattr(captures, "typed_facts", spy)
    saved, tx = _typed(
        monkeypatch, CaptureNote(text="Factura a cliente", document_type="venta"), OWN
    )
    assert seen == [OWN]
    assert any("business_rnc" in call.args[0] for call in tx.rows.call_args_list)
    assert saved["facts"]["kind"]["value"] == "income"


def _practice(record_id: str) -> FiscalRecord:
    index = ["P01", "P02", "P03", "P04", "S01", "S02"].index(record_id)
    return practice_records()[index]


def _forms(*records: FiscalRecord) -> dict:
    manifest, _rows = fiscal_manifest(
        records, rnc="199990013", business_name="Taller Ensayo", **PERIOD
    )
    return manifest


def _issue_codes(manifest: dict, form: str) -> set[str]:
    return {issue["code"] for issue in manifest["forms"][form]["issues"]}


def test_a_declaration_of_the_other_form_is_held_on_the_types_form():
    """A Venta holding 606 data has no 607 declaration: the 607 holds it, the
    606 never carries it."""

    manifest = _forms(replace(_practice("P01"), document_type="venta", kind="income"))
    [item] = manifest["reconciliation"]
    assert (item["disposition"], item["reason"]) == (
        "needs_review",
        "fiscal_declaration_missing",
    )
    assert _issue_codes(manifest, "607") == {"fiscal_declaration_missing"}
    assert (manifest["forms"]["606"]["status"], _issue_codes(manifest, "606")) == (
        "no_operations",
        set(),
    )


def test_a_kind_the_type_does_not_admit_is_held_as_a_direction_conflict():
    """A receipt recorded as income before the type owned the kind stays on
    the 606, held, and never reaches the 607."""

    manifest = _forms(replace(_practice("P01"), kind="income"))
    [item] = manifest["reconciliation"]
    assert (item["disposition"], item["reason"]) == (
        "needs_review",
        "fiscal_direction_conflict",
    )
    assert "fiscal_direction_conflict" in _issue_codes(manifest, "606")
    assert manifest["forms"]["607"]["status"] == "no_operations"


def test_money_with_no_document_is_on_neither_form():
    transfer = replace(
        _practice("P01"),
        kind="transfer",
        document_type=None,
        declaration=None,
        facts=BusinessFacts(),
    )
    manifest = _forms(transfer)
    [item] = manifest["reconciliation"]
    assert (item["disposition"], item["reason"]) == (
        "excluded",
        "non_fiscal_money_movement",
    )
    assert manifest["issues"] == []


def test_a_credit_note_keeps_its_types_family_and_the_link_sets_the_adjustment():
    """A supplier's credit note is a purchase whether or not the purchase it
    returns is linked; only the adjustment is unknown until then."""

    credit = _practice("P04")
    original = _practice("P01")
    unlinked = project(_recorded(credit), None, {}, "199990013")
    assert (unlinked.family, unlinked.adjustment_effect) == ("purchase", "unknown")
    linked = project(
        _recorded(credit), None, {original.activity_id: original}, "199990013"
    )
    assert (linked.family, linked.adjustment_effect) == ("purchase", "known")


def test_month_close_reads_the_role_from_the_type():
    def activity(identifier: str, kind: str) -> dict:
        return {
            "activity_id": identifier,
            "kind": kind,
            "amount_minor": 11800,
            "currency": "DOP",
            "occurred_at": "2026-09-10T12:00:00-04:00",
            "time_zone": "America/Santo_Domingo",
        }

    def resolution(identifier: str, document_type: str) -> dict:
        return {
            "activity_id": identifier,
            "resolution": {
                "business": {
                    "schema_version": 1,
                    "document_type": document_type,
                    "facts": BusinessFacts().model_dump(mode="json"),
                }
            },
        }

    documents = project_documents(
        [
            activity("sale", "income"),
            activity("legacy", "income"),
            activity("bought", "expense"),
            activity("undrafted-sale", "income"),
        ],
        [resolution("sale", "venta"), resolution("legacy", "recibo")],
        {},
        "space-a",
    )
    assert {item.activity_id: item.role for item in documents} == {
        "sale": "invoice",
        "legacy": "receipt",
        "bought": "receipt",
        "undrafted-sale": "invoice",
    }
