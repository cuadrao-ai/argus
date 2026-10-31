"""Canonical default-off Household wire, consent, and retry boundaries."""

from uuid import uuid4

from tests.household.conftest import HouseholdApi


def test_create_preview_accept_and_named_sharing(alice: HouseholdApi, bob: HouseholdApi):
    key = str(uuid4())
    created = alice.create_household({"name": "Casa", "display_name": "Alice"}, key)
    assert created.status_code == 201, created.text
    hid = created.json()["household_id"]
    assert (
        alice.create_household({"name": "Casa", "display_name": "Alice"}, key).json()[
            "household_id"
        ]
        == hid
    )
    assert bob.get_household(hid).status_code == 404
    invitation = alice.invite(hid).json()["invitation"]
    preview = bob.write("/household-invitations/preview", {"token": invitation["token"]})
    assert preview.json()["available"]
    assert bob.list_households().json()["households"] == []
    accepted = bob.accept(invitation["token"])
    assert accepted.status_code == 200, accepted.text
    mid = accepted.json()["membership_id"]
    assert bob.accept(invitation["token"]).json()["membership_id"] == mid
    assert bob.shared_accounts(hid).json()["accounts"] == []
    aid = alice.create_account(
        {"type": "checking", "currency": "DOP", "amount": "1000"}
    ).json()["id"]
    private = alice.create_account(
        {"type": "checking", "currency": "USD", "amount": "9000"}
    ).json()["id"]
    assert alice.share(hid, aid, mid).status_code == 201
    accounts = bob.shared_accounts(hid).json()["accounts"]
    assert [a["account_id"] for a in accounts] == [aid]
    assert accounts[0]["permission"] == "view"
    assert (
        bob.share(
            hid, private, alice.get_household(hid).json()["membership_id"]
        ).status_code
        == 403
    )
    assert bob.invite(hid).status_code == 403
    members = bob.get_household(hid).json()["members"]
    assert len(members) == 2 and {m["role"] for m in members} == {"admin", "member"}


def test_departure_replay_keeps_original_incarnation_and_rejoin_private(
    alice: HouseholdApi, bob: HouseholdApi
):
    hid = alice.create_household().json()["household_id"]
    invitation = alice.invite(hid).json()["invitation"]
    mid = bob.accept(invitation["token"]).json()["membership_id"]
    aid = alice.create_account(
        {"type": "cash", "currency": "DOP", "amount": "20"}
    ).json()["id"]
    alice.share(hid, aid, mid)
    version = bob.get_household(hid).json()["version"]
    key = str(uuid4())
    args = {"expected_version": version}
    assert bob.write(f"/households/{hid}/leave", args, key=key).status_code == 200
    assert bob.write(f"/households/{hid}/leave", args, key=key).json()["replayed"]
    assert bob.accept(invitation["token"]).json()["state"] == "departed"
    fresh = alice.invite(hid).json()["invitation"]
    new = bob.accept(fresh["token"]).json()["membership_id"]
    assert new != mid
    assert bob.shared_accounts(hid).json()["accounts"] == []
    assert bob.accept(invitation["token"]).json()["membership_id"] == mid
    assert (
        alice.write(f"/households/{hid}/leave", version_household=hid).status_code == 409
    )
    assert (
        alice.write(
            f"/households/{hid}/transfer-admin",
            {"user_id": bob.user_id},
            version_household=hid,
        ).status_code
        == 200
    )
    assert (
        alice.write(f"/households/{hid}/leave", version_household=hid).status_code == 200
    )
    assert bob.get_household(hid).json()["admin_user_id"] == bob.user_id


def test_flag_off_hides_surface(monkeypatch, gateway) -> None:  # noqa: ANN001
    from unittest.mock import patch

    from argus.api import state as api_state
    from argus.api.main import app
    from fastapi.testclient import TestClient

    monkeypatch.setenv("CUADRAO_HOUSEHOLDS_ENABLED", "false")
    monkeypatch.setenv("ARGUS_FINANCIAL_ACCOUNTS_ENABLED", "true")
    monkeypatch.setenv("CUADRAO_MOCK_AUTH", "false")
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    with (
        patch.object(api_state, "supabase_gateway", gateway),
        patch("argus.api.dependencies.auth_session_is_active", return_value=True),
        TestClient(app) as client,
    ):
        response = client.get(
            "/api/v1/households", headers={"Authorization": "Bearer registered-alice"}
        )
        assert (response.status_code, response.json()["code"]) == (
            404,
            "households_unavailable",
        )


def test_financial_adapter_requires_durable_authorization(alice: HouseholdApi):
    hid = alice.create_household().json()["household_id"]
    response = alice._client.get(
        f"/api/v1/households/{hid}/snapshot", headers=alice._headers
    )
    assert response.status_code == 404
