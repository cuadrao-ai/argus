"""The founder's phone walk (PRUEBA_MOVIL steps 2 to 8) against the real money service, with literal balances.

Steps: Banco prueba opens at 1,000; income 500; expense 200; refund 50 of that expense; Efectivo opens at 0;
transfer 100 to Efectivo; BoFa credit card opens at 0; expense 300 on BoFa; pay 300 of BoFa from Banco prueba;
correct the 200 expense to 250 with a reason.
"""

from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from argus.api.financial_accounts import configure_financial_accounts_service
from argus.domain.recording.repository import InMemoryFinancialAccountRepository
from argus.domain.recording.service import FinancialAccountService

from financial_accounts.conftest import ALICE

H = {"Authorization": f"Bearer {ALICE}"}
# The founder's walk on the evening of October 12, Santo Domingo time.
WALK = datetime(2026, 10, 12, 22, 58, tzinfo=ZoneInfo("America/Santo_Domingo"))


class Clock:
    """Each step happens a minute after the last, and every movement keeps today's date."""

    def __init__(self) -> None:
        self.at = WALK

    def __call__(self) -> datetime:
        return self.at

    def step(self) -> str:
        self.at += timedelta(minutes=1)
        return self.at.isoformat()


def _account(client, clock: Clock, kind: str, amount: str) -> dict:
    clock.step()
    response = client.post(
        "/api/v1/financial-accounts",
        headers={**H, "Idempotency-Key": str(uuid4())},
        json={"type": kind, "currency": "DOP", "amount": amount},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _version(client, account_id: str) -> int:
    return client.get("/api/v1/financial-accounts/" + account_id, headers=H).json()[
        "version"
    ]


def _balance(client, account_id: str) -> str | None:
    return client.get("/api/v1/financial-accounts/" + account_id, headers=H).json()[
        "balance"
    ]["amount"]


def _record(
    client,
    body: dict,
    answer: bool,
    asked: list,
    *,
    path: str = "/api/v1/financial-activities",
    method: str = "post",
) -> dict:
    accounts = [
        body.get(k)
        for k in ("account_id", "source_account_id", "destination_account_id")
        if body.get(k)
    ]
    body = {**body, "expected_versions": {a: _version(client, a) for a in accounts}}
    preview = client.post(path + "/preview", headers=H, json=body)
    assert preview.status_code == 200, preview.text
    data = preview.json()
    questions = [
        (a["account_id"], o["observation_id"])
        for a in data["affected_accounts"]
        for o in a["observations"]
        if o["included"] is None
    ]
    asked.extend(questions)
    if questions:
        body["coverage"] = [
            {"account_id": a, "observation_id": o, "included": answer}
            for a, o in questions
        ]
        data = client.post(path + "/preview", headers=H, json=body).json()
    assert data["ready"], data
    reviewed = data["reviewed_request"]
    reviewed["preview_token"] = data["preview_token"]
    response = getattr(client, method)(
        path, headers={**H, "Idempotency-Key": str(uuid4())}, json=reviewed
    )
    assert response.status_code in (200, 201), response.text
    return response.json()["activity"]


@pytest.mark.parametrize("answer", [False, True], ids=["answers-no", "answers-yes"])
def test_founder_walk_steps_2_to_8(client, answer):
    clock = Clock()
    configure_financial_accounts_service(
        FinancialAccountService(InMemoryFinancialAccountRepository(clock), clock)
    )
    asked: list = []

    def record(body: dict, **where) -> dict:
        return _record(
            client, {**body, "occurred_at": clock.step()}, answer, asked, **where
        )

    banco = _account(client, clock, "checking", "1000")["id"]
    assert _balance(client, banco) == "1000.00"

    record({"kind": "income", "account_id": banco, "amount": "500"})
    assert _balance(client, banco) == "1500.00"

    expense = record({"kind": "expense", "account_id": banco, "amount": "200"})
    assert _balance(client, banco) == "1300.00"

    record(
        {
            "kind": "refund",
            "account_id": banco,
            "amount": "50",
            "purchase_activity_id": expense["activity_id"],
        }
    )
    assert _balance(client, banco) == "1350.00"

    efectivo = _account(client, clock, "cash", "0")["id"]
    assert _balance(client, efectivo) == "0.00"
    record(
        {
            "kind": "transfer",
            "source_account_id": banco,
            "destination_account_id": efectivo,
            "amount": "100",
        }
    )
    assert (_balance(client, banco), _balance(client, efectivo)) == ("1250.00", "100.00")

    bofa = _account(client, clock, "credit_card", "0")["id"]
    assert _balance(client, bofa) == "0.00"
    record({"kind": "expense", "account_id": bofa, "amount": "300"})
    assert _balance(client, bofa) == "-300.00"
    record(
        {
            "kind": "card_payment",
            "source_account_id": banco,
            "destination_account_id": bofa,
            "amount": "300",
        }
    )
    assert (_balance(client, banco), _balance(client, bofa)) == ("950.00", "0.00")

    clock.step()
    _record(
        client,
        {
            "kind": "expense",
            "account_id": banco,
            "amount": "250",
            "occurred_at": expense["occurred_at"],
            "expected_revision": expense["revision"],
            "reason": "the receipt said 250",
        },
        answer,
        asked,
        path="/api/v1/financial-activities/" + expense["activity_id"],
        method="patch",
    )
    assert (
        _balance(client, banco),
        _balance(client, efectivo),
        _balance(client, bofa),
    ) == ("900.00", "100.00", "0.00")
    assert (
        asked == []
    ), "movements entered with today's date after each opening are never asked"
