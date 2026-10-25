"""Business close/reopen against the complete isolated integration schema."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import UUID, uuid4

import psycopg
import pytest
from argus.domain.business.access import PostgresAccessStore
from argus.domain.business.authority import ActionError, authorize
from argus.domain.business.contracts.authority import TrustedActor
from argus.domain.business.lifecycle import (
    BusinessLifecycleError,
    PostgresBusinessLifecycle,
)
from argus.domain.business.spaces import PostgresSpaceStore
from psycopg_pool import ConnectionPool

from tests import test_financial_accounts_postgres as shared

users = shared.users
pytestmark = pytest.mark.skipif(not shared.DSN, reason="Disposable database required")


@pytest.fixture
def world(users):  # noqa: ANN001
    with ConnectionPool(shared.DSN, min_size=0, max_size=8) as pool:
        spaces = PostgresSpaceStore(pool)
        space, _ = spaces.create(users["owner"], "Colmado Muñoz")
        access = PostgresAccessStore(pool)
        with psycopg.connect(shared.DSN) as db:
            email = db.execute(
                "update auth.users set email_confirmed_at=now() where id=%s returning email",
                (users["other"],),
            ).fetchone()[0]
        _, listing = access.give(space.id, users["owner"], email)
        access.accept_invite(users["other"], space.id, listing.invites[0].id)
        member = next(
            g for g in access.list(space.id, users["owner"]).grants if not g.owner
        )
        yield pool, space, users, access, member


def _actor(user_id: str, space_id: str) -> TrustedActor:
    return TrustedActor(
        actor_id=UUID(user_id), actor_kind="member", space_id=UUID(space_id)
    )


def _close(world, *, key="close-1", confirmation=None):  # noqa: ANN001
    pool, space, users, _, _ = world
    return PostgresBusinessLifecycle(pool).close(
        owner_id=users["owner"],
        space_id=space.id,
        confirmation=space.name if confirmation is None else confirmation,
        idempotency_key=key,
    )


def _reopen(world, *, key="reopen-1"):  # noqa: ANN001
    pool, space, users, _, _ = world
    return PostgresBusinessLifecycle(pool).reopen(
        owner_id=users["owner"],
        space_id=space.id,
        idempotency_key=key,
    )


def test_close_denies_existing_grants_and_reopen_restores_them_without_invites(world):  # noqa: ANN001
    pool, space, users, access, member = world
    closed = _close(world)
    assert closed.closed_at is not None
    assert closed.reopen_until == closed.closed_at + timedelta(days=30)
    assert access.spaces_for(users["owner"]) == ()
    assert access.spaces_for(users["other"]) == ()
    with psycopg.connect(shared.DSN) as db:
        for person in (users["owner"], users["other"]):
            with pytest.raises(ActionError, match="business_closed"):
                authorize(db, _actor(person, space.id))
    assert [
        s.space_id for s in PostgresBusinessLifecycle(pool).closed_spaces(users["owner"])
    ] == [space.id]
    assert PostgresBusinessLifecycle(pool).closed_spaces(users["other"]) == ()
    assert _reopen(world).closed_at is None
    restored = access.granted(users["other"], member.id)
    assert restored is not None and restored.capabilities == ("read", "prepare")
    with psycopg.connect(shared.DSN) as db:
        authorize(db, _actor(users["owner"], space.id)).require("approve")
        with pytest.raises(ActionError):
            authorize(db, _actor(users["other"], space.id)).require("approve")
        assert (
            db.execute(
                "select count(*) from public.business_access_invites where space_id=%s",
                (space.id,),
            ).fetchone()[0]
            == 1
        )


@pytest.mark.parametrize(
    "confirmation", ["Colmado Muñoz ", "colmado Muñoz", "", "Otro negocio"]
)
def test_confirmation_must_match_the_current_business_name(world, confirmation):  # noqa: ANN001
    with pytest.raises(BusinessLifecycleError, match="business_name_mismatch"):
        _close(world, confirmation=confirmation)
    pool, space, users, _, _ = world
    assert PostgresSpaceStore(pool).open_space(users["owner"]).id == space.id


@pytest.mark.parametrize("action", ["close", "reopen"])
def test_nonowners_and_unknown_businesses_reveal_nothing(world, action):  # noqa: ANN001
    pool, space, users, _, _ = world
    if action == "reopen":
        _close(world)
    service = PostgresBusinessLifecycle(pool)
    for person, business in [(users["other"], space.id), (users["owner"], str(uuid4()))]:
        args = dict(owner_id=person, space_id=business, idempotency_key="foreign")
        if action == "close":
            args["confirmation"] = space.name
        with pytest.raises(BusinessLifecycleError, match="business_record_not_found"):
            getattr(service, action)(**args)


def test_delayed_close_and_reopen_replays_never_reverse_a_later_command(world):  # noqa: ANN001
    first = _close(world)
    _reopen(world)
    assert _close(world) == first
    pool, space, users, access, _ = world
    assert access.spaces_for(users["other"])
    _close(world, key="close-2")
    assert _reopen(world).closed_at is None
    assert access.spaces_for(users["other"]) == ()
    with psycopg.connect(shared.DSN) as db:
        assert (
            db.execute(
                "select count(*) from public.business_lifecycle_commands where space_id=%s",
                (space.id,),
            ).fetchone()[0]
            == 3
        )
    assert PostgresSpaceStore(pool).open_space(users["owner"]) is None


def test_reusing_a_key_with_a_different_action_or_name_conflicts(world):  # noqa: ANN001
    _close(world)
    for operation in [
        lambda: _reopen(world, key="close-1"),
        lambda: _close(world, confirmation="different"),
    ]:
        with pytest.raises(BusinessLifecycleError, match="idempotency_conflict"):
            operation()


def test_concurrent_duplicate_closures_and_reopens_have_one_effect(world):  # noqa: ANN001
    with ThreadPoolExecutor(max_workers=4) as executor:
        closed = list(executor.map(lambda _: _close(world), range(4)))
    assert all(result == closed[0] for result in closed)
    with ThreadPoolExecutor(max_workers=4) as executor:
        reopened = list(executor.map(lambda _: _reopen(world), range(4)))
    assert all(result == reopened[0] for result in reopened)
    pool, space, _, _, _ = world
    with pool.connection() as db:
        assert (
            db.execute(
                "select count(*) from public.business_lifecycle_commands where space_id=%s",
                (space.id,),
            ).fetchone()[0]
            == 2
        )


@pytest.mark.parametrize("age", ["30 days", "30 days 1 microsecond", "31 days"])
def test_reopen_is_refused_at_or_after_day_30(world, age):  # noqa: ANN001
    _close(world)
    pool, space, users, _, _ = world
    with pool.connection() as db:
        db.execute(
            "update public.spaces set closed_at=clock_timestamp()-%s::interval where id=%s",
            (age, space.id),
        )
    with pytest.raises(BusinessLifecycleError, match="business_reopen_expired"):
        _reopen(world)
    assert PostgresBusinessLifecycle(pool).closed_spaces(users["owner"]) == ()


def test_reopen_just_before_deadline_and_revoked_grants_stay_revoked(world):  # noqa: ANN001
    pool, space, users, access, member = world
    access.revoke_grant(space.id, users["owner"], member.id)
    _close(world)
    with pool.connection() as db:
        db.execute(
            "update public.spaces set closed_at=clock_timestamp()-interval '29 days 23 hours' where id=%s",
            (space.id,),
        )
    _reopen(world)
    assert access.granted(users["other"], member.id) is None
    assert access.spaces_for(users["owner"])


def test_another_open_business_prevents_reopen_without_changing_either(world):  # noqa: ANN001
    pool, space, users, _, _ = world
    _close(world)
    other, _ = PostgresSpaceStore(pool).create(users["owner"], "Otro negocio")
    with pytest.raises(BusinessLifecycleError, match="business_already_open"):
        _reopen(world)
    assert PostgresSpaceStore(pool).open_space(users["owner"]).id == other.id
    assert [
        s.space_id for s in PostgresBusinessLifecycle(pool).closed_spaces(users["owner"])
    ] == [space.id]


def test_reopening_keeps_expired_grants_expired(world):  # noqa: ANN001
    pool, space, users, access, member = world
    _close(world)
    with pool.connection() as db:
        db.execute(
            "update public.business_client_grants set created_at=clock_timestamp()-interval '1 day', expires_at=clock_timestamp()-interval '1 second' where id=%s",
            (member.id,),
        )
    _reopen(world)
    assert access.granted(users["other"], member.id) is None


def test_lifecycle_commands_are_server_only_and_append_only(world):  # noqa: ANN001
    pool, space, _, _, _ = world
    _close(world)
    with pool.connection() as db:
        for role in ("anon", "authenticated"):
            with pytest.raises(psycopg.errors.InsufficientPrivilege), db.transaction():
                db.execute(f"set local role {role}")
                db.execute("select * from public.business_lifecycle_commands")
        with pytest.raises(psycopg.errors.InsufficientPrivilege), db.transaction():
            db.execute("set local role service_role")
            db.execute(
                "update public.business_lifecycle_commands set idempotency_key='changed' where space_id=%s",
                (space.id,),
            )


def test_retry_keeps_its_original_result_after_the_business_is_renamed(world):  # noqa: ANN001
    first = _close(world)
    _reopen(world)
    pool, _, users, _, _ = world
    PostgresSpaceStore(pool).rename(users["owner"], "Nuevo nombre")
    assert _close(world) == first


def test_a_new_close_key_does_not_extend_the_original_deadline(world):  # noqa: ANN001
    first = _close(world)
    assert _close(world, key="close-2") == first


@pytest.mark.parametrize("key", ["", " ", "x" * 201])
def test_invalid_keys_never_close_the_business(world, key):  # noqa: ANN001
    with pytest.raises(BusinessLifecycleError, match="invalid_idempotency_key"):
        _close(world, key=key)
    pool, space, users, _, _ = world
    assert PostgresSpaceStore(pool).open_space(users["owner"]).id == space.id


def test_close_waits_for_a_protected_business_operation(world):  # noqa: ANN001
    import time

    _, space, users, _, _ = world
    with (
        psycopg.connect(shared.DSN) as protected,
        ThreadPoolExecutor(max_workers=1) as executor,
    ):
        authorize(protected, _actor(users["other"], space.id)).require("prepare")
        holder = protected.info.backend_pid
        closing = executor.submit(_close, world)
        try:
            deadline = time.monotonic() + 3
            blocked = False
            with psycopg.connect(shared.DSN, autocommit=True) as observer:
                while time.monotonic() < deadline:
                    blocked = observer.execute(
                        "select exists(select 1 from pg_stat_activity where %s=any(pg_blocking_pids(pid)))",
                        (holder,),
                    ).fetchone()[0]
                    if blocked:
                        break
                    time.sleep(0.01)
            assert blocked and not closing.done()
        finally:
            protected.rollback()
        assert closing.result(timeout=3).closed_at is not None
    with psycopg.connect(shared.DSN) as db:
        with pytest.raises(ActionError):
            authorize(db, _actor(users["other"], space.id))


def test_reopen_rechecks_the_deadline_after_waiting_for_the_space_lock(world):  # noqa: ANN001
    import time

    _close(world)
    _, space, _, _, _ = world
    with (
        psycopg.connect(shared.DSN) as protected,
        ThreadPoolExecutor(max_workers=1) as executor,
    ):
        protected.execute(
            "update public.spaces set closed_at=clock_timestamp()-interval '29 days' where id=%s",
            (space.id,),
        )
        holder = protected.info.backend_pid
        reopening = executor.submit(_reopen, world)
        try:
            deadline = time.monotonic() + 3
            with psycopg.connect(shared.DSN, autocommit=True) as observer:
                while time.monotonic() < deadline:
                    if observer.execute(
                        "select exists(select 1 from pg_stat_activity where %s=any(pg_blocking_pids(pid)))",
                        (holder,),
                    ).fetchone()[0]:
                        break
                    time.sleep(0.01)
                else:
                    pytest.fail("Reopen never waited for the held Business row")
            protected.execute(
                "update public.spaces set closed_at=clock_timestamp()-interval '30 days' where id=%s",
                (space.id,),
            )
        finally:
            protected.commit()
        with pytest.raises(BusinessLifecycleError, match="business_reopen_expired"):
            reopening.result(timeout=3)


def test_a_closed_business_reads_as_closed_and_removed_access_reads_as_nothing(world):  # noqa: ANN001
    pool, space, users, access, member = world
    closed = _close(world)
    owner_view = access.closed_spaces_for(users["owner"])
    member_view = access.closed_spaces_for(users["other"])
    assert [(c.space_id, c.role, c.closed_at) for c in owner_view] == [
        (space.id, "owner", closed.closed_at)
    ]
    assert [(c.space_id, c.grant_id, c.role) for c in member_view] == [
        (space.id, member.id, "accountant")
    ]
    assert access.closed_grant(users["other"], member.id) == member_view[0]
    with psycopg.connect(shared.DSN) as db:
        db.execute(
            "update public.business_client_grants set revoked_at=now() where id=%s",
            (member.id,),
        )
        db.commit()
        # Removed access is not a closed Business: nothing reads as closed.
        with pytest.raises(ActionError, match="business_record_not_found"):
            authorize(db, _actor(users["other"], space.id))
    assert access.closed_spaces_for(users["other"]) == ()
    assert access.closed_grant(users["other"], member.id) is None
    assert access.granted(users["other"], member.id) is None


def _person(db, *, confirmed: bool = True) -> str:  # noqa: ANN001
    person = str(uuid4())
    db.execute(
        "insert into auth.users (id, email, is_anonymous, email_confirmed_at)"
        " values (%s, %s, false, case when %s then now() end)",
        (person, f"lifecycle-{person}@example.test", confirmed),
    )
    return person


def _member(db, space_id: str, owner: str, person: str, *caps: str) -> str:  # noqa: ANN001
    return db.execute(
        "insert into public.business_client_grants(space_id,grantee_id,issuer_id,capabilities)"
        " values(%s,%s,%s,%s) returning id::text",
        (space_id, person, owner, list(caps)),
    ).fetchone()[0]


def test_close_preview_counts_members_and_says_who_may_take_ownership(world):  # noqa: ANN001
    from argus.domain.business.transfer import PostgresBusinessTransfer

    pool, space, users, _, member = world
    owner = users["owner"]
    extra: list[str] = []
    try:
        with psycopg.connect(shared.DSN) as db:
            viewer, unconfirmed, owning, leaving = (
                _person(db),
                _person(db, confirmed=False),
                _person(db),
                _person(db),
            )
            extra += [viewer, unconfirmed, owning, leaving]
            grants = {
                "viewer": _member(db, space.id, owner, viewer, "read"),
                "unconfirmed": _member(
                    db, space.id, owner, unconfirmed, "read", "prepare"
                ),
                "owning": _member(db, space.id, owner, owning, "read", "prepare"),
                "leaving": _member(db, space.id, owner, leaving, "read", "prepare"),
            }
            db.execute(
                "insert into public.spaces (kind, name, created_by) values ('business', 'Propio', %s)",
                (owning,),
            )
            db.execute(
                "insert into argus_private.account_deletion_runs"
                " (user_id, subject_hash, analytics_distinct_id) values (%s, %s, %s)",
                (leaving, uuid4().hex * 2, leaving),
            )
            now = db.execute("select clock_timestamp()").fetchone()[0]
        [preview] = PostgresBusinessLifecycle(pool).owned_spaces(owner)
        assert preview["member_count"] == 5
        assert abs(preview["reopen_until"] - (now + timedelta(days=30))) < timedelta(
            minutes=1
        )
        assert preview["export_windows"] == []
        reasons = {
            m["grant_id"]: (m["eligible"], m["reason"]) for m in preview["members"]
        }
        assert reasons == {
            member.id: (True, None),
            grants["viewer"]: (False, "not_editor"),
            grants["unconfirmed"]: (False, "email_unconfirmed"),
            grants["owning"]: (False, "owns_open_business"),
            grants["leaving"]: (False, "account_unavailable"),
        }
        transfers = PostgresBusinessTransfer(pool)
        for ineligible in ("viewer", "unconfirmed", "owning", "leaving"):
            with pytest.raises(
                BusinessLifecycleError, match="business_transfer_target_invalid"
            ):
                transfers.request(
                    owner_id=owner,
                    space_id=space.id,
                    target_grant_id=grants[ineligible],
                    confirmation=space.name,
                    idempotency_key=f"ineligible-{ineligible}",
                )
        with psycopg.connect(shared.DSN) as db:
            assert db.execute(
                "select count(*) from public.business_ownership_transfers where space_id=%s",
                (space.id,),
            ).fetchone() == (0,)
    finally:
        with psycopg.connect(shared.DSN) as db:
            db.execute(
                "delete from argus_private.account_deletion_runs where user_id = any(%s::uuid[])",
                (extra,),
            )
            db.execute(
                "delete from public.spaces where created_by = any(%s::uuid[])", (extra,)
            )
            db.execute(
                "delete from public.business_client_grants where grantee_id = any(%s::uuid[])",
                (extra,),
            )
            db.execute("delete from auth.users where id = any(%s::uuid[])", (extra,))


from tests.test_business_actions_postgres import actions  # noqa: E402,F401


@pytest.mark.owner_acts
def test_export_windows_download_the_whole_history_with_exact_money(actions):  # noqa: F811
    import io
    import json
    from zipfile import ZipFile

    from argus.domain.business.contracts.actions import ApproveExpense, ReviewDraft
    from argus.domain.business.contracts.facts import BusinessFactPatch
    from argus.domain.business.export import ExportPeriod, export_package
    from argus.domain.business.ledger import today
    from argus.domain.ingestion.documents.objects import InMemorySourceObjects

    from tests.test_business_actions_postgres import create

    service, context, _ = actions
    recorded = [("2024-02-29", "850", "DOP"), ("2026-10-01", "12.34", "USD")]
    for day, amount, currency in recorded:
        draft, version = create(service, context)
        facts = BusinessFactPatch.model_validate(
            {
                name: {"state": "known", "value": value}
                for name, value in {
                    "kind": "expense",
                    "amount": amount,
                    "currency": currency,
                    "occurred_on": day,
                    "funding": {"kind": "owner_funds"},
                    "business_share": {"kind": "all"},
                }.items()
            }
        )
        review = ReviewDraft(version=version, facts=facts)
        assert service.review(context, draft, review, f"r-{day}").outcome == "applied"
        approve = ApproveExpense(version=version + 1, action="record_expense")
        assert service.approve(context, draft, approve, f"a-{day}").outcome == "applied"
    [preview] = PostgresBusinessLifecycle(service.authority.pool).owned_spaces(
        str(context.owner_id)
    )
    windows = preview["export_windows"]
    assert windows[0]["start"].isoformat() == "2024-02-29"
    assert windows[-1]["end"] >= today()
    for before, after in zip(windows, windows[1:], strict=False):
        assert (after["start"] - before["end"]).days == 1
    rows = []
    for window in windows:
        package = export_package(
            service.authority,
            context,
            ExportPeriod(window["start"], window["end"]),
            InMemorySourceObjects(),
        )
        with ZipFile(io.BytesIO(package)) as archive:
            rows += json.loads(archive.read("manifest.json"))["records"]
    assert sorted((r["occurred_on"], r["amount"], r["currency"]) for r in rows) == [
        ("2024-02-29", "850.00", "DOP"),
        ("2026-10-01", "12.34", "USD"),
    ]
