"""Transacciones over HTTP, on the real app, Auth and Postgres.

Every bank movement of the period comes back with a server-owned state, the
document it is or may be matched to, and totals per currency. A settled
document from the bank account that the statement does not show is listed
once the bank has reached its date. A document approved after the statement
still reaches its line.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from psycopg import Connection

from tests import test_financial_accounts_postgres as shared
from tests.test_business_open_items_postgres import _account, _record, _send
from tests.test_business_scope_switch_routes_postgres import (  # noqa: F401
    API,
    _as,
    _code,
    web,
)
from tests.test_business_scope_switch_routes_postgres import (
    pytestmark as _local_supabase,
)

pytestmark = _local_supabase
BANK = f"{API}/business/bank"
OCTOBER = {"period_start": "2026-10-01", "period_end": "2026-10-31"}


@pytest.fixture
def bank(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest):  # noqa: ANN201
    monkeypatch.setenv("CUADRAO_BUSINESS_BANK_MATCHING_ENABLED", "true")
    return request.getfixturevalue("web")


def _checking(world) -> str:  # noqa: ANN001
    return _send(
        world,
        "POST",
        "/business/accounts",
        {"nickname": "Cuenta Popular", "type": "checking", "currency": "DOP"},
        world.alice.headers,
    )["id"]


def _statement(rows: list[tuple[str, str, str, str]]) -> bytes:
    lines = ["# synthetic", "Fecha,Descripcion,Debito,Credito,Moneda"]
    lines += [f"{day},{text},{debit},{credit},DOP" for day, text, debit, credit in rows]
    return ("\n".join(lines) + "\n").encode()


def _foreign_line(world, listed: dict, import_id: str, day: str, amount: str) -> str:  # noqa: ANN001
    """A statement line in another currency, written as the bank would have it.
    An import refuses a line outside the account's currency, so the row is
    inserted directly; the read must still keep it apart from the account's."""

    with Connection.connect(shared.DSN) as db:
        return str(
            db.execute(
                "insert into public.business_bank_lines ("
                " space_id, bank_account_id, first_import_id, occurred_on, description,"
                " normalized_description, amount, currency, raw_line, line_hash)"
                " values (%s, %s, %s, %s, 'PAGO USD', 'pago usd', %s, 'USD',"
                " '{\"synthetic\": true}'::jsonb, %s) returning id",
                (
                    world.alice.space_id,
                    listed["accounts"][0]["bank_account_id"],
                    import_id,
                    day,
                    amount,
                    uuid4().hex * 2,
                ),
            ).fetchone()[0]
        )


def _import(world, account: str, content: bytes) -> dict:  # noqa: ANN001
    answer = world.client.post(
        f"{BANK}/imports",
        files={"statement": ("estado.csv", content, "text/csv")},
        data={"account_id": account},
        headers={**world.alice.headers, "Idempotency-Key": str(uuid4())},
    )
    assert answer.status_code == 201, answer.text
    return answer.json()


def _movements(world, headers: dict, **params) -> dict:  # noqa: ANN001
    answer = world.client.get(
        f"{BANK}/movements", params={**OCTOBER, **params}, headers=headers
    )
    assert answer.status_code == 200, answer.text
    assert answer.headers["cache-control"] == "no-store"
    return answer.json()


def _settle(world, activity: str, day: str) -> None:  # noqa: ANN001
    _send(
        world,
        "PATCH",
        f"/business/month-close/documents/{activity}",
        {"status": "pagado", "settled_on": day, "payment_method": "transferencia"},
        world.alice.headers,
    )


def _by_id(listed: dict) -> dict[str, dict]:
    return {item["id"]: item for item in listed["items"]}


