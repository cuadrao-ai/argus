from __future__ import annotations

import hashlib
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from argus.llm.openrouter import (
    begin_openrouter_route_receipt_capture,
    end_openrouter_route_receipt_capture,
)
from psycopg import Connection
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from tests.evals.business_scripted_plans import scripted_interpretation


@dataclass(frozen=True)
class CaseCapture:
    observed_steps: list[dict[str, Any]]
    capture_id: str
    graph_run_ids: list[str]
    tool_records: list[list[dict[str, Any]]]
    saved_states: list[dict[str, Any]]
    replies: list[str]
    db_namespace: str
    step_route_receipts: list[list[dict[str, Any]]]


class ScriptedInterpreter:
    def __init__(self, case_id: str, step_index: int, bindings: dict[str, str]) -> None:
        self.case_id = case_id
        self.step_index = step_index
        self.bindings = bindings

    async def ainterpret_business(self, payload: dict[str, Any]) -> dict[str, Any]:
        return scripted_interpretation(self.case_id, self.step_index, self.bindings)

    async def acompose_business(self, payload: dict[str, Any]) -> str:
        return f"Business state pending human review: {self.case_id}:{self.step_index}"


def scripted_interpreter(
    case_id: str, step_index: int, bindings: dict[str, str]
) -> ScriptedInterpreter:
    return ScriptedInterpreter(case_id, step_index, bindings)


def _local_dsn(dsn: str) -> str:
    try:
        options = conninfo_to_dict(dsn)
    except Exception as error:
        raise ValueError("Business E1 capture requires a valid Postgres DSN") from error
    loopback = {"127.0.0.1", "localhost", "::1"}
    if (
        options.get("host") not in loopback
        or options.get("hostaddr", options["host"]) not in loopback
        or options.get("service")
    ):
        raise ValueError("Business E1 capture requires an explicit loopback Postgres DSN")
    if os.environ.get("PGSERVICE") or os.environ.get("PGHOSTADDR") not in {
        None,
        "",
        "127.0.0.1",
        "::1",
    }:
        raise ValueError("Business E1 capture rejects inherited Postgres redirects")
    hostaddr = "::1" if options["host"] == "::1" else "127.0.0.1"
    return make_conninfo(dsn, hostaddr=hostaddr)


def _rows(pool: ConnectionPool, query: str, params: tuple[Any, ...]) -> list[dict]:
    with pool.connection() as db, db.cursor(row_factory=dict_row) as cursor:
        cursor.execute(query, params)
        return list(cursor.fetchall())


def _actor(bindings: dict[str, str], actor: dict[str, Any]) -> dict[str, str]:
    inverse = {str(value): key for key, value in bindings.items()}
    return {
        "actor": inverse[str(actor["actor_id"])],
        "grant": inverse[str(actor["grant_id"])],
        "issuer": inverse[str(actor["issuer_id"])],
    }


def _source_aliases(bindings: dict[str, str]) -> dict[str, str]:
    return {
        str(value): key
        for key, value in bindings.items()
        if key.startswith("message_") or key.startswith("review_")
    }


def _fact(fact: dict[str, Any], bindings: dict[str, str]) -> dict[str, Any]:
    result = {
        "state": fact["state"],
        "value": fact["value"],
        "verified": fact["verified"],
    }
    if fact.get("origin") is not None:
        result["origin"] = fact["origin"]
    value = result["value"]
    if isinstance(value, dict) and value.get("kind") == "business_account":
        inverse = {str(item): key for key, item in bindings.items()}
        result["value"] = {
            "kind": "business_account",
            "account": inverse[str(value["account_id"])],
        }
    return result


def _facts(facts: dict[str, Any], bindings: dict[str, str]) -> dict[str, Any]:
    return {
        field: _fact(fact, bindings) if field != "fiscal" else fact
        for field, fact in facts.items()
    }


def _fact_sources(facts: dict[str, Any], aliases: dict[str, str]) -> dict:
    return {
        field: [aliases[source_id] for source_id in fact["source_ids"]]
        for field, fact in facts.items()
        if field != "fiscal"
    }


