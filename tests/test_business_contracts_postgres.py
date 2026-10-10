from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

import pytest
from argus.domain.business.contracts.actions import MAX_TURN_ACTIONS
from faker import Faker
from psycopg import Connection, errors
from psycopg.types.json import Jsonb

from tests import test_financial_accounts_postgres as shared
from tests.test_business_spaces_migration_postgres import (
    connection,
    event,
    observation,
    space,
)

fake = Faker()
users = shared.users
pytestmark = pytest.mark.skipif(
    not shared.DSN, reason="ARGUS_DISPOSABLE_DATABASE_URL is not configured"
)
TABLES = (
    "business_client_grants",
    "business_sources",
    "business_draft_sources",
    "business_draft_revisions",
    "business_questions",
    "business_sender_leases",
    "business_turns",
    "business_action_receipts",
)


@pytest.fixture
def db(users: dict[str, str]) -> Iterator[Connection]:
    with Connection.connect(shared.DSN) as conn:
        with conn.transaction(force_rollback=True):
            yield conn


@pytest.fixture
def client(db: Connection, users: dict[str, str]) -> dict[str, str]:
    owner = users["owner"]
    client_id = space(db, owner)
    return {
        "id": client_id,
        "owner": owner,
        "draft": event(db, owner, client_id),
        "grant": fake.uuid4(),
    }


def actor_provenance(client: dict[str, str]) -> dict[str, str]:
    return {
        "actor_id": client["owner"],
        "actor_kind": "member",
        "display_name": "Synthetic member",
        "grant_id": client["grant"],
        "issuer_id": client["owner"],
        "issuer_display_name": "Synthetic issuer",
    }


def add_source(db: Connection, space_id: str) -> str:
    return str(
        db.execute(
            "insert into public.business_sources"
            " (space_id, kind, channel, source_key, text_content, received_at)"
            " values (%s, 'message', 'whatsapp', %s, %s, now()) returning id",
            (space_id, fake.sha256(), fake.sentence()),
        ).fetchone()[0]
    )


def add_turn(db: Connection, client: dict[str, str], actions: list[dict] | None) -> str:
    key = fake.sha256()
    plan = None if actions is None else Jsonb({"schema_version": 1, "actions": actions})
    db.execute(
        "insert into public.business_turns"
        " (turn_key, space_id, sender_hash, actor_id, model_state, plan, plan_actor)"
        " values (%s, %s, %s, %s, %s, %s, %s)",
        (
            key,
            client["id"],
            fake.sha256(),
            client["owner"],
            "not_started" if plan is None else "completed",
            plan,
            None if actions is None else Jsonb(actor_provenance(client)),
        ),
    )
    return key


def add_receipt(db: Connection, client: dict[str, str], key: str, command: dict) -> None:
    db.execute(
        "insert into public.business_action_receipts"
        " (space_id, actor_id, idempotency_key, input_hash, command, turn_key, action_index, actor)"
        " values (%s, %s, %s, %s, %s, %s, 0, %s)",
        (
            client["id"],
            client["owner"],
            key,
            fake.sha256(),
            Jsonb(command),
            key,
            Jsonb(actor_provenance(client)),
        ),
    )


@pytest.mark.parametrize("table", TABLES)
def test_contract_tables_have_rls_and_no_client_grants(
    db: Connection, table: str
) -> None:
    enabled, anon, authenticated = db.execute(
        "select c.relrowsecurity,"
        " has_table_privilege('anon', c.oid, 'SELECT,INSERT,UPDATE,DELETE'),"
        " has_table_privilege('authenticated', c.oid, 'SELECT,INSERT,UPDATE,DELETE')"
        " from pg_class c join pg_namespace n on n.oid=c.relnamespace"
        " where n.nspname='public' and c.relname=%s",
        (table,),
    ).fetchone()
    assert enabled and not anon and not authenticated
    assert not db.execute(
        "select has_table_privilege('service_role', %s, 'TRUNCATE')",
        (f"public.{table}",),
    ).fetchone()[0]


def test_business_resolution_cannot_attach_to_personal_event(
    db: Connection,
    users: dict[str, str],
    client: dict[str, str],
) -> None:
    personal = event(db, users["owner"])
    resolution = Jsonb({"business": {"schema_version": 1, "facts": {}}})
    with pytest.raises(errors.CheckViolation), db.transaction():
        db.execute(
            "update public.financial_import_events set resolution=%s where id=%s",
            (resolution, personal),
        )
    db.execute(
        "update public.financial_import_events set resolution=%s where id=%s",
        (resolution, client["draft"]),
    )
    with pytest.raises(errors.CheckViolation), db.transaction():
        db.execute(
            "update public.financial_import_events set resolution=%s where id=%s",
            (Jsonb({"business": {}}), client["draft"]),
        )


