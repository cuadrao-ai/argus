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
from argus.domain.business.actions import approval, captures, mutations, sources
from argus.domain.business.actions import dossier as dossier_actions
from argus.domain.business.actions.retype import recheck_open_drafts
from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.actions import CaptureNote
from argus.domain.business.contracts.dgii import (
    FiscalReview,
    PurchaseReview,
    SalePaymentSplit,
)
from argus.domain.business.contracts.facts import BusinessFacts, BusinessResolution, Known
from argus.domain.business.dgii_export import fiscal_manifest
from argus.domain.business.dgii_validation import FiscalRecord
from argus.domain.business.month_close import project_documents
from argus.domain.business.purchase_review import (
    apply_payment_split,
    apply_purchase,
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

from tests.business.test_document_type_direction import (
    PURCHASE_NCF,
    _event,
    _facts,
    _review,
)
from tests.business.test_venta import _actor, _draft
from tests.dgii.test_packet import practice_records
from tests.dgii_qr_support import RNC as QR_ISSUER
from tests.dgii_qr_support import URL

OWN = "131000002"
OTHER = "101000007"
DAY = date(2026, 9, 3)
PERIOD = dict(
    start=date(2026, 9, 1), end=date(2026, 9, 30), captured_on=date(2026, 10, 18)
)


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
        # No Business RNC to compare with: a receipt the rule suggests,
        # whatever is printed, typed again once the RNC arrives.
        (None, OTHER, None, ("recibo", False, True)),
        (None, "RNC 131000002", OWN, ("recibo", False)),
        (None, None, None, ("recibo", False, True)),
        # A named type is never the rule's.
        ("venta", None, None, ("venta", False)),
    ],
)
def test_one_rule_names_the_type_and_whether_the_read_chose_it(
    named, issuer, own, expected
):
    found = types.resolved_document_type(named, issuer, own)
    assert (found.document_type, found.detected, found.suggested) == (*expected, False)[
        :3
    ]


@pytest.mark.parametrize(
    "document_type,family,form", [("recibo", "purchase", "606"), ("venta", "sale", "607")]
)
def test_each_type_is_one_family_on_one_form(document_type, family, form):
    found = types.direction(document_type)
    assert (found.family, found.form) == (family, form)


