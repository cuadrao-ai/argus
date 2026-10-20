"""The document type a read sets and a person changes: who wins, what the
type means for the kind, the bill mark and the declaration."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from argus.domain.business.actions import mutations, sources
from argus.domain.business.contracts.actions import ExistingDraft
from argus.domain.business.contracts.facts import BusinessFacts, Known
from argus.domain.business.document_type import detected_document_type
from argus.domain.ingestion.documents.dgii_qr import parse_dgii_url
from argus.domain.ingestion.documents.models import ExtractionBatch, ReceiptDetails
from argus.domain.ingestion.reconcile.model import ImportEvent

from tests.business.test_venta import _actor, _draft
from tests.dgii_qr_support import RNC as QR_ISSUER
from tests.dgii_qr_support import URL

OWN = "131000002"
OTHER = "101000007"


@pytest.mark.parametrize(
    "issuer,own,expected",
    [
        (OWN, OWN, "venta"),
        ("1-31-00000-2", OWN, "venta"),
        ("131 00000 2", "1-31-00000-2", "venta"),
        ("001-0000000-1", "00100000001", "venta"),
        (OTHER, OWN, "recibo"),
        (OWN, None, "recibo"),
        (None, OWN, "recibo"),
        (None, None, "recibo"),
        ("RNC 131000002", OWN, "recibo"),
        ("1310000021", "1310000021", "recibo"),
        ("000000000", "000000000", "recibo"),
    ],
)
def test_only_the_business_own_identity_reads_as_a_venta(issuer, own, expected):
    assert detected_document_type(issuer, own) == expected


def _batch(rnc: str | None, qr: bool = False) -> ExtractionBatch:
    return ExtractionBatch(
        complete=True,
        readable=True,
        candidates=(),
        receipt=ReceiptDetails(total="118.00", currency="DOP", rnc=rnc),
        dgii_qr=parse_dgii_url(URL) if qr else None,
    )


def _event(business: dict | None = None) -> ImportEvent:
    now = datetime.now(timezone.utc)
    return ImportEvent(
        str(uuid4()),
        str(uuid4()),
        "open",
        "transaction",
        None,
        None,
        None,
        (),
        {} if business is None else {"business": business},
        None,
        None,
        now,
        now,
        2,
    )


def _tx(own: str | None):
    return SimpleNamespace(
        context=SimpleNamespace(actor=SimpleNamespace(space_id=uuid4())),
        rows=Mock(return_value=[{"business_rnc": own}]),
    )


@pytest.mark.parametrize(
    "named,printed,qr,previous,expected",
    [
        ("recibo", OWN, False, None, ("recibo", False)),
        ("venta", OTHER, False, None, ("venta", False)),
        (None, OWN, False, None, ("venta", True)),
        (None, OTHER, False, None, ("recibo", True)),
        (None, OTHER, True, None, ("venta", True)),
        (None, QR_ISSUER, True, None, ("venta", True)),
        (None, OWN, False, {"document_type": "recibo"}, ("recibo", False)),
        (
            None,
            OTHER,
            False,
            {"document_type": "venta", "document_type_detected": True},
            ("venta", True),
        ),
    ],
)
def test_the_named_type_wins_then_the_draft_then_the_issuer(
    named, printed, qr, previous, expected
):
    """The QR's issuer is the business here, whatever RNC the read printed."""

    own = QR_ISSUER if qr else OWN
    found = mutations._read_document_type(
        _tx(own), _event(previous), _draft(document_type=named), _batch(printed, qr)
    )
    assert found == expected


def test_the_issuer_from_the_qr_outranks_a_printed_own_rnc():
    found = mutations._read_document_type(
        _tx(OWN), _event(), _draft(), _batch(OWN, qr=True)
    )
    assert found == ("recibo", True)


def _known(value: str, source) -> dict:  # noqa: ANN001
    return Known(value=value, origin="extracted", source_ids=(source,)).model_dump(
        mode="json"
    )


SALE = {
    "form": "607",
    "id_type": "1",
    "modified_ncf": None,
    "selective_tax": "0.00",
    "other_taxes": "0.00",
    "legal_tip": "0.00",
    "income_type": "01",
    "withheld_on": None,
    "billed_amount": "100.00",
    "itbis_withheld_by_third_parties": "0.00",
    "itbis_perceived": "0.00",
    "income_withheld_by_third_parties": "0.00",
    "income_perceived": "0.00",
    "cash": "118.00",
    "card": "0.00",
    "bank": "0.00",
    "credit": "0.00",
    "gift": "0.00",
    "barter": "0.00",
    "other_payment": "0.00",
}


