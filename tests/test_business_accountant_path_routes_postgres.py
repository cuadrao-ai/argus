"""Invited recipients pass Auth admission and explicitly accept before Business access.
Profile and listing reads keep pending invitations unchanged; financial approval
remains Owner-only after an Editor joins.
"""

from __future__ import annotations

import io
import json
import secrets
import zipfile
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from argus.api import state as api_state
from argus.api.main import app
from argus.api.routers import auth as auth_router
from fastapi.testclient import TestClient
from psycopg import Connection
from psycopg.types.json import Jsonb

from tests import test_financial_accounts_postgres as shared
from tests.business_cleanup import delete_spaces
from tests.local_supabase_support import local_supabase_gateway
from tests.test_business_scope_switch_routes_postgres import (
    API,
    ENV,
    PERIOD,
    _code,
    seed_business_rnc,
)
from tests.test_business_scope_switch_routes_postgres import (
    pytestmark as _local_supabase,
)
from tests.test_financial_accounts_api_postgres import ORIGIN

pytestmark = _local_supabase
ALLOWLIST_ONLY = {
    **ENV,
    "CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED": "false",
    "CUADRAO_BUSINESS_INVITE_ADMISSION_ENABLED": "true",
}
CAPTCHA = "local-captcha-proof"
GRANT = "X-Business-Grant"


@dataclass
class Account:
    email: str
    password: str
    id: str = ""
    headers: dict[str, str] | None = None


def _allow(email: str) -> None:
    with Connection.connect(shared.DSN) as db:
        db.execute(
            "insert into public.private_alpha_allowlist (email, role) values (%s, 'user')",
            (email,),
        )


def _credentials(world, label: str) -> Account:  # noqa: ANN001
    """A fresh email and password; nothing exists in Auth until ``_create``."""

    account = Account(
        f"acct-{label}-{secrets.token_hex(4)}@example.test",
        f"Pw-{secrets.token_urlsafe(18)}",
    )
    world.emails.append(account.email)
    return account


def _create(world, account: Account) -> None:  # noqa: ANN001
    """A confirmed account made by the Auth admin API, so no email is sent."""

    user = world.gateway.client.auth.admin.create_user(
        {"email": account.email, "password": account.password, "email_confirm": True}
    )
    assert user.user is not None
    account.id = str(user.user.id)
    world.created.append(account.id)


def _login(world, account: Account):  # noqa: ANN001, ANN202
    return world.client.post(
        f"{API}/auth/login",
        json={
            "email": account.email,
            "password": account.password,
            "captcha_token": CAPTCHA,
        },
        headers=ORIGIN,
    )


def _signed_in(world, account: Account) -> Account:  # noqa: ANN001
    answer = _login(world, account)
    assert answer.status_code == 200, answer.text
    account.headers = {
        "Authorization": f"Bearer {answer.json()['session']['access_token']}",
        **ORIGIN,
    }
    return account


def _invite(world, email: str) -> None:  # noqa: ANN001
    given = world.client.post(
        f"{API}/business/access", json={"email": email}, headers=world.owner.headers
    )
    assert given.status_code == 201, given.text
    assert [i["email"] for i in given.json()["invites"]][-1] == email


def _invite_state(email: str) -> list[bool]:
    with Connection.connect(shared.DSN) as db:
        return [
            row[0]
            for row in db.execute(
                "select accepted_at is not null from public.business_access_invites"
                " where email=%s",
                (email,),
            ).fetchall()
        ]


def _grants_and_accepts(space_id: str, grantee_id: str) -> tuple[int, int]:
    with Connection.connect(shared.DSN) as db:
        grants = db.execute(
            "select count(*) from public.business_client_grants"
            " where space_id=%s and grantee_id=%s and revoked_at is null",
            (space_id, grantee_id),
        ).fetchone()[0]
        accepts = db.execute(
            "select count(*) from public.business_action_receipts"
            " where space_id=%s and command->>'action'='accept_invite'"
            " and actor->>'actor_id'=%s",
            (space_id, grantee_id),
        ).fetchone()[0]
    return grants, accepts