def _money(
    service: Any, owner_id: str, space_id: str, baseline: dict
) -> tuple[dict, list]:
    from argus.domain.owner_scope import PERSONAL, BusinessSpace
    from argus.domain.recording.schemas import account_response

    money = service.imports.money
    business_scope = BusinessSpace(space_id)
    business = money.accounts.list_accounts(user_id=owner_id, scope=business_scope)
    personal = money.accounts.list_accounts(user_id=owner_id, scope=PERSONAL)
    purchases = money.purchases(user_id=owner_id, scope=business_scope)["items"]

    def positions(accounts: list) -> dict[str, tuple[int, int]]:
        projected = [account_response(account) for account in accounts]
        if any(item.balance.amount_minor is None for item in projected):
            raise ValueError("E1 seeded accounts require known balances")
        return {item.id: (item.balance.amount_minor, item.version) for item in projected}

    bank = positions(business)
    private = positions(personal)

    def delta(before: dict, after: dict) -> str:
        difference = sum(value[0] for value in after.values()) - sum(
            value[0] for value in before.values()
        )
        return str((Decimal(difference) / Decimal(100)).normalize())

    return (
        {
            "record_count": len(purchases),
            "bank_balance_delta": delta(baseline["bank"], bank),
            "personal_balance_delta": delta(baseline["personal"], private),
            "bank_versions_unchanged": {key: value[1] for key, value in bank.items()}
            == {key: value[1] for key, value in baseline["bank"].items()},
            "personal_versions_unchanged": {
                key: value[1] for key, value in private.items()
            }
            == {key: value[1] for key, value in baseline["personal"].items()},
            "bank_record_count": sum(len(account.expenses) for account in business),
            "personal_record_count": sum(len(account.expenses) for account in personal),
        },
        purchases,
    )


def _baseline(service: Any, owner_id: str, space_id: str) -> dict:
    from argus.domain.owner_scope import PERSONAL, BusinessSpace
    from argus.domain.recording.schemas import account_response

    def positions(scope: Any) -> dict[str, tuple[int, int]]:
        accounts = service.imports.money.accounts.list_accounts(
            user_id=owner_id, scope=scope
        )
        return {
            view.id: (view.balance.amount_minor, view.version)
            for view in (account_response(account) for account in accounts)
        }

    return {
        "bank": positions(BusinessSpace(space_id)),
        "personal": positions(PERSONAL),
    }


def _dossiers(service: Any, context: Any, drafts: dict[str, str]) -> list[dict]:
    return [
        service.dossier(context, UUID(draft_id)).model_dump(mode="json")
        for draft_id in drafts.values()
    ]


def _plan_references(
    plan: dict, outcomes: list[dict], by_id: dict[str, str]
) -> list[dict]:
    references = []
    for index, action in enumerate(plan["actions"]):
        reference = action.get("draft")
        if reference is None:
            continue
        if "from_action" in reference:
            draft_id = outcomes[reference["from_action"]]["draft_id"]
            references.append(
                {
                    "action_index": index,
                    "from_action": reference["from_action"],
                    "resolved_draft": by_id[draft_id],
                    "version": outcomes[reference["from_action"]]["version"],
                }
            )
        else:
            version = (
                reference["base_version"]
                if "base_version" in reference
                else reference["version"]
            )
            if "base_version" in reference:
                for previous, earlier in enumerate(plan["actions"][:index]):
                    if earlier.get("draft") != reference:
                        continue
                    receipt = outcomes[previous]
                    if (
                        receipt["outcome"] not in {"applied", "replayed"}
                        or receipt.get("draft_id") != reference["draft_id"]
                        or not isinstance(receipt.get("version"), int)
                        or receipt["version"] < version
                    ):
                        raise ValueError("Bound draft revision lacks applied receipt")
                    version = receipt["version"]
            references.append(
                {
                    "action_index": index,
                    "existing_draft": by_id[reference["draft_id"]],
                    "version": version,
                }
            )
    return references


