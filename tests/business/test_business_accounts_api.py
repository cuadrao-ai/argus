"""POST /business/accounts through the real app: the owner creates the account
an expense is paid from, an exact replay answers the same account, and a
client's accountant cannot create one in the owner's Business."""

from __future__ import annotations

from uuid import uuid4

from tests.business.test_business_api import Owner, alice, bob  # noqa: F401
from tests.business.test_business_switcher_api import GRANT, _grant

BODY = {"nickname": "Caja chica", "type": "cash", "currency": "DOP"}


def test_the_owner_creates_one_account_and_a_replay_answers_the_same_one(
    alice: Owner,  # noqa: F811
) -> None:
    key = str(uuid4())
    created = alice.post("/accounts", BODY, key=key)
    assert created.status_code == 201, created.text
    account = created.json()
    assert {k: account[k] for k in ("nickname", "type", "currency")} == BODY
    replay = alice.post("/accounts", BODY, key=key)
    assert replay.status_code == 200, replay.text
    assert replay.json() == account
    listed = alice.get("/workspace").json()
    assert [a["id"] for a in listed["accounts"]] == [account["id"]]
    assert listed["currencies"] == ["DOP"]


def test_an_accountant_cannot_create_an_account_in_the_clients_business(
    alice: Owner,  # noqa: F811
    bob: Owner,  # noqa: F811
) -> None:
    grant = _grant(alice, bob)
    refused = bob.post("/accounts", BODY, key=str(uuid4()), **{GRANT: grant})
    assert (refused.status_code, refused.json()["code"]) == (
        403,
        "business_permission_denied",
    )
    assert alice.get("/workspace").json()["accounts"] == []