def test_business_imports_require_server_reads_while_personal_owner_access_remains(
    db: Connection,
    client: dict[str, str],
) -> None:
    personal_event = event(db, client["owner"])
    personal_connection = connection(db, client["owner"])
    business_connection = connection(db, client["owner"], client["id"])
    personal_observation = observation(
        db, client["owner"], personal_event, personal_connection
    )
    business_observation = observation(
        db, client["owner"], client["draft"], business_connection
    )
    db.execute("set local role authenticated")
    db.execute(
        "select set_config('request.jwt.claims', %s, true)",
        (
            json.dumps(
                {"sub": client["owner"], "role": "authenticated", "is_anonymous": False}
            ),
        ),
    )
    event_ids = [personal_event, client["draft"]]
    source_ids = [personal_observation, business_observation]
    assert {
        str(row[0])
        for row in db.execute(
            "select id from public.financial_import_events where id = any(%s::uuid[])",
            (event_ids,),
        ).fetchall()
    } == {personal_event}
    assert {
        str(row[0])
        for row in db.execute(
            "select id from public.financial_import_observations where id = any(%s::uuid[])",
            (source_ids,),
        ).fetchall()
    } == {personal_observation}
    db.execute("set local role service_role")
    assert {
        str(row[0])
        for row in db.execute(
            "select id from public.financial_import_events where id = any(%s::uuid[])",
            (event_ids,),
        ).fetchall()
    } == set(event_ids)
    assert {
        str(row[0])
        for row in db.execute(
            "select id from public.financial_import_observations where id = any(%s::uuid[])",
            (source_ids,),
        ).fetchall()
    } == set(source_ids)


def test_sources_and_questions_cannot_cross_clients(
    db: Connection,
    users: dict[str, str],
    client: dict[str, str],
) -> None:
    other_space = space(db, users["other"])
    foreign_source = add_source(db, other_space)
    foreign_connection = connection(db, users["other"], other_space)
    with pytest.raises(errors.ForeignKeyViolation), db.transaction():
        db.execute(
            "insert into public.business_draft_sources (space_id,draft_id,source_id)"
            " values (%s,%s,%s)",
            (client["id"], client["draft"], foreign_source),
        )
    with pytest.raises(errors.ForeignKeyViolation), db.transaction():
        db.execute(
            "insert into public.business_sources"
            " (space_id,kind,channel,source_key,connection_id,received_at)"
            " values (%s,'attachment','web',%s,%s,now())",
            (client["id"], fake.sha256(), foreign_connection),
        )
    with pytest.raises(errors.ForeignKeyViolation), db.transaction():
        db.execute(
            "insert into public.business_questions"
            " (space_id,draft_id,field,asked_of,channel,state,prompt,"
            " allowed_answers,answer_source_id)"
            " values (%s,%s,'funding','accountant','web','answered',%s,"
            " ARRAY['known'],%s)",
            (client["id"], client["draft"], fake.sentence(), foreign_source),
        )


def test_revision_before_after_cannot_be_rewritten_and_client_deletion_cascades(
    db: Connection,
    client: dict[str, str],
) -> None:
    fixture = json.loads(
        (
            Path(__file__).parent
            / "business"
            / "fixtures"
            / "hosted_business_dossier.json"
        ).read_text()
    )
    revision = fixture["history"][0]
    db.execute(
        "insert into public.business_draft_revisions"
        " (space_id,draft_id,version,actor,before_facts,after_facts)"
        " values (%s,%s,2,%s,%s,%s)",
        (
            client["id"],
            client["draft"],
            Jsonb(revision["actor"]),
            Jsonb(revision["before"]),
            Jsonb(revision["after"]),
        ),
    )
    with (
        pytest.raises(errors.CheckViolation, match="business_evidence_immutable"),
        db.transaction(),
    ):
        db.execute(
            "update public.business_draft_revisions set after_facts='{}'"
            " where draft_id=%s",
            (client["draft"],),
        )
    with (
        pytest.raises(errors.CheckViolation, match="business_evidence_immutable"),
        db.transaction(),
    ):
        db.execute(
            "delete from public.business_draft_revisions where draft_id=%s",
            (client["draft"],),
        )
    saved = db.execute(
        "select before_facts,after_facts from public.business_draft_revisions"
        " where draft_id=%s",
        (client["draft"],),
    ).fetchone()
    assert saved == (revision["before"], revision["after"])
    db.execute("delete from public.spaces where id=%s", (client["id"],))
    assert (
        db.execute(
            "select count(*) from public.business_draft_revisions" " where draft_id=%s",
            (client["draft"],),
        ).fetchone()[0]
        == 0
    )