def _project(
    *,
    pool: ConnectionPool,
    service: Any,
    context: Any,
    bindings: dict[str, str],
    drafts: dict[str, str],
    baseline: dict,
    actions: list[dict],
    plan: dict | None,
    outcomes: list[dict],
    transport: dict | None,
) -> dict[str, Any]:
    visible = {} if transport else drafts
    views = _dossiers(service, context, visible) if context is not None else []
    aliases = _source_aliases(bindings)
    by_id = {str(value): key for key, value in visible.items()}
    state: dict[str, Any] = {
        "draft_count": len(views),
        "draft_versions": {},
        "draft_sources": {},
        "fact_sources": {},
        "draft_facts": {},
        "revision_transitions": {},
        "questions": [],
        "actions": actions,
        "visible_sources": [],
        "source_evidence": {},
    }
    for view in views:
        alias = by_id[view["draft_id"]]
        state["draft_versions"][alias] = view["version"]
        state["draft_sources"][alias] = [
            aliases[source["id"]] for source in view["sources"]
        ]
        facts = view["facts"]
        state["draft_facts"][alias] = _facts(facts, bindings)
        state["fact_sources"][alias] = _fact_sources(facts, aliases)
        state["questions"].extend(
            {
                "field": question["field"],
                "asked_of": question["asked_of"],
                "state": question["state"],
                **(
                    {"answer_source": aliases[question["answer_source_id"]]}
                    if question["answer_source_id"]
                    else {}
                ),
            }
            for question in view["questions"]
        )
        state["blockers"] = [
            {
                "code": blocker["code"],
                **({"field": blocker["field"]} if blocker["field"] else {}),
            }
            for blocker in view["blockers"]
        ]
        state["approval_available"] = view["approval_available"]
        approval = view["approval_result"]
        state["approval"] = (
            None
            if approval is None
            else {
                "status": approval["status"],
                "reviewed_version": approval["reviewed_version"],
                **(
                    _actor(bindings, approval["actor"])
                    if approval["status"] == "recorded"
                    else {"code": approval["code"]}
                ),
            }
        )
        state["history"] = [
            {
                "version": revision["version"],
                **_actor(bindings, revision["actor"]),
                "sources": [aliases[item] for item in revision["source_ids"]],
            }
            for revision in view["history"]
        ]
        state.setdefault("revision_transitions", {})[alias] = [
            {
                "version": revision["version"],
                **_actor(bindings, revision["actor"]),
                "sources": [aliases[item] for item in revision["source_ids"]],
                "before": (
                    _facts(revision["before"], bindings)
                    if revision["before"] is not None
                    else None
                ),
                "before_sources": (
                    _fact_sources(revision["before"], aliases)
                    if revision["before"] is not None
                    else None
                ),
                "after": _facts(revision["after"], bindings),
                "after_sources": _fact_sources(revision["after"], aliases),
            }
            for revision in view["history"]
        ]
    if context is not None:
        sources = _rows(
            pool,
            "select id,kind,channel,text_content from public.business_sources"
            " where space_id=%s order by received_at,id",
            (context.actor.space_id,),
        )
        state["visible_sources"] = [aliases[str(row["id"])] for row in sources]
        state["source_evidence"] = {
            aliases[str(row["id"])]: {
                "kind": row["kind"],
                "channel": row["channel"],
                "text": row["text_content"],
            }
            for row in sources
        }
    if plan is not None:
        state["plan_references"] = _plan_references(plan, outcomes, by_id)
    if transport is not None:
        state["transport"] = transport
    money, purchases = _money(service, bindings["owner_a"], bindings["pilot_a"], baseline)
    state["money"] = money
    if len(purchases) == 1:
        purchase = purchases[0]
        state["recorded_activity"] = {
            "kind": purchase["kind"],
            "amount": format(Decimal(purchase["amount"]).normalize(), "f"),
            "currency": purchase["currency"],
            "funding": purchase["funding"],
        }
    return state


