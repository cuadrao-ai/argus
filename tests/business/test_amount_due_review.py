"""A readable priced read becomes an unverified review draft.

Currency choice: an amount's own currency wins, and the account currency
on that same observation or candidate counts as its own. When the amount
names none, the one currency named anywhere else on the same read is used,
and only when every named currency agrees. No currency, or currencies that
disagree, leaves that amount unpriced. A credit that is only a negative
figure is not a positive amount, so the read stays not a receipt. Direction
is not a gate. Evidence labels are not a gate.

A candidate is the projection of its observation. It prices the read when
that observation did not already contribute a positive priced amount. The
prefilled amount is the greatest positive priced amount. Several priced
amounts stay on the draft as read purchases, which is the existing review
state, and the amount stays unverified. Nothing here approves the draft.

The five stored reads are statement-read batches: readable, complete, no
issues, no fiscal QR, and observations with matching candidates. Merchants,
hashes, and invoice numbers are synthetic. No model is called on replay.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import Mock
from uuid import uuid4

import pytest
from argus.domain.business.actions import mutations, sources
from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.facts import BusinessResolution
from argus.domain.business.receipts import compose
from argus.domain.ingestion.contract import AccountHint
from argus.domain.ingestion.documents.extractor import batch_from_result
from argus.domain.ingestion.documents.models import (
    DocumentDraft,
    ExtractionBatch,
    ExtractionResult,
)
from argus.domain.owner_scope import BusinessSpace

from tests.business.test_business_handoff_retry import reading_on
from tests.ingestion.test_business_document_bridge import document_bridge  # noqa: F401
from tests.test_business_attachment_preparation import checked  # noqa: F401

NOW = datetime(2026, 10, 18, 15, 0, tzinfo=timezone.utc)
MERCHANT = "Example Cloud Inc"


def _row(amount: str | None, *, currency: str | None, evidence: str, row: int) -> dict:
    return {
        "page": 1,
        "row": row,
        "evidence": evidence,
        "status": "posted",
        "amount": amount,
        "currency": currency,
        "occurred_on": "2026-10-18",
        "direction": "unknown" if evidence == "due_notice" else "outflow",
        "kind_hint": "unknown" if evidence == "due_notice" else "expense",
        "merchant": MERCHANT,
    }


def _stored(
    draft: DocumentDraft,
    rows: list[dict],
    *,
    receipt: dict | None,
    complete: bool = True,
    readable: bool = True,
) -> ExtractionBatch:
    """The batch the document store would hand back on a later prepare."""

    result = ExtractionResult.model_validate(
        {
            "complete": complete,
            "readable": readable,
            "pages_read": [1],
            "observations": rows,
            "receipt": receipt,
        }
    )
    batch = batch_from_result(result, draft.sha256, draft.connection_id, NOW, 1)
    return ExtractionBatch.model_validate_json(batch.model_dump_json())


def _notice(
    invoice: str,
    amount: str | None,
    *,
    evidence: str = "due_notice",
    currency: str | None = "USD",
    row: int = 1,
    status: str = "pending",
    occurred_on: str | None = None,
    account: dict | None = None,
    period_start: str | None = None,
    period_end: str | None = None,
) -> dict:
    """One synthetic observation in the stored statement-read shape."""

    payload = {
        "page": 1,
        "row": row,
        "evidence": evidence,
        "status": status,
        "amount": amount,
        "currency": currency,
        "direction": "outflow",
        "kind_hint": "expense",
        "merchant": MERCHANT,
        "description": invoice,
    }
    if occurred_on is not None:
        payload["occurred_on"] = occurred_on
    if account is not None:
        payload["account"] = account
    if period_start is not None:
        payload["period_start"] = period_start
    if period_end is not None:
        payload["period_end"] = period_end
    return payload


def _assert_stored(draft: DocumentDraft, batch: ExtractionBatch) -> None:
    """The batch the store keeps: a complete read and its projected rows."""

    assert batch.readable is True
    assert batch.complete is True
    assert batch.issues == ()
    assert batch.dgii_qr is None
    assert batch.ecf_checks is None
    assert batch.observations
    assert len(batch.candidates) == len(batch.observations)
    pairs = zip(batch.observations, batch.candidates, strict=True)
    for observation, candidate in pairs:
        assert candidate.evidence == observation.evidence
        assert candidate.merchant == MERCHANT
        assert candidate.description == observation.description
        assert candidate.source.external_id == (
            f"{draft.sha256}:p{observation.page}:r{observation.row}"
        )
        if observation.amount is None:
            assert candidate.amount is None
        else:
            assert Decimal(candidate.amount) == Decimal(observation.amount)


def _refused(draft: DocumentDraft) -> DocumentDraft:
    return draft.model_copy(
        update={"status": "needs_attention", "error_code": "not_a_receipt"}
    )


def _prepare(checked, monkeypatch, batch, draft):  # noqa: ANN001, F811
    _, tx, binding, _ = checked
    event = mutations.new_candidate(str(binding.owner_id), draft.created_at)
    monkeypatch.setattr(sources, "record_source", lambda *args: uuid4())
    monkeypatch.setattr(sources, "attach", lambda *args: None)
    monkeypatch.setattr(mutations, "validate_facts", lambda *args: None)
    tx.imports = Mock()
    tx.rows = Mock(return_value=[{"business_rnc": None}])
    tx.context = Mock(actor=Mock(space_id=binding.space_id))
    monkeypatch.setattr(mutations, "new_candidate", lambda *args: event)
    result = mutations.prepare_attachment(tx, None, batch, draft, binding.actor)
    saved = tx.imports.put_event.call_args.args[0]
    resolution = BusinessResolution.model_validate(saved.resolution["business"])
    return result, resolution, saved


def _assert_refused(checked, monkeypatch, draft, batch) -> None:  # noqa: ANN001, F811
    with pytest.raises(ActionError, match="not_a_receipt"):
        _prepare(checked, monkeypatch, batch, draft)
    shown = compose(_refused(draft), batch, [], "web")
    assert (shown.attention, shown.preparable) == ("not_a_receipt", False)


def _assert_unverified_draft(  # noqa: ANN001
    checked,  # noqa: F811
    monkeypatch,  # noqa: ANN001
    draft,
    batch,
    amount: str,
    *,
    flagged: bool = False,
    currency: str = "USD",
) -> None:
    shown = compose(_refused(draft), batch, [], "web")
    assert shown.attention != "not_a_receipt"
    assert shown.preparable is True
    result, resolution, saved = _prepare(checked, monkeypatch, batch, draft)
    amount_fact = resolution.facts.amount
    assert result.outcome == "applied"
    assert saved.state == "open"
    assert amount_fact.state == "known"
    assert amount_fact.verified is False
    assert Decimal(amount_fact.value) == Decimal(amount)
    assert resolution.facts.currency.value == currency
    assert resolution.facts.currency.verified is False
    assert resolution.facts.kind.value == "expense"
    assert resolution.facts.counterparty.value == MERCHANT
    if flagged:
        assert len(resolution.read_purchases) > 1
        assert Decimal(amount_fact.value) == max(
            Decimal(purchase.amount) for purchase in resolution.read_purchases
        )
    else:
        assert resolution.read_purchases == ()


def _draft(checked):  # noqa: ANN001, F811
    _, _, _, row = checked
    return DocumentDraft.model_validate(row["draft"])


def test_replay_of_the_stored_reads(checked, monkeypatch) -> None:  # noqa: ANN001, F811
    """The five stored reads. Zeros stay refused. A 0.50 notice and a 32.03
    notice become unverified drafts. The 32.08 receipt stays a purchase."""

    draft = _draft(checked)
    period = {"period_start": "2026-09-01", "period_end": "2026-09-30"}

    zero = _stored(
        draft,
        [_notice("INV-0002", "0.00", **period)],
        receipt=None,
    )
    _assert_stored(draft, zero)
    observed = zero.observations[0]
    projected = zero.candidates[0]
    assert observed.amount == "0.00"
    assert observed.currency == "USD"
    assert observed.evidence == "due_notice"
    assert observed.direction == "outflow"
    assert observed.kind_hint == "expense"
    assert (observed.period_start, observed.period_end) == (
        date(2026, 9, 1),
        date(2026, 9, 30),
    )
    assert zero.receipt is None
    assert projected.direction == "unknown"
    assert projected.kind_hint == "unknown"
    assert (projected.period_start, projected.period_end) == (
        observed.period_start,
        observed.period_end,
    )
    _assert_refused(checked, monkeypatch, draft, zero)

    accounted = _stored(
        draft,
        [_notice("INV-0003", "0.00", account={"currency": "USD"}, **period)],
        receipt=None,
    )
    _assert_stored(draft, accounted)
    assert accounted.observations[0].amount == "0.00"
    assert accounted.observations[0].currency == "USD"
    assert accounted.observations[0].account.currency == "USD"
    assert accounted.candidates[0].account.currency == "USD"
    assert accounted.receipt is None
    _assert_refused(checked, monkeypatch, draft, accounted)

    opening = _notice(
        "INV-0004",
        None,
        evidence="statement_period",
        currency=None,
        row=1,
        status="unknown",
    )
    due = _notice("INV-0004", "0.50", row=2, occurred_on="2026-10-18")
    half = _stored(draft, [opening, due], receipt=None)
    _assert_stored(draft, half)
    assert half.receipt is None
    assert half.candidates[0].amount is None
    assert half.candidates[0].currency is None
    assert half.candidates[0].uncertain == frozenset(
        {"occurred_on", "currency", "amount"}
    )
    assert half.observations[1].evidence == "due_notice"
    assert half.observations[1].amount == "0.50"
    assert half.observations[1].currency == "USD"
    assert half.observations[1].status == "pending"
    _assert_unverified_draft(checked, monkeypatch, draft, half, "0.50")

    posted = _notice(
        "INV-0005",
        "32.08",
        evidence="transaction",
        status="posted",
        occurred_on="2026-10-18",
    )
    passed = _stored(
        draft,
        [posted],
        receipt={
            "merchant": MERCHANT,
            "occurred_on": "2026-10-18",
            "currency": "USD",
            "total": "32.08",
        },
    )
    _assert_stored(draft, passed)
    assert passed.receipt is not None
    assert passed.receipt.total == "32.08"
    assert passed.observations[0].evidence == "transaction"
    assert passed.observations[0].status == "posted"
    assert passed.candidates[0].status == "posted"
    assert passed.candidates[0].direction == "outflow"
    assert passed.candidates[0].kind_hint == "expense"
    _, resolution, saved = _prepare(checked, monkeypatch, passed, draft)
    assert saved.state == "open"
    assert resolution.facts.amount.state == "known"
    assert resolution.facts.amount.verified is False
    assert Decimal(resolution.facts.amount.value) == Decimal("32.08")
    assert resolution.facts.currency.value == "USD"
    assert resolution.facts.kind.value == "expense"
    assert resolution.read_purchases == ()

    notice = _notice("INV-0006", "32.03", occurred_on="2026-10-18")
    pending = _stored(draft, [notice], receipt=None)
    _assert_stored(draft, pending)
    assert pending.receipt is None
    assert pending.observations[0].evidence == "due_notice"
    assert pending.observations[0].amount == "32.03"
    assert pending.observations[0].currency == "USD"
    assert pending.observations[0].status == "pending"
    _assert_unverified_draft(checked, monkeypatch, draft, pending, "32.03")


def test_a_candidate_amount_prices_the_read_when_the_observation_does_not(
    checked,  # noqa: F811
    monkeypatch,  # noqa: ANN001
) -> None:
    """The positive amount survives only on the projected candidate.

    The observation amount and currency are cleared after projection. The
    evidence is a statement period, and the candidate's account currency
    prices the amount.
    """

    draft = _draft(checked)
    row = _row("8.40", currency=None, evidence="statement_period", row=1)
    row["account"] = {"currency": "USD"}
    row["description"] = "INV-0099"
    batch = _stored(draft, [row], receipt=None)
    _assert_stored(draft, batch)
    assert batch.candidates[0].evidence == "statement_period"
    assert batch.candidates[0].account.currency == "USD"
    assert Decimal(batch.candidates[0].amount) == Decimal("8.40")
    blank = batch.observations[0].model_copy(
        update={"amount": None, "currency": None, "account": AccountHint()}
    )
    priced_only_on_candidate = batch.model_copy(update={"observations": (blank,)})
    _assert_unverified_draft(
        checked, monkeypatch, draft, priced_only_on_candidate, "8.40"
    )


def test_equal_amounts_on_two_rows_stay_in_review(
    checked,  # noqa: F811
    monkeypatch,  # noqa: ANN001
) -> None:
    draft = _draft(checked)
    batch = _stored(
        draft,
        [
            _row("12.00", currency="USD", evidence="due_notice", row=1),
            _row("12.00", currency="USD", evidence="payment_notice", row=2),
        ],
        receipt=None,
    )
    _assert_unverified_draft(
        checked, monkeypatch, draft, batch, "12.00", flagged=True
    )


def test_several_amount_rows_prefill_the_largest_and_stay_in_review(
    checked,  # noqa: F811
    monkeypatch,  # noqa: ANN001
) -> None:
    draft = _draft(checked)
    batch = _stored(
        draft,
        [
            _row("4.00", currency="USD", evidence="due_notice", row=1),
            _row("32.03", currency="USD", evidence="payment_notice", row=2),
            _row("10.50", currency="USD", evidence="statement_period", row=3),
        ],
        receipt=None,
    )
    _assert_unverified_draft(
        checked, monkeypatch, draft, batch, "32.03", flagged=True
    )


def test_a_total_with_no_amount_row_is_an_unverified_draft(
    checked,  # noqa: F811
    monkeypatch,  # noqa: ANN001
) -> None:
    draft = _draft(checked)
    batch = _stored(
        draft,
        [],
        receipt={
            "merchant": MERCHANT,
            "occurred_on": "2026-10-18",
            "currency": "USD",
            "total": "64.20",
        },
    )
    _assert_unverified_draft(checked, monkeypatch, draft, batch, "64.20")


def test_subtotal_tax_and_total_prefill_the_largest_and_stay_in_review(
    checked,  # noqa: F811
    monkeypatch,  # noqa: ANN001
) -> None:
    draft = _draft(checked)
    batch = _stored(
        draft,
        [],
        receipt={
            "merchant": MERCHANT,
            "occurred_on": "2026-10-18",
            "currency": "USD",
            "subtotal": "30.00",
            "tax": "2.03",
            "total": "32.03",
        },
    )
    _assert_unverified_draft(
        checked, monkeypatch, draft, batch, "32.03", flagged=True
    )


def test_a_fiscal_amount_with_no_total_is_an_unverified_draft(
    checked,  # noqa: F811
    monkeypatch,  # noqa: ANN001
) -> None:
    draft = _draft(checked)
    batch = _stored(
        draft,
        [],
        receipt={
            "merchant": MERCHANT,
            "occurred_on": "2026-10-18",
            "currency": "USD",
            "itbis": "18.40",
        },
    )
    _assert_unverified_draft(checked, monkeypatch, draft, batch, "18.40")


def test_a_line_count_does_not_outrank_the_money(
    checked,  # noqa: F811
    monkeypatch,  # noqa: ANN001
) -> None:
    draft = _draft(checked)
    batch = _stored(
        draft,
        [],
        receipt={
            "merchant": MERCHANT,
            "occurred_on": "2026-10-18",
            "currency": "USD",
            "items": [
                {
                    "id": "1",
                    "description": "Seats",
                    "quantity": "100",
                    "unit_price": "0.32",
                    "total": "32.00",
                }
            ],
            "total": "32.03",
        },
    )
    _assert_unverified_draft(
        checked, monkeypatch, draft, batch, "32.03", flagged=True
    )


def test_a_positive_inflow_is_still_a_review_draft(
    checked,  # noqa: F811
    monkeypatch,  # noqa: ANN001
) -> None:
    draft = _draft(checked)
    row = _row("15.00", currency="USD", evidence="unclassified", row=1)
    row["direction"] = "inflow"
    batch = _stored(draft, [row], receipt=None)
    _assert_unverified_draft(checked, monkeypatch, draft, batch, "15.00")


def test_a_positive_amount_with_no_currency_stays_refused(
    checked,  # noqa: F811
    monkeypatch,  # noqa: ANN001
) -> None:
    draft = _draft(checked)
    batch = _stored(
        draft,
        [_row("19.00", currency=None, evidence="due_notice", row=1)],
        receipt=None,
    )
    _assert_refused(checked, monkeypatch, draft, batch)


def test_a_bare_amount_uses_the_one_currency_named_on_the_read(
    checked,  # noqa: F811
    monkeypatch,  # noqa: ANN001
) -> None:
    """The row names no currency. The receipt names USD and no other
    currency appears, so the amount is priced in USD."""

    draft = _draft(checked)
    batch = _stored(
        draft,
        [_row("19.00", currency=None, evidence="due_notice", row=1)],
        receipt={"merchant": MERCHANT, "currency": "USD"},
    )
    _assert_unverified_draft(checked, monkeypatch, draft, batch, "19.00")


def test_a_bare_amount_uses_the_account_currency_on_its_own_row(
    checked,  # noqa: F811
    monkeypatch,  # noqa: ANN001
) -> None:
    draft = _draft(checked)
    row = _row("19.00", currency=None, evidence="due_notice", row=1)
    row["account"] = {"currency": "USD"}
    batch = _stored(draft, [row], receipt=None)
    _assert_unverified_draft(checked, monkeypatch, draft, batch, "19.00")


def test_disagreeing_currencies_do_not_price_a_bare_amount(
    checked,  # noqa: F811
    monkeypatch,  # noqa: ANN001
) -> None:
    draft = _draft(checked)
    batch = _stored(
        draft,
        [
            _row("19.00", currency=None, evidence="due_notice", row=1),
            _row("0", currency="EUR", evidence="balance", row=2),
        ],
        receipt={"merchant": MERCHANT, "currency": "USD"},
    )
    _assert_refused(checked, monkeypatch, draft, batch)


@pytest.mark.parametrize(
    "receipt",
    [
        None,
        {
            "merchant": MERCHANT,
            "occurred_on": "2026-10-18",
            "currency": "USD",
            "total": "-20.00",
        },
    ],
)
def test_a_negative_or_credit_only_read_stays_refused(
    checked,  # noqa: F811
    monkeypatch,  # noqa: ANN001
    receipt,  # noqa: ANN001
) -> None:
    draft = _draft(checked)
    batch = _stored(
        draft,
        [_row("-3.25", currency="USD", evidence="due_notice", row=1)],
        receipt=receipt,
    )
    _assert_refused(checked, monkeypatch, draft, batch)


def test_an_unreadable_read_stays_unreadable(
    checked,  # noqa: F811
    monkeypatch,  # noqa: ANN001
) -> None:
    draft = _draft(checked)
    batch = _stored(
        draft,
        [_row("32.03", currency="USD", evidence="due_notice", row=1)],
        receipt=None,
        readable=False,
    )
    with pytest.raises(ActionError, match="unreadable_document"):
        _prepare(checked, monkeypatch, batch, draft)
    held = draft.model_copy(
        update={"status": "needs_attention", "error_code": "unreadable_document"}
    )
    shown = compose(held, batch, [], "web")
    assert (shown.attention, shown.preparable) == ("unreadable", False)


@pytest.mark.asyncio
async def test_reprepare_of_a_stored_refusal_builds_the_draft_without_a_new_read(
    document_bridge,  # noqa: F811
    checked,  # noqa: F811
    monkeypatch,  # noqa: ANN001
) -> None:
    """The first prepare stored the refusal. The replay reads that batch
    again and does not ask the model for another read."""

    service, bridge, extractor, _ = document_bridge
    scope = BusinessSpace(str(uuid4()))
    owner = str(uuid4())
    reading_on(service, scope, owner)
    calls: list[str] = []

    async def extract(**kwargs):  # noqa: ANN003
        calls.append(kwargs["connection_id"])
        draft = service.get(
            user_id=owner, connection_id=kwargs["connection_id"], scope=scope
        )
        return _stored(
            draft,
            [_row("32.03", currency="USD", evidence="due_notice", row=1)],
            receipt=None,
        )

    extractor.extract.side_effect = extract
    produced: dict[str, BusinessResolution] = {}

    def replay(**kwargs):  # noqa: ANN003
        del kwargs
        batch = service.store.get(user_id=owner, connection_id=calls[0])
        assert batch is not None
        _, resolution, _ = _prepare(
            checked,
            monkeypatch,
            batch,
            service.get(user_id=owner, connection_id=calls[0], scope=scope),
        )
        produced["resolution"] = resolution

    seen = {"count": 0}

    def on_prepare(**kwargs):  # noqa: ANN003
        seen["count"] += 1
        if seen["count"] == 1:
            raise ActionError("invalid_input", "not_a_receipt")
        replay(**kwargs)

    bridge.prepare_attachment.side_effect = on_prepare
    uploaded = await service.upload(
        user_id=owner,
        content=b"%PDF-fixture",
        filename="invoice.pdf",
        media_type="application/pdf",
        consent=True,
        scope=scope,
    )
    with pytest.raises(ActionError, match="not_a_receipt"):
        await service.resume(
            user_id=owner, connection_id=uploaded.connection_id, scope=scope
        )
    assert calls == [uploaded.connection_id]
    stored = service.store.get(user_id=owner, connection_id=uploaded.connection_id)
    held = service.get(user_id=owner, connection_id=uploaded.connection_id, scope=scope)
    shown = compose(held, stored, [], "web")
    assert shown.attention != "not_a_receipt"
    assert shown.preparable is True
    outcome = await service.resume(
        user_id=owner, connection_id=uploaded.connection_id, scope=scope
    )
    assert calls == [uploaded.connection_id]
    assert outcome.replayed is True
    assert outcome.status == "review_ready"
    assert produced["resolution"].facts.amount.verified is False
    assert Decimal(produced["resolution"].facts.amount.value) == Decimal("32.03")
    assert produced["resolution"].facts.amount.state == "known"