def _with_ncf(draft_id: str) -> None:
    """The draft carries a printed NCF, as a receipt read would leave it."""

    with Connection.connect(shared.DSN) as db:
        db.execute(
            "update public.financial_import_events set resolution ="
            " jsonb_set(resolution, '{business,facts,fiscal}', %s) where id=%s",
            (
                Jsonb(
                    {
                        "rnc": {"state": "unknown"},
                        "ncf": {
                            "state": "known",
                            "value": "B0100000001",
                            "origin": "extracted",
                            "verified": False,
                            "source_ids": [str(uuid4())],
                        },
                        "ecf": {"state": "unknown"},
                        "itbis": {"state": "unknown"},
                        "include_606": {"state": "unknown"},
                    }
                ),
                draft_id,
            ),
        )


def _post(world, path: str, body: dict, headers: dict):  # noqa: ANN001, ANN202
    return world.client.post(
        f"{API}{path}", json=body, headers={**headers, "Idempotency-Key": str(uuid4())}
    )


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch):  # noqa: ANN201
    """Allowlist mode. The owner is on the allowlist and has started a Business."""

    auth_router.reset_auth_attempt_limiter_for_tests()
    for name, value in ALLOWLIST_ONLY.items():
        monkeypatch.setenv(name, value)
    gateway = local_supabase_gateway()
    found = SimpleNamespace(gateway=gateway, created=[], emails=[])
    try:
        with (
            patch.object(api_state, "supabase_gateway", gateway),
            patch.object(api_state, "DATABASE_URL", shared.DSN),
            patch.object(api_state, "PERSISTENCE_MODE", "supabase"),
            TestClient(app, base_url="http://localhost:3000") as client,
        ):
            found.client = client
            found.owner = _credentials(found, "owner")
            _allow(found.owner.email)
            _create(found, found.owner)
            _signed_in(found, found.owner)
            started = client.post(
                f"{API}/business/space",
                json={"name": "Ferretería Prueba"},
                headers=found.owner.headers,
            )
            assert started.status_code == 201, started.text
            found.space_id = started.json()["id"]
            seed_business_rnc(client, found.owner.headers)
            yield found
    finally:
        with Connection.connect(shared.DSN) as db:
            for user_id in found.created:
                db.execute(
                    "update public.spaces set closed_at=coalesce(closed_at,clock_timestamp()) where created_by=%s and kind='business'",
                    (user_id,),
                )
                db.execute(
                    "delete from public.business_client_grants where grantee_id=%s or issuer_id=%s",
                    (user_id, user_id),
                )
            for email in found.emails:
                db.execute(
                    "delete from public.business_access_invites where email=%s", (email,)
                )
                db.execute(
                    "delete from public.private_alpha_allowlist where email=%s", (email,)
                )
            db.execute("set constraints all deferred")
            db.execute(
                "delete from public.financial_activity_groups where user_id=any(%s::uuid[])",
                (found.created,),
            )
            delete_spaces(db, "created_by=any(%s::uuid[])", (found.created,))
        for user_id in found.created:
            try:
                gateway.delete_auth_user(user_id)
            except Exception:  # noqa: BLE001
                pass


def _signup(world, account: Account):  # noqa: ANN001, ANN202
    return world.client.post(
        f"{API}/auth/signup",
        json={
            "age_confirmed_at": "2026-01-01T00:00:00Z",
            "email": account.email,
            "password": account.password,
            "captcha_token": CAPTCHA,
        },
        headers=ORIGIN,
    )


