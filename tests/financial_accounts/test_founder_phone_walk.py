"""The founder's phone walk (PRUEBA_MOVIL steps 2 to 8) against the real money service, with literal balances.

Steps: Banco prueba opens at 1,000; income 500; expense 200; refund 50 of that expense; Efectivo opens at 0;
transfer 100 to Efectivo; BoFa credit card opens at 0; expense 300 on BoFa; pay 300 of BoFa from Banco prueba;
correct the 200 expense to 250 with a reason.
"""

from uuid import uuid4

from financial_accounts.conftest import ALICE

H = {"Authorization": f"Bearer {ALICE}"}
OPEN = "2026-10-12T09:00:00-04:00"
QUESTIONS: list[tuple[str, int]] = []


def _at(minute: int) -> str:
    return f"2026-10-12T10:{minute:02d}:00-04:00"


def _account(client, kind: str, amount: str) -> dict:
    response = client.post(
        "/api/v1/financial-accounts",
        headers={**H, "Idempotency-Key": str(uuid4())},
        json={"type": kind, "currency": "DOP", "amount": amount, "as_of": OPEN},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _version(client, account_id: str) -> int:
    return client.get("/api/v1/financial-accounts/" + account_id, headers=H).json()["version"]


def _balance(client, account_id: str) -> str | None:
    return client.get("/api/v1/financial-accounts/" + account_id, headers=H).json()["balance"]["amount"]


def _record(client, body: dict, *, path: str = "/api/v1/financial-activities", method: str = "post") -> dict:
    accounts = [body.get(k) for k in ("account_id", "source_account_id", "destination_account_id") if body.get(k)]
    body = {**body, "expected_versions": {a: _version(client, a) for a in accounts}}
    preview = client.post(path + "/preview", headers=H, json=body)
    assert preview.status_code == 200, preview.text
    data = preview.json()
    asked = [(a["account_id"], o["observation_id"]) for a in data["affected_accounts"] for o in a["observations"] if o["included"] is None]
    QUESTIONS.append((body["kind"], len(asked)))
    if asked:
        # The founder's answer that applies the movement: "No, apply it".
        body["coverage"] = [{"account_id": a, "observation_id": o, "included": False} for a, o in asked]
        data = client.post(path + "/preview", headers=H, json=body).json()
    assert data["ready"], data
    reviewed = data["reviewed_request"]
    reviewed["preview_token"] = data["preview_token"]
    response = getattr(client, method)(path, headers={**H, "Idempotency-Key": str(uuid4())}, json=reviewed)
    assert response.status_code in (200, 201), response.text
    return response.json()["activity"]


def test_founder_walk_steps_2_to_8(client):
    banco = _account(client, "checking", "1000")["id"]
    assert _balance(client, banco) == "1000.00"

    _record(client, {"kind": "income", "account_id": banco, "amount": "500", "occurred_at": _at(1)})
    assert _balance(client, banco) == "1500.00"

    expense = _record(client, {"kind": "expense", "account_id": banco, "amount": "200", "occurred_at": _at(2)})
    assert _balance(client, banco) == "1300.00"

    _record(client, {"kind": "refund", "account_id": banco, "amount": "50", "occurred_at": _at(3),
                     "purchase_activity_id": expense["activity_id"]})
    assert _balance(client, banco) == "1350.00"

    efectivo = _account(client, "cash", "0")["id"]
    assert _balance(client, efectivo) == "0.00", "an account opened at 0 has a recorded balance of 0.00"
    _record(client, {"kind": "transfer", "source_account_id": banco, "destination_account_id": efectivo,
                     "amount": "100", "occurred_at": _at(4)})
    assert (_balance(client, banco), _balance(client, efectivo)) == ("1250.00", "100.00")

    bofa = _account(client, "credit_card", "0")["id"]
    assert _balance(client, bofa) == "0.00"
    _record(client, {"kind": "expense", "account_id": bofa, "amount": "300", "occurred_at": _at(5)})
    owed_after_purchase = _balance(client, bofa)
    _record(client, {"kind": "card_payment", "source_account_id": banco, "destination_account_id": bofa,
                     "amount": "300", "occurred_at": _at(6)})
    assert _balance(client, banco) == "950.00"
    owed_after_payment = _balance(client, bofa)

    _record(client, {"kind": "expense", "account_id": banco, "amount": "250", "occurred_at": _at(2),
                     "expected_revision": expense["revision"], "reason": "the receipt said 250"},
            path="/api/v1/financial-activities/" + expense["activity_id"], method="patch")
    assert _balance(client, banco) == "900.00"
    assert _balance(client, efectivo) == "100.00"
    assert (owed_after_purchase, owed_after_payment) == ("-300.00", "0.00"), "paying the card clears what is owed"
    # Today every movement made the same day as the openings is asked whether the opening already includes it
    # (loop.eligible compares dates). The answer that applies it, "No, apply it", gives the balances above.
    assert all(count > 0 for _, count in QUESTIONS)