def test_movements_carry_state_document_and_totals(bank) -> None:  # noqa: ANN001
    owner = bank.alice.headers
    checking = _checking(bank)
    cash = _account(bank, "DOP")
    hardware = _record(
        bank, checking, "expense", "3450", "DOP", "2026-10-16", "Ferreteria La Esquina"
    )
    sale = _record(bank, checking, "income", "5000", "DOP", "2026-10-10", "Cliente Uno")
    unmoved = _record(
        bank, checking, "expense", "900", "DOP", "2026-10-02", "Papeleria Central"
    )
    _settle(bank, unmoved, "2026-10-03")
    in_cash = _record(bank, cash, "expense", "75", "DOP", "2026-10-02", "Colmado")
    _settle(bank, in_cash, "2026-10-02")
    late = _record(bank, checking, "expense", "60", "DOP", "2026-10-19", "Taller")
    _settle(bank, late, "2026-10-19")

    imported = _import(
        bank,
        checking,
        _statement(
            [
                ("17/10/2026", "COMPRA  FERRETERIA LA ESQUINA", "3450.00", ""),
                ("10/10/2026", "DEP CLIENTE UNO", "", "5000.00"),
                ("12/10/2026", "COMISION MANEJO", "150.00", ""),
                ("20/10/2026", "CARGO CERO", "0.00", ""),
            ]
        ),
    )
    assert [line["state"] for line in imported["lines"]] == [
        "sugerencia",
        "sugerencia",
        "falta_comprobante",
        "no_lleva_comprobante",
    ]

    listed = _movements(bank, owner)
    assert listed["accounts"] == [
        {
            "account_id": checking,
            "name": "Cuenta Popular",
            "type": "checking",
            "bank_account_id": listed["accounts"][0]["bank_account_id"],
            "currency": "DOP",
            "covered_through": "2026-10-20",
        }
    ]
    states = {
        item["description"] or item["id"]: item["state"] for item in listed["items"]
    }
    assert states == {
        "COMPRA  FERRETERIA LA ESQUINA": "sugerencia",
        "DEP CLIENTE UNO": "sugerencia",
        "COMISION MANEJO": "falta_comprobante",
        "CARGO CERO": "no_lleva_comprobante",
    }
    charge = next(i for i in listed["items"] if i["description"].startswith("COMPRA"))
    assert charge["counterparty"] == "COMPRA FERRETERIA LA ESQUINA"
    assert (charge["amount_minor"], charge["amount"]) == (-345000, "-3450.00")
    assert charge["account"] == {
        "account_id": checking,
        "name": "Cuenta Popular",
        "type": "checking",
    }
    assert charge["method"] == "transferencia"
    [offer] = charge["suggestions"]
    assert offer["reasons"] == [
        {"code": "monto_exacto", "days": None},
        {"code": "fecha_cercana", "days": -1},
        {"code": "nombre_parecido", "days": None},
    ]
    assert offer["document"] == {
        "activity_id": hardware,
        "kind": "receipt",
        "counterparty": "Ferreteria La Esquina",
        "occurred_on": "2026-10-16",
        "currency": "DOP",
        "total_minor": 345000,
        "total": "3450.00",
        "itbis_minor": None,
        "itbis": None,
        "rnc": None,
        "ncf": None,
        "ecf": None,
        "status": "pendiente",
        "settled_on": None,
        "payment_method": None,
        "category_id": None,
    }
    zero = next(i for i in listed["items"] if i["description"] == "CARGO CERO")
    assert zero["reason"] == "monto_cero"
    assert listed["totals"] == [
        {
            "currency": "DOP",
            "entradas_minor": 500000,
            "entradas": "5000.00",
            "salidas_minor": 360000,
            "salidas": "3600.00",
            "por_igualar_minor": 950000,
            "por_igualar": "9500.00",
            "counts": {
                "movimientos": 4,
                "igualadas": 0,
                "no_lleva_comprobante": 1,
                "sugerencias": 2,
                "falta_comprobante": 1,
                "sin_movimiento": 1,
                "por_igualar": 4,
            },
        }
    ]

    pending = _movements(bank, owner, segment="por_igualar")
    assert [(item["state"], item["counterparty"]) for item in pending["items"]] == [
        ("sugerencia", "DEP CLIENTE UNO"),
        ("sugerencia", "COMPRA FERRETERIA LA ESQUINA"),
        ("falta_comprobante", "COMISION MANEJO"),
        ("sin_movimiento", "Papeleria Central"),
    ]
    assert pending["items"][0]["suggestions"][0]["document"]["activity_id"] == sale
    assert in_cash not in _by_id(pending) and late not in _by_id(pending)

    confirmed = bank.client.post(
        f"{BANK}/suggestions/{offer['id']}/confirm",
        headers={**owner, "Idempotency-Key": str(uuid4())},
    )
    assert confirmed.status_code == 200, confirmed.text
    after = _by_id(_movements(bank, owner))
    matched = after[charge["id"]]
    assert matched["state"] == "igualada"
    assert matched["counterparty"] == "Ferreteria La Esquina"
    assert matched["document"]["activity_id"] == hardware
    assert matched["suggestions"] == []


