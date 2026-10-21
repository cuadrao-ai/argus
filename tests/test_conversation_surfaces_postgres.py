"""Personal and Business chat histories on the real API, Auth and Postgres.

Production already holds Personal conversations written before the Business
migration, every one with ``owner_space_id`` null. They are seeded here the way
the pre-S4 code wrote them. A Business conversation is inserted directly by SQL,
which is the D1 reproduction: before S4 such a row appeared in Personal reads in
any flag state. Needs the local Supabase proof variables and
``ARGUS_DISPOSABLE_DATABASE_URL``.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from contextlib import suppress
from dataclasses import dataclass, field
from unittest.mock import patch

import psycopg
import pytest
from argus.api import state as api_state
from argus.api.business_spaces import business_spaces, configure_business_spaces
from argus.api.main import app
from argus.api.routers import auth as auth_router
from argus.domain.business.spaces import PostgresSpaceStore
from fastapi.testclient import TestClient
from psycopg_pool import ConnectionPool

from tests.local_supabase_support import local_supabase_gateway
from tests.test_financial_accounts_api_postgres import ORIGIN, _login

DSN = os.getenv("ARGUS_DISPOSABLE_DATABASE_URL", "").strip()
pytestmark = pytest.mark.skipif(
    not (DSN and os.getenv("ARGUS_LOCAL_SUPABASE_URL")),
    reason="local Supabase proof variables are not configured",
)
PERSONAL_TITLES = ("Rent ledger", "Groceries ledger", "Savings ledger")


@dataclass
class Person:
    id: str
    headers: dict[str, str]
    personal: list[str] = field(default_factory=list)
    business: list[str] = field(default_factory=list)
    space_id: str | None = None


@dataclass
class Rig:
    client: TestClient
    alice: Person
    bob: Person


def _insert_conversation(person: str, title: str, space_id: str | None) -> str:
    """One chat and its question, written as SQL with or without a space."""
    with psycopg.connect(DSN) as connection:
        row = connection.execute(
            "insert into public.conversations (user_id, title, title_source, language, "
            "owner_space_id) values (%s, %s, 'system_default', 'en', %s) returning id",
            (person, title, space_id),
        ).fetchone()
        assert row is not None
        conversation_id = str(row[0])
        connection.execute(
            "insert into public.messages (conversation_id, user_id, role, content) "
            "values (%s, %s, 'user', %s)",
            (conversation_id, person, f"How is my {title.lower()} doing?"),
        )
    return conversation_id


def _insert_pre_s4_conversation(person: str, title: str) -> str:
    """The pre-S4 insert names no space column at all."""
    with psycopg.connect(DSN) as connection:
        row = connection.execute(
            "insert into public.conversations (user_id, title, title_source, language) "
            "values (%s, %s, 'system_default', 'en') returning id",
            (person, title),
        ).fetchone()
        assert row is not None
        conversation_id = str(row[0])
        connection.execute(
            "insert into public.messages (conversation_id, user_id, role, content) "
            "values (%s, %s, 'user', %s)",
            (conversation_id, person, f"How is my {title.lower()} doing?"),
        )
    return conversation_id


@pytest.fixture
def rig(monkeypatch: pytest.MonkeyPatch) -> Iterator[Rig]:
    auth_router.reset_auth_attempt_limiter_for_tests()
    monkeypatch.setenv("ARGUS_PUBLIC_ACCOUNT_ACCESS_ENABLED", "true")
    monkeypatch.setenv("NEXT_PUBLIC_MOCK_AUTH", "false")
    monkeypatch.setenv("ARGUS_MOCK_AUTH", "false")
    monkeypatch.setenv("ARGUS_DEV_MEMORY_FALLBACK", "false")
    monkeypatch.setenv("ARGUS_BUSINESS_PILOT_ENABLED", "true")
    monkeypatch.setenv("ARGUS_BUSINESS_CHAT_ENABLED", "true")
    gateway = local_supabase_gateway()
    created: list[str] = []
    previous_spaces = business_spaces()
    with ConnectionPool(DSN, min_size=0, max_size=4) as pool:
        try:
            with (
                patch.object(api_state, "supabase_gateway", gateway),
                patch.object(api_state, "DATABASE_URL", DSN),
                patch.object(api_state, "PERSISTENCE_MODE", "supabase"),
                TestClient(app, base_url="http://localhost:3000") as client,
            ):
                configure_business_spaces(PostgresSpaceStore(pool))
                alice_headers = {**_login(client, gateway, "chats-a", created), **ORIGIN}
                bob_headers = {**_login(client, gateway, "chats-b", created), **ORIGIN}
                alice = Person(created[0], alice_headers)
                bob = Person(created[1], bob_headers)
                for headers in (alice_headers, bob_headers):
                    assert client.get("/api/v1/me", headers=headers).status_code == 200
                alice.personal = [
                    _insert_pre_s4_conversation(alice.id, title)
                    for title in PERSONAL_TITLES
                ]
                spaces = business_spaces()
                assert spaces is not None
                alice.space_id = spaces.create(alice.id, "Mi negocio")[0].id
                alice.business.append(
                    _insert_conversation(alice.id, "Shop ledger", alice.space_id)
                )
                bob.space_id = spaces.create(bob.id, "Mi negocio")[0].id
                yield Rig(client, alice, bob)
        finally:
            configure_business_spaces(previous_spaces)
            for user_id in created:
                with suppress(Exception):
                    gateway.delete_auth_user(user_id)


def _ids(rig: Rig, person: Person, path: str, **params: str) -> list[str]:
    response = rig.client.get(path, params=params, headers=person.headers)
    assert response.status_code == 200, response.text
    return sorted(
        item.get("conversation_id") or item["id"]
        for item in response.json()["items"]
        if item.get("type", "chat") in {"chat", "conversation"}
    )


def _previews(rig: Rig, person: Person, surface: str) -> list[str]:
    response = rig.client.get(
        "/api/v1/conversations", params={"surface": surface}, headers=person.headers
    )
    return sorted(item["preview"]["text"] for item in response.json()["items"])


def _reads(rig: Rig, person: Person, surface: str) -> dict[str, list[str]]:
    return {
        "recents": _ids(rig, person, "/api/v1/conversations", surface=surface),
        "search": _ids(rig, person, "/api/v1/search", q="ledger", surface=surface),
        "history": _ids(rig, person, "/api/v1/history", surface=surface),
    }


def _every_read(ids: list[str]) -> dict[str, list[str]]:
    return {"recents": sorted(ids), "search": sorted(ids), "history": sorted(ids)}


def _deleted(conversation_ids: list[str]) -> list[bool]:
    with psycopg.connect(DSN) as connection:
        rows = dict(
            connection.execute(
                "select id::text, deleted_at is not null from public.conversations "
                "where id = any(%s::uuid[])",
                (conversation_ids,),
            ).fetchall()
        )
    return [rows[value] for value in conversation_ids]


def test_pre_existing_and_business_chats_stay_on_their_own_surface(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    alice = rig.alice
    created = rig.client.post(
        "/api/v1/conversations", json={"surface": "business"}, headers=alice.headers
    )
    assert created.status_code == 200, created.text
    with psycopg.connect(DSN) as connection:
        stored = connection.execute(
            "select owner_space_id::text from public.conversations where id = %s",
            (created.json()["conversation"]["id"],),
        ).fetchone()
    assert stored == (alice.space_id,)
    with psycopg.connect(DSN) as connection:
        connection.execute(
            "insert into public.messages (conversation_id, user_id, role, content) "
            "values (%s, %s, 'user', 'How is my supplier ledger doing?')",
            (created.json()["conversation"]["id"], alice.id),
        )
    alice.business.append(created.json()["conversation"]["id"])

    assert _reads(rig, alice, "personal") == _every_read(alice.personal)
    assert _reads(rig, alice, "business") == _every_read(alice.business)
    assert _previews(rig, alice, "personal") == sorted(
        f"How is my {title.lower()} doing?" for title in PERSONAL_TITLES
    )
    assert _previews(rig, alice, "business") == [
        "How is my shop ledger doing?",
        "How is my supplier ledger doing?",
    ]

    monkeypatch.delenv("ARGUS_BUSINESS_PILOT_ENABLED")
    assert _reads(rig, alice, "personal") == _every_read(alice.personal)
    refused = rig.client.get(
        "/api/v1/conversations", params={"surface": "business"}, headers=alice.headers
    )
    assert (refused.status_code, refused.json()["code"]) == (404, "business_unavailable")


@pytest.mark.parametrize("flag", ["true", "false"])
def test_personal_delete_all_covers_pre_existing_chats_and_never_business(
    rig: Rig, monkeypatch: pytest.MonkeyPatch, flag: str
) -> None:
    monkeypatch.setenv("ARGUS_BUSINESS_PILOT_ENABLED", flag)
    alice = rig.alice

    cleared = rig.client.delete("/api/v1/conversations", headers=alice.headers)

    assert cleared.json() == {"success": True, "deleted_count": 3}
    assert _deleted(alice.personal) == [True, True, True]
    assert _deleted(alice.business) == [False]
    assert _reads(rig, alice, "personal") == _every_read([])


def test_business_delete_all_leaves_personal_chats(rig: Rig) -> None:
    alice = rig.alice

    cleared = rig.client.delete(
        "/api/v1/conversations", params={"surface": "business"}, headers=alice.headers
    )

    assert cleared.json() == {"success": True, "deleted_count": 1}
    assert _deleted(alice.business) == [True]
    assert _deleted(alice.personal) == [False, False, False]
    assert _reads(rig, alice, "personal") == _every_read(alice.personal)


def test_another_owner_sees_nothing(rig: Rig) -> None:
    empty = _every_read([])
    assert _reads(rig, rig.bob, "personal") == empty
    assert _reads(rig, rig.bob, "business") == empty
    cleared = rig.client.delete("/api/v1/conversations", headers=rig.bob.headers)
    assert cleared.json()["deleted_count"] == 0
    assert _deleted(rig.alice.personal + rig.alice.business) == [False] * 4


def test_artifact_routes_answer_404_for_a_business_conversation(rig: Rig) -> None:
    alice = rig.alice
    business = alice.business[0]
    personal = alice.personal[0]

    def decision(conversation_id: str) -> tuple[int, str]:
        response = rig.client.post(
            f"/api/v1/conversations/{conversation_id}/messages/"
            "00000000-0000-4000-8000-000000000001/decision",
            json={"decision_state": "watching"},
            headers=alice.headers,
        )
        return response.status_code, response.json()["detail"]

    assert decision(business) == (404, "Conversation not found.")
    assert decision(personal)[1] != "Conversation not found."


def test_a_run_in_a_business_chat_stays_on_the_business_surface(rig: Rig) -> None:
    alice = rig.alice
    with psycopg.connect(DSN) as connection:
        row = connection.execute(
            """
            insert into public.backtest_runs (
                user_id, conversation_id, status, asset_class, symbols,
                allocation_method, benchmark_symbol, config_snapshot, metrics,
                conversation_result_card
            )
            values (
                %s, %s, 'completed', 'equity', array['NVDA'], 'equal_weight', 'SPY',
                '{}'::jsonb, '{}'::jsonb, %s::jsonb
            )
            returning id
            """,
            (
                alice.id,
                alice.business[0],
                json.dumps({"title": "NVDA test", "rows": [{"value": "+12%"}]}),
            ),
        ).fetchone()
    assert row is not None
    run_id = str(row[0])

    def history_runs(surface: str) -> list[str]:
        response = rig.client.get(
            "/api/v1/history", params={"surface": surface}, headers=alice.headers
        )
        return [item["id"] for item in response.json()["items"] if item["type"] == "run"]

    def symbol_hits(surface: str) -> list[str]:
        return _ids(rig, alice, "/api/v1/search", q="NVDA", surface=surface)

    assert history_runs("business") == [run_id]
    assert history_runs("personal") == []
    assert symbol_hits("business") == alice.business
    assert symbol_hits("personal") == []
