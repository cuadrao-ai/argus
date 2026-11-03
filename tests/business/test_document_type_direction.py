"""The document type is the one answer to purchase or sale. A known kind is one
the type admits, on the read, a review, a chat and an approval: a Venta is
income, a receipt an expense or a refund."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from argus.domain.business import document_type as types
from argus.domain.business.actions import mutations, sources
from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.actions import ExistingDraft
from argus.domain.business.contracts.facts import BusinessFactPatch, BusinessFacts, Known
from argus.domain.ingestion.contract import ImportCandidate, SourceRef
from argus.domain.ingestion.documents.models import ExtractionBatch, ReceiptDetails
from argus.domain.ingestion.reconcile.model import ImportEvent

from tests.business.test_venta import _actor, _draft, _prepare_batch

PURCHASE_NCF = "B0100000001"
CREDIT_NCF = "B0400000001"


def _facts(ncf: str | None = None, kind: str | None = None) -> BusinessFacts:
    source = uuid4()
    data = {}
    if ncf is not None:
        data["fiscal"] = {
            "ncf": Known(value=ncf, origin="extracted", source_ids=(source,))
        }
    if kind is not None:
        data["kind"] = Known(value=kind, origin="extracted", source_ids=(source,))
    return BusinessFacts.model_validate(data)


@pytest.mark.parametrize(
    "document_type,kind,admitted",
    [
        ("venta", "income", True),
        ("venta", "expense", False),
        ("recibo", "expense", True),
        ("recibo", "refund", True),
        ("recibo", "income", False),
        ("recibo", "transfer", False),
    ],
)
def test_each_type_admits_its_own_kinds(document_type, kind, admitted):
    assert types.kind_disagrees(document_type, _facts(kind=kind)) is not admitted
    assert types.kind_disagrees(document_type, _facts()) is False


def _read(document_type, kind_hint, ncf, *, uncertain=False):  # noqa: ANN001, ANN202
    draft = _draft(document_type=document_type)
    candidate = ImportCandidate(
        source=SourceRef(
            source="statement",
            connection_id=draft.connection_id,
            external_id=draft.sha256,
            observed_at=draft.created_at,
        ),
        evidence="transaction",
        direction="unknown" if uncertain else "outflow",
        amount="118.00",
        currency="DOP",
        kind_hint=kind_hint,
        merchant="PRÁCTICA Ferretería",
        uncertain=frozenset({"direction"}) if uncertain else frozenset(),
    )
    return ExtractionBatch(
        complete=True,
        readable=True,
        candidates=(candidate,),
        receipt=ReceiptDetails(total="118.00", currency="DOP", ncf=ncf),
    ), draft


@pytest.mark.parametrize(
    "named,hint,ncf,expected",
    [
        ("recibo", "income", PURCHASE_NCF, "expense"),
        ("recibo", "transfer", PURCHASE_NCF, "expense"),
        ("recibo", "refund", CREDIT_NCF, "refund"),
        ("recibo", "expense", CREDIT_NCF, "expense"),
        ("venta", "expense", PURCHASE_NCF, "income"),
    ],
)
def test_a_read_kind_follows_the_type(monkeypatch, named, hint, ncf, expected):
    batch, draft = _read(named, hint, ncf)
    business = _prepare_batch(draft, batch, monkeypatch)
    assert business["document_type"] == named
    assert business["facts"]["kind"]["value"] == expected


def test_a_read_unsure_of_the_direction_leaves_the_kind_for_a_person(monkeypatch):
    batch, draft = _read(None, "unknown", PURCHASE_NCF, uncertain=True)
    business = _prepare_batch(draft, batch, monkeypatch)
    assert business["document_type"] == "recibo"
    assert business["facts"]["kind"]["state"] == "unknown"


def _event(document_type: str, facts: BusinessFacts) -> ImportEvent:
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
        {
            "business": {
                "schema_version": 1,
                "document_type": document_type,
                "document_type_detected": True,
                "facts": facts.model_dump(mode="json"),
            }
        },
        None,
        None,
        now,
        now,
        2,
    )


def _review(monkeypatch, event: ImportEvent | None, kind: str | None, **inputs) -> dict:  # noqa: ANN001
    actor = _actor().model_copy(update={"actor_kind": inputs.pop("actor", "member")})
    tx = SimpleNamespace(
        context=SimpleNamespace(
            owner_id=str(uuid4()), actor=SimpleNamespace(space_id=uuid4())
        ),
        imports=SimpleNamespace(put_event=Mock()),
        rows=Mock(
            side_effect=lambda sql, *args: [{"business_rnc": None}]
            if "business_rnc" in sql
            else []
        ),
    )
    monkeypatch.setattr(sources, "require_sources", lambda *args: None)
    monkeypatch.setattr(sources, "attach", lambda *args: None)
    monkeypatch.setattr(mutations, "validate_facts", lambda *args: None)
    if event is not None:
        monkeypatch.setattr(mutations, "event_at", lambda *args: event)
        monkeypatch.setattr(mutations, "_open_for_type", lambda *args: event)
    mutations.revise(
        tx,
        ExistingDraft(draft_id=event.id, version=event.version) if event else None,
        BusinessFactPatch.model_validate({"kind": {"state": "known", "value": kind}})
        if kind is not None
        else None,
        (uuid4(),),
        actor,
        **inputs,
    )
    return tx.imports.put_event.call_args.args[0].resolution["business"]


def _typed(saved: dict) -> tuple:
    return (
        saved["document_type"],
        saved.get("document_type_detected", False),
        saved["facts"]["kind"]["value"],
    )


@pytest.mark.parametrize(
    "document_type,stated,expected",
    [
        ("recibo", "income", "venta"),
        ("venta", "expense", "recibo"),
        ("recibo", "expense", "recibo"),
    ],
)
def test_a_kind_a_person_picks_sets_the_type(
    monkeypatch, document_type, stated, expected
):
    """The kind editor's Ingreso on a receipt makes it a Venta, the same as
    the Compra or Venta control."""

    event = _event(document_type, _facts(PURCHASE_NCF))
    saved = _review(monkeypatch, event, stated)
    assert _typed(saved) == (expected, False, stated)
    assert saved["facts"]["kind"]["origin"] == "member_set"


def test_a_chat_that_says_income_starts_a_venta(monkeypatch):
    saved = _review(monkeypatch, None, "income", actor="owner_via_agent")
    assert _typed(saved) == ("venta", False, "income")


@pytest.mark.parametrize(
    "stated,inputs",
    [
        ("transfer", {}),
        ("owner_contribution", {}),
        ("income", {"document_type": "recibo"}),
        ("expense", {"document_type": "venta"}),
        ("refund", {"document_type": "venta"}),
    ],
)
def test_a_kind_the_type_does_not_admit_is_refused(monkeypatch, stated, inputs):
    """A kind that is neither a purchase nor a sale, or a kind and a type that
    disagree in one request."""

    event = _event("recibo", _facts(PURCHASE_NCF))
    with pytest.raises(ActionError) as refused:
        _review(monkeypatch, event, stated, **inputs)
    assert refused.value.code == "activity_kind_unsupported"


@pytest.mark.parametrize("ncf", [CREDIT_NCF, PURCHASE_NCF, None])
def test_a_refund_is_a_receipt(monkeypatch, ncf):
    event = _event("venta", _facts(ncf, kind="income"))
    saved = _review(monkeypatch, event, "refund")
    assert _typed(saved) == ("recibo", False, "refund")


def test_confirming_a_receipt_answers_an_unknown_kind(monkeypatch):
    """One control: the Compra a person confirms is the expense."""

    event = _event("recibo", _facts(PURCHASE_NCF))
    saved = _review(monkeypatch, event, None, document_type="recibo")
    assert _typed(saved) == ("recibo", False, "expense")
