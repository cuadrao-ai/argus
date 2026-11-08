"""The guide follows the signed-in person across Businesses and sessions."""

from __future__ import annotations

import os
from uuid import uuid4

import psycopg
import pytest
from argus.api.main import app
from fastapi.testclient import TestClient
from psycopg_pool import PoolTimeout

from tests import test_business_scope_switch_routes_postgres as scope
from tests import test_financial_accounts_postgres as shared
from tests.test_financial_accounts_api_postgres import ORIGIN

API = scope.API
GRANT = scope.GRANT
DSN = shared.DSN
web = scope.web
users = shared.users

CARD = f"{API}/business/guide-cards/bandeja-intro"
INSERT = (
    "insert into public.business_guide_dismissals (user_id, card_id)"
    " values (%s, 'bandeja-intro') on conflict (user_id, card_id) do nothing"
)
SELECT = "select user_id::text, dismissed_at from public.business_guide_dismissals"

pytestmark = pytest.mark.skipif(not DSN, reason="Disposable database required")


@pytest.mark.skipif(
    not os.getenv("ARGUS_LOCAL_SUPABASE_URL"), reason="Local Supabase Auth required"
)
def test_guide_http_uses_the_person_across_grants_and_browser_sessions(web, monkeypatch):
    bob_on_a = {**web.bob.headers, GRANT: web.grant_a}
    fresh = web.client.get(CARD, headers=bob_on_a)
    assert fresh.status_code == 200, fresh.text
    assert fresh.json() == {"dismissed": False}
    assert fresh.headers["cache-control"] == "no-store"

    second_browser = TestClient(app, base_url="http://localhost:3000")
    unauthenticated = second_browser.get(
        CARD, headers={**ORIGIN, "X-User-Id": web.bob.id}
    )
    assert unauthenticated.status_code == 401
    assert unauthenticated.headers["cache-control"] == "no-store"
    for response in (
        web.client.get(f"{API}/business/guide-cards/unknown", headers=bob_on_a),
        web.client.post(f"{API}/business/guide-cards/unknown/dismiss", headers=bob_on_a),
    ):
        assert response.status_code == 422
        assert response.headers["cache-control"] == "no-store"

    spoofed = {**bob_on_a, "X-User-Id": web.alice.id}
    dismissed = web.client.post(f"{CARD}/dismiss", headers=spoofed)
    assert dismissed.status_code == 200, dismissed.text
    assert dismissed.json() == {"dismissed": True}
    assert dismissed.headers["cache-control"] == "no-store"
    assert web.client.post(f"{CARD}/dismiss", headers=bob_on_a).json() == {
        "dismissed": True
    }

    assert second_browser.get(
        CARD, headers={**web.bob.headers, GRANT: web.grant_c}
    ).json() == {"dismissed": True}
    assert second_browser.get(CARD, headers=web.alice.headers).json() == {
        "dismissed": False
    }
    assert second_browser.get(
        CARD, headers={**web.dave.headers, GRANT: web.grant_d}
    ).json() == {"dismissed": False}

    assert second_browser.get(
        CARD, headers={**web.bob.headers, GRANT: str(uuid4())}
    ).json() == {"dismissed": True}

    pool = app.state.financial_accounts_pool

    def exhausted_pool():
        raise PoolTimeout("test pool is exhausted")

    for unavailable_pool in (None, pool):
        with monkeypatch.context() as patch:
            patch.setattr(app.state, "financial_accounts_pool", unavailable_pool)
            patch.setattr(pool, "connection", exhausted_pool)
            for response in (
                web.client.get(CARD, headers=bob_on_a),
                web.client.post(f"{CARD}/dismiss", headers=bob_on_a),
            ):
                assert response.status_code == 503
                assert response.json()["code"] == "business_guide_unavailable"
                assert response.headers["x-request-id"] == response.json()["request_id"]
                assert response.headers["cache-control"] == "no-store"


def test_guide_row_security_and_retry_keep_the_first_dismissal(users):
    owner, other, guest = (users[label] for label in ("owner", "other", "guest"))
    with psycopg.connect(DSN) as db:
        with db.transaction(), db.cursor() as cursor:
            shared._set_authenticated_claims(cursor, user_id=owner, is_anonymous=False)
            cursor.execute(INSERT, (owner,))
            cursor.execute(SELECT)
            first = cursor.fetchone()
            assert first is not None and first[0] == owner

        with db.transaction(), db.cursor() as cursor:
            shared._set_authenticated_claims(cursor, user_id=owner, is_anonymous=False)
            cursor.execute(INSERT, (owner,))
            cursor.execute(SELECT)
            assert cursor.fetchall() == [first]

        for user, anonymous in ((other, False), (guest, True)):
            with db.transaction(), db.cursor() as cursor:
                shared._set_authenticated_claims(
                    cursor, user_id=user, is_anonymous=anonymous
                )
                cursor.execute(SELECT)
                assert cursor.fetchall() == []

        refused = (
            (owner, False, INSERT, (other,)),
            (guest, True, INSERT, (guest,)),
            (
                owner,
                False,
                "update public.business_guide_dismissals set dismissed_at=now()",
                (),
            ),
            (owner, False, "delete from public.business_guide_dismissals", ()),
            (
                owner,
                False,
                "insert into public.business_guide_dismissals (user_id, card_id, dismissed_at) values (%s, 'bandeja-intro', now())",
                (owner,),
            ),
        )
        for user, anonymous, query, params in refused:
            with (
                pytest.raises(psycopg.errors.InsufficientPrivilege),
                db.transaction(),
                db.cursor() as cursor,
            ):
                shared._set_authenticated_claims(
                    cursor, user_id=user, is_anonymous=anonymous
                )
                cursor.execute(query, params)

        with (
            pytest.raises(psycopg.errors.InsufficientPrivilege),
            db.transaction(),
            db.cursor() as cursor,
        ):
            cursor.execute("set local role anon")
            cursor.execute(SELECT)