def test_the_table_follows_the_chosen_currency_and_counts_span_them(bank) -> None:  # noqa: ANN001
    owner = bank.alice.headers
    checking = _checking(bank)
    imported = _import(
        bank,
        checking,
        _statement(
            [
                ("10/10/2026", "DEP CLIENTE UNO", "", "5000.00"),
                ("12/10/2026", "COMISION MANEJO", "150.00", ""),
            ]
        ),
    )
    listed = _movements(bank, owner)
    usd_fee = _foreign_line(bank, listed, imported["id"], "2026-10-13", "-20")
    usd_sale = _foreign_line(bank, listed, imported["id"], "2026-10-14", "300")

    every = _movements(bank, owner)
    counts = {
        "movimientos": 4,
        "igualadas": 0,
        "no_lleva_comprobante": 0,
        "sugerencias": 0,
        "falta_comprobante": 4,
        "sin_movimiento": 0,
        "por_igualar": 4,
    }
    assert (every["currency"], every["other_currencies"], every["counts"]) == (
        None,
        [],
        counts,
    )
    assert [block["currency"] for block in every["totals"]] == ["DOP", "USD"]
    assert {item["id"] for item in every["items"]} > {usd_fee, usd_sale}

    dollars = _movements(bank, owner, currency="USD")
    assert [item["id"] for item in dollars["items"]] == [usd_sale, usd_fee]
    assert dollars["currency"] == "USD"
    assert [block["currency"] for block in dollars["totals"]] == ["USD"]
    assert (dollars["totals"][0]["entradas"], dollars["totals"][0]["salidas"]) == (
        "300.00",
        "20.00",
    )
    assert dollars["other_currencies"] == [{"currency": "DOP", "count": 2}]
    assert dollars["counts"] == counts

    charges = _movements(bank, owner, currency="DOP", sense="charge")
    assert [item["description"] for item in charges["items"]] == ["COMISION MANEJO"]
    assert charges["other_currencies"] == [{"currency": "USD", "count": 1}]
    assert charges["counts"] == counts

    euros = _movements(bank, owner, currency="EUR")
    assert (euros["items"], euros["totals"]) == ([], [])
    assert euros["other_currencies"] == [
        {"currency": "DOP", "count": 2},
        {"currency": "USD", "count": 2},
    ]

    lower = bank.client.get(
        f"{BANK}/movements", params={**OCTOBER, "currency": "usd"}, headers=owner
    )
    assert lower.status_code == 422, lower.text


