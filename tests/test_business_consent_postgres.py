"""The Business consent screen's acceptance over HTTP, on the real app, Auth and
Postgres: it is saved on the server once per wording, names the Business the
person works in, and answers the same to every later session of that person."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from argus.domain.business.spaces import PostgresSpaceStore
from psycopg import Connection
from psycopg_pool import ConnectionPool

from tests import test_financial_accounts_postgres as shared
from tests.test_business_scope_switch_routes_postgres import API, GRANT
from tests.test_business_scope_switch_routes_postgres import (
    pytestmark as _local_supabase,
)
from tests.test_business_scope_switch_routes_postgres import web as web  # noqa: F401

pytestmark = _local_supabase
WORDING = "0123456789abcdef"
NEXT_WORDING = "fedcba9876543210"


def _rows(user_id: str) -> list[tuple[str, str]]:
    with Connection.connect(shared.DSN) as db:
        return db.execute(
            "select space_id::text, copy_version from public.business_consent_acceptances"
            " where user_id = %s order by accepted_at",
            (user_id,),
        ).fetchall()


def _read(world, headers: dict[str, str], version: str = WORDING):  # noqa: ANN001, ANN202
    answer = world.client.get(
        f"{API}/business/consent", params={"version": version}, headers=headers
    )
    assert answer.status_code == 200, answer.text
    assert answer.headers["cache-control"] == "no-store"
    return answer.json()["accepted_at"]


def test_an_owner_accepts_once_per_wording_and_later_reads_see_it(web) -> None:  # noqa: ANN001, F811
    alice = web.alice
    assert _read(web, alice.headers) is None

    first = web.client.post(
        f"{API}/business/consent", json={"version": WORDING}, headers=alice.headers
    )
    assert first.status_code == 200, first.text
    accepted_at = first.json()["accepted_at"]
    assert accepted_at and first.json()["version"] == WORDING
    again = web.client.post(
        f"{API}/business/consent", json={"version": WORDING}, headers=alice.headers
    )
    assert again.json()["accepted_at"] == accepted_at

    assert _rows(alice.id) == [(alice.space_id, WORDING)]
    assert _read(web, {"Authorization": alice.headers["Authorization"]}) == accepted_at
    assert _read(web, alice.headers, NEXT_WORDING) is None, "a new wording asks again"


def test_an_accountant_records_the_business_they_work_in(web) -> None:  # noqa: ANN001, F811
    dave = web.dave
    missing = web.client.post(
        f"{API}/business/consent", json={"version": WORDING}, headers=dave.headers
    )
    assert missing.status_code == 404, missing.text
    assert missing.json()["code"] == "business_space_missing"

    under_grant = {**dave.headers, GRANT: web.grant_d}
    accepted = web.client.post(
        f"{API}/business/consent", json={"version": WORDING}, headers=under_grant
    )
    assert accepted.status_code == 200, accepted.text
    assert _rows(dave.id) == [(web.alice.space_id, WORDING)]
    assert _read(web, dave.headers) == accepted.json()["accepted_at"]
    assert _rows(web.alice.id) == [], "the owner's own acceptance is still theirs to give"


@pytest.mark.parametrize("version", ["", "v1", "0123456789ABCDEF", "0" * 17])
def test_a_wording_that_is_not_a_copy_digest_is_refused(web, version: str) -> None:  # noqa: ANN001, F811
    read = web.client.get(
        f"{API}/business/consent", params={"version": version}, headers=web.alice.headers
    )
    written = web.client.post(
        f"{API}/business/consent", json={"version": version}, headers=web.alice.headers
    )
    assert (read.status_code, written.status_code) == (422, 422)
    assert _rows(web.alice.id) == []


def test_a_first_acceptance_committed_meanwhile_is_the_answer(web) -> None:  # noqa: ANN001, F811
    alice = web.alice
    with (
        ConnectionPool(shared.DSN, min_size=1, max_size=1, open=True) as pool,
        Connection.connect(shared.DSN) as other,
        ThreadPoolExecutor(1) as worker,
    ):
        (committed,) = other.execute(
            "insert into public.business_consent_acceptances"
            " (user_id, space_id, copy_version) values (%s, %s, %s) returning accepted_at",
            (alice.id, alice.space_id, WORDING),
        ).fetchone()
        pending = worker.submit(
            PostgresSpaceStore(pool).accept_consent, alice.id, alice.space_id, WORDING
        )
        deadline = time.monotonic() + 10
        with Connection.connect(shared.DSN, autocommit=True) as watch:
            while not watch.execute(
                "select exists (select 1 from pg_stat_activity where wait_event_type = 'Lock'"
                " and query like '%%business_consent_acceptances%%')"
            ).fetchone()[0]:
                assert time.monotonic() < deadline, "the second acceptance never waited"
                time.sleep(0.05)
        other.commit()
        assert pending.result(timeout=10) == committed
    assert _rows(alice.id) == [(alice.space_id, WORDING)]
