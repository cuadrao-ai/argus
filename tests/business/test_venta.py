"""A Venta is an already-issued invoice: income, the 607, and Por cobrar."""

from __future__ import annotations

from datetime import date, datetime, timezone
from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from argus.domain.business.actions import mutations, sources
from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.actions import ExistingDraft
from argus.domain.business.contracts.authority import ActorProvenance
from argus.domain.business.contracts.facts import (
    BusinessFactPatch,
    BusinessFacts,
    Known,
    KnownInput,
)
from argus.domain.business.document_type import parse_document_type, require_venta_kind
from argus.domain.business.month_close import formato_totals, project_documents, summarize
from argus.domain.ingestion.contract import ImportCandidate, SourceRef
from argus.domain.ingestion.documents.models import (
    DocumentDraft,
    ExtractionBatch,
    ReceiptDetails,
)
from argus.domain.ingestion.documents.service import owner_purchase
from argus.domain.ingestion.reconcile.model import ImportEvent

DAY = date(2026, 10, 5)
START = date(2026, 10, 1)
END = date(2026, 10, 31)


def _draft(**overrides) -> DocumentDraft:
    now = datetime.now(timezone.utc)
    data = b"issued invoice"
    values = dict(
        connection_id=str(uuid4()),
        filename="factura.pdf",
        media_type="application/pdf",
        sha256=sha256(data).hexdigest(),
        size_bytes=len(data),
        consent=True,
        created_at=now,
        updated_at=now,
    )
    values.update(overrides)
    return DocumentDraft(**values)


def _actor() -> ActorProvenance:
    return ActorProvenance(
        actor_id=uuid4(),
        actor_kind="extractor",
        display_name="Test",
        grant_id=uuid4(),
        issuer_id=uuid4(),
        issuer_display_name="Test owner",
    )


def _prepare(draft: DocumentDraft, receipt: ReceiptDetails, monkeypatch):
    actor = _actor()
    candidate = ImportCandidate(
        source=SourceRef(
            source="statement",
            connection_id=draft.connection_id,
            external_id=draft.sha256,
            observed_at=draft.created_at,
        ),
        evidence="transaction",
        direction="unknown",
        amount="118.00",
        currency="DOP",
        kind_hint="unknown",
        merchant="Cliente Norte",
        uncertain=frozenset({"direction"}),
    )
    batch = ExtractionBatch(
        complete=True,
        readable=True,
        candidates=(candidate,),
        receipt=receipt,
    )
    tx = SimpleNamespace(
        context=SimpleNamespace(
            owner_id=str(uuid4()), actor=SimpleNamespace(space_id=uuid4())
        ),
        imports=SimpleNamespace(put_event=Mock()),
        rows=Mock(return_value=[]),
    )
    monkeypatch.setattr(sources, "record_source", lambda *args: uuid4())
    monkeypatch.setattr(sources, "attach", lambda *args: None)
    mutations.prepare_attachment(tx, None, batch, draft, actor)
    saved = tx.imports.put_event.call_args.args[0]
    return saved.resolution["business"]


def _close(resolution: dict, *, status: str = "pendiente"):
    activity_id = "venta-1"
    documents = project_documents(
        [
            {
                "activity_id": activity_id,
                "kind": "income",
                "amount_minor": 11800,
                "currency": "DOP",
                "occurred_at": "2026-10-05T12:00:00-04:00",
                "time_zone": "America/Santo_Domingo",
            }
        ],
        [{"activity_id": activity_id, "resolution": {"business": resolution}}],
        {}
        if status == "pendiente"
        else {
            activity_id: {
                "status": status,
                "settled_on": DAY,
                "payment_method": "transferencia",
            }
        },
        "space-a",
    )
    return documents, summarize(documents, START, END)


def test_parse_accepts_the_two_capture_types():
    assert parse_document_type(None) == "recibo"
    assert parse_document_type("venta") == "venta"
    with pytest.raises(ValueError, match="document_type_invalid"):
        parse_document_type("invoice")


