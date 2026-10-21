"""Route-level acceptance for the first slice through the real auth dependency."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from argus.api import state as api_state
from argus.api.main import app
from fastapi.testclient import TestClient

from tests.financial_accounts.conftest import ALICE, AccountsApi

CHECKING = {"type": "checking", "currency": "DOP", "nickname": "Cuenta nomina"}


def _created(api: AccountsApi, body: dict, key: str | None = None) -> dict:
    response = api.create(body, key=key or str(uuid4()))
    assert response.status_code == 201, response.text
    return response.json()


def test_create_then_reopen_returns_the_same_accepted_data(alice: AccountsApi) -> None:
    created = _created(alice, {**CHECKING, "amount": "12500.00"})
    reopened = alice.get(created["id"])
    assert reopened.status_code == 200
    assert reopened.json() == created
    assert created["balance"] == {
        "state": "known",
        "amount_minor": 1_250_000,
        "amount": "12500.00",
        "as_of": created["opening"]["as_of"],
        "basis": "opening",
        "activity_since_tracking_minor": 0,
        "credit_minor": None,
    }
    assert created["opening"]["revision"] == 1
    assert created["opening"]["time_zone"] == "America/Santo_Domingo"
    assert created["version"] == 1
    assert created["nature"] == "asset"
    assert created["currency_fraction_digits"] == 2
    listed = alice.list().json()["accounts"]
    assert [item["id"] for item in listed] == [created["id"]]


def test_reads_format_a_stored_currency_after_tender_retirement(
    alice: AccountsApi, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GET/list must not re-check tender membership on a stored code.

    A CLDR upgrade can drop a currency from the current tender set after an
    account already stores it. Response construction sits outside the route's
    domain-error mapping, so a tender re-check on read would 500 the owner.
    """

    created = _created(alice, {**CHECKING, "amount": "12500.00"})
    # Simulate retirement: DOP is no longer among the codes writes may name.
    still_writable = frozenset({"USD", "JPY", "EUR"})
    monkeypatch.setattr(
        "argus.domain.recording.currency.currency_codes",
        lambda: still_writable,
    )

    reopened = alice.get(created["id"])
    assert reopened.status_code == 200, reopened.text
    body = reopened.json()
    assert body["currency"] == "DOP"
    assert body["currency_fraction_digits"] == 2
    assert body["balance"]["amount"] == "12500.00"
    assert body["opening"]["amount"] == "12500.00"

    listed = alice.list()
    assert listed.status_code == 200, listed.text
    assert listed.json()["accounts"][0]["balance"]["amount"] == "12500.00"

    # Opening corrections still format under the stored code.
    corrected = alice.opening(
        created["id"],
        {
            "expected_version": 1,
            "expected_revision": 1,
            "amount": "12000.00",
            "reason": "typo after tender retirement",
        },
    )
    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["balance"]["amount"] == "12000.00"

    # Writes that name a currency still enforce the current tender set.
    refused = alice.edit(
        created["id"],
        {"expected_version": corrected.json()["version"], "currency": "DOP"},
    )
    assert (refused.status_code, refused.json()["code"]) == (
        422,
        "currency_unsupported",
    )


def test_blank_opening_is_a_recorded_zero(alice: AccountsApi) -> None:
    blank = _created(alice, {"type": "cash", "currency": "DOP"})
    assert blank["balance"]["state"] == "known"
    assert blank["balance"]["amount"] == "0.00"
    assert blank["opening"]["amount_minor"] == 0


@pytest.mark.usefixtures("legacy_blank_accounts")
def test_known_zero_differs_from_legacy_unknown(alice: AccountsApi) -> None:
    zero = _created(alice, {"type": "cash", "currency": "DOP", "amount": "0"})
    unknown = _created(alice, {"type": "cash", "currency": "DOP"})
    assert zero["balance"]["state"] == "known"
    assert zero["balance"]["amount_minor"] == 0
    assert unknown["balance"] == {
        "state": "unknown",
        "amount_minor": None,
        "amount": None,
        "as_of": None,
        "basis": None,
        "activity_since_tracking_minor": 0,
        "credit_minor": None,
    }
    assert unknown["opening"] is None
    assert unknown["nickname"] is None


