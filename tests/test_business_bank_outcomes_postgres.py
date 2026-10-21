"""Igualar and desigualar over HTTP, on the real app, Auth and Postgres.

Igualar writes the document's cobrado or pagado with the movement's date and
the account's method, in the same transaction as the match. Desigualar puts
back exactly what was there. A document is held by one live line, whatever
arrives at once. While matched, nobody else changes its settlement.
"""

from __future__ import annotations

import threading
from uuid import uuid4

import psycopg
from psycopg import Connection

from tests import test_financial_accounts_postgres as shared
from tests.test_business_bank_movements_postgres import (
    BANK,
    _checking,
    _import,
    _movements,
    _statement,
    bank,  # noqa: F401
)
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


def _post(world, path: str, headers: dict, body: dict | None = None, key=None):  # noqa: ANN001, ANN202
    return world.client.post(
        f"{BANK}{path}",
        json=body,
        headers={**headers, "Idempotency-Key": key or str(uuid4())},
    )


def _ok(answer) -> dict:  # noqa: ANN001
    assert answer.status_code == 200, answer.text
    return answer.json()


def _paid_state(world, activity: str, month: str = "2026-10") -> tuple:  # noqa: ANN001
    """Every place the paid state shows: the month read, open items, the row."""

    owner = world.alice.headers
    month_read = _ok(
        world.client.get(
            f"{API}/business/month-close", params={"month": month}, headers=owner
        )
    )
    open_read = _ok(world.client.get(f"{API}/business/open-items", headers=owner))
    with Connection.connect(shared.DSN) as db:
        row = db.execute(
            "select status, settled_on, payment_method from public.business_document_settlements"
            " where activity_id = %s",
            (activity,),
        ).fetchone()
    return month_read, open_read, row and (row[0], row[1], row[2])


def _revisions(activity: str) -> list[tuple]:
    with Connection.connect(shared.DSN) as db:
        return db.execute(
            "select previous_status, previous_settled_on::text, previous_payment_method"
            " from public.business_document_settlement_revisions where activity_id = %s"
            " order by created_at",
            (activity,),
        ).fetchall()


def _line(listed: dict, text: str) -> dict:
    return next(item for item in listed["items"] if item["description"] == text)


def test_igualar_writes_pagado_and_desigualar_restores_it_byte_for_byte(bank) -> None:  # noqa: ANN001, F811
    owner = bank.alice.headers
    checking = _checking(bank)
    receipt = _record(
        bank, checking, "expense", "3450", "DOP", "2026-10-16", "Ferreteria La Esquina"
    )
    _import(
        bank,
        checking,
        _statement([("17/10/2026", "FERRETERIA LA ESQUINA", "3450.00", "")]),
    )
    line = _line(_movements(bank, owner), "FERRETERIA LA ESQUINA")
    [offer] = line["suggestions"]
    before = _paid_state(bank, receipt)
    assert before[2] is None
    assert [i["activity_id"] for i in before[1]["cuentas_por_pagar"]["items"]] == [
        receipt
    ]

    key = str(uuid4())
    confirmed = _ok(_post(bank, f"/suggestions/{offer['id']}/confirm", owner, key=key))
    assert (confirmed["status"], confirmed["actionable"]) == ("confirmed", False)
    assert (
        _ok(_post(bank, f"/suggestions/{offer['id']}/confirm", owner, key=key))
        == confirmed
    )
    again = _post(bank, f"/suggestions/{offer['id']}/confirm", owner)
    assert _code(again) == (409, "suggestion_not_pending")

    matched = _paid_state(bank, receipt)
    assert matched[2] == ("pagado", _date("2026-10-17"), "transferencia")
    assert matched[1]["cuentas_por_pagar"]["items"] == []
    assert matched[0]["cuentas_por_pagar"] == []
    listed = _line(_movements(bank, owner), "FERRETERIA LA ESQUINA")
    assert listed["state"] == "igualada"
    assert listed["document"]["status"] == "pagado"
    assert listed["document"]["settled_on"] == "2026-10-17"
    assert listed["document"]["payment_method"] == "transferencia"

    undone = _ok(_post(bank, f"/movements/{line['id']}/unmatch", owner, key="undo-1"))
    assert undone["state"] == "sugerencia"
    assert [s["id"] for s in undone["suggestions"]] == [offer["id"]]
    assert (
        _ok(_post(bank, f"/movements/{line['id']}/unmatch", owner, key="undo-1"))
        == undone
    )
    after = _paid_state(bank, receipt)
    assert after[0] == before[0]
    assert after[1] == before[1]
    assert after[2] == ("pendiente", None, None)
    assert _revisions(receipt) == [
        ("pendiente", None, None),
        ("pagado", "2026-10-17", "transferencia"),
    ]
    history = _ok(
        bank.client.get(f"{BANK}/movements/{line['id']}/history", headers=owner)
    )
    assert [
        (h["kind"], h["activity_id"], h["ended_at"] is not None) for h in history
    ] == [("match", receipt, True)]
    second = _post(bank, f"/movements/{line['id']}/unmatch", owner)
    assert _code(second) == (409, "line_not_matched")