def test_an_invited_accountant_is_admitted_by_the_invite_and_works_from_the_first_listing(
    world,  # noqa: ANN001
) -> None:
    client, owner = world.client, world.owner
    accountant = _credentials(world, "contadora")
    stranger = _credentials(world, "extrana")

    # Off the allowlist and uninvited, signup, login and requests are refused.
    assert _code(_signup(world, accountant)) == (400, "auth_signup_failed")
    _create(world, stranger)
    assert _code(_login(world, stranger)) == (401, "unauthorized")
    session = world.gateway.login(
        email=stranger.email, password=stranger.password, captcha_token=CAPTCHA
    )
    bearer = {"Authorization": f"Bearer {session['session']['access_token']}", **ORIGIN}
    for path in ("/business/spaces", "/me"):
        assert _code(client.get(f"{API}{path}", headers=bearer)) == (
            403,
            "private_alpha_access_required",
        ), path

    # The invite admits exactly the invited email to signup and login; the
    # stranger stays refused; the recipient must still accept explicitly.
    _invite(world, accountant.email)
    assert _code(_login(world, stranger)) == (401, "unauthorized")
    signed_up = _signup(world, accountant)
    assert signed_up.status_code == 200, signed_up.text
    accountant.id = str(signed_up.json()["user"]["id"])
    world.created.append(accountant.id)
    assert _invite_state(accountant.email) == [False]
    assert _grants_and_accepts(world.space_id, accountant.id) == (0, 0)
    _signed_in(world, accountant)
    first = client.get(f"{API}/business/spaces", headers=accountant.headers)
    assert first.status_code == 200, first.text
    assert first.json()["spaces"] == []
    assert _grants_and_accepts(world.space_id, accountant.id) == (0, 0)
    [invitation] = client.get(
        f"{API}/business/invitations", headers=accountant.headers
    ).json()
    accepted = client.post(
        f"{API}/business/invitations/{invitation['id']}/accept",
        headers=accountant.headers,
        json={"space_id": world.space_id},
    )
    assert accepted.status_code == 200, accepted.text
    [business] = client.get(f"{API}/business/spaces", headers=accountant.headers).json()[
        "spaces"
    ]
    assert (
        business["space_id"],
        business["role"],
        business["capabilities"],
        business["access_seen"],
    ) == (world.space_id, "accountant", ["read", "prepare"], False)
    assert _invite_state(accountant.email) == [True]
    me = client.get(f"{API}/me", headers=accountant.headers)
    assert me.status_code == 200, me.text
    assert client.get(f"{API}/business/spaces", headers=accountant.headers).json()[
        "spaces"
    ] == [business]
    assert _grants_and_accepts(world.space_id, accountant.id) == (1, 1)
    chosen = {**accountant.headers, GRANT: business["grant_id"]}

    # The owner writes a note; a read leaves an NCF on it; the owner marks it Personal.
    note = _post(
        world,
        "/business/captures",
        {"text": "Pagué 850 en Ferretería Prueba"},
        owner.headers,
    )
    assert note.status_code == 200, note.text
    draft = note.json()["draft_id"]
    _with_ncf(draft)
    version = client.get(
        f"{API}/business/drafts/{draft}/dossier", headers=owner.headers
    ).json()["version"]
    marked = _post(
        world,
        f"/business/drafts/{draft}/personal",
        {"version": version, "personal": True},
        owner.headers,
    )
    assert marked.status_code == 200, marked.text

    # The accountant switches to the client, opens the record and answers the 606 question.
    notes = client.get(f"{API}/business/captures", headers=chosen)
    assert notes.status_code == 200, notes.text
    assert [item["draft_id"] for item in notes.json()["items"]] == [draft]
    record = client.get(f"{API}/business/drafts/{draft}/dossier", headers=chosen)
    assert record.status_code == 200, record.text
    opened = record.json()
    assert (
        opened["space_id"],
        sorted(opened["capabilities"]),
        opened["personal"],
        opened["fiscal_value"],
        opened.get("include_606"),
    ) == (world.space_id, ["prepare", "read"], True, "ncf", None)
    answered = _post(
        world,
        f"/business/drafts/{draft}/fiscal-inclusion",
        {"version": opened["version"], "include": True},
        chosen,
    )
    assert answered.status_code == 200, answered.text
    # A newcomer with no display name is named by the shared fallback.
    assert (answered.json()["include_606"], answered.json()["include_606_by"]) == (
        True,
        "Member",
    )
    assert (
        client.get(
            f"{API}/business/drafts/{draft}/dossier", headers=owner.headers
        ).json()["include_606"]
        is True
    )

    # The export package downloads under the grant.
    export = client.get(
        f"{API}/business/exports",
        params={"start": PERIOD["from"], "end": PERIOD["to"]},
        headers=chosen,
    )
    assert export.status_code == 200, export.text
    assert export.headers["content-type"] == "application/zip"
    package = zipfile.ZipFile(io.BytesIO(export.content))
    manifest = json.loads(package.read("manifest.json"))
    originals = [s["file"] for s in manifest["sources"]]
    assert sorted(package.namelist()) == sorted(
        [
            "manifest.json",
            "records.csv",
            "personal.csv",
            "records.xlsx",
            "unresolved.csv",
            "dgii/606-607.xlsx",
            "dgii/summary.json",
            *originals,
        ]
    )
    assert len(originals) == 3 and all(n.startswith("originals/") for n in originals)
    assert {tuple(s["draft_ids"]) for s in manifest["sources"]} == {(draft,)}
    assert (
        manifest["records"],
        manifest["unresolved_drafts"],
        manifest["evidence_complete"],
    ) == (
        [],
        [
            {
                "draft_id": draft,
                "version": 3,
                "review_state": "open",
                "occurred_on": None,
                "reason": "date_unknown",
            }
        ],
        True,
    )

    # Approval stays the owner's.
    refused = _post(
        world,
        f"/business/drafts/{draft}/approve",
        {"version": answered.json()["version"], "action": "record_expense"},
        chosen,
    )
    assert _code(refused) == (403, "business_permission_denied")