def test_a_liability_typed_as_amount_owed_reads_negative_to_the_owner(
    alice: AccountsApi,
) -> None:
    card = _created(
        alice, {"type": "credit_card", "currency": "DOP", "amount": "15000.00"}
    )
    assert card["nature"] == "liability"
    assert card["balance"]["amount_minor"] == -1_500_000
    assert card["balance"]["amount"] == "-15000.00"


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ({"type": "cash", "currency": "JPY", "amount": "1500.5"}, "amount_precision"),
        ({"type": "cash", "currency": "DOP", "amount": "1.005"}, "amount_precision"),
        ({"type": "cash", "currency": "DOP", "amount": "12,50"}, "amount_invalid"),
        ({"type": "cash", "currency": "DOP", "amount": "abc"}, "amount_invalid"),
        (
            {"type": "cash", "currency": "DOP", "amount": "92233720368547758.08"},
            "amount_out_of_range",
        ),
        ({"type": "cash", "currency": "JPY", "amount": "9" * 40}, "amount_out_of_range"),
        ({"type": "cash", "currency": "ZZZ", "amount": "1"}, "currency_unsupported"),
        ({"type": "cash", "currency": "XXX"}, "currency_unsupported"),
        ({"type": "cash", "currency": "DOP", "nickname": "x" * 61}, "nickname_invalid"),
        (
            {
                "type": "cash",
                "currency": "DOP",
                "amount": "1",
                "as_of": "2999-01-01T00:00:00Z",
            },
            "date_in_future",
        ),
        (
            {
                "type": "cash",
                "currency": "DOP",
                "amount": "1",
                "time_zone": "Mars/Olympus",
            },
            "time_zone_invalid",
        ),
    ],
)
def test_invalid_inputs_return_their_documented_code(
    alice: AccountsApi, body: dict, code: str
) -> None:
    response = alice.create(body, key=str(uuid4()))
    assert response.status_code == 422, response.text
    problem = response.json()
    assert problem["code"] == code
    assert problem["type"] == f"https://api.argus.app/problems/{code.replace('_', '-')}"
    assert alice.list().json()["accounts"] == []


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ({"type": "wallet", "currency": "DOP"}, "validation_error"),
        (
            {"type": "cash", "currency": "DOP", "ownership_share_bps": 0},
            "validation_error",
        ),
        (
            {"type": "cash", "currency": "DOP", "ownership_share_bps": 10_001},
            "validation_error",
        ),
        ({"type": "cash", "currency": "DOP", "unexpected": 1}, "validation_error"),
    ],
)
def test_shape_errors_are_validation_errors(
    alice: AccountsApi, body: dict, code: str
) -> None:
    response = alice.create(body, key=str(uuid4()))
    assert response.status_code == 422
    assert response.json()["code"] == code


@pytest.mark.parametrize(
    ("currency", "amount", "minor", "rendered", "digits"),
    [
        ("JPY", "1500", 1500, "1500", 0),
        ("KWD", "1.234", 1234, "1.234", 3),
        ("DOP", "10.50", 1050, "10.50", 2),
    ],
)
def test_currency_precision_follows_cldr(
    alice: AccountsApi, currency: str, amount: str, minor: int, rendered: str, digits: int
) -> None:
    created = _created(alice, {"type": "cash", "currency": currency, "amount": amount})
    assert created["balance"]["amount_minor"] == minor
    assert created["balance"]["amount"] == rendered
    assert created["currency_fraction_digits"] == digits


def test_duplicate_create_retries_make_one_account(alice: AccountsApi) -> None:
    body = {
        "type": "cash",
        "currency": "DOP",
        "nickname": "Efectivo",
        "amount": "1000.00",
    }
    first = alice.create(body, key="create-efectivo")
    again = alice.create(body, key="create-efectivo")
    assert first.status_code == 201
    assert again.status_code == 200
    assert again.json() == first.json()
    changed = alice.create({**body, "amount": "2000.00"}, key="create-efectivo")
    assert changed.status_code == 409
    assert changed.json()["code"] == "idempotency_conflict"
    assert len(alice.list().json()["accounts"]) == 1