def test_desigualar_restores_a_settlement_set_by_hand(bank) -> None:  # noqa: ANN001, F811
    owner = bank.alice.headers
    checking = _checking(bank)
    sale = _record(bank, checking, "income", "5000", "DOP", "2026-10-10", "Cliente Uno")
    _send(
        bank,
        "PATCH",
        f"/business/month-close/documents/{sale}",
        {"status": "cobrado", "settled_on": "2026-10-09", "payment_method": "efectivo"},
        owner,
    )
    _import(
        bank, checking, _statement([("10/10/2026", "DEP CLIENTE UNO", "", "5000.00")])
    )
    line = _line(_movements(bank, owner), "DEP CLIENTE UNO")
    before = _paid_state(bank, sale)

    matched = _ok(
        _post(bank, f"/movements/{line['id']}/match", owner, {"activity_id": sale})
    )
    assert matched["state"] == "igualada"
    assert _paid_state(bank, sale)[2] == ("cobrado", _date("2026-10-10"), "transferencia")

    by_hand = bank.client.patch(
        f"{API}/business/month-close/documents/{sale}",
        json={"status": "pendiente"},
        headers={**owner, "Idempotency-Key": str(uuid4())},
    )
    assert _code(by_hand) == (409, "business_document_matched")
    same = _send(
        bank,
        "PATCH",
        f"/business/month-close/documents/{sale}",
        {
            "status": "cobrado",
            "settled_on": "2026-10-10",
            "payment_method": "transferencia",
        },
        owner,
    )
    assert same["changed"] is False

    _ok(_post(bank, f"/movements/{line['id']}/unmatch", owner))
    after = _paid_state(bank, sale)
    assert after == before
    assert after[2] == ("cobrado", _date("2026-10-09"), "efectivo")