def test_profile_and_listing_reads_leave_invitation_pending(world) -> None:  # noqa: ANN001
    accountant = _credentials(world, "perfil")
    _invite(world, accountant.email)
    _allow(accountant.email)
    _create(world, accountant)
    _signed_in(world, accountant)

    me = world.client.get(f"{API}/me", headers=accountant.headers)
    assert me.status_code == 200, me.text
    assert _grants_and_accepts(world.space_id, accountant.id) == (0, 0)
    listed = world.client.get(f"{API}/business/spaces", headers=accountant.headers)
    assert [
        (s["space_id"], s["role"], s["capabilities"]) for s in listed.json()["spaces"]
    ] == []
    assert _grants_and_accepts(world.space_id, accountant.id) == (0, 0)


def test_an_invited_person_cannot_start_a_business_or_admit_anyone(world) -> None:  # noqa: ANN001
    """Admission does not chain. A person the gate admits only through a
    Business invitation or grant works in that Business and nowhere else: no
    Business of their own, no invitation issued, no ownership accepted. The
    hand-listed owner keeps every one of those powers."""

    client, owner = world.client, world.owner
    refused = (403, "private_alpha_access_required")
    invitee = _credentials(world, "invitada")
    outsider = _credentials(world, "ajena")
    _invite(world, invitee.email)
    signed_up = _signup(world, invitee)
    assert signed_up.status_code == 200, signed_up.text
    invitee.id = str(signed_up.json()["user"]["id"])
    world.created.append(invitee.id)
    _signed_in(world, invitee)

    def start(account: Account):  # noqa: ANN202
        return client.post(
            f"{API}/business/space", json={"name": "Mi Negocio"}, headers=account.headers
        )

    def start_additional(account: Account):  # noqa: ANN202
        return _post(
            world, "/business/spaces", {"name": "Otro", "country": "DO"}, account.headers
        )

    # Pending only: nothing can be started.
    assert _code(start(invitee)) == refused
    assert _code(start_additional(invitee)) == refused

    # Accepted as an editor, then promoted to admin by the owner: still nothing.
    [invitation] = client.get(
        f"{API}/business/invitations", headers=invitee.headers
    ).json()
    accepted = client.post(
        f"{API}/business/invitations/{invitation['id']}/accept",
        headers=invitee.headers,
        json={"space_id": world.space_id},
    )
    assert accepted.status_code == 200, accepted.text
    assert _code(start(invitee)) == refused
    assert _code(start_additional(invitee)) == refused
    [membership] = client.get(f"{API}/business/spaces", headers=invitee.headers).json()[
        "spaces"
    ]
    promoted = client.patch(
        f"{API}/business/access/grants/{membership['grant_id']}",
        json={"role": "admin"},
        headers=owner.headers,
    )
    assert promoted.status_code == 200, promoted.text
    [upgrade] = client.get(f"{API}/business/invitations", headers=invitee.headers).json()
    assert (
        client.post(
            f"{API}/business/invitations/{upgrade['id']}/accept",
            headers=invitee.headers,
            json={"space_id": world.space_id},
        ).status_code
        == 200
    )
    acting = {**invitee.headers, GRANT: membership["grant_id"]}
    assert client.get(f"{API}/business/access", headers=acting).status_code == 200

    # An admin admitted only by the Business issues no invitation of any kind.
    invite_one = client.post(
        f"{API}/business/access", json={"email": outsider.email}, headers=acting
    )
    assert _code(invite_one) == refused
    invite_many = client.post(
        f"{API}/business/access/invitations",
        json={
            "recipients": [
                {"email": outsider.email, "role": "editor", "command_key": "k1"}
            ]
        },
        headers=acting,
    )
    assert _code(invite_many) == refused
    pending = _credentials(world, "pendiente")
    _invite(world, pending.email)
    pending_id = next(
        i["id"]
        for i in client.get(f"{API}/business/access", headers=owner.headers).json()[
            "invites"
        ]
        if i["email"] == pending.email
    )
    resent = client.post(
        f"{API}/business/access/invites/{pending_id}/resend", headers=acting
    )
    assert _code(resent) == refused
    assert _code(_signup(world, outsider)) == (400, "auth_signup_failed")
    assert [
        i["email"]
        for i in client.get(f"{API}/business/access", headers=owner.headers).json()[
            "invites"
        ]
    ] == [pending.email]

    # Nor can such a person take a Business over.
    transfer = _post(
        world,
        f"/business/spaces/{world.space_id}/ownership-transfers",
        {"target_grant_id": membership["grant_id"], "confirmation": "Ferretería Prueba"},
        owner.headers,
    )
    assert transfer.status_code == 200, transfer.text
    taken = client.post(
        f"{API}/business/ownership-transfers/{transfer.json()['id']}/accept",
        headers=invitee.headers,
    )
    assert _code(taken) == refused
    [still_pending] = client.get(
        f"{API}/business/ownership-transfers", headers=owner.headers
    ).json()["transfers"]
    assert (still_pending["id"], still_pending["status"]) == (
        transfer.json()["id"],
        "pending",
    )

    # The hand-listed owner keeps every power.
    assert start(owner).status_code == 200
    assert start_additional(owner).status_code == 201