def test_the_same_key_is_a_different_reservation_for_another_user(
    alice: AccountsApi, bob: AccountsApi
) -> None:
    body = {"type": "cash", "currency": "DOP", "amount": "1000.00"}
    assert alice.create(body, key="shared-key").status_code == 201
    assert bob.create(body, key="shared-key").status_code == 201
    assert len(alice.list().json()["accounts"]) == 1
    assert len(bob.list().json()["accounts"]) == 1


@pytest.mark.parametrize(
    ("key", "status", "code"),
    [
        (None, 400, "idempotency_key_required"),
        ("   ", 400, "idempotency_key_required"),
        ("has space", 422, "validation_error"),
        ("x" * 129, 422, "validation_error"),
    ],
)
def test_idempotency_key_grammar(
    alice: AccountsApi, key: str | None, status: int, code: str
) -> None:
    response = alice.create({"type": "cash", "currency": "DOP"}, key=key)
    assert (response.status_code, response.json()["code"]) == (status, code)


def test_unauthenticated_and_guest_requests_are_refused(
    alice: AccountsApi, guest: AccountsApi, anonymous: AccountsApi
) -> None:
    owned = _created(alice, {**CHECKING, "amount": "1.00"})
    body = {"type": "cash", "currency": "DOP", "amount": "1.00"}

    assert anonymous.create(body, key=str(uuid4())).status_code == 401
    assert anonymous.list().status_code == 401
    assert anonymous.get(owned["id"]).status_code == 401

    for response in (
        guest.create(body, key=str(uuid4())),
        guest.list(),
        guest.get(owned["id"]),
        guest.edit(owned["id"], {"expected_version": 1, "nickname": "x"}),
        guest.opening(
            owned["id"],
            {
                "expected_version": 1,
                "expected_revision": 1,
                "amount": "2",
                "reason": "r",
            },
        ),
    ):
        assert response.status_code == 403, response.text
        assert response.json()["code"] == "account_conversion_required"
    assert alice.get(owned["id"]).json() == owned


def test_a_malformed_account_id_is_not_found(alice: AccountsApi) -> None:
    for response in (
        alice.get("not-a-uuid"),
        alice.edit("not-a-uuid", {"expected_version": 1, "nickname": "x"}),
        alice.opening(
            "not-a-uuid",
            {"expected_version": 1, "expected_revision": None, "amount": "1"},
        ),
    ):
        assert (response.status_code, response.json()["code"]) == (
            404,
            "financial_account_not_found",
        ), response.text


def test_two_users_cannot_read_or_mutate_each_others_accounts(
    alice: AccountsApi, bob: AccountsApi
) -> None:
    owned = _created(alice, {**CHECKING, "amount": "100.00"})
    assert bob.list().json()["accounts"] == []
    for response in (
        bob.get(owned["id"]),
        bob.edit(owned["id"], {"expected_version": 1, "nickname": "Mine now"}),
        bob.opening(
            owned["id"],
            {
                "expected_version": 1,
                "expected_revision": 1,
                "amount": "0",
                "reason": "drain",
            },
        ),
    ):
        assert response.status_code == 404, response.text
        assert response.json()["code"] == "financial_account_not_found"
    assert alice.get(owned["id"]).json() == owned


@pytest.mark.usefixtures("legacy_blank_accounts")
def test_edits_follow_the_locks_and_expected_version(alice: AccountsApi) -> None:
    opened = _created(alice, {**CHECKING, "amount": "12500.00"})
    empty = _created(alice, {"type": "checking", "currency": "DOP"})

    edited = alice.edit(
        opened["id"], {"expected_version": 1, "nickname": "  Nomina ", "type": "savings"}
    )
    assert edited.status_code == 200
    assert (
        edited.json()["nickname"],
        edited.json()["type"],
        edited.json()["version"],
    ) == (
        "Nomina",
        "savings",
        2,
    )

    stale = alice.edit(opened["id"], {"expected_version": 1, "nickname": "Otra"})
    assert (stale.status_code, stale.json()["code"]) == (409, "stale_version")
    assert alice.get(opened["id"]).json()["nickname"] == "Nomina"

    cleared = alice.edit(opened["id"], {"expected_version": 2, "nickname": "   "})
    assert cleared.json()["nickname"] is None

    for body, code in (
        ({"type": "credit_card"}, "nature_change_requires_empty_account"),
        ({"currency": "USD"}, "currency_locked"),
        ({"nickname": "x" * 61}, "nickname_invalid"),
        ({"currency": "ZZZ"}, "currency_unsupported"),
    ):
        response = alice.edit(opened["id"], {"expected_version": 3, **body})
        assert (response.status_code, response.json()["code"]) == (
            422,
            code,
        ), response.text
    assert alice.get(opened["id"]).json()["version"] == 3

    flipped = alice.edit(
        empty["id"], {"expected_version": 1, "type": "credit_card", "currency": "USD"}
    )
    assert flipped.status_code == 200
    assert (
        flipped.json()["type"],
        flipped.json()["currency"],
        flipped.json()["nature"],
    ) == (
        "credit_card",
        "USD",
        "liability",
    )

    shared = alice.edit(
        opened["id"], {"expected_version": 3, "ownership_share_bps": 5000}
    )
    assert shared.json()["ownership_share_bps"] == 5000