def test_one_document_one_live_line_when_two_arrive_together(bank) -> None:  # noqa: ANN001, F811
    owner = bank.alice.headers
    checking = _checking(bank)
    receipt = _record(bank, checking, "expense", "150", "DOP", "2026-10-12", "Banco")
    _import(
        bank,
        checking,
        _statement(
            [
                ("12/10/2026", "COMISION A", "150.00", ""),
                ("12/10/2026", "COMISION B", "150.00", ""),
            ]
        ),
    )
    listed = _movements(bank, owner)
    first, second = (_line(listed, "COMISION A"), _line(listed, "COMISION B"))
    gate = threading.Barrier(2)
    answers: dict[str, object] = {}

    def igualar(line_id: str) -> None:
        gate.wait()
        answers[line_id] = _post(
            bank, f"/movements/{line_id}/match", owner, {"activity_id": receipt}
        )

    threads = [
        threading.Thread(target=igualar, args=(row["id"],)) for row in (first, second)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    codes = sorted(_code(answer)[0] for answer in answers.values())
    assert codes == [200, 409]
    [refused] = [a for a in answers.values() if a.status_code == 409]
    assert _code(refused) == (409, "document_already_matched")
    assert _live_matches(receipt) == 1
    assert len(_revisions(receipt)) == 1
    offers = _ok(bank.client.get(f"{BANK}/suggestions", headers=owner))
    assert sorted((o["status"], o["actionable"]) for o in offers) == [
        ("confirmed", False),
        ("pending", False),
    ]


def test_a_held_match_blocks_the_second_line_until_it_commits(bank) -> None:  # noqa: ANN001, F811
    owner = bank.alice.headers
    checking = _checking(bank)
    receipt = _record(bank, checking, "expense", "150", "DOP", "2026-10-12", "Banco")
    _import(
        bank,
        checking,
        _statement(
            [
                ("12/10/2026", "COMISION A", "150.00", ""),
                ("12/10/2026", "COMISION B", "150.00", ""),
            ]
        ),
    )
    listed = _movements(bank, owner)
    first, second = (_line(listed, "COMISION A"), _line(listed, "COMISION B"))
    holder = psycopg.connect(shared.DSN)
    try:
        holder.execute(
            "insert into public.business_bank_line_outcomes ("
            " space_id, line_id, kind, target_kind, target_id, prior_status,"
            " applied_status, applied_settled_on, applied_payment_method, create_key)"
            " values (%s, %s, 'match', 'receipt', %s, 'pendiente', 'pagado',"
            " '2026-10-12', 'transferencia', 'held')",
            (bank.alice.space_id, first["id"], receipt),
        )
        answer: dict[str, object] = {}
        racer = threading.Thread(
            target=lambda: answer.setdefault(
                "it",
                _post(
                    bank,
                    f"/movements/{second['id']}/match",
                    owner,
                    {"activity_id": receipt},
                ),
            )
        )
        racer.start()
        racer.join(timeout=2)
        assert racer.is_alive(), "the second match must wait for the held one"
        holder.commit()
        racer.join(timeout=30)
    finally:
        holder.close()
    assert _code(answer["it"]) == (409, "document_already_matched")
    assert _live_matches(receipt) == 1


def test_no_lleva_comprobante_is_a_reason_that_can_change_and_clear(bank) -> None:  # noqa: ANN001, F811
    owner = bank.alice.headers
    checking = _checking(bank)
    receipt = _record(bank, checking, "expense", "150", "DOP", "2026-10-12", "Banco")
    _import(bank, checking, _statement([("12/10/2026", "COMISION", "150.00", "")]))
    line = _line(_movements(bank, owner), "COMISION")
    path = f"{BANK}/movements/{line['id']}/disposition"

    def mark(reason: str):  # noqa: ANN202
        return bank.client.put(
            path,
            json={"reason": reason},
            headers={**owner, "Idempotency-Key": str(uuid4())},
        )

    marked = _ok(mark("cargo_banco"))
    assert (marked["state"], marked["reason"], marked["suggestions"]) == (
        "no_lleva_comprobante",
        "cargo_banco",
        [],
    )
    assert _ok(mark("cargo_banco")) == marked
    assert _ok(mark("entre_cuentas"))["reason"] == "entre_cuentas"
    blocked = _post(
        bank, f"/movements/{line['id']}/match", owner, {"activity_id": receipt}
    )
    assert _code(blocked) == (409, "line_marked_no_receipt")
    assert _code(mark("otro")) == (422, "validation_error")
    unmatched = _ok(
        bank.client.get(
            f"{BANK}/unmatched",
            params={"period_start": "2026-10-01", "period_end": "2026-10-31"},
            headers=owner,
        )
    )
    assert unmatched["count"] == 0
    totals = _movements(bank, owner)["totals"][0]["counts"]
    assert (totals["no_lleva_comprobante"], totals["por_igualar"]) == (1, 0)

    cleared = bank.client.delete(path, headers={**owner, "Idempotency-Key": "clear-1"})
    assert _ok(cleared)["state"] == "sugerencia"
    replay = bank.client.delete(path, headers={**owner, "Idempotency-Key": "clear-1"})
    assert _ok(replay)["state"] == "sugerencia"
    again = bank.client.delete(path, headers={**owner, "Idempotency-Key": str(uuid4())})
    assert _code(again) == (409, "line_not_marked")
    history = _ok(
        bank.client.get(f"{BANK}/movements/{line['id']}/history", headers=owner)
    )
    assert [(h["reason"], h["ended_at"] is not None) for h in history] == [
        ("cargo_banco", True),
        ("entre_cuentas", True),
    ]


def test_manual_match_is_checked_and_decline_is_kept(bank) -> None:  # noqa: ANN001, F811
    owner = bank.alice.headers
    checking = _checking(bank)
    cash = _account(bank, "DOP")
    near = _record(bank, checking, "expense", "800", "DOP", "2026-10-03", "Suplidor")
    far = _record(bank, cash, "expense", "800", "DOP", "2026-08-01", "Suplidor viejo")
    wrong = _record(bank, checking, "expense", "801", "DOP", "2026-10-03", "Otro")
    sale = _record(bank, checking, "income", "800", "DOP", "2026-10-03", "Cliente")
    _import(bank, checking, _statement([("03/10/2026", "SUPLIDOR", "800.00", "")]))
    line = _line(_movements(bank, owner), "SUPLIDOR")
    [offer] = line["suggestions"]
    assert offer["document"]["activity_id"] == near

    declined = _ok(_post(bank, f"/suggestions/{offer['id']}/decline", owner))
    assert declined["status"] == "declined"
    assert _code(_post(bank, f"/suggestions/{offer['id']}/confirm", owner)) == (
        409,
        "pair_declined",
    )
    for document in (wrong, sale):
        refused = _post(
            bank, f"/movements/{line['id']}/match", owner, {"activity_id": document}
        )
        assert _code(refused) == (422, "document_not_matchable")
    stranger = _post(
        bank, f"/movements/{line['id']}/match", owner, {"activity_id": str(uuid4())}
    )
    assert _code(stranger) == (404, "business_record_not_found")

    key = str(uuid4())
    path = f"/movements/{line['id']}/match"
    matched = _ok(_post(bank, path, owner, {"activity_id": far}, key=key))
    assert _ok(_post(bank, path, owner, {"activity_id": far}, key=key)) == matched
    reused = _post(bank, path, owner, {"activity_id": near}, key=key)
    assert _code(reused) == (409, "idempotency_conflict")
    assert matched["document"]["activity_id"] == far
    assert matched["document"]["payment_method"] == "transferencia"
    taken = _post(bank, f"/movements/{line['id']}/match", owner, {"activity_id": near})
    assert _code(taken) == (409, "line_already_confirmed")


def test_the_accountant_igualar_and_a_reader_cannot(bank) -> None:  # noqa: ANN001, F811
    checking = _checking(bank)
    receipt = _record(bank, checking, "expense", "150", "DOP", "2026-10-12", "Banco")
    _import(bank, checking, _statement([("12/10/2026", "COMISION", "150.00", "")]))
    accountant = _as(bank.bob, bank.grant_a)
    line = _line(_movements(bank, accountant), "COMISION")
    _ok(
        _post(
            bank, f"/movements/{line['id']}/match", accountant, {"activity_id": receipt}
        )
    )
    with Connection.connect(shared.DSN) as db:
        db.execute(
            "update public.business_client_grants set capabilities=ARRAY['read'] where id=%s",
            (bank.grant_a,),
        )
    refused = _post(bank, f"/movements/{line['id']}/unmatch", accountant)
    assert _code(refused) == (403, "business_permission_denied")
    again = _post(
        bank, f"/movements/{line['id']}/match", accountant, {"activity_id": receipt}
    )
    assert _code(again) == (403, "business_permission_denied")
    no_key = bank.client.post(
        f"{BANK}/movements/{line['id']}/unmatch", headers=bank.alice.headers
    )
    assert _code(no_key) == (400, "idempotency_key_required")


def test_two_reasons_for_one_line_at_once_both_land_in_turn(bank) -> None:  # noqa: ANN001, F811
    owner = bank.alice.headers
    checking = _checking(bank)
    _import(bank, checking, _statement([("12/10/2026", "COMISION", "150.00", "")]))
    line = _line(_movements(bank, owner), "COMISION")
    path = f"{BANK}/movements/{line['id']}/disposition"

    def mark(gate: threading.Barrier, answers: list, reason: str) -> None:
        gate.wait()
        answers.append(
            bank.client.put(
                path,
                json={"reason": reason},
                headers={**owner, "Idempotency-Key": str(uuid4())},
            )
        )

    for _round in range(3):
        gate, answers = threading.Barrier(2), []
        threads = [
            threading.Thread(target=mark, args=(gate, answers, reason))
            for reason in ("cargo_banco", "personal")
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert [answer.status_code for answer in answers] == [200, 200]
    with Connection.connect(shared.DSN) as db:
        live = db.execute(
            "select count(*) from public.business_bank_line_outcomes"
            " where line_id = %s and ended_at is null",
            (line["id"],),
        ).fetchone()[0]
    assert live == 1


def _live_matches(activity: str) -> int:
    with Connection.connect(shared.DSN) as db:
        return db.execute(
            "select count(*) from public.business_bank_line_outcomes"
            " where target_id = %s and ended_at is null",
            (activity,),
        ).fetchone()[0]


def _date(text: str):  # noqa: ANN202
    from datetime import date

    return date.fromisoformat(text)