def _revised(  # noqa: ANN001
    monkeypatch, previous: dict, document_type: str, printed: str = OTHER
) -> dict:
    source = uuid4()
    facts = BusinessFacts.model_validate(
        {
            "kind": _known(previous["kind"], source),
            "fiscal": {"rnc": _known(printed, source)},
        }
    ).model_dump(mode="json")
    event = _event(
        {
            "schema_version": 1,
            "document_type": previous["document_type"],
            "document_type_detected": True,
            "facts": facts,
            "dgii": previous.get("dgii"),
            "bill_mark": previous.get("bill_mark"),
        }
    )
    actor = _actor().model_copy(update={"actor_kind": "member"})
    tx = SimpleNamespace(
        context=SimpleNamespace(
            owner_id=event.user_id, actor=SimpleNamespace(space_id=uuid4())
        ),
        imports=SimpleNamespace(put_event=Mock()),
        rows=Mock(return_value=[{"business_rnc": OWN}]),
    )
    monkeypatch.setattr(sources, "require_sources", lambda *args: None)
    monkeypatch.setattr(sources, "attach", lambda *args: None)
    monkeypatch.setattr(mutations, "validate_facts", lambda *args: None)
    monkeypatch.setattr(mutations, "_open_for_type", lambda *args: event)
    mutations.revise(
        tx,
        ExistingDraft(draft_id=event.id, version=event.version),
        None,
        (uuid4(),),
        actor,
        document_type=document_type,
    )
    return tx.imports.put_event.call_args.args[0].resolution["business"]


def test_a_venta_made_a_receipt_is_a_purchase_without_its_607_declaration(
    monkeypatch,
):
    saved = _revised(
        monkeypatch,
        {"kind": "income", "document_type": "venta", "dgii": SALE},
        "recibo",
    )
    assert (saved["document_type"], saved.get("document_type_detected", False)) == (
        "recibo",
        False,
    )
    assert (saved["facts"]["kind"]["value"], saved["facts"]["kind"]["origin"]) == (
        "expense",
        "member_set",
    )
    assert saved["facts"]["fiscal"]["rnc"]["value"] == OTHER
    assert saved["dgii"] is None


def test_a_receipt_made_a_venta_is_income_and_loses_the_payable_mark(monkeypatch):
    saved = _revised(
        monkeypatch,
        {
            "kind": "expense",
            "document_type": "recibo",
            "bill_mark": mutations.PAYABLE_BILL_MARK,
        },
        "venta",
    )
    assert saved["document_type"] == "venta"
    assert saved["facts"]["kind"]["value"] == "income"
    assert saved["bill_mark"] is None


def test_confirming_the_detected_type_keeps_the_facts_and_the_declaration(
    monkeypatch,
):
    saved = _revised(
        monkeypatch,
        {"kind": "income", "document_type": "venta", "dgii": SALE},
        "venta",
    )
    assert (saved["document_type"], saved.get("document_type_detected", False)) == (
        "venta",
        False,
    )
    assert saved["facts"]["kind"]["origin"] == "extracted"
    assert saved["dgii"]["form"] == "607"


@pytest.mark.parametrize(
    "capabilities,state,expected",
    [
        (("read", "prepare"), "open", True),
        (("read",), "open", False),
        (("read", "prepare"), "accepted", False),
    ],
)
def test_a_listed_receipt_type_is_editable_by_preparers_while_open(
    monkeypatch, capabilities, state, expected
):
    from argus.api import business_drafts
    from argus.domain.business.transactions import GrantImportStore

    draft = str(uuid4())
    business = {
        "schema_version": 1,
        "document_type": "venta",
        "document_type_detected": True,
        "facts": BusinessFacts().model_dump(mode="json"),
    }
    row = {
        "id": draft,
        "state": state,
        "version": 2,
        "attention": None,
        "activity_id": None,
        "resolution": {"business": business},
        "marks": {},
    }
    summary = {"id": str(uuid4()), "document_type": "recibo"}
    monkeypatch.setattr(
        "argus.api.business_receipt_activity.project",
        lambda context, views: [business_drafts.draft_overlay(summary, [row])],
    )
    context = SimpleNamespace(
        service=SimpleNamespace(
            imports=SimpleNamespace(store=Mock(spec=GrantImportStore))
        ),
        record_context=SimpleNamespace(capabilities=capabilities),
    )
    [view] = business_drafts.bridged(context, [summary])
    assert (view["document_type"], view["document_type_detected"]) == ("venta", True)
    assert view.get("document_type_editable") is expected


@pytest.mark.parametrize(
    "printed,kept", [(OTHER, True), (OWN, False), ("1-31-00000-2", False)]
)
def test_a_venta_never_names_the_business_as_its_client(monkeypatch, printed, kept):
    """The Business's own number on its invoice is the issuer, not the client."""

    saved = _revised(
        monkeypatch, {"kind": "expense", "document_type": "recibo"}, "venta", printed
    )
    rnc = saved["facts"]["fiscal"]["rnc"]
    assert (rnc["state"], rnc["value"]) == (
        ("known", printed) if kept else ("unknown", None)
    )
    back = _revised(
        monkeypatch, {"kind": "income", "document_type": "venta"}, "recibo", OWN
    )
    assert back["facts"]["fiscal"]["rnc"]["value"] == OWN
