"""Business-data rollback probe on real Postgres and local Storage.

seed and verify run under the activation code; read, grant and delete run under
Build 2 code. Run from that version's worktree with PYTHONPATH=src:.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import secrets
import sys
import traceback
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import psycopg
from psycopg_pool import ConnectionPool

HANDOFF = Path(os.environ["COMPAT_HANDOFF"])
DSN = os.environ["ARGUS_DISPOSABLE_DATABASE_URL"]
ZONE = "America/Santo_Domingo"
RECEIPT = Path("tests/document_extraction_fixtures/receipt-dop.png").read_bytes()
ROWS_SQL = Path(
    "/Users/garces/Documents/projects/repos/argus-worktrees/compat-activation/"
    "scripts/ops/business_space_rows.sql"
).read_text()


def out(label: str, value: object) -> None:
    print(f"{label}: {json.dumps(value, default=str)}", flush=True)


def now() -> datetime:
    return datetime.now(timezone.utc)


def attempt(label: str, fn):
    try:
        value = fn()
        out(label, {"ok": True, "value": value})
        return value
    except Exception as error:  # the probe reports every outcome, raised or not
        out(label, {"ok": False, "error": f"{type(error).__name__}: {error}"[:400]})
        return None


def rows_sql() -> dict:
    with psycopg.connect(DSN) as conn:
        cur = conn.execute(ROWS_SQL)
        return dict(zip([d.name for d in cur.description], cur.fetchone()))


def gateway():
    from tests.local_supabase_support import local_supabase_gateway

    return local_supabase_gateway()


def label_of(state: dict, ident: str) -> str:
    for name, value in state["ids"].items():
        if value == ident:
            return name
    return "other"


def seed() -> None:
    from argus.api.whatsapp import DocumentsDestination
    from argus.domain.business.scope import resolve_business_scope
    from argus.domain.ingestion.documents.jobs import PreparationJobs, run_attempt
    from argus.domain.ingestion.whatsapp.store import Settlement
    from argus.domain.ingestion.whatsapp.store_postgres import PostgresWhatsAppStore
    from argus.domain.owner_scope import PERSONAL

    from tests.test_business_space_isolation_postgres import SIDES, World, _seed

    out("rows_sql_before_seed", rows_sql())
    pool = ConnectionPool(DSN, min_size=0, max_size=8, open=True)
    world = World(pool)
    email = f"compat-biz-{secrets.token_hex(4)}@example.test"
    person = str(
        gateway()
        .client.auth.admin.create_user(
            {"email": email, "password": f"Pw-{secrets.token_urlsafe(18)}", "email_confirm": True}
        )
        .user.id
    )
    world.people["a"] = person
    world.spaces.create(person, "Mi negocio")
    scope = resolve_business_scope(world.spaces, person)
    world.biz["a"] = scope
    world.scope[("a", "personal")] = PERSONAL
    world.scope[("a", "business")] = scope.owner
    for side in SIDES:
        _seed(world, "a", side)
    ids = {
        "personal_account": world.account[("a", "personal")],
        "business_account": world.account[("a", "business")],
        "personal_expense": world.expense[("a", "personal")],
        "business_expense": world.expense[("a", "business")],
        "personal_receipt": world.receipt[("a", "personal")],
        "business_receipt": world.receipt[("a", "business")],
        "space": scope.owner.space_id,
    }
    store = PostgresWhatsAppStore(pool)
    sender, code = bytes(range(32)), hashlib.sha256(secrets.token_bytes(16)).digest()
    t = now()
    store.issue_code(
        destination_owner_id=person,
        code_digest=code,
        reply_language="es-419",
        now=t,
        expires_at=t + timedelta(minutes=10),
    )
    store.redeem_code(code_digest=code, sender_hash=sender, last4="1234", now=t)
    captured = asyncio.run(
        DocumentsDestination(world.documents, world.spaces).capture(
            owner_id=person,
            content=RECEIPT + b"wa",
            filename="wa.png",
            media_type="image/png",
        )
    )
    key = hashlib.sha256(secrets.token_bytes(16)).digest()
    claim = store.claim(
        provider_message_key=key, sender_hash=sender, now=t, claim_until=t + timedelta(seconds=90)
    )
    store.settle(
        provider_message_key=key,
        claim_until=claim.record.claim_until,
        settlement=Settlement("captured", person, captured.connection_id),
        now=t,
    )
    ids["whatsapp_receipt"] = captured.connection_id
    dispatched: list[tuple[str, str]] = []
    jobs = PreparationJobs(world.documents, lambda cid, aid: dispatched.append((cid, aid)))
    for name, tag, owner, run in (
        ("personal_job_prepared", b"pjob", PERSONAL, True),
        ("personal_job_queued", b"pq", PERSONAL, False),
        ("business_job_prepared", b"bjob", scope.owner, True),
    ):
        receipt = asyncio.run(
            world.documents.upload(
                user_id=person,
                content=RECEIPT + tag,
                filename=f"{name}.png",
                media_type="image/png",
                consent=True,
                scope=owner,
            )
        ).connection_id
        jobs.start(user_id=person, connection_id=receipt)
        cid, attempt_id = dispatched[-1]
        if run:
            out(f"run_attempt_{name}", asyncio.run(run_attempt(world.documents, cid, attempt_id)))
        ids[name] = receipt
    state = {"person": person, "ids": ids}
    HANDOFF.write_text(json.dumps(state))
    out("seeded_ids", ids)
    with pool.connection() as conn:
        out(
            "jobs",
            conn.execute(
                "select connection_id::text, draft->>'status', preparation_job is not null"
                " from public.financial_document_extractions where user_id=%s order by 1",
                (person,),
            ).fetchall(),
        )
        out(
            "whatsapp_rows",
            {
                t: conn.execute(
                    f"select count(*) from public.{t} where destination_owner_id=%s", (person,)
                ).fetchone()[0]
                for t in ("whatsapp_link_codes", "whatsapp_sender_links", "whatsapp_inbound_messages")
            },
        )
    out("rows_sql_after_seed", rows_sql())
    pool.close()


class StubExtractor:
    async def extract(self, *, connection_id: str, observed_at=None, **_: object):  # noqa: ANN001
        from argus.domain.ingestion.contract import ImportCandidate, SourceRef
        from argus.domain.ingestion.documents.models import ExtractionBatch

        return ExtractionBatch(
            candidates=(
                ImportCandidate(
                    source=SourceRef(
                        source="statement",
                        connection_id=connection_id,
                        external_id="stub:1",
                        observed_at=observed_at or now(),
                    ),
                    evidence="transaction",
                    status="posted",
                    amount="40.00",
                    currency="DOP",
                    direction="outflow",
                    kind_hint="expense",
                    occurred_on=date(2026, 10, 6),
                ),
            )
        )


def build2_world(pool: ConnectionPool) -> dict:
    from argus.domain.ingestion.connections_postgres import PostgresConnectionRepository
    from argus.domain.ingestion.documents.service import DocumentsService
    from argus.domain.ingestion.documents.store_postgres import PostgresDocumentStore
    from argus.domain.ingestion.hub import IngestionHub
    from argus.domain.ingestion.reconcile.service import ReconciliationService
    from argus.domain.ingestion.reconcile.store_postgres import PostgresImportStore
    from argus.domain.recording.money_service import MoneyService
    from argus.domain.recording.postgres_repository import PostgresFinancialAccountRepository
    from argus.domain.recording.service import FinancialAccountService

    try:
        from tests.document_sources_support import source_objects
    except ImportError:  # Build 1 has no Storage-backed sources
        source_objects = None

    repository = PostgresFinancialAccountRepository(pool)
    accounts = FinancialAccountService(repository, now)
    money = MoneyService(accounts)
    connections = PostgresConnectionRepository(pool)
    imports = ReconciliationService(PostgresImportStore(pool), money, now, connections=connections)
    hub = IngestionHub(connections, box=None, sink=imports, clock=now)
    import inspect

    takes_objects = "objects" in inspect.signature(PostgresDocumentStore).parameters
    store = (
        PostgresDocumentStore(pool, source_objects())
        if takes_objects
        else PostgresDocumentStore(pool)
    )
    documents = DocumentsService(hub, store, StubExtractor())
    return {
        "repository": repository,
        "accounts": accounts,
        "money": money,
        "connections": connections,
        "imports": imports,
        "hub": hub,
        "documents": documents,
    }


def read() -> None:
    from argus.domain import financial_search
    from argus.domain.planning import storage
    from argus.domain.planning.service import PlanService
    from argus.domain.recording.money_schemas import MoneyRequest

    state = json.loads(HANDOFF.read_text())
    person, ids = state["person"], state["ids"]
    pool = ConnectionPool(DSN, min_size=0, max_size=8, open=True)
    w = build2_world(pool)
    L = lambda i: label_of(state, i)  # noqa: E731
    out(
        "R_accounts_list",
        [(L(s.account.id), s.account.nickname) for s in w["accounts"].list_accounts(user_id=person)],
    )
    st, accts = storage.read(w["repository"], person)
    out("R_storage_read_accounts", [L(s.account.id) for s in accts])
    out("R_canonical_activities", sorted(L(a) for a in st["_canonical_groups"].current))
    hits = financial_search.search(w["accounts"], person, q="").items
    out(
        "R_search_hits",
        sorted(
            (h.kind, L(h.account.id if h.kind == "account" else h.activity.activity_id))
            for h in hits
            if h.kind in ("account", "activity")
        ),
    )
    today = datetime.now(ZoneInfo(ZONE)).date()
    overview = PlanService(w["accounts"]).read(person, today, today + timedelta(days=30))
    out("R_home_currencies", overview["home"]["currencies"])
    out(
        "R_home_recent_activity_accounts",
        sorted({L(a["account_id"]) for a in overview["home"]["recent_activity"]}),
    )
    out("R_connections", sorted(L(c.id) for c in w["connections"].list(user_id=person)))
    events = w["imports"].list(user_id=person, states=("open",))
    out(
        "R_open_import_events",
        sorted(L(o["connection_id"]) for e in events for o in e["observations"]),
    )
    for name in (
        "personal_receipt",
        "business_receipt",
        "whatsapp_receipt",
        "personal_job_prepared",
        "personal_job_queued",
        "business_job_prepared",
    ):
        attempt(
            f"R_document_get_{name}",
            lambda n=name: w["documents"].get(user_id=person, connection_id=ids[n]).status,
        )
    attempt(
        "R_document_source_business_receipt",
        lambda: len(w["documents"].source_bytes(user_id=person, connection_id=ids["business_receipt"])),
    )
    if os.environ.get("COMPAT_WRITES", "1") == "0":
        out("rows_sql_after_read", rows_sql())
        pool.close()
        return
    # Writes Build 2 offers on what it shows as Personal.
    attempt(
        "W_expense_into_business_account",
        lambda: w["money"].write_entered(
            user_id=person,
            request=MoneyRequest(
                kind="expense",
                account_id=ids["business_account"],
                amount="55.00",
                occurred_at=datetime(2026, 10, 7, tzinfo=timezone.utc),
                time_zone=ZONE,
                note="Escrito por Build 2",
                category_id=None,
            ),
            idempotency_key="build2-into-business",
        )["activity"]["activity_id"],
    )
    business_events = [
        e for e in events for o in e["observations"] if o["connection_id"] == ids["business_receipt"]
    ]
    if business_events:
        event = business_events[0]
        attempt(
            "W_resolve_business_receipt_event_to_personal_account",
            lambda: w["imports"].resolve(
                user_id=person,
                event_id=event["id"],
                version=event["version"],
                changes={"account_id": ids["personal_account"]},
            )["state"],
        )

    def requeue_and_prepare() -> object:
        queued = w["documents"].queue(
            user_id=person, connection_id=ids["personal_job_queued"], consent=True
        )
        asyncio.run(
            w["documents"].background_prepare(
                user_id=person, connection_id=ids["personal_job_queued"]
            )
        )
        return (queued.status, w["documents"].get(
            user_id=person, connection_id=ids["personal_job_queued"]
        ).status)

    attempt("W_prepare_activation_queued_personal_job", requeue_and_prepare)
    with pool.connection() as conn:
        out(
            "W_job_column_after_build2_prepare",
            conn.execute(
                "select draft->>'status', preparation_job from public.financial_document_extractions"
                " where connection_id=%s",
                (ids["personal_job_queued"],),
            ).fetchone(),
        )
    attempt(
        "W_disconnect_whatsapp_business_receipt",
        lambda: w["hub"].disconnect(user_id=person, connection_id=ids["whatsapp_receipt"]).__class__.__name__,
    )
    with pool.connection() as conn:
        out(
            "whatsapp_inbound_after_disconnect",
            conn.execute(
                "select status, connection_id is not null from public.whatsapp_inbound_messages"
                " where destination_owner_id=%s",
                (person,),
            ).fetchall(),
        )
    out("rows_sql_after_build2_writes", rows_sql())
    pool.close()


def grant() -> None:
    from argus.domain.household.postgres import PostgresHouseholdRepository
    from argus.domain.household.repository import FinancialAccountLookup
    from argus.domain.household.service import HouseholdService
    from argus.domain.recording.postgres_repository import PostgresFinancialAccountRepository

    from tests.household.financial_fixtures import NOW, setup, share

    os.environ.setdefault("ARGUS_INVITE_CODE_SECRET", secrets.token_hex(32))
    state = json.loads(HANDOFF.read_text())
    person, ids = state["person"], state["ids"]
    pool = ConnectionPool(DSN, min_size=1, max_size=5)
    records = PostgresFinancialAccountRepository(pool)
    s = HouseholdService(
        PostgresHouseholdRepository(pool, FinancialAccountLookup(records), clock=lambda: NOW)
    )
    other = str(
        gateway()
        .client.auth.admin.create_user(
            {
                "email": f"compat-member-{secrets.token_hex(4)}@example.test",
                "password": f"Pw-{secrets.token_urlsafe(18)}",
                "email_confirm": True,
            }
        )
        .user.id
    )
    hid, member, _ = setup((s, records, (person, other, other)))
    state["household"], state["member_user"] = hid, other
    HANDOFF.write_text(json.dumps(state))
    attempt(
        "W_share_personal_account_with_household",
        lambda: share(s, person, hid, ids["personal_account"], member).__class__.__name__,
    )
    try:
        share(s, person, hid, ids["business_account"], member)
        out("W_share_business_account_with_household", {"ok": True})
    except Exception as error:
        out(
            "W_share_business_account_with_household",
            {"ok": False, "error": f"{type(error).__name__}: {error}"[:300]},
        )
        traceback.print_exc(limit=2)
    pool.close()


def verify() -> None:
    from argus.domain.owner_scope import PERSONAL

    from tests.test_business_space_isolation_postgres import World
    from argus.domain.business.scope import resolve_business_scope

    state = json.loads(HANDOFF.read_text())
    person, ids = state["person"], state["ids"]
    pool = ConnectionPool(DSN, min_size=0, max_size=8, open=True)
    world = World(pool)
    scope = resolve_business_scope(world.spaces, person)
    L = lambda i: label_of(state, i)  # noqa: E731
    out(
        "V_business_expenses",
        [
            (L(e["id"]), e.get("amount"))
            for e in world.business.expenses(scope, date(2026, 10, 1), date(2026, 10, 31))
        ],
    )
    out("V_business_accounts", [L(x["id"]) for x in world.business.accounts_for_expenses(scope)])
    out("V_business_receipts", [(L(r.id), r.status) for r in world.business.receipts(scope)])
    out(
        "V_personal_accounts",
        [L(s.account.id) for s in world.accounts.list_accounts(user_id=person, scope=PERSONAL)],
    )
    out(
        "V_personal_open_events",
        sorted(
            L(o["connection_id"])
            for e in world.imports.list(user_id=person, states=("open",), scope=PERSONAL)
            for o in e["observations"]
        ),
    )
    from argus.domain.ingestion.documents.jobs import run_attempt

    with pool.connection() as conn:
        job = conn.execute(
            "select preparation_job from public.financial_document_extractions where connection_id=%s",
            (ids["personal_job_queued"],),
        ).fetchone()[0]
    attempt(
        "V_activation_runs_its_pending_attempt_after_build2_prepared",
        lambda: asyncio.run(run_attempt(world.documents, ids["personal_job_queued"], job["attempt_id"])),
    )
    with pool.connection() as conn:
        out(
            "V_job_after_activation_attempt",
            conn.execute(
                "select draft->>'status', preparation_job from public.financial_document_extractions where connection_id=%s",
                (ids["personal_job_queued"],),
            ).fetchone(),
        )
    for name in ("personal_job_queued",):
        attempt(
            f"V_document_{name}",
            lambda n=name: world.documents.get(
                user_id=person, connection_id=ids[n], scope=PERSONAL
            ).status,
        )
    pool.close()


def delete() -> None:
    from argus.api.account_deletion_runtime import build_service

    state = json.loads(HANDOFF.read_text())
    person = state["person"]
    os.environ.setdefault("APP_ENV", "local")
    service = build_service(database_url=DSN, supabase_client=gateway().client)
    attempt(
        "D_account_deletion",
        lambda: (lambda o: {"status": o.status})(service.delete_account(user_id=person)),
    )
    with psycopg.connect(DSN) as conn:
        out(
            "D_after",
            {
                "auth_user": conn.execute(
                    "select count(*) from auth.users where id=%s", (person,)
                ).fetchone()[0],
                "spaces": conn.execute(
                    "select count(*) from public.spaces where created_by=%s", (person,)
                ).fetchone()[0],
                "accounts": conn.execute(
                    "select count(*) from public.financial_accounts where user_id=%s", (person,)
                ).fetchone()[0],
                "whatsapp_links": conn.execute(
                    "select count(*) from public.whatsapp_sender_links where destination_owner_id=%s",
                    (person,),
                ).fetchone()[0],
                "storage_objects": conn.execute(
                    "select count(*) from storage.objects where bucket_id='financial-document-sources'"
                    " and starts_with(name, %s)",
                    (person + "/",),
                ).fetchone()[0],
                "deletion_run": conn.execute(
                    "select status, steps from argus_private.account_deletion_runs order by created_at desc limit 1"
                ).fetchone(),
            },
        )
    out("rows_sql_after_delete", rows_sql())


if __name__ == "__main__":
    {"seed": seed, "read": read, "grant": grant, "verify": verify, "delete": delete, "writes2": lambda: None}[sys.argv[1]]()


def writes2() -> None:
    """Build 2: enter an expense into the account it lists as Personal (the
    Business one), and accept the Business receipt's event into the Personal
    account it was resolved to."""
    from argus.domain.recording.money_schemas import MoneyRequest

    state = json.loads(HANDOFF.read_text())
    person, ids = state["person"], state["ids"]
    pool = ConnectionPool(DSN, min_size=0, max_size=8, open=True)
    w = build2_world(pool)
    L = lambda i: label_of(state, i)  # noqa: E731
    request = MoneyRequest(
        kind="expense",
        account_id=ids["business_account"],
        amount="55.00",
        occurred_at=datetime(2026, 10, 7, tzinfo=timezone.utc),
        time_zone=ZONE,
        note="Written by Build 2",
        category_id=None,
    )

    def enter() -> object:
        preview = w["money"].preview(user_id=person, request=request)
        reviewed = MoneyRequest.model_validate(preview["reviewed_request"]).model_copy(
            update={"preview_token": preview["preview_token"]}
        )
        result = w["money"].write(
            user_id=person, request=reviewed, idempotency_key="build2-into-business"
        )
        state["ids"]["build2_expense_in_business_account"] = result["activity"]["activity_id"]
        HANDOFF.write_text(json.dumps(state))
        return result["activity"]["activity_id"]

    if os.environ.get("COMPAT_SKIP_ENTER") != "1":
        attempt("W_expense_into_business_account", enter)
    events = w["imports"].list(user_id=person, states=("open",))
    [event] = [
        e for e in events for o in e["observations"] if o["connection_id"] == ids["business_job_prepared"]
    ]

    def accept() -> object:
        w["imports"].resolve(
            user_id=person,
            event_id=event["id"],
            version=event["version"],
            changes={"account_id": ids["personal_account"]},
        )
        preview = w["imports"].preview(user_id=person, event_id=event["id"], overrides={})
        reviewed = request.__class__.model_validate(preview["preview"]["reviewed_request"])
        reviewed = reviewed.model_copy(update={"preview_token": preview["preview"]["preview_token"]})
        current = w["imports"].detail(user_id=person, event_id=event["id"])
        result = w["imports"].accept(
            user_id=person,
            event_id=event["id"],
            idempotency_key="build2-accept-business-receipt",
            version=current["version"],
            request=reviewed,
        )
        activity = result.get("activity", {}) if isinstance(result, dict) else {}
        state["ids"]["build2_accepted_business_receipt"] = activity.get("activity_id")
        HANDOFF.write_text(json.dumps(state))
        return {"account": L(reviewed.account_id), "activity": activity.get("activity_id"), "state": result.get("state") if isinstance(result, dict) else None}

    attempt("W_accept_business_receipt_into_personal_account", accept)
    with pool.connection() as conn:
        out(
            "W_records_by_account_space",
            conn.execute(
                "select coalesce(a.owner_space_id::text,'personal') as account_space, r.record_kind, count(*)"
                " from public.financial_records r join public.financial_accounts a on a.id=r.account_id"
                " where r.user_id=%s group by 1,2 order by 1,2",
                (person,),
            ).fetchall(),
        )
        out(
            "W_event_space_vs_account",
            conn.execute(
                "select e.owner_space_id is not null as event_is_business, e.state"
                " from public.financial_import_events e where e.id=%s",
                (event["id"],),
            ).fetchone(),
        )
    pool.close()


if __name__ == "__main__" and sys.argv[1] == "writes2":
    writes2()