def test_action_receipt_requires_matching_persisted_plan_and_actor(
    db: Connection,
    client: dict[str, str],
    users: dict[str, str],
) -> None:
    command = {"action": "business_read_context"}
    key = add_turn(db, client, None)
    with pytest.raises(errors.CheckViolation, match="plan_required"), db.transaction():
        add_receipt(db, client, key, command)
    db.execute(
        "update public.business_turns set model_state='completed',plan=%s,plan_actor=%s"
        " where turn_key=%s",
        (
            Jsonb({"schema_version": 1, "actions": [command]}),
            Jsonb(actor_provenance(client)),
            key,
        ),
    )
    with pytest.raises(errors.CheckViolation, match="plan_required"), db.transaction():
        add_receipt(db, {**client, "owner": users["other"]}, key, command)
    with pytest.raises(errors.CheckViolation, match="plan_required"), db.transaction():
        add_receipt(db, client, key, {"action": "business_explain_status"})
    add_receipt(db, client, key, command)
    with pytest.raises(errors.UniqueViolation), db.transaction():
        add_receipt(db, client, key, command)
    with pytest.raises(errors.CheckViolation, match="plan_immutable"), db.transaction():
        db.execute(
            "update public.business_turns set plan=%s where turn_key=%s",
            (Jsonb({"schema_version": 1, "actions": []}), key),
        )


def test_action_result_is_immutable_after_reconciliation(
    db: Connection,
    client: dict[str, str],
) -> None:
    command = {"action": "business_read_context"}
    key = add_turn(db, client, [command])
    add_receipt(db, client, key, command)
    for outcome in ("outcome_unknown", "applied"):
        db.execute(
            "update public.business_action_receipts set outcome=%s where turn_key=%s",
            (Jsonb({"outcome": outcome}), key),
        )
        with (
            pytest.raises(errors.CheckViolation, match="outcome_immutable"),
            db.transaction(),
        ):
            db.execute(
                "update public.business_action_receipts set outcome=null where turn_key=%s",
                (key,),
            )
    with (
        pytest.raises(errors.CheckViolation, match="outcome_immutable"),
        db.transaction(),
    ):
        db.execute(
            "update public.business_action_receipts set outcome=null where turn_key=%s",
            (key,),
        )
    with (
        pytest.raises(errors.CheckViolation, match="identity_immutable"),
        db.transaction(),
    ):
        db.execute(
            "update public.business_action_receipts set input_hash=%s where turn_key=%s",
            (fake.sha256(), key),
        )


def test_turn_plan_bound_matches_contract(db: Connection, client: dict[str, str]) -> None:
    action = {"action": "business_read_context"}
    add_turn(db, client, [action] * MAX_TURN_ACTIONS)
    with pytest.raises(errors.CheckViolation), db.transaction():
        add_turn(db, client, [action] * (MAX_TURN_ACTIONS + 1))


def test_grant_is_explicit_for_one_client_and_can_be_revoked(
    db: Connection,
    client: dict[str, str],
    users: dict[str, str],
) -> None:
    other_space = space(db, users["other"])
    grant_id = db.execute(
        "insert into public.business_client_grants"
        " (space_id,grantee_id,issuer_id,capabilities)"
        " values (%s,%s,%s,ARRAY['read','prepare']) returning id",
        (client["id"], users["other"], client["owner"]),
    ).fetchone()[0]
    assert (
        db.execute(
            "select count(*) from public.business_client_grants" " where space_id=%s",
            (other_space,),
        ).fetchone()[0]
        == 0
    )
    db.execute(
        "update public.business_client_grants set revoked_at=now() where id=%s",
        (grant_id,),
    )
    assert (
        db.execute(
            "select count(*) from public.business_client_grants"
            " where id=%s and revoked_at is null",
            (grant_id,),
        ).fetchone()[0]
        == 0
    )