@pytest.fixture
def switch_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CUADRAO_BUSINESS_INVITE_ADMISSION_ENABLED", raising=False)


def test_with_the_switch_off_only_the_allowlist_admits_the_invited_accountant(
    world,
    switch_off,  # noqa: ANN001
) -> None:
    """The walk before this switch, which is the default: the invite admits
    nobody to sign-up, login or requests; a hand-listed accountant signs in,
    sees and accepts the invitation; and every route the standing check guards
    answers as it did for a hand-listed person before the check existed."""

    client, owner = world.client, world.owner
    accountant = _credentials(world, "contadora")
    _invite(world, accountant.email)

    # Off the allowlist the invite admits nobody: signup, login and requests are refused.
    assert _code(_signup(world, accountant)) == (400, "auth_signup_failed")
    _create(world, accountant)
    assert _code(_login(world, accountant)) == (401, "unauthorized")
    session = world.gateway.login(
        email=accountant.email, password=accountant.password, captcha_token=CAPTCHA
    )
    bearer = {"Authorization": f"Bearer {session['session']['access_token']}", **ORIGIN}
    for path in ("/business/spaces", "/me"):
        assert _code(client.get(f"{API}{path}", headers=bearer)) == (
            403,
            "private_alpha_access_required",
        ), path
    assert _invite_state(accountant.email) == [False]
    assert _grants_and_accepts(world.space_id, accountant.id) == (0, 0)

    # Allowlisting permits sign-in; the recipient must still accept explicitly.
    _allow(accountant.email)
    _signed_in(world, accountant)
    first = client.get(f"{API}/business/spaces", headers=accountant.headers)
    assert first.status_code == 200, first.text
    assert first.json()["spaces"] == []
    [invitation] = client.get(
        f"{API}/business/invitations", headers=accountant.headers
    ).json()
    accepted = client.post(
        f"{API}/business/invitations/{invitation['id']}/accept",
        headers=accountant.headers,
        json={"space_id": world.space_id},
    )
    assert accepted.status_code == 200, accepted.text
    assert _invite_state(accountant.email) == [True]
    [membership] = client.get(
        f"{API}/business/spaces", headers=accountant.headers
    ).json()["spaces"]

    # The guarded routes, as before the check existed: the hand-listed owner
    # starts and adds Businesses and invites; a hand-listed admin invites; a
    # transfer to a hand-listed member is accepted; the new owner adds a
    # Business of their own.
    assert (
        client.post(
            f"{API}/business/space",
            json={"name": "Ferretería Prueba"},
            headers=owner.headers,
        ).status_code
        == 200
    )
    assert (
        _post(
            world, "/business/spaces", {"name": "Otro", "country": "DO"}, owner.headers
        ).status_code
        == 201
    )
    outsider = _credentials(world, "ajena")
    many = client.post(
        f"{API}/business/access/invitations",
        json={
            "recipients": [
                {"email": outsider.email, "role": "editor", "command_key": "k1"}
            ]
        },
        headers=owner.headers,
    )
    assert many.status_code == 200, many.text
    assert _code(_signup(world, outsider)) == (400, "auth_signup_failed")
    promoted = client.patch(
        f"{API}/business/access/grants/{membership['grant_id']}",
        json={"role": "admin"},
        headers=owner.headers,
    )
    assert promoted.status_code == 200, promoted.text
    [upgrade] = client.get(
        f"{API}/business/invitations", headers=accountant.headers
    ).json()
    assert (
        client.post(
            f"{API}/business/invitations/{upgrade['id']}/accept",
            headers=accountant.headers,
            json={"space_id": world.space_id},
        ).status_code
        == 200
    )
    acting = {**accountant.headers, GRANT: membership["grant_id"]}
    invited_by_admin = _credentials(world, "colega")
    invite_one = client.post(
        f"{API}/business/access", json={"email": invited_by_admin.email}, headers=acting
    )
    assert invite_one.status_code == 201, invite_one.text
    transfer = _post(
        world,
        f"/business/spaces/{world.space_id}/ownership-transfers",
        {"target_grant_id": membership["grant_id"], "confirmation": "Ferretería Prueba"},
        owner.headers,
    )
    assert transfer.status_code == 200, transfer.text
    taken = client.post(
        f"{API}/business/ownership-transfers/{transfer.json()['id']}/accept",
        headers=accountant.headers,
    )
    assert taken.status_code == 200, taken.text
    assert (
        _post(
            world,
            "/business/spaces",
            {"name": "Mi Negocio", "country": "DO"},
            accountant.headers,
        ).status_code
        == 201
    )