def test_a_settled_document_the_bank_reached_has_no_movement(bank) -> None:  # noqa: ANN001
    owner = bank.alice.headers
    checking = _checking(bank)
    unmoved = _record(
        bank, checking, "expense", "900", "DOP", "2026-10-02", "Papeleria Central"
    )
    _settle(bank, unmoved, "2026-10-03")
    _import(bank, checking, _statement([("07/10/2026", "COMISION", "150.00", "")]))
    pending = _movements(bank, owner, segment="por_igualar")
    assert [(i["kind"], i["state"]) for i in pending["items"]] == [
        ("movement", "falta_comprobante")
    ]

    _import(bank, checking, _statement([("20/10/2026", "COMISION", "150.00", "")]))
    pending = _movements(bank, owner, segment="por_igualar")
    document = pending["items"][-1]
    assert (document["kind"], document["id"], document["state"]) == (
        "document",
        unmoved,
        "sin_movimiento",
    )
    assert (document["amount_minor"], document["sense"], document["method"]) == (
        -90000,
        "charge",
        "transferencia",
    )
    assert pending["totals"][0]["counts"]["sin_movimiento"] == 1


def test_a_document_approved_after_the_statement_is_offered(bank) -> None:  # noqa: ANN001
    owner = bank.alice.headers
    checking = _checking(bank)
    _import(bank, checking, _statement([("12/10/2026", "COMISION MANEJO", "150.00", "")]))
    first = _movements(bank, owner)
    assert [i["state"] for i in first["items"]] == ["falta_comprobante"]
    fee = _record(bank, checking, "expense", "150", "DOP", "2026-10-11", "Banco")
    [line] = _movements(bank, owner)["items"]
    assert line["state"] == "sugerencia"
    assert [s["document"]["activity_id"] for s in line["suggestions"]] == [fee]


def test_pages_walk_the_whole_segment_and_bad_input_is_refused(bank) -> None:  # noqa: ANN001
    owner = bank.alice.headers
    checking = _checking(bank)
    _import(
        bank,
        checking,
        _statement(
            [
                (f"{day:02d}/10/2026", f"PAGO {day}", f"{day}.00", "")
                for day in range(1, 8)
            ]
        ),
    )
    whole = [item["id"] for item in _movements(bank, owner)["items"]]
    assert len(whole) == 7
    walked, cursor = [], None
    while True:
        params = {"limit": 3, **({"cursor": cursor} if cursor else {})}
        listed = _movements(bank, owner, **params)
        walked += [item["id"] for item in listed["items"]]
        cursor = listed["next_cursor"]
        if cursor is None:
            break
    assert walked == whole
    days = [item["occurred_on"] for item in _movements(bank, owner)["items"]]
    assert days == sorted(days, reverse=True)
    assert _movements(bank, owner, sense="deposit")["items"] == []

    backwards = bank.client.get(
        f"{BANK}/movements",
        params={"period_start": "2026-10-31", "period_end": "2026-10-01"},
        headers=owner,
    )
    assert _code(backwards) == (422, "invalid_period")
    garbled = bank.client.get(
        f"{BANK}/movements", params={**OCTOBER, "cursor": "not-a-cursor"}, headers=owner
    )
    assert _code(garbled) == (422, "invalid_cursor")


def test_the_accountant_reads_the_same_movements_and_strangers_none(bank) -> None:  # noqa: ANN001
    checking = _checking(bank)
    _import(bank, checking, _statement([("12/10/2026", "COMISION", "150.00", "")]))
    owner_view = _movements(bank, bank.alice.headers)
    assert _movements(bank, _as(bank.bob, bank.grant_a)) == owner_view
    assert _movements(bank, bank.bob.headers)["items"] == []
    borrowed = bank.client.get(
        f"{BANK}/movements", params=OCTOBER, headers=_as(bank.carol, bank.grant_a)
    )
    assert _code(borrowed) == (403, "business_grant_not_live")

    with Connection.connect(shared.DSN) as db:
        db.execute(
            "update public.business_client_grants set capabilities=ARRAY['read'] where id=%s",
            (bank.grant_a,),
        )
    reader = _as(bank.bob, bank.grant_a)
    assert _movements(bank, reader) == owner_view
    refused = bank.client.post(
        f"{BANK}/imports",
        files={"statement": ("estado.csv", _statement([]), "text/csv")},
        data={"account_id": checking},
        headers={**reader, "Idempotency-Key": str(uuid4())},
    )
    assert _code(refused) == (403, "business_permission_denied")