def test_web_action_evidence_is_immutable_idempotent_and_web_only(
    db: Connection, client: dict[str, str]
) -> None:
    source_key = fake.sha256()
    text = json.dumps(
        {"version": 1, "facts": {"amount": {"state": "known", "value": "25"}}}
    )
    insert = (
        "insert into public.business_sources"
        " (space_id,kind,channel,source_key,text_content,received_at)"
        " values (%s,'web_action',%s,%s,%s,now()) returning id"
    )
    source_id = db.execute(insert, (client["id"], "web", source_key, text)).fetchone()[0]
    assert (
        db.execute(
            "select text_content from public.business_sources where id=%s", (source_id,)
        ).fetchone()[0]
        == text
    )
    with pytest.raises(errors.CheckViolation), db.transaction():
        db.execute(insert, (client["id"], "whatsapp", fake.sha256(), text))
    with pytest.raises(errors.UniqueViolation), db.transaction():
        db.execute(insert, (client["id"], "web", source_key, text))
    with (
        pytest.raises(errors.CheckViolation, match="business_evidence_immutable"),
        db.transaction(),
    ):
        db.execute(
            "update public.business_sources set text_content=%s where id=%s",
            (fake.sentence(), source_id),
        )
    db.execute(
        "insert into public.business_questions"
        " (space_id,draft_id,field,asked_of,channel,state,prompt,allowed_answers,answer_source_id)"
        " values (%s,%s,'amount','accountant','web','answered',%s,ARRAY['known'],%s)",
        (client["id"], client["draft"], fake.sentence(), source_id),
    )


def test_plan_actor_cannot_be_missing_foreign_or_substituted(
    db: Connection, client: dict[str, str], users: dict[str, str]
) -> None:
    key = add_turn(db, client, None)
    plan = Jsonb({"schema_version": 1, "actions": []})
    for actor in (None, Jsonb({**actor_provenance(client), "actor_id": users["other"]})):
        with pytest.raises(errors.CheckViolation), db.transaction():
            db.execute(
                "update public.business_turns set model_state='completed',plan=%s,plan_actor=%s"
                " where turn_key=%s",
                (plan, actor, key),
            )
    key = add_turn(db, client, [{"action": "business_read_context"}])
    replacement = {**actor_provenance(client), "grant_id": fake.uuid4()}
    with pytest.raises(errors.CheckViolation, match="plan_immutable"), db.transaction():
        db.execute(
            "update public.business_turns set plan_actor=%s where turn_key=%s",
            (Jsonb(replacement), key),
        )
    with pytest.raises(errors.CheckViolation, match="plan_required"), db.transaction():
        add_receipt(
            db,
            {**client, "grant": replacement["grant_id"]},
            key,
            {"action": "business_read_context"},
        )


def test_human_receipt_retains_immutable_actor_without_a_turn(
    db: Connection, client: dict[str, str], users: dict[str, str]
) -> None:
    command = {
        "action": "review_draft",
        "draft_id": client["draft"],
        "request": {"version": 1, "facts": {"amount": {"state": "unknown"}}},
    }
    key = fake.sha256()
    insert = (
        "insert into public.business_action_receipts"
        " (space_id,actor_id,actor,idempotency_key,input_hash,command)"
        " values (%s,%s,%s,%s,%s,%s)"
    )
    params = (
        client["id"],
        client["owner"],
        Jsonb(actor_provenance(client)),
        key,
        fake.sha256(),
        Jsonb(command),
    )
    for invalid in (
        None,
        Jsonb({**actor_provenance(client), "actor_id": users["other"]}),
    ):
        with (
            pytest.raises((errors.CheckViolation, errors.NotNullViolation)),
            db.transaction(),
        ):
            db.execute(insert, (*params[:2], invalid, *params[3:]))
    db.execute(insert, params)
    with (
        pytest.raises(errors.CheckViolation, match="identity_immutable"),
        db.transaction(),
    ):
        db.execute(
            "update public.business_action_receipts set actor=%s where idempotency_key=%s",
            (Jsonb({**actor_provenance(client), "grant_id": fake.uuid4()}), key),
        )
    assert db.execute(
        "select actor,turn_key from public.business_action_receipts"
        " where idempotency_key=%s",
        (key,),
    ).fetchone() == (actor_provenance(client), None)


def add_revision(
    db: Connection, client: dict[str, str], source_ids: list[str | None]
) -> None:
    db.execute(
        "insert into public.business_draft_revisions"
        " (space_id,draft_id,version,actor,after_facts,source_ids)"
        " values (%s,%s,1,%s,'{}',%s::uuid[])",
        (client["id"], client["draft"], Jsonb(actor_provenance(client)), source_ids),
    )