def _turn_row(pool: ConnectionPool, turn_key: str) -> dict:
    return _rows(
        pool,
        "select space_id,actor_id,sender_hash,turn_key,arrival_sequence,phase,"
        "model_state,plan,plan_actor,lease_fence,reply_text"
        " from public.business_turns where turn_key=%s",
        (turn_key,),
    )[0]


def _begin_reply(pool: ConnectionPool, turn_key: str) -> str | None:
    with pool.connection() as db, db.transaction():
        row = db.execute(
            "select phase,reply_text from public.business_turns"
            " where turn_key=%s for update",
            (turn_key,),
        ).fetchone()
        if row[1] is not None:
            return row[1]
        if row[0] != "turn_running":
            raise RuntimeError("business_reply_outcome_unknown")
        db.execute(
            "update public.business_turns set phase='reply_pending' where turn_key=%s",
            (turn_key,),
        )
    return None


def _save_reply(pool: ConnectionPool, turn_key: str, reply: str) -> None:
    with pool.connection() as db:
        db.execute(
            "update public.business_turns set phase='reply_sent',reply_text=%s"
            " where turn_key=%s and phase='reply_pending'",
            (reply, turn_key),
        )


def _turn_receipts(
    pool: ConnectionPool,
    turn_key: str,
    tool_records: tuple[dict[str, Any], ...],
    bindings: dict[str, str],
    draft_alias: str | None,
) -> tuple[list[dict], list[dict]]:
    rows = _rows(
        pool,
        "select action_index,actor,command,outcome from public.business_action_receipts"
        " where turn_key=%s order by action_index",
        (turn_key,),
    )
    if len(rows) != len(tool_records):
        raise ValueError("Business executor receipts do not match executed tools")
    actions = []
    outcomes = []
    for index, (row, record) in enumerate(zip(rows, tool_records, strict=True)):
        if (
            row["action_index"] != index
            or row["command"]["action"] != record["tool_name"]
        ):
            raise ValueError("Business tool and SQL receipt identities differ")
        saved = row["outcome"]
        if saved is None:
            raise ValueError("Business action receipt is unsettled")
        delivered = (
            record["tool_outcome"]["result"]["outcome"]
            if record["outcome"] == "succeeded"
            else saved
        )
        if record["outcome"] != "succeeded" and (
            record["tool_outcome"]["failure"]["code"] != saved["code"]
        ):
            raise ValueError("Business refusal differs from its SQL receipt")
        outcome = delivered["outcome"]
        if saved["outcome"] != outcome and not (
            saved["outcome"] == "applied" and outcome == "replayed"
        ):
            raise ValueError("Business tool outcome differs from its SQL receipt")
        action = {
            "name": record["tool_name"],
            "outcome": outcome,
            **_actor(bindings, row["actor"]),
        }
        answer_id = row["command"].get("answers_question_id")
        if answer_id is not None:
            questions = {
                str(value): key.removeprefix("question_")
                for key, value in bindings.items()
                if key.startswith("question_")
            }
            action["answers_question"] = questions[str(answer_id)]
        actions.append(action)
        outcomes.append(delivered)
        if (
            draft_alias is not None
            and index == 0
            and row["command"]["action"] == "business_propose_activity"
            and row["command"].get("draft") is None
            and delivered.get("draft_id")
        ):
            bindings[draft_alias] = delivered["draft_id"]
        if delivered.get("question_id"):
            bindings[f"question_{row['command']['field']}"] = delivered["question_id"]
    return actions, outcomes


def _command_receipt(
    pool: ConnectionPool, key: str, outcome: Any, bindings: dict[str, str]
) -> list[dict]:
    rows = _rows(
        pool,
        "select actor,command,outcome from public.business_action_receipts"
        " where idempotency_key=%s and space_id=%s",
        (key, UUID(bindings["pilot_a"])),
    )
    if len(rows) != 1:
        raise ValueError("Human command has no durable Business receipt")
    row = rows[0]
    saved = row["outcome"]
    if saved is None or (
        saved["outcome"] != outcome.outcome
        and not (saved["outcome"] == "applied" and outcome.outcome == "replayed")
    ):
        raise ValueError("Human outcome differs from its SQL receipt")
    return [
        {
            "name": row["command"]["action"],
            "outcome": outcome.outcome,
            **_actor(bindings, row["actor"]),
            "receipt_key": key,
        }
    ]


