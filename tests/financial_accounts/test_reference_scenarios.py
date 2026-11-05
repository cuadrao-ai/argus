"""The first-slice scenarios of the proposed recording contract, over production.

PR #724 commits these scenarios and their literal outcomes against an in-memory
reference model. Its ``Scene`` reaches into the model's ``store.book``, so the
functions cannot take a different driver; the steps are re-expressed here over
the real routes and checked against the same literals. Rows that need
activity, totals or positions (none exist in this slice) are named and skipped.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from tests.financial_accounts.conftest import ALICE, AccountsApi

SANTO_DOMINGO = ZoneInfo("America/Santo_Domingo")
CLOCK = datetime(2026, 9, 1, 9, 0, tzinfo=SANTO_DOMINGO)


def local(day: int, hour: int = 9) -> str:
    return datetime(2026, 9, day, hour, 0, tzinfo=SANTO_DOMINGO).isoformat()


class Refused(Exception):
    def __init__(self, problem: dict[str, Any]) -> None:
        super().__init__(problem["code"])
        self.problem = problem


def outcome(action: Callable[[], object]) -> str:
    """The reference's outcome grammar, derived from the problem the route returns."""

    try:
        action()
    except Refused as error:
        code = error.problem["code"]
        if code == "stale_version":
            return "StaleVersion"
        if code == "idempotency_conflict":
            return "IdempotencyConflict"
        return f"InvalidInput:{code}"
    return "ok"


class ProductionScene:
    """The reference ``Scene`` surface, over the routes.

    The reference clock is injected as the explicit balance date, because a
    production request has no scene clock; every other step is the same call.
    """

    def __init__(self, api: AccountsApi) -> None:
        self.api = api

    def account(
        self,
        name: str | None,
        type: str = "checking",
        currency: str = "DOP",
        entered=None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"type": type, "currency": currency, "nickname": name}
        if entered is not None:
            body["amount"] = entered
            body["as_of"] = CLOCK.isoformat()
        # The reference key may contain spaces; the wire grammar is visible ASCII.
        key = f"create:{name}:{type}:{currency}".replace(" ", "_")
        return self._ok(self.api.create(body, key=key))

    def reopen(self, account: dict[str, Any]) -> dict[str, Any]:
        return self._ok(self.api.get(account["id"]))

    def edit_account(
        self, account_id: str, expected_version: int, **fields
    ) -> dict[str, Any]:
        return self._ok(
            self.api.edit(account_id, {"expected_version": expected_version, **fields})
        )

    def correct(
        self, account_id: str, expected_revision: int, reason: str, **fields
    ) -> dict[str, Any]:
        # Reopen for the caller-visible account version the opening write binds.
        expected_version = self.reopen({"id": account_id})["version"]
        return self._ok(
            self.api.opening(
                account_id,
                {
                    "expected_version": expected_version,
                    "expected_revision": expected_revision,
                    "reason": reason,
                    **fields,
                },
            )
        )

    def balance(self, account: dict[str, Any]) -> dict[str, Any]:
        current = self.reopen(account)["balance"]
        if current["state"] == "unknown":
            return {"state": "unknown", "activity_since_tracking": 0}
        return {
            "state": "known",
            "amount": current["amount_minor"],
            "as_of": current["as_of"],
            "basis": current["basis"],
        }

    def amount(self, account: dict[str, Any]) -> int | None:
        return self.reopen(account)["balance"]["amount_minor"]

    def revisions(self, account: dict[str, Any]) -> int:
        return len(self.reopen(account)["opening"]["revisions"])

    def _ok(self, response) -> dict[str, Any]:  # noqa: ANN001
        if response.status_code >= 400:
            raise Refused(response.json())
        return response.json()


@pytest.fixture
def scene(client: TestClient) -> ProductionScene:
    return ProductionScene(AccountsApi(client, ALICE))


def test_clavito_large_opening(scene: ProductionScene) -> None:
    clavito = scene.account("Clavito", "savings", "DOP", "250000.00")
    assert scene.balance(clavito) == {
        "state": "known",
        "amount": 25_000_000,
        "as_of": "2026-09-01T09:00:00-04:00",
        "basis": "opening",
    }
    # "totals" needs activity reads; outside this slice.


@pytest.mark.usefixtures("legacy_blank_accounts")
def test_blank_opening_unknown(scene: ProductionScene) -> None:
    wallet = scene.account(None, "cash", "DOP")
    assert wallet["nickname"] is None
    assert scene.balance(wallet) == {"state": "unknown", "activity_since_tracking": 0}
    # "balance_after", "totals" and "position" need an expense; outside this slice.


