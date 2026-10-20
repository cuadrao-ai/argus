"""One class for the two prepare_attachment rules that have to stay together.

A retry reads the provider again only for an unfinished saved read.
Unreadable, no-receipt and fiscal-bill reads replay or stay closed.
An NCF due notice books one expense marked Factura por pagar, and the
same record becomes Factura pagada when that bill is paid.
"""

from __future__ import annotations

from unittest.mock import Mock
from uuid import uuid4

import pytest
from argus.domain.business.actions import mutations, sources
from argus.domain.business.contracts.actions import ExistingDraft
from argus.domain.business.contracts.facts import BusinessResolution
from argus.domain.ingestion.documents.extractor import batch_from_result
from argus.domain.ingestion.documents.models import DocumentDraft, ExtractionResult

from tests.business.test_business_handoff_retry import (
    test_a_retry_rereads_only_a_saved_read_that_cannot_finish,
)
from tests.ingestion.test_business_document_bridge import (  # noqa: F401
    document_bridge,
    reading_on,
)
from tests.test_business_attachment_preparation import checked  # noqa: F401
from tests.test_business_multi_purchase import _batch, _prepared, _row


def _due_notice(draft: DocumentDraft, payment_status: str):
    notice = {
        "page": 1,
        "row": 1,
        "evidence": "due_notice",
        "amount": "1500.00",
        "currency": "DOP",
        "occurred_on": "2026-10-01",
        "direction": "unknown",
        "kind_hint": "unknown",
        "merchant": "Servicios del Norte",
    }
    result = ExtractionResult.model_validate(
        dict(
            complete=True,
            readable=True,
            pages_read=[1],
            observations=[notice],
            receipt=dict(
                merchant="Servicios del Norte",
                occurred_on="2026-10-01",
                currency="DOP",
                total="1500.00",
                ncf="B0100000001",
                payment_status=payment_status,
            ),
        )
    )
    return batch_from_result(
        result, draft.sha256, draft.connection_id, draft.created_at, 1
    )


class TestNcfDueNoticeAndRetry:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("kind", "attention", "preparable", "extracts_again"),
        [
            ("incomplete", "interrupted", True, False),
            ("unreadable", "unreadable", False, False),
            ("no_receipt", "not_a_receipt", False, False),
            ("ncf_bill", "interrupted", True, False),
        ],
    )
    async def test_only_an_unfinished_saved_read_is_read_again(
        self,
        document_bridge,  # noqa: F811
        kind: str,
        attention: str,
        preparable: bool,
        extracts_again: bool,
    ):
        await test_a_retry_rereads_only_a_saved_read_that_cannot_finish(
            document_bridge, kind, attention, preparable, extracts_again
        )

    def test_an_ncf_due_notice_is_one_gasto_that_is_marked_paid_in_place(
        self,
        checked,  # noqa: F811
        monkeypatch,  # noqa: ANN001
    ) -> None:
        _, tx, binding, row = checked
        draft = DocumentDraft.model_validate(row["draft"])
        created = {"count": 0}
        real_new = mutations.new_candidate

        def counting(*args):  # noqa: ANN002
            created["count"] += 1
            return real_new(*args)

        held: dict[str, object] = {}

        def put_event(event):  # noqa: ANN001
            held["event"] = event

        monkeypatch.setattr(mutations, "new_candidate", counting)
        monkeypatch.setattr(sources, "record_source", lambda *args: uuid4())
        monkeypatch.setattr(sources, "attach", lambda *args: None)
        monkeypatch.setattr(mutations, "validate_facts", lambda *args: None)
        tx.imports = Mock()
        tx.imports.put_event.side_effect = put_event
        tx.imports.event.side_effect = lambda _draft_id: held["event"]
        tx.rows = Mock(return_value=[])
        tx.context = Mock(actor=Mock(space_id=binding.space_id))

        unpaid = _due_notice(draft, "pending")
        mutations.prepare_attachment(tx, None, unpaid, draft, binding.actor)
        first = held["event"]
        first_resolution = BusinessResolution.model_validate(
            first.resolution["business"]
        )
        assert first_resolution.bill_mark == "Factura por pagar"
        assert first_resolution.facts.kind.value == "expense"
        assert first_resolution.facts.amount.value in ("1500.00", "1500")
        assert first_resolution.facts.counterparty.value == "Servicios del Norte"

        paid = _due_notice(draft, "paid")
        mutations.prepare_attachment(
            tx,
            ExistingDraft(draft_id=first.id, version=first.version),
            paid,
            draft,
            binding.actor,
        )
        second = held["event"]
        second_resolution = BusinessResolution.model_validate(
            second.resolution["business"]
        )
        assert second.id == first.id
        assert second.version == first.version + 1
        assert created["count"] == 1
        assert second_resolution.bill_mark == "Factura pagada"
        assert second_resolution.facts.kind.value == "expense"
        assert second_resolution.facts.amount.value == first_resolution.facts.amount.value

    def test_a_paid_purchase_with_an_ncf_is_not_marked_as_a_due_bill(
        self,
        checked,  # noqa: F811
        monkeypatch,  # noqa: ANN001
    ) -> None:
        _, _, _, row = checked
        draft = DocumentDraft.model_validate(row["draft"])
        batch = _batch(
            draft,
            [_row("250.50", "Colmado La Esquina", "2026-10-11")],
            "250.50",
        )
        batch = batch.model_copy(
            update={
                "receipt": batch.receipt.model_copy(update={"ncf": "B0100000002"})
            }
        )
        _, resolution, _ = _prepared(checked, monkeypatch, batch)
        assert resolution.facts.kind.value == "expense"
        assert resolution.bill_mark is None