def _scope_counts(pool: ConnectionPool, space_id: str) -> tuple[int, int, int]:
    return tuple(
        _rows(
            pool,
            f"select count(*) as n from public.{table} where {column}=%s",
            (UUID(space_id),),
        )[0]["n"]
        for table, column in (
            ("financial_import_events", "owner_space_id"),
            ("business_sources", "space_id"),
            ("business_action_receipts", "space_id"),
        )
    )


def _receipt_snapshot(pool: ConnectionPool, space_id: str) -> list[dict]:
    return _rows(
        pool,
        "select actor_id,actor,idempotency_key,input_hash,turn_key,action_index,"
        "command,outcome"
        " from public.business_action_receipts where space_id=%s"
        " order by actor_id,idempotency_key",
        (UUID(space_id),),
    )


def _domain_snapshot(
    pool: ConnectionPool, service: Any, bindings: dict[str, str], baseline: dict
) -> tuple:
    space_id = UUID(bindings["pilot_a"])
    return (
        _rows(
            pool,
            "select id,kind,channel,text_content from public.business_sources"
            " where space_id=%s order by id",
            (space_id,),
        ),
        _rows(
            pool,
            "select draft_id,version,actor,source_ids from public.business_draft_revisions"
            " where space_id=%s order by draft_id,version",
            (space_id,),
        ),
        _rows(
            pool,
            "select id,version,state,resolution from public.financial_import_events"
            " where owner_space_id=%s order by id",
            (space_id,),
        ),
        _rows(
            pool,
            "select id,state,answer_source_id from public.business_questions"
            " where space_id=%s order by id",
            (space_id,),
        ),
        _money(service, bindings["owner_a"], bindings["pilot_a"], baseline),
    )


def _foreign_snapshot(pool: ConnectionPool, bindings: dict[str, str]) -> tuple:
    space_id = UUID(bindings["pilot_foreign"])
    owner_id = UUID(bindings["owner_foreign"])
    scoped = (
        ("business_client_grants", "space_id", space_id),
        ("business_sources", "space_id", space_id),
        ("business_draft_sources", "space_id", space_id),
        ("business_draft_revisions", "space_id", space_id),
        ("business_questions", "space_id", space_id),
        ("business_sender_leases", "space_id", space_id),
        ("business_turns", "space_id", space_id),
        ("business_action_receipts", "space_id", space_id),
        ("financial_import_events", "owner_space_id", space_id),
        ("financial_accounts", "owner_space_id", space_id),
        ("financial_records", "user_id", owner_id),
        ("financial_record_revisions", "user_id", owner_id),
        ("financial_activity_groups", "user_id", owner_id),
    )
    return tuple(
        _rows(
            pool,
            f"select to_jsonb(item) as value from public.{table} item"
            f" where {column}=%s order by to_jsonb(item)::text",
            (value,),
        )
        for table, column, value in scoped
    )


def _seed_accounts(service: Any, owner_id: str, space_id: str) -> dict[str, str]:
    from argus.domain.owner_scope import PERSONAL, BusinessSpace
    from argus.domain.recording.records import OpeningWrite
    from argus.domain.recording.repository import NewAccount

    accounts = {}
    for alias, scope in (
        ("shop_cash", BusinessSpace(space_id)),
        ("personal_cash", PERSONAL),
    ):
        created = service.imports.money.repository.create(
            user_id=owner_id,
            idempotency_key=str(uuid4()),
            identity_hash=uuid4().hex,
            account=NewAccount(
                type="cash",
                currency="DOP",
                nickname="Shop Cash" if alias == "shop_cash" else "Personal Cash",
                ownership_share_bps=10000,
            ),
            opening=OpeningWrite(
                amount_minor=1000000,
                as_of=datetime(2026, 10, 1, tzinfo=timezone.utc),
                time_zone="America/Santo_Domingo",
                reason=None,
            ),
            scope=scope,
        )
        accounts[alias] = created.stored.account.id
    return accounts