def test_a_hand_entered_venta_is_income():
    draft = _draft(document_type="venta")
    purchase = owner_purchase(draft, draft.created_at)
    assert (purchase.kind_hint, purchase.direction) == ("income", "inflow")
    receipt = owner_purchase(_draft(), draft.created_at)
    assert (receipt.kind_hint, receipt.direction) == ("expense", "outflow")


def test_a_venta_counts_in_income_the_607_and_por_cobrar_until_cobrado(monkeypatch):
    business = _prepare(
        _draft(document_type="venta"),
        ReceiptDetails(
            total="118.00",
            currency="DOP",
            rnc="131000001",
            ncf="B0100000001",
            itbis="18.00",
        ),
        monkeypatch,
    )
    assert business["document_type"] == "venta"
    kind = business["facts"]["kind"]
    assert (kind["state"], kind["value"], kind["origin"]) == (
        "known",
        "income",
        "owner_stated",
    )
    fiscal = business["facts"]["fiscal"]
    assert fiscal["rnc"]["value"] == "131000001"
    assert fiscal["ncf"]["value"] == "B0100000001"
    assert fiscal["itbis"]["state"] == "known"

    documents, summary = _close(business)
    block = summary["currencies"][0]
    formato = formato_totals(documents, START, END)["DOP"]
    assert block["income_before_itbis_minor"] == formato.income_before_itbis == 10000
    assert block["itbis_charged_minor"] == formato.itbis_charged == 1800
    assert summary["closed"] is True
    assert [item["activity_id"] for item in summary["cuentas_por_cobrar"]] == ["venta-1"]
    assert block["cuentas_por_cobrar_minor"] == 11800

    _, collected = _close(business, status="cobrado")
    assert collected["cuentas_por_cobrar"] == []
    assert collected["currencies"][0]["cuentas_por_cobrar_minor"] == 0
    assert collected["currencies"][0]["income_before_itbis_minor"] == 10000


@pytest.mark.parametrize(
    ("rnc", "ncf", "reason", "income"),
    [
        (None, "B0100000001", "missing_rnc", 10000),
        ("131000001", None, "missing_ncf", 0),
    ],
)
def test_a_venta_missing_rnc_or_ncf_blocks_close(monkeypatch, rnc, ncf, reason, income):
    business = _prepare(
        _draft(document_type="venta"),
        ReceiptDetails(total="118.00", currency="DOP", rnc=rnc, ncf=ncf, itbis="18.00"),
        monkeypatch,
    )
    _, summary = _close(business)
    assert summary["closed"] is False
    assert reason in {item["code"] for item in summary["reasons"]}
    assert summary["currencies"][0]["income_before_itbis_minor"] == income


def test_a_receipt_read_does_not_become_income(monkeypatch):
    business = _prepare(
        _draft(),
        ReceiptDetails(
            total="118.00", currency="DOP", rnc="131000001", ncf="B0100000001"
        ),
        monkeypatch,
    )
    assert business["document_type"] == "recibo"
    assert business["facts"]["kind"]["state"] == "unknown"


def test_a_venta_cannot_be_changed_into_an_expense(monkeypatch):
    actor = _actor().model_copy(update={"actor_kind": "member"})
    source_id = uuid4()
    now = datetime.now(timezone.utc)
    event = ImportEvent(
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
                "document_type": "venta",
                "facts": BusinessFacts(
                    kind=Known(
                        value="income",
                        origin="owner_stated",
                        source_ids=(source_id,),
                    )
                ).model_dump(mode="json"),
            }
        },
        None,
        None,
        now,
        now,
        1,
    )
    tx = SimpleNamespace(context=SimpleNamespace(owner_id=event.user_id, actor=actor))
    monkeypatch.setattr(sources, "require_sources", lambda *args: None)
    monkeypatch.setattr(mutations, "event_at", lambda *args: event)
    with pytest.raises(ActionError) as refused:
        mutations.revise(
            tx,
            ExistingDraft(draft_id=event.id, version=1),
            BusinessFactPatch(kind=KnownInput(value="expense")),
            (source_id,),
            actor,
        )
    assert refused.value.code == "activity_kind_unsupported"
    require_venta_kind("recibo", BusinessFacts())
