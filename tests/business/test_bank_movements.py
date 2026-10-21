"""Transacciones rules: state, offers, documents without a movement, totals, pages."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from argus.domain.business.bank.matching import new_offers
from argus.domain.business.bank.model import BankLine, ScoreParts
from argus.domain.business.bank.movements import (
    Account,
    Document,
    InvalidCursor,
    StoredPair,
    build_movements,
    decode_cursor,
    item_payload,
    method_for,
    movement_state,
    page,
    totals,
    unmoved_documents,
)
from faker import Faker

fake = Faker("es_ES")
Faker.seed(29)
BANK_ACCOUNT = UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
CHECKING = Account(
    bank_account_id=str(BANK_ACCOUNT),
    account_id="acct-checking",
    name="Cuenta",
    type="checking",
    currency="DOP",
    covered_through=date(2026, 10, 20),
)
PARTS = ScoreParts(Decimal("1.000"), Decimal("0.800"), Decimal("0.500"))


def _line(day: int, amount: str, text: str | None = None) -> BankLine:
    description = text or fake.company()
    return BankLine(
        id=uuid4(),
        space_id=uuid4(),
        bank_account_id=BANK_ACCOUNT,
        first_import_id=uuid4(),
        occurred_on=date(2026, 10, day),
        description=description,
        normalized_description=description.casefold(),
        amount=Decimal(amount),
        currency="DOP",
        raw_line={},
        line_hash="0" * 64,
        created_at=datetime(2026, 10, 21, tzinfo=timezone.utc),
    )


def _document(
    day: int,
    total_minor: int,
    *,
    kind: str = "receipt",
    status: str = "pendiente",
    settled_on: date | None = None,
    account_id: str | None = "acct-checking",
    currency: str = "DOP",
) -> Document:
    return Document(
        activity_id=str(uuid4()),
        kind=kind,  # type: ignore[arg-type]
        currency=currency,
        total_minor=total_minor,
        itbis_minor=None,
        occurred_on=date(2026, 10, day),
        counterparty=fake.company(),
        rnc=None,
        ncf=None,
        ecf=None,
        status=status,
        settled_on=settled_on,
        payment_method="transferencia" if settled_on else None,
        account_id=account_id,
        category_id=None,
    )


def _pair(line: BankLine, document: Document, status: str) -> StoredPair:
    return StoredPair(
        suggestion_id=str(uuid4()),
        line_id=str(line.id),
        target_kind=document.kind,
        target_id=document.activity_id,
        status=status,
        parts=PARTS,
    )


@pytest.mark.parametrize(
    ("amount", "matched", "has_offer", "expected"),
    [
        ("-10", True, True, ("igualada", None)),
        ("0", False, True, ("no_lleva_comprobante", "monto_cero")),
        ("-10", False, True, ("sugerencia", None)),
        ("25", False, False, ("falta_comprobante", None)),
    ],
)
def test_one_rule_names_the_state(amount, matched, has_offer, expected) -> None:  # noqa: ANN001
    assert (
        movement_state(Decimal(amount), matched=matched, has_offer=has_offer) == expected
    )


@pytest.mark.parametrize(
    ("account_type", "method"),
    [
        ("checking", "transferencia"),
        ("savings", "transferencia"),
        ("credit_card", "tarjeta"),
        ("cash", "efectivo"),
        ("other_debt", "otro"),
    ],
)
def test_the_method_comes_from_the_account_type(account_type, method) -> None:  # noqa: ANN001
    assert method_for(account_type) == method


def test_a_taken_document_is_neither_offered_nor_an_open_offer() -> None:
    line, other = _line(12, "-150.00"), _line(13, "-150.00")
    document = _document(12, 15000)
    assert new_offers([line], [document], frozenset(), frozenset({document.id})) == []
    assert (
        new_offers(
            [line], [document], frozenset({(str(line.id), document.id)}), frozenset()
        )
        == []
    )
    [(_, offered, _parts)] = new_offers([line], [document], frozenset(), frozenset())
    assert offered is document

    documents = {document.activity_id: document}
    pairs = [_pair(line, document, "pending"), _pair(other, document, "confirmed")]
    taken = frozenset({document.activity_id})
    movements = build_movements(
        [line, other], {CHECKING.bank_account_id: CHECKING}, documents, pairs, taken
    )
    assert [(m.state, len(m.offers)) for m in movements] == [
        ("falta_comprobante", 0),
        ("igualada", 0),
    ]
    assert movements[1].document is document
    assert movements[1].counterparty == document.counterparty


def test_a_pending_pair_of_a_vanished_or_other_kind_document_is_not_an_offer() -> None:
    line = _line(12, "-150.00")
    sale = _document(12, 15000, kind="venta")
    gone = _document(12, 15000)
    pairs = [
        StoredPair("s1", str(line.id), "receipt", sale.activity_id, "pending", PARTS),
        _pair(line, gone, "pending"),
    ]
    [movement] = build_movements(
        [line],
        {CHECKING.bank_account_id: CHECKING},
        {sale.activity_id: sale},
        pairs,
        frozenset(),
    )
    assert movement.state == "falta_comprobante"


def test_offers_run_best_first() -> None:
    line = _line(12, "-150.00")
    weak, strong = _document(10, 15000), _document(12, 15000)
    pairs = [
        StoredPair(
            "a",
            str(line.id),
            "receipt",
            weak.activity_id,
            "pending",
            ScoreParts(Decimal("1"), Decimal("0.6"), Decimal("0")),
        ),
        StoredPair(
            "b",
            str(line.id),
            "receipt",
            strong.activity_id,
            "pending",
            ScoreParts(Decimal("1"), Decimal("1"), Decimal("0")),
        ),
    ]
    [movement] = build_movements(
        [line],
        {CHECKING.bank_account_id: CHECKING},
        {weak.activity_id: weak, strong.activity_id: strong},
        pairs,
        frozenset(),
    )
    assert [offer.document for offer in movement.offers] == [strong, weak]
    payload = item_payload(movement)
    assert [s["reasons"][1] for s in payload["suggestions"]] == [
        {"code": "misma_fecha"},
        {"code": "fecha_cercana", "days": -2},
    ]
    assert [s["reasons"][0] for s in payload["suggestions"]] == [
        {"code": "monto_exacto"},
        {"code": "monto_exacto"},
    ]


def test_without_a_movement_needs_a_settled_bank_document_the_bank_reached() -> None:
    start, end = date(2026, 10, 1), date(2026, 10, 31)
    reached = _document(2, 9000, status="pagado", settled_on=date(2026, 10, 15))
    edge_out = _document(2, 9000, status="pagado", settled_on=date(2026, 10, 16))
    pending = _document(2, 9000)
    in_cash = _document(
        2, 9000, status="pagado", settled_on=date(2026, 10, 2), account_id="acct-cash"
    )
    matched = _document(2, 9000, status="pagado", settled_on=date(2026, 10, 2))
    september = Document(
        **{**reached.__dict__, "activity_id": "sept", "occurred_on": date(2026, 9, 30)}
    )
    found = unmoved_documents(
        [reached, edge_out, pending, in_cash, matched, september],
        [CHECKING],
        frozenset({matched.activity_id}),
        start,
        end,
    )
    assert [item.document for item in found] == [reached]
    uncovered = Account(**{**CHECKING.__dict__, "covered_through": None})
    assert unmoved_documents([reached], [uncovered], frozenset(), start, end) == []


def test_totals_keep_currencies_apart_and_count_por_igualar() -> None:
    accounts = {CHECKING.bank_account_id: CHECKING}
    deposit, charge, fee = _line(3, "5000.00"), _line(4, "-3450.50"), _line(5, "-150")
    sale = _document(3, 500000, kind="venta")
    movements = build_movements(
        [deposit, charge, fee],
        accounts,
        {sale.activity_id: sale},
        [_pair(deposit, sale, "confirmed")],
        frozenset({sale.activity_id}),
    )
    dollars = _document(
        1, 2400, status="pagado", settled_on=date(2026, 10, 1), currency="USD"
    )
    unmoved = unmoved_documents(
        [dollars], [CHECKING], frozenset(), date(2026, 10, 1), date(2026, 10, 31)
    )
    blocks = totals([*movements, *unmoved])
    assert [block["currency"] for block in blocks] == ["DOP", "USD"]
    pesos, usd = blocks
    assert (pesos["entradas_minor"], pesos["entradas"]) == (500000, "5000.00")
    assert (pesos["salidas_minor"], pesos["salidas"]) == (360050, "3600.50")
    assert (pesos["por_igualar_minor"], pesos["por_igualar"]) == (360050, "3600.50")
    assert pesos["counts"] == {
        "movimientos": 3,
        "igualadas": 1,
        "no_lleva_comprobante": 0,
        "sugerencias": 0,
        "falta_comprobante": 2,
        "sin_movimiento": 0,
        "por_igualar": 2,
    }
    assert (usd["entradas_minor"], usd["salidas_minor"], usd["por_igualar"]) == (
        0,
        0,
        "24.00",
    )
    assert usd["counts"]["sin_movimiento"] == usd["counts"]["por_igualar"] == 1
    assert usd["counts"]["movimientos"] == 0


def test_pages_are_keyed_so_a_walk_sees_every_row_once() -> None:
    lines = [_line(day, f"-{day}") for day in (3, 9, 9, 1, 5)]
    movements = build_movements(
        lines, {CHECKING.bank_account_id: CHECKING}, {}, [], frozenset()
    )
    whole, _ = page(movements, segment="todas", sense=None, limit=10, cursor=None)
    days = [item.line.occurred_on.day for item in whole]
    assert days == [9, 9, 5, 3, 1]
    walked, cursor = [], None
    while True:
        shown, cursor = page(
            movements, segment="todas", sense=None, limit=2, cursor=cursor
        )
        walked += shown
        if cursor is None:
            break
    assert walked == whole
    deposits, _ = page(movements, segment="todas", sense="deposit", limit=10, cursor=None)
    assert deposits == []
    igualadas, _ = page(movements, segment="igualadas", sense=None, limit=10, cursor=None)
    assert igualadas == []


@pytest.mark.parametrize("cursor", ["%%%", "W10", "WzEsMiwzXQ", "WzEsMiwzLDRd"])
def test_a_cursor_that_is_not_ours_is_refused(cursor: str) -> None:
    with pytest.raises(InvalidCursor):
        decode_cursor(cursor)