def _provision(
    db: Connection, case: dict[str, Any], users: dict[str, str]
) -> dict[str, str]:
    from tests.test_business_spaces_migration_postgres import event, space

    owner = users["e1-owner"]
    accountant = users["e1-accountant"]
    primary = space(db, owner)
    rows = db.execute(
        "insert into public.business_client_grants"
        " (space_id,grantee_id,issuer_id,capabilities)"
        " values (%s,%s,%s,ARRAY['read','prepare','approve']) returning id",
        (primary, owner, owner),
    ).fetchone()
    bindings = {
        "pilot_a": primary,
        "owner_a": owner,
        "accountant_a": accountant,
        "owner_grant_a": str(rows[0]),
    }
    if "accountant" in case["setup"]:
        grant = db.execute(
            "insert into public.business_client_grants"
            " (space_id,grantee_id,issuer_id,capabilities)"
            " values (%s,%s,%s,ARRAY['read','prepare','approve']) returning id",
            (primary, accountant, owner),
        ).fetchone()[0]
        bindings["grant_a"] = str(grant)
        if "revoked_grant" in case["setup"]:
            db.execute(
                "update public.business_client_grants set revoked_at=now() where id=%s",
                (grant,),
            )
    if "foreign_draft" in case["setup"]:
        foreign = space(db, users["e1-foreign"])
        bindings["pilot_foreign"] = foreign
        bindings["owner_foreign"] = users["e1-foreign"]
        bindings["draft_foreign"] = event(db, users["e1-foreign"], foreign)
    if "existing_draft" in case["setup"]:
        bindings["draft_f"] = event(db, owner, primary)
    db.commit()
    return bindings