def test_archive_changes_no_balance_and_restore_returns_it(alice: AccountsApi) -> None:
    created = _created(alice, {**CHECKING, "amount": "13500.00"})
    archived = alice.edit(created["id"], {"expected_version": 1, "archived": True}).json()
    assert archived["archived"] is True
    assert archived["balance"] == created["balance"]
    assert archived["opening"] == created["opening"]
    listed = alice.list().json()["accounts"]
    assert [(item["id"], item["archived"]) for item in listed] == [(created["id"], True)]
    restored = alice.edit(
        created["id"], {"expected_version": 2, "archived": False}
    ).json()
    assert restored["archived"] is False
    assert restored["balance"] == created["balance"]


@pytest.mark.usefixtures("legacy_blank_accounts")
def test_opening_write_binds_caller_visible_account_version(alice: AccountsApi) -> None:
    """Opening must refuse a stale client view of account metadata.

    Before this guard, PUT …/opening checked only expected_revision and CASed
    the account version the server had just read. A concurrent currency/type
    edit between the client's GET and the opening PUT still applied, because
    the server re-read the new version and signed under metadata the caller
    never saw.
    """

    created = _created(alice, {"type": "checking", "currency": "DOP"})
    assert created["version"] == 1
    assert created["opening"] is None
    seen_version = created["version"]

    concurrent = alice.edit(
        created["id"],
        {"expected_version": 1, "currency": "USD", "type": "credit_card"},
    )
    assert concurrent.status_code == 200, concurrent.text
    assert concurrent.json()["version"] == 2
    assert concurrent.json()["nature"] == "liability"

    stale = alice.opening(
        created["id"],
        {
            "expected_version": seen_version,
            "expected_revision": None,
            "amount": "100.00",
        },
    )
    assert (stale.status_code, stale.json()["code"]) == (409, "stale_version")
    unchanged = alice.get(created["id"]).json()
    assert unchanged["opening"] is None
    assert unchanged["version"] == 2
    assert unchanged["currency"] == "USD"
    assert unchanged["type"] == "credit_card"

    fresh = alice.opening(
        created["id"],
        {
            "expected_version": 2,
            "expected_revision": None,
            "amount": "100.00",
        },
    )
    assert fresh.status_code == 200, fresh.text
    assert fresh.json()["balance"]["amount_minor"] == -10_000
    assert fresh.json()["version"] == 3
    assert fresh.json()["opening"]["revision"] == 1