def test_revision_rejects_foreign_missing_or_null_sources(
    db: Connection, client: dict[str, str], users: dict[str, str]
) -> None:
    foreign_source = add_source(db, space(db, users["other"]))
    local_source = add_source(db, client["id"])
    db.execute("set local role service_role")
    for source_id in (foreign_source, fake.uuid4(), None):
        with (
            pytest.raises(errors.ForeignKeyViolation, match="revision_source_not_found"),
            db.transaction(),
        ):
            add_revision(db, client, [local_source, source_id])
    add_revision(db, client, [local_source])


def test_direct_source_erasure_preserves_history_but_parent_deletion_cascades(
    db: Connection, client: dict[str, str]
) -> None:
    source_id = add_source(db, client["id"])
    db.execute(
        "insert into public.business_draft_sources (space_id,draft_id,source_id)"
        " values (%s,%s,%s)",
        (client["id"], client["draft"], source_id),
    )
    add_revision(db, client, [source_id])
    db.execute("set local role service_role")
    with (
        pytest.raises(errors.CheckViolation, match="business_evidence_immutable"),
        db.transaction(),
    ):
        db.execute("delete from public.business_sources where id=%s", (source_id,))
    assert (
        db.execute(
            "select count(*) from public.business_sources where id=%s", (source_id,)
        ).fetchone()[0]
        == 1
    )
    assert (
        db.execute(
            "select count(*) from public.business_draft_sources where source_id=%s",
            (source_id,),
        ).fetchone()[0]
        == 1
    )
    assert db.execute(
        "select source_ids from public.business_draft_revisions where draft_id=%s",
        (client["draft"],),
    ).fetchone()[0] == [UUID(source_id)]
    db.execute("delete from public.spaces where id=%s", (client["id"],))
    assert (
        db.execute(
            "select count(*) from public.business_sources where id=%s", (source_id,)
        ).fetchone()[0]
        == 0
    )
    assert (
        db.execute(
            "select count(*) from public.business_draft_revisions where draft_id=%s",
            (client["draft"],),
        ).fetchone()[0]
        == 0
    )


def test_answered_attachment_allows_existing_account_deletion_order(
    db: Connection, client: dict[str, str]
) -> None:
    connection_id = connection(db, client["owner"], client["id"])
    source_id = str(
        db.execute(
            "insert into public.business_sources"
            " (space_id,kind,channel,source_key,connection_id,received_at)"
            " values (%s,'attachment','web',%s,%s,now()) returning id",
            (client["id"], fake.sha256(), connection_id),
        ).fetchone()[0]
    )
    db.execute(
        "insert into public.business_questions"
        " (space_id,draft_id,field,asked_of,channel,state,prompt,allowed_answers,answer_source_id)"
        " values (%s,%s,'amount','accountant','web','answered',%s,ARRAY['known'],%s)",
        (client["id"], client["draft"], fake.sentence(), source_id),
    )
    add_revision(db, client, [source_id])
    db.execute("set local role service_role")
    db.execute(
        "delete from public.financial_source_connections where user_id = %s",
        (client["owner"],),
    )
    assert (
        db.execute(
            "select count(*) from public.business_questions where draft_id=%s",
            (client["draft"],),
        ).fetchone()[0]
        == 0
    )
    assert (
        db.execute(
            "select count(*) from public.business_sources where id=%s", (source_id,)
        ).fetchone()[0]
        == 0
    )
    db.execute("reset role")
    db.execute("select set_config('argus.locked_history_writer', 'deletion', true)")
    db.execute(
        "select argus_private.deletion_finish(%s, %s)", (client["owner"], fake.sha256())
    )
    db.execute("delete from auth.users where id=%s", (client["owner"],))
    assert (
        db.execute(
            "select count(*) from public.spaces where id=%s", (client["id"],)
        ).fetchone()[0]
        == 0
    )
    assert (
        db.execute(
            "select count(*) from public.business_draft_revisions where draft_id=%s",
            (client["draft"],),
        ).fetchone()[0]
        == 0
    )


@pytest.mark.parametrize(
    "command", [{"action": "business_read_context"}, {}, {"action": "unknown"}]
)
def test_no_turn_receipt_is_reserved_for_human_commands(
    db: Connection, client: dict[str, str], command: dict
) -> None:
    db.execute("set local role service_role")
    with pytest.raises(errors.CheckViolation), db.transaction():
        db.execute(
            "insert into public.business_action_receipts"
            " (space_id,actor_id,actor,idempotency_key,input_hash,command)"
            " values (%s,%s,%s,%s,%s,%s)",
            (
                client["id"],
                client["owner"],
                Jsonb(actor_provenance(client)),
                fake.sha256(),
                fake.sha256(),
                Jsonb(command),
            ),
        )