async def capture_case(
    case: dict[str, Any],
    *,
    dsn: str,
    interpreter_factory: Callable[[str, int, dict[str, str]], Any],
    receipt_sink: Callable[[int, list[dict[str, Any]]], None] | None = None,
) -> CaseCapture:
    dsn = _local_dsn(dsn)
    from argus.agent_runtime.business.context import AuthorizedBusinessContext
    from argus.agent_runtime.business.runner import BusinessTurnRunner
    from argus.api.business_drafts import action_problem
    from argus.domain.business.actions import BusinessActions
    from argus.domain.business.authority import ActionError
    from argus.domain.business.contracts.actions import ApproveExpense
    from argus.domain.business.contracts.authority import TrustedActor
    from argus.domain.business.contracts.recovery import DurableTurn, SenderLease
    from argus.domain.ingestion.reconcile.service import ReconciliationService
    from argus.domain.ingestion.reconcile.store_postgres import PostgresImportStore
    from argus.domain.recording.money_service import MoneyService
    from argus.domain.recording.postgres_repository import (
        PostgresFinancialAccountRepository,
    )
    from argus.domain.recording.service import FinancialAccountService
    from fastapi import Request

    from tests import test_financial_accounts_postgres as shared

    users = None
    receipt_token = None
    active_step = -1
    with Connection.connect(dsn) as db:
        try:
            users = shared._create_users(
                db,
                ("e1-owner", False),
                ("e1-accountant", False),
                ("e1-foreign", False),
            )
            bindings = _provision(db, case, users)
            with ConnectionPool(dsn, min_size=0, max_size=4) as pool:
                money = MoneyService(
                    FinancialAccountService(PostgresFinancialAccountRepository(pool))
                )
                imports = ReconciliationService(
                    PostgresImportStore(pool), money, lambda: datetime.now(timezone.utc)
                )
                service = BusinessActions(pool, imports)
                bindings.update(
                    _seed_accounts(service, bindings["owner_a"], bindings["pilot_a"])
                )
                baseline = _baseline(service, bindings["owner_a"], bindings["pilot_a"])
                foreign_before = (
                    _foreign_snapshot(pool, bindings)
                    if "pilot_foreign" in bindings
                    else None
                )
                capture_id = uuid4().hex
                sender_hash = hashlib.sha256(capture_id.encode()).hexdigest()
                holder = uuid4()
                lease_until = datetime.now(timezone.utc) + timedelta(minutes=20)
                with pool.connection() as connection:
                    connection.execute(
                        "insert into public.business_sender_leases"
                        " (space_id,sender_hash,holder,fence,lease_until)"
                        " values (%s,%s,%s,1,%s)",
                        (
                            UUID(bindings["pilot_a"]),
                            sender_hash,
                            holder,
                            lease_until,
                        ),
                    )
                lease = SenderLease(
                    space_id=UUID(bindings["pilot_a"]),
                    sender_hash=sender_hash,
                    holder=holder,
                    fence=1,
                    lease_until=lease_until,
                )
                turns: dict[str, str] = {}
                messages: dict[str, tuple[UUID, datetime]] = {}
                histories: dict[str, list[dict[str, str]]] = {}
                history: list[dict[str, str]] = []
                drafts: dict[str, str] = {}
                observed_steps = []
                graph_run_ids = []
                all_tool_records = []
                saved_states = []
                replies = []
                step_route_receipts = []
                draft_aliases = {
                    "es_owner_funds_no_receipt": "draft_a",
                    "en_funding_correction": "draft_b",
                    "es_owner_does_not_know_amount": "draft_c",
                    "en_amount_not_supplied": "draft_g",
                    "en_replay_stale_and_current_grant": "draft_e",
                }
                for index, step in enumerate(case["steps"]):
                    active_step = index
                    prior_receipts = (
                        _receipt_snapshot(pool, bindings["pilot_a"])
                        if step.get("replay")
                        else None
                    )
                    prior_domain = (
                        _domain_snapshot(pool, service, bindings, baseline)
                        if step.get("replay")
                        else None
                    )
                    actions = []
                    outcomes = []
                    plan = None
                    transport = None
                    context = None
                    receipt_token = begin_openrouter_route_receipt_capture()
                    if step["actor"] == "owner_a":
                        source_alias = step["source"]
                        if source_alias not in messages:
                            messages[source_alias] = (
                                uuid4(),
                                datetime.now(timezone.utc),
                            )
                        message_id, received_at = messages[source_alias]
                        bindings[source_alias] = str(message_id)
                        if source_alias not in turns:
                            turns[source_alias] = f"e1:{capture_id}:{index}"
                            histories[source_alias] = list(history)
                            with pool.connection() as connection:
                                connection.execute(
                                    "insert into public.business_turns"
                                    " (turn_key,space_id,sender_hash,actor_id,phase,lease_fence)"
                                    " values (%s,%s,%s,%s,'turn_running',1)",
                                    (
                                        turns[source_alias],
                                        UUID(bindings["pilot_a"]),
                                        sender_hash,
                                        UUID(bindings["owner_a"]),
                                    ),
                                )
                        turn_key = turns[source_alias]
                        actor = TrustedActor(
                            actor_id=UUID(bindings["owner_a"]),
                            actor_kind="owner_via_agent",
                            space_id=UUID(bindings["pilot_a"]),
                        )
                        context = service.resolve_actor(
                            actor, grant_id=UUID(bindings["owner_grant_a"])
                        )
                        durable = DurableTurn.model_validate(_turn_row(pool, turn_key))
                        authorized = AuthorizedBusinessContext(
                            actions=service,
                            authorization=context,
                            turn_key=turn_key,
                            lease=lease,
                            message_id=message_id,
                            received_at=received_at,
                            channel=step["channel"],
                            begin_reply=lambda key=turn_key: _begin_reply(pool, key),
                            language="en" if case["id"].startswith("en_") else "es-419",
                        )
                        interpreter = interpreter_factory(case["id"], index, bindings)
                        result = await BusinessTurnRunner(interpreter=interpreter).run(
                            context=authorized,
                            turn=durable,
                            message=step["message"],
                            history=histories[source_alias],
                        )
                        _save_reply(pool, turn_key, result.reply_text)
                        plan = result.plan
                        actions, outcomes = _turn_receipts(
                            pool,
                            turn_key,
                            result.tool_records,
                            bindings,
                            draft_aliases.get(case["id"]),
                        )
                        if case["id"] in draft_aliases:
                            alias = draft_aliases[case["id"]]
                            if alias in bindings:
                                drafts[alias] = bindings[alias]
                        graph_run_ids.append(str(result.graph_run_id))
                        all_tool_records.append(list(result.tool_records))
                        saved_states.append(result.saved_state)
                        replies.append(result.reply_text)
                        if not step.get("replay"):
                            history.extend(
                                (
                                    {"role": "user", "content": step["message"]},
                                    {
                                        "role": "assistant",
                                        "content": result.reply_text,
                                    },
                                )
                            )
                    else:
                        actor = TrustedActor(
                            actor_id=UUID(bindings["accountant_a"]),
                            actor_kind="member",
                            space_id=UUID(bindings["pilot_a"]),
                        )
                        before = _scope_counts(pool, bindings["pilot_a"])
                        try:
                            context = service.resolve_actor(
                                actor, grant_id=UUID(bindings["grant_a"])
                            )
                        except ActionError as error:
                            request = Request(
                                {
                                    "type": "http",
                                    "method": "GET",
                                    "path": "/business/drafts",
                                    "headers": [],
                                }
                            )
                            request.state.request_id = capture_id
                            problem = action_problem(request, error.result)
                            transport = {
                                "status": problem.status_code,
                                "code": problem.detail["code"],
                            }
                            if _scope_counts(pool, bindings["pilot_a"]) != before:
                                raise ValueError(
                                    "Denied human command changed Business rows"
                                ) from error
                        else:
                            command = step["command"]
                            if command["action"] != "approve_expense":
                                raise ValueError(
                                    "Only approved human commands are scripted"
                                )
                            key = step["command_key"]
                            outcome = service.approve(
                                context,
                                UUID(bindings[command["draft"]]),
                                ApproveExpense(
                                    version=command["version"],
                                    action="record_expense",
                                ),
                                key,
                            )
                            actions = _command_receipt(pool, key, outcome, bindings)
                    step_receipts = [
                        receipt.as_dict()
                        for receipt in end_openrouter_route_receipt_capture(receipt_token)
                    ]
                    receipt_token = None
                    step_route_receipts.append(step_receipts)
                    if receipt_sink is not None:
                        receipt_sink(index, step_receipts)
                    observed = _project(
                        pool=pool,
                        service=service,
                        context=context,
                        bindings=bindings,
                        drafts=drafts,
                        baseline=baseline,
                        actions=actions,
                        plan=plan,
                        outcomes=outcomes,
                        transport=transport,
                    )
                    if foreign_before is not None:
                        observed["foreign_scope_unchanged"] = foreign_before == (
                            _foreign_snapshot(pool, bindings)
                        )
                    if prior_receipts is not None:
                        observed["replay_receipts_unchanged"] = (
                            prior_receipts == _receipt_snapshot(pool, bindings["pilot_a"])
                            and bool(prior_receipts)
                        )
                        observed["replay_domain_unchanged"] = prior_domain == (
                            _domain_snapshot(pool, service, bindings, baseline)
                        )
                    observed_steps.append(observed)
                return CaseCapture(
                    observed_steps=observed_steps,
                    capture_id=capture_id,
                    graph_run_ids=graph_run_ids,
                    tool_records=all_tool_records,
                    saved_states=saved_states,
                    replies=replies,
                    db_namespace=bindings["pilot_a"],
                    step_route_receipts=step_route_receipts,
                )
        finally:
            if receipt_token is not None:
                partial_receipts = [
                    receipt.as_dict()
                    for receipt in end_openrouter_route_receipt_capture(receipt_token)
                ]
                if receipt_sink is not None:
                    receipt_sink(active_step, partial_receipts)
            if users is not None:
                shared._delete_users(db, users)