@pytest.mark.parametrize(
    "kind,document_type",
    [
        ("expense", "recibo"),
        ("refund", "recibo"),
        ("income", "venta"),
        ("transfer", None),
    ],
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


def _typed(
    monkeypatch, request: CaptureNote, own: str | None
) -> tuple[dict, SimpleNamespace]:  # noqa: ANN001
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
    "suggested_with_no_business_rnc": (
        lambda m: _read(m, named=None, printed=OTHER, own=None),
        ("recibo", False),
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
    assert (
        saved["document_type"],
        saved.get("document_type_detected", False),
    ) == expected
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
    assert (
        project(_recorded(record), None, {}, OWN).family
        == types.direction(document_type).family
    )


@pytest.mark.parametrize(
    "make",
    [
        lambda m: _read(m, named=None, printed=None, own=OWN),
        lambda m: _typed(m, CaptureNote(text="Compra de clavos"), OWN)[0],
    ],
)
def test_a_defaulted_type_is_never_marked_detected(monkeypatch, make):
    saved = make(monkeypatch)
    assert (saved["document_type"], saved.get("document_type_detected", False)) == (
        "recibo",
        False,
    )


SUGGESTED_CASES = {
    "read_with_no_business_rnc": lambda m: _read(m, named=None, printed=OTHER, own=None),
    "own_rnc_printed_with_no_business_rnc": lambda m: _read(
        m, named=None, printed=OWN, own=None
    ),
    "typed_note_with_no_business_rnc": lambda m: _typed(
        m, CaptureNote(text="Compra de clavos"), None
    )[0],
}


def _resolved(saved: dict) -> tuple:
    return (
        saved["document_type"],
        saved.get("document_type_detected", False),
        saved.get("document_type_suggested", False),
    )


@pytest.mark.parametrize("name", list(SUGGESTED_CASES))
def test_with_no_business_rnc_and_no_named_type_the_rule_suggests_a_receipt(
    monkeypatch, name
):
    """A receipt the rule may type again: not the read's choice, yet shown as
    one on the wire so the Bandeja offers the switch to Venta. Approval and
    the 606 editor work as on any receipt."""

    saved = SUGGESTED_CASES[name](monkeypatch)
    assert _resolved(saved) == ("recibo", False, True)
    resolution = BusinessResolution.model_validate(saved)
    assert resolution.rule_chose_type() is True
    assert takes_purchase_declaration("recibo", resolution.facts) is True
    event = _event("recibo", resolution.facts)
    event.resolution["business"] = saved
    assert _workflow_blockers(monkeypatch, event) == []


@pytest.mark.parametrize(
    "request_body,expected",
    [
        (CaptureNote(text="Factura a cliente", document_type="venta"), "venta"),
        (CaptureNote(text="Clavos", document_type="recibo"), "recibo"),
        (
            CaptureNote(
                text="Clavos", purchase={"amount": "118.00", "occurred_on": "2026-09-03"}
            ),
            "recibo",
        ),
    ],
)
def test_a_named_type_or_a_typed_purchase_is_never_the_rules(
    monkeypatch, request_body, expected
):
    saved = _typed(monkeypatch, request_body, None)[0]
    assert _resolved(saved) == (expected, False, False)
    assert BusinessResolution.model_validate(saved).rule_chose_type() is False


def _suggested_event(printed: str | None = OTHER) -> ImportEvent:
    """An open draft read with no Business RNC: the suggested receipt, a kind
    as read, and the RNC the read printed, if any."""

    source = uuid4()
    data = {"kind": Known(value="expense", origin="extracted", source_ids=(source,))}
    if printed is not None:
        data["fiscal"] = {
            "rnc": Known(value=printed, origin="extracted", source_ids=(source,)),
            "ncf": Known(value=PURCHASE_NCF, origin="extracted", source_ids=(source,)),
        }
    event = _event("recibo", BusinessFacts.model_validate(data))
    event.resolution["business"].update(
        document_type_detected=False, document_type_suggested=True
    )
    return event


def _workflow_blockers(monkeypatch, event: ImportEvent) -> list[str]:  # noqa: ANN001
    monkeypatch.setattr(dossier_actions, "blockers", lambda *args: [])
    monkeypatch.setattr(dossier_actions, "pending_duplicates", lambda *args: {})
    facts = BusinessFacts.model_validate(event.resolution["business"]["facts"])
    blocked, _ids = dossier_actions.workflow_blockers(_tx(None), event, facts, (), ())
    return [blocker.code for blocker in blocked]


@pytest.mark.parametrize(
    "pick,sale",
    [
        ({"document_type": "venta"}, True),
        ({"document_type": "recibo"}, False),
        ({"kind": "income"}, True),
    ],
)
def test_a_person_picks_the_type_of_a_suggested_receipt_by_hand(monkeypatch, pick, sale):
    """The pick is a named type: it wins, the kind follows it, the matching
    form's editor opens, and the rule no longer owns the draft."""

    saved = _review(
        monkeypatch,
        _suggested_event(),
        pick.get("kind"),
        **{key: value for key, value in pick.items() if key != "kind"},
    )
    document_type = saved["document_type"]
    assert _resolved(saved) == ("venta" if sale else "recibo", False, False)
    facts = BusinessFacts.model_validate(saved["facts"])
    assert facts.kind.value == ("income" if sale else "expense")
    assert takes_payment_split(document_type) is sale
    assert takes_purchase_declaration(document_type, facts) is not sale


MEMBER = _actor().model_copy(update={"actor_kind": "member"})


def _recheck(
    monkeypatch,  # noqa: ANN001
    own: str | None,
    *events: ImportEvent,
) -> tuple[int, dict[str, dict]]:
    """The rule run again over ``events`` as the open drafts of a Business
    whose RNC is now ``own``: how many changed, and each saved resolution."""

    monkeypatch.setattr(sources, "attach", lambda *args: None)
    monkeypatch.setattr(mutations, "validate_facts", lambda *args: None)
    tx = _tx(own)
    tx.imports.events = lambda states: list(events) if states == ("open",) else []
    changed = recheck_open_drafts(tx, MEMBER, (uuid4(),))
    saved = {
        call.args[0].id: call.args[0].resolution["business"]
        for call in tx.imports.put_event.call_args_list
    }
    return changed, saved


def _typed_saved(saved: dict) -> tuple:
    return (*_resolved(saved), saved["facts"]["kind"]["value"])


def test_adding_the_business_rnc_types_the_open_drafts_the_rule_owns_again(monkeypatch):
    """A suggested receipt whose issuer is the Business becomes a Venta, one
    whose issuer differs a detected receipt, one with no issuer the default
    receipt; a type a person named, or the rule already defaulted, stays."""

    own_issuer = _suggested_event(OWN)
    other_issuer = _suggested_event(OTHER)
    no_issuer = _suggested_event(None)
    named = _event("venta", _facts(PURCHASE_NCF, kind="income"))
    named.resolution["business"]["document_type_detected"] = False
    defaulted = _event("recibo", _facts(PURCHASE_NCF, kind="expense"))
    defaulted.resolution["business"]["document_type_detected"] = False
    changed, saved = _recheck(
        monkeypatch, OWN, own_issuer, other_issuer, no_issuer, named, defaulted
    )
    assert changed == 3
    assert {key: _typed_saved(value) for key, value in saved.items()} == {
        own_issuer.id: ("venta", True, False, "income"),
        other_issuer.id: ("recibo", True, False, "expense"),
        no_issuer.id: ("recibo", False, False, "expense"),
    }


def test_changing_the_business_rnc_re_reads_a_detected_type_and_removing_it_suggests_again(
    monkeypatch,
):
    detected = _suggested_event(OWN)
    detected.resolution["business"].update(
        document_type_detected=True, document_type_suggested=False
    )
    changed, saved = _recheck(monkeypatch, OWN, detected)
    assert (changed, _typed_saved(saved[detected.id])) == (
        1,
        ("venta", True, False, "income"),
    )

    sold = _event("venta", _facts(PURCHASE_NCF, kind="income"))
    changed, saved = _recheck(monkeypatch, None, sold)
    assert (changed, _typed_saved(saved[sold.id])) == (
        1,
        ("recibo", False, True, "expense"),
    )


def test_a_profile_change_types_open_drafts_again_only_when_the_number_changes(
    monkeypatch,
):
    """The Business RNC the rule compares with changed: the open drafts it
    owns are typed again in the same transaction, sourced to the change. A
    name-only change leaves them alone."""

    from contextlib import contextmanager

    from argus.domain.business import fiscal_profile

    waiting = _suggested_event(OWN)
    tx = _tx(OWN)
    tx.imports.events = lambda states: [waiting] if states == ("open",) else []
    tx.authorization = SimpleNamespace(provenance=MEMBER, permissions=("manage",))
    rows = {
        "select name": [
            {"name": "Taller", "business_rnc": None, "business_tax_id_type": None}
        ],
        "business_rnc from": [{"business_rnc": OWN}],
    }
    tx.rows = Mock(
        side_effect=lambda sql, *args: next(
            (value for key, value in rows.items() if key in sql), []
        )
    )
    monkeypatch.setattr(fiscal_profile.plans, "receipt", lambda *args: None)
    monkeypatch.setattr(fiscal_profile.plans, "start_receipt", lambda *args: None)
    monkeypatch.setattr(fiscal_profile.plans, "finish_receipt", lambda *args: None)
    monkeypatch.setattr(fiscal_profile, "read_profile", lambda *args: {})
    monkeypatch.setattr(sources, "record_source", lambda *args: uuid4())
    monkeypatch.setattr(sources, "attach", lambda *args: None)
    monkeypatch.setattr(mutations, "validate_facts", lambda *args: None)

    @contextmanager
    def opened(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        yield tx

    monkeypatch.setattr(fiscal_profile, "transaction", opened)
    context = SimpleNamespace(
        actor=SimpleNamespace(actor_kind="member", actor_id=uuid4(), space_id=uuid4())
    )
    renamed = fiscal_profile.FiscalProfileChange(
        name="Taller Nuevo", previous_name="Taller", tax_id=None, previous_tax_id=None
    )
    fiscal_profile.set_profile(None, context, renamed, "key-1")
    assert tx.imports.put_event.call_args_list == []

    numbered = fiscal_profile.FiscalProfileChange(
        name="Taller",
        previous_name="Taller",
        tax_id={"type": "rnc", "value": OWN},
        previous_tax_id=None,
    )
    fiscal_profile.set_profile(None, context, numbered, "key-2")
    [saved] = [
        call.args[0].resolution["business"]
        for call in tx.imports.put_event.call_args_list
    ]
    assert _typed_saved(saved) == ("venta", True, False, "income")


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


STRAY_606 = apply_purchase(
    None, PurchaseReview(category="09", payment_method="01")
).model_dump(mode="json")
STRAY_607 = apply_payment_split(None, SalePaymentSplit(cash="118.00")).model_dump(
    mode="json"
)


def _holding(document_type: str, kind: str, declaration: dict) -> ImportEvent:
    event = _event(document_type, _facts(PURCHASE_NCF, kind=kind))
    event.resolution["business"]["dgii"] = declaration
    return event


@pytest.mark.parametrize(
    "document_type,kind,stray,write,form",
    [
        (
            "venta",
            "income",
            STRAY_606,
            {"payment_split": SalePaymentSplit(bank="118.00")},
            "607",
        ),
        (
            "recibo",
            "expense",
            STRAY_607,
            {"purchase": PurchaseReview(category="02")},
            "606",
        ),
    ],
)
def test_an_enabled_editor_replaces_a_declaration_saved_for_the_other_form(
    monkeypatch, document_type, kind, stray, write, form
):
    """A declaration saved for the other form is no declaration of the
    record: the type's own editor saves and starts its own form."""

    saved = _review(monkeypatch, _holding(document_type, kind, stray), None, **write)
    assert saved["dgii"]["form"] == form
    if form == "607":
        assert (saved["dgii"]["bank"], saved["dgii"].get("category")) == ("118.00", None)
    else:
        assert (saved["dgii"]["category"], saved["dgii"].get("bank")) == ("02", None)


@pytest.mark.parametrize(
    "document_type,kind,stray",
    [("venta", "income", STRAY_606), ("recibo", "expense", STRAY_607)],
)
def test_a_reviewed_declaration_of_the_other_form_is_refused(
    monkeypatch, document_type, kind, stray
):
    review = FiscalReview.model_validate(
        {
            "fiscal": {"rnc": OTHER, "ncf": PURCHASE_NCF, "itbis": "18.00"},
            "declaration": stray,
        }
    )
    event = _event(document_type, _facts(PURCHASE_NCF, kind=kind))
    with pytest.raises(ActionError) as refused:
        _review(monkeypatch, event, None, fiscal_review=review)
    assert refused.value.code == "fiscal_direction_unsupported"


def test_an_expense_approval_writes_its_606_over_a_stray_607():
    source = uuid4()
    facts = BusinessFacts.model_validate(
        {
            "kind": Known(value="expense", origin="member_set", source_ids=(source,)),
            "fiscal": {
                "rnc": Known(value=OTHER, origin="extracted", source_ids=(source,)),
                "ncf": Known(
                    value=PURCHASE_NCF, origin="extracted", source_ids=(source,)
                ),
            },
        }
    )
    event = _holding("recibo", "expense", STRAY_607)
    written = approval._approval_declaration(_tx(OWN), event, facts, None)
    assert written is not None and written.form == "606"