def test_corrections_keep_history_and_enforce_expected_revision(
    alice: AccountsApi,
) -> None:
    created = _created(alice, {**CHECKING, "amount": "12500.00"})
    account_id = created["id"]

    corrected = alice.opening(
        account_id,
        {
            "expected_version": 1,
            "expected_revision": 1,
            "amount": "12000.00",
            "reason": "typo in starting balance",
        },
    )
    assert corrected.status_code == 200, corrected.text
    body = corrected.json()
    assert body["balance"]["amount_minor"] == 1_200_000
    assert body["version"] == 2
    assert body["opening"]["revision"] == 2
    assert [
        (item["revision"], item["amount_minor"], item["reason"])
        for item in body["opening"]["revisions"]
    ] == [
        (1, 1_250_000, None),
        (2, 1_200_000, "typo in starting balance"),
    ]
    assert body["opening"]["revisions"][0]["as_of"] == created["opening"]["as_of"]

    stale = alice.opening(
        account_id,
        {
            "expected_version": 2,
            "expected_revision": 1,
            "amount": "1.00",
            "reason": "late",
        },
    )
    assert (stale.status_code, stale.json()["code"]) == (409, "stale_version")
    assert alice.get(account_id).json() == body

    redated = alice.opening(
        account_id,
        {
            "expected_version": 2,
            "expected_revision": 2,
            "as_of": "2026-09-01T08:00:00-04:00",
            "reason": "balance was from the 1st",
        },
    )
    assert redated.status_code == 200, redated.text
    assert redated.json()["opening"]["revision"] == 3
    assert redated.json()["opening"]["amount_minor"] == 1_200_000
    assert redated.json()["opening"]["as_of"] == "2026-09-01T08:00:00-04:00"
    assert redated.json()["balance"]["as_of"] == "2026-09-01T08:00:00-04:00"
    assert len(redated.json()["opening"]["revisions"]) == 3

    for body, code in (
        (
            {"expected_version": 3, "expected_revision": 3, "amount": "1"},
            "reason_required",
        ),
        (
            {"expected_version": 3, "expected_revision": 3, "reason": "nothing changes"},
            "field_missing",
        ),
        (
            {
                "expected_version": 3,
                "expected_revision": 3,
                "amount": "1",
                "reason": "x" * 201,
            },
            "reason_invalid",
        ),
        (
            {
                "expected_version": 3,
                "expected_revision": 3,
                "amount": "1.005",
                "reason": "r",
            },
            "amount_precision",
        ),
        (
            {
                "expected_version": 3,
                "expected_revision": 3,
                "as_of": "2999-01-01T00:00:00Z",
                "reason": "r",
            },
            "date_in_future",
        ),
    ):
        response = alice.opening(account_id, body)
        assert (response.status_code, response.json()["code"]) == (
            422,
            code,
        ), response.text
    assert alice.get(account_id).json()["opening"]["revision"] == 3


@pytest.mark.usefixtures("legacy_blank_accounts")
def test_an_unknown_balance_can_be_recorded_later_with_no_expected_revision(
    alice: AccountsApi,
) -> None:
    created = _created(alice, {"type": "cash", "currency": "USD"})
    premature = alice.opening(
        created["id"],
        {
            "expected_version": 1,
            "expected_revision": 1,
            "amount": "5",
            "reason": "r",
        },
    )
    assert (premature.status_code, premature.json()["code"]) == (409, "stale_version")
    missing = alice.opening(
        created["id"], {"expected_version": 1, "expected_revision": None}
    )
    assert (missing.status_code, missing.json()["code"]) == (422, "field_missing")

    recorded = alice.opening(
        created["id"],
        {"expected_version": 1, "expected_revision": None, "amount": "5.25"},
    )
    assert recorded.status_code == 200, recorded.text
    assert recorded.json()["balance"]["amount_minor"] == 525
    assert recorded.json()["opening"]["revision"] == 1
    assert recorded.json()["opening"]["reason"] is None
    assert recorded.json()["version"] == 2

    twice = alice.opening(
        created["id"],
        {"expected_version": 1, "expected_revision": None, "amount": "9"},
    )
    assert (twice.status_code, twice.json()["code"]) == (409, "stale_version")


def test_flag_off_hides_the_surface_from_everyone(
    monkeypatch: pytest.MonkeyPatch, surface_env: None, gateway: MagicMock
) -> None:
    monkeypatch.setenv("ARGUS_FINANCIAL_ACCOUNTS_ENABLED", "false")
    with (
        patch.object(api_state, "supabase_gateway", gateway),
        patch("argus.api.dependencies.auth_session_is_active", return_value=True),
        TestClient(app) as client,
    ):
        registered = AccountsApi(client, ALICE)
        nobody = AccountsApi(client, None)
        for response in (
            registered.create({"type": "cash", "currency": "DOP"}, key="k"),
            registered.list(),
            nobody.list(),
            nobody.get(str(uuid4())),
        ):
            assert response.status_code == 404
            assert response.json()["code"] == "financial_accounts_unavailable"
        gateway.get_auth_user_from_token.assert_not_called()
