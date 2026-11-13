"""A Dominican receipt prints "RD$" or "US$", not an ISO code. The read keeps
the currency the receipt states: each marker that names exactly one currency
becomes its code where the model's text enters the reader, and the change is
logged. A bare "$" names pesos or dollars, so it stays as read."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import Mock
from uuid import uuid4

import pytest
from argus.domain.ingestion.documents.extractor import batch_from_result, priced_amounts
from argus.domain.ingestion.documents.models import (
    RECEIPT_PURCHASE_AMBIGUOUS,
    DocumentDraft,
    ExtractionResult,
    ReceiptDetails,
)
from loguru import logger

from tests.test_business_attachment_preparation import checked  # noqa: F401

NOW = datetime(2026, 11, 13, 15, 0, tzinfo=timezone.utc)


@pytest.fixture
def logged():
    records: list[dict] = []
    sink = logger.add(lambda message: records.append(message.record), level="INFO")
    yield records
    logger.remove(sink)


def _marker_logs(records: list[dict]) -> list[str]:
    return [r["message"] for r in records if "document_read_currency_marker" in r["message"]]


def _read(currency: str | None, *, row: bool = True, account: str | None = None):
    observation = dict(
        page=1,
        row=1,
        evidence="transaction",
        amount="1250.00",
        currency=currency,
        occurred_on="2026-11-10",
        direction="outflow",
        kind_hint="expense",
        merchant="Colmado La Esquina",
    )
    if account is not None:
        observation["account"] = {"currency": account}
    return ExtractionResult.model_validate(
        dict(
            complete=True,
            readable=True,
            pages_read=[1],
            observations=[observation] if row else [],
            receipt=dict(
                merchant="Colmado La Esquina",
                occurred_on="2026-11-10",
                currency=currency,
                total="1250.00",
                payment_status="paid",
            ),
        )
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("RD$", "DOP"),
        ("rd$", "DOP"),
        (" RD$ ", "DOP"),
        ("US$", "USD"),
        ("$", "$"),
        ("R$", "R$"),
        ("", ""),
    ],
)
def test_a_marker_naming_one_currency_is_read_as_its_code(logged, raw, expected):
    assert ReceiptDetails(currency=raw).currency == expected
    if expected == raw:
        assert _marker_logs(logged) == []
    else:
        assert _marker_logs(logged) == [
            f"document_read_currency_marker raw={raw!r} mapped={expected}"
        ]


def test_rows_and_account_hints_go_through_the_same_marker_owner(logged):
    result = _read("RD$", account="US$")

    observation = result.observations[0]
    assert (observation.currency, observation.account.currency) == ("DOP", "USD")
    assert result.receipt.currency == "DOP"
    assert len(_marker_logs(logged)) == 3


def test_an_rd_dollar_read_projects_one_dop_purchase():
    batch = batch_from_result(_read("RD$"), "a" * 64, "c1", NOW, 1)

    assert RECEIPT_PURCHASE_AMBIGUOUS not in [issue.code for issue in batch.issues]
    assert [candidate.currency for candidate in batch.candidates] == ["DOP"]
    assert {priced.currency for priced in priced_amounts(batch)} == {"DOP"}


@pytest.mark.parametrize("row", [True, False], ids=["purchase-row", "receipt-only"])
def test_a_non_fiscal_rd_dollar_receipt_becomes_a_dop_draft_from_the_read(
    checked, monkeypatch, row  # noqa: F811
):
    from argus.domain.business.actions import mutations, sources

    _, tx, binding, stored = checked
    draft = DocumentDraft.model_validate(stored["draft"])
    tx.context.owner_id = str(binding.owner_id)
    batch = batch_from_result(
        _read("RD$", row=row), draft.sha256, draft.connection_id, NOW, 1
    )
    source_id = uuid4()
    monkeypatch.setattr(sources, "record_source", lambda *args: source_id)
    save = Mock()
    monkeypatch.setattr(mutations, "save_revision", save)

    mutations.prepare_attachment(tx, None, batch, draft, binding.actor)

    currency = save.call_args.args[3].currency
    assert (currency.state, currency.value) == ("known", "DOP")
    assert currency.origin == "extracted"
    assert currency.source_ids == (source_id,)