@pytest.mark.usefixtures("legacy_blank_accounts")
def test_first_slice_create_reopen_edit(scene: ProductionScene) -> None:
    created = scene.account("Cuenta nomina", "checking", "DOP", "12500.00")
    unnamed = scene.account(None, "cash", "USD")
    reopened = scene.reopen(created)
    first = {
        "nickname": reopened["nickname"],
        "type": reopened["type"],
        "currency": reopened["currency"],
        "balance": scene.balance(reopened),
        "version": reopened["version"],
    }
    edited = scene.edit_account(
        created["id"], reopened["version"], nickname="Nomina", type="savings"
    )
    stale = outcome(lambda: scene.edit_account(created["id"], 1, nickname="Otra"))
    scene.correct(created["id"], 1, "typo in starting balance", amount="12000.00")
    redated = outcome(
        lambda: scene.correct(
            created["id"], 2, "balance was from the 1st", as_of=local(1, 8)
        )
    )
    result = {
        "opening_date_edit_without_activity": redated,
        "reopened": first,
        "unnamed_account": [unnamed["nickname"], scene.balance(unnamed)],
        "edited": [edited["nickname"], edited["type"], edited["version"]],
        "stale_edit": stale,
        "balance_after_opening_correction": scene.amount(created),
        "opening_revisions": scene.revisions(created),
    }
    assert result == {
        "opening_date_edit_without_activity": "ok",
        "reopened": {
            "nickname": "Cuenta nomina",
            "type": "checking",
            "currency": "DOP",
            "balance": {
                "state": "known",
                "amount": 1_250_000,
                "as_of": "2026-09-01T09:00:00-04:00",
                "basis": "opening",
            },
            "version": 1,
        },
        "unnamed_account": [None, {"state": "unknown", "activity_since_tracking": 0}],
        "edited": ["Nomina", "savings", 2],
        "stale_edit": "StaleVersion",
        "balance_after_opening_correction": 1_200_000,
        "opening_revisions": 3,
    }
    # "catalog_untouched" and "totals_after_opening_correction" read the
    # category catalog and activity totals; neither exists in this slice.


def test_multiple_precisions(scene: ProductionScene) -> None:
    yen = scene.account("Yen", "cash", "JPY", "1500")
    dinar = scene.account("Dinar", "cash", "KWD", "1.234")
    pesos = scene.account("Pesos", "cash", "DOP", "10.50")
    assert {
        "minor_units": [scene.amount(yen), scene.amount(dinar), scene.amount(pesos)],
        "jpy_fraction": outcome(lambda: scene.account("Yen2", "cash", "JPY", "1500.5")),
        "dop_three_decimals": outcome(
            lambda: scene.account("Pesos2", "cash", "DOP", "1.005")
        ),
        "unknown_currency": outcome(lambda: scene.account("Zeta", "cash", "ZZZ", "1")),
    } == {
        "minor_units": [1500, 1234, 1050],
        "jpy_fraction": "InvalidInput:amount_precision",
        "dop_three_decimals": "InvalidInput:amount_precision",
        "unknown_currency": "InvalidInput:currency_unsupported",
    }
    # "positions" needs the position read; outside this slice.


def test_duplicate_submission_create_part(scene: ProductionScene) -> None:
    cash = scene.account("Efectivo", "cash", "DOP", "1000.00")
    again = scene.account("Efectivo", "cash", "DOP", "1000.00")
    changed = outcome(lambda: scene.account("Efectivo", "cash", "DOP", "2000.00"))
    assert {
        "accounts": len(scene.api.list().json()["accounts"]),
        "same_account_returned": again["id"] == cash["id"],
        "create_changed_body": changed,
    } == {
        "accounts": 1,
        "same_account_returned": True,
        "create_changed_body": "IdempotencyConflict",
    }
    # The confirm rows need activity drafts; outside this slice.


@pytest.mark.usefixtures("legacy_blank_accounts")
def test_account_edit_rules_account_rows(scene: ProductionScene) -> None:
    empty = scene.account("  Clavito  ", "savings", "DOP")
    opened = scene.account("Solo apertura", "checking", "DOP", "100.00")
    cleared = scene.edit_account(empty["id"], 1, nickname="   ")
    results = {
        "trimmed": empty["nickname"],
        "blank_clears_nickname": cleared["nickname"],
        "long_nickname": outcome(
            lambda: scene.edit_account(empty["id"], 2, nickname="x" * 61)
        ),
        "currency_on_empty": scene.edit_account(empty["id"], 2, currency="USD")[
            "currency"
        ],
        "currency_on_opened": outcome(
            lambda: scene.edit_account(opened["id"], 1, currency="USD")
        ),
        "nature_flip_on_opened": outcome(
            lambda: scene.edit_account(opened["id"], 1, type="credit_card")
        ),
        "same_nature_on_opened": scene.edit_account(opened["id"], 1, type="savings")[
            "type"
        ],
        "stale_version": outcome(
            lambda: scene.edit_account(opened["id"], 1, nickname="Otra")
        ),
    }
    archived = scene.edit_account(opened["id"], 2, archived=True)
    results.update(
        archived_version=archived["version"],
        correct_on_archived=outcome(
            lambda: scene.correct(opened["id"], 1, "typo", amount="150.00")
        ),
        archived_balance_kept=scene.amount(opened),
    )
    assert results == {
        "trimmed": "Clavito",
        "blank_clears_nickname": None,
        "long_nickname": "InvalidInput:nickname_invalid",
        "currency_on_empty": "USD",
        "currency_on_opened": "InvalidInput:currency_locked",
        "nature_flip_on_opened": "InvalidInput:nature_change_requires_empty_account",
        "same_nature_on_opened": "savings",
        "stale_version": "StaleVersion",
        "archived_version": 3,
        "correct_on_archived": "ok",
        "archived_balance_kept": 15_000,
    }
    # "type_after_activity", "archived_draft_*" and "archived_still_in_totals"
    # need activity and totals; outside this slice.
