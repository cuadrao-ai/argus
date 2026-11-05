"""Real-Postgres guest cleanup ordering and permanent-account safety proofs."""

from __future__ import annotations

import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from threading import Barrier

import pytest

DSN = os.getenv("ARGUS_DISPOSABLE_DATABASE_URL", "").strip()
pytestmark = pytest.mark.skipif(
    not DSN,
    reason="ARGUS_DISPOSABLE_DATABASE_URL is not configured",
)
psycopg = pytest.importorskip("psycopg")


def _connect(*, autocommit: bool = True):
    return psycopg.connect(DSN, autocommit=autocommit)


def _seed_expired_guest(connection) -> dict[str, str]:
    user_id = str(uuid.uuid4())
    conversation_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(days=8)
    with connection.cursor() as cursor:
        cursor.execute(
            "insert into auth.users (id, email, is_anonymous)" " values (%s, null, true)",
            (user_id,),
        )
        cursor.execute(
            "insert into public.profiles (id, email) values (%s, null)",
            (user_id,),
        )
        cursor.execute(
            "insert into public.conversations (id, user_id, title)"
            " values (%s, %s, 'expired guest')",
            (conversation_id, user_id),
        )
        cursor.execute(
            "insert into public.messages"
            " (conversation_id, user_id, role, content)"
            " values (%s, %s, 'user', 'private content')",
            (conversation_id, user_id),
        )
        cursor.execute(
            "insert into public.guest_workspaces"
            " (user_id, conversation_id, created_at, expires_at)"
            " values (%s, %s, %s, %s)",
            (
                user_id,
                conversation_id,
                created_at,
                created_at + timedelta(days=7),
            ),
        )
    return {"user_id": user_id, "conversation_id": conversation_id}


def _seed_complete_expired_guest_graph(connection) -> dict[str, str]:
    graph = _seed_expired_guest(connection)
    graph.update(
        {
            name: str(uuid.uuid4())
            for name in (
                "assistant_message_id",
                "strategy_id",
                "run_id",
                "job_id",
                "idea_id",
                "version_id",
                "evidence_id",
                "decision_id",
                "context_packet_id",
                "run_context_packet_id",
                "route_receipt_id",
                "cost_ledger_id",
            )
        }
    )
    with connection.cursor() as cursor:
        cursor.execute(
            "select id::text from public.messages"
            " where conversation_id = %s and user_id = %s"
            " order by created_at limit 1",
            (graph["conversation_id"], graph["user_id"]),
        )
        graph["user_message_id"] = cursor.fetchone()[0]
        cursor.execute(
            "select created_at, expires_at from public.guest_workspaces"
            " where user_id = %s",
            (graph["user_id"],),
        )
        created_at, expires_at = cursor.fetchone()
        cursor.execute(
            "insert into public.messages"
            " (id,conversation_id,user_id,role,content,metadata)"
            " values (%s,%s,%s,'assistant','completed guest result','{}'::jsonb)",
            (
                graph["assistant_message_id"],
                graph["conversation_id"],
                graph["user_id"],
            ),
        )
        cursor.execute(
            "insert into public.strategies"
            " (id,user_id,conversation_id,name,template,asset_class,symbols,"
            "  benchmark_symbol)"
            " values (%s,%s,%s,'Expired AAPL test','buy_and_hold','equity',"
            " array['AAPL'],'SPY')",
            (
                graph["strategy_id"],
                graph["user_id"],
                graph["conversation_id"],
            ),
        )
        cursor.execute(
            "insert into public.backtest_runs"
            " (id,user_id,conversation_id,strategy_id,status,asset_class,symbols,"
            "  benchmark_symbol,config_snapshot,conversation_result_card)"
            " values (%s,%s,%s,%s,'completed','equity',array['AAPL'],'SPY',"
            " '{}'::jsonb,'{}'::jsonb)",
            (
                graph["run_id"],
                graph["user_id"],
                graph["conversation_id"],
                graph["strategy_id"],
            ),
        )
        cursor.execute(
            "insert into public.backtest_jobs"
            " (id,user_id,conversation_id,request_message_id,"
            "  confirmation_message_id,idempotency_key,payload_hash,"
            "  launch_payload,status,result_run_id)"
            " values (%s,%s,%s,%s,%s,'cleanup-run','cleanup-payload',"
            " '{}'::jsonb,'succeeded',%s)",
            (
                graph["job_id"],
                graph["user_id"],
                graph["conversation_id"],
                graph["user_message_id"],
                graph["assistant_message_id"],
                graph["run_id"],
            ),
        )
        cursor.execute(
            "insert into public.ideas"
            " (id,user_id,source_conversation_id,title,lifecycle)"
            " values (%s,%s,%s,'Expired AAPL idea','decided')",
            (graph["idea_id"], graph["user_id"], graph["conversation_id"]),
        )
        cursor.execute(
            "insert into public.idea_versions"
            " (id,user_id,idea_id,source_conversation_id,source_run_id,"
            "  canonical_spec,strategy_snapshot,title,lifecycle)"
            " values (%s,%s,%s,%s,%s,'{}'::jsonb,'{}'::jsonb,"
            " 'Expired AAPL idea','decided')",
            (
                graph["version_id"],
                graph["user_id"],
                graph["idea_id"],
                graph["conversation_id"],
                graph["run_id"],
            ),
        )
        cursor.execute(
            "update public.ideas set active_version_id = %s where id = %s",
            (graph["version_id"], graph["idea_id"]),
        )
        cursor.execute(
            "insert into public.evidence_artifacts"
            " (id,user_id,idea_id,idea_version_id,source_conversation_id,"
            "  source_run_id,lifecycle,title,digest,payload)"
            " values (%s,%s,%s,%s,%s,%s,'decided','Expired AAPL result',"
            " 'cleanup-proof','{}'::jsonb)",
            (
                graph["evidence_id"],
                graph["user_id"],
                graph["idea_id"],
                graph["version_id"],
                graph["conversation_id"],
                graph["run_id"],
            ),
        )
        cursor.execute(
            "insert into public.decision_notes"
            " (id,user_id,idea_id,idea_version_id,evidence_artifact_id,"
            "  source_conversation_id,decision_state,note)"
            " values (%s,%s,%s,%s,%s,%s,'watching','cleanup proof')",
            (
                graph["decision_id"],
                graph["user_id"],
                graph["idea_id"],
                graph["version_id"],
                graph["evidence_id"],
                graph["conversation_id"],
            ),
        )
        cursor.execute(
            "insert into public.context_packets"
            " (id,user_id,provider,packet_type,retrieved_at)"
            " values (%s,%s,'alpaca','news',%s)",
            (graph["context_packet_id"], graph["user_id"], created_at),
        )
        cursor.execute(
            "insert into public.run_context_packets"
            " (id,user_id,run_id,context_packet_id)"
            " values (%s,%s,%s,%s)",
            (
                graph["run_context_packet_id"],
                graph["user_id"],
                graph["run_id"],
                graph["context_packet_id"],
            ),
        )
        cursor.execute(
            "insert into public.feedback (user_id,type,message)"
            " values (%s,'general','private cleanup proof')",
            (graph["user_id"],),
        )
        cursor.execute(
            "insert into public.usage_counters"
            " (user_id,resource,period,period_start,period_end,"
            "  used_count,limit_count)"
            " values (%s,'chat_messages','guest_session',%s,%s,4,10),"
            "        (%s,'backtest_runs','guest_session',%s,%s,1,1)",
            (
                graph["user_id"],
                created_at,
                expires_at,
                graph["user_id"],
                created_at,
                expires_at,
            ),
        )
        cursor.execute(
            "insert into public.checkpoints"
            " (thread_id,checkpoint_ns,checkpoint_id,checkpoint)"
            " values (%s,'','cleanup-checkpoint','{}'::jsonb)",
            (graph["conversation_id"],),
        )
        cursor.execute(
            "insert into public.checkpoint_blobs"
            " (thread_id,checkpoint_ns,channel,version,type,blob)"
            " values (%s,'','messages','1','msgpack',null)",
            (graph["conversation_id"],),
        )
        cursor.execute(
            "insert into public.checkpoint_writes"
            " (thread_id,checkpoint_ns,checkpoint_id,task_id,idx,"
            "  channel,type,blob)"
            " values (%s,'','cleanup-checkpoint','cleanup-task',0,"
            "  'messages','msgpack',%s)",
            (graph["conversation_id"], b"cleanup-checkpoint"),
        )
        cursor.execute(
            "insert into public.route_receipts"
            " (id,user_id,conversation_id,run_id,message_id,task,tier,mode,"
            "  latency_ms,outcome,context_packet_ids)"
            " values (%s,%s,%s,%s,%s,'interpretation','structured',"
            " 'json_schema',12,'succeeded',array[%s])",
            (
                graph["route_receipt_id"],
                graph["user_id"],
                graph["conversation_id"],
                graph["run_id"],
                graph["assistant_message_id"],
                graph["context_packet_id"],
            ),
        )
        cursor.execute(
            "insert into public.cost_ledger_entries"
            " (id,source,service,provider,feature_area,user_id,conversation_id,"
            "  message_id,backtest_run_id,backtest_job_id,route_receipt_id,"
            "  correlation_id,billable_unit,status)"
            " values (%s,'api_turn','openrouter','openrouter','guest_cleanup',"
            " %s,%s,%s,%s,%s,%s,'cleanup-correlation','request','succeeded')",
            (
                graph["cost_ledger_id"],
                graph["user_id"],
                graph["conversation_id"],
                graph["assistant_message_id"],
                graph["run_id"],
                graph["job_id"],
                graph["route_receipt_id"],
            ),
        )
    return graph


def _claim_cleanup(connection, *, dry_run: bool) -> list[tuple[str, str | None]]:
    with connection.cursor() as cursor:
        cursor.execute(
            "select user_id::text, conversation_id::text"
            " from public.claim_expired_guest_workspaces(%s, %s)",
            (25, dry_run),
        )
        return list(cursor.fetchall())


def _complete_graph_state(connection, graph: dict[str, str]) -> dict[str, object]:
    counts: dict[str, int] = {}
    with connection.cursor() as cursor:
        for table in (
            "conversations",
            "messages",
            "strategies",
            "backtest_jobs",
            "backtest_runs",
            "ideas",
            "idea_versions",
            "evidence_artifacts",
            "decision_notes",
            "context_packets",
            "run_context_packets",
            "feedback",
            "usage_counters",
            "guest_workspaces",
        ):
            cursor.execute(
                f"select count(*) from public.{table} where user_id = %s",
                (graph["user_id"],),
            )
            counts[table] = cursor.fetchone()[0]
        for table in ("checkpoints", "checkpoint_blobs", "checkpoint_writes"):
            cursor.execute(
                f"select count(*) from public.{table} where thread_id = %s",
                (graph["conversation_id"],),
            )
            counts[table] = cursor.fetchone()[0]
        cursor.execute(
            "select count(*) from auth.users where id = %s",
            (graph["user_id"],),
        )
        auth_count = cursor.fetchone()[0]
        cursor.execute(
            "select status,conversation_id::text from public.guest_workspaces"
            " where user_id = %s",
            (graph["user_id"],),
        )
        workspace = cursor.fetchone()
        cursor.execute(
            "select user_id::text,conversation_id::text,run_id::text,message_id::text"
            " from public.route_receipts where id = %s",
            (graph["route_receipt_id"],),
        )
        route_receipt = cursor.fetchone()
        cursor.execute(
            "select user_id::text,conversation_id::text,message_id::text,"
            " backtest_run_id::text,backtest_job_id::text,route_receipt_id::text"
            " from public.cost_ledger_entries where id = %s",
            (graph["cost_ledger_id"],),
        )
        cost_ledger = cursor.fetchone()
    return {
        "counts": counts,
        "auth_count": auth_count,
        "workspace": workspace,
        "route_receipt": route_receipt,
        "cost_ledger": cost_ledger,
    }


def test_cleanup_removes_complete_graph_before_deleting_anonymous_auth() -> None:
    with _connect(autocommit=False) as connection:
        graph = _seed_complete_expired_guest_graph(connection)
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                create function pg_temp.assert_guest_product_graph_removed()
                returns trigger
                language plpgsql
                as $$
                begin
                  if old.id = '{graph["user_id"]}'::uuid then
                    if not coalesce(old.is_anonymous, false) then
                      raise exception 'cleanup attempted to delete permanent auth';
                    end if;
                    if exists (
                      select 1 from public.conversations where user_id = old.id
                      union all select 1 from public.messages where user_id = old.id
                      union all select 1 from public.strategies where user_id = old.id
                      union all select 1 from public.backtest_jobs where user_id = old.id
                      union all select 1 from public.backtest_runs where user_id = old.id
                      union all select 1 from public.ideas where user_id = old.id
                      union all select 1 from public.idea_versions where user_id = old.id
                      union all select 1 from public.evidence_artifacts where user_id = old.id
                      union all select 1 from public.decision_notes where user_id = old.id
                      union all select 1 from public.context_packets where user_id = old.id
                      union all select 1 from public.run_context_packets where user_id = old.id
                      union all select 1 from public.feedback where user_id = old.id
                      union all select 1 from public.checkpoints
                        where thread_id = '{graph["conversation_id"]}'
                      union all select 1 from public.checkpoint_blobs
                        where thread_id = '{graph["conversation_id"]}'
                      union all select 1 from public.checkpoint_writes
                        where thread_id = '{graph["conversation_id"]}'
                    ) then
                      raise exception 'anonymous auth deleted before product graph';
                    end if;
                  end if;
                  return old;
                end;
                $$;

                create trigger assert_guest_product_graph_removed
                before delete on auth.users
                for each row execute function pg_temp.assert_guest_product_graph_removed();
                """
            )

        rows = _claim_cleanup(connection, dry_run=False)
        selected = next(row for row in rows if row[0] == graph["user_id"])
        assert selected == (graph["user_id"], graph["conversation_id"])

        with connection.cursor() as cursor:
            for table in (
                "conversations",
                "messages",
                "strategies",
                "backtest_jobs",
                "backtest_runs",
                "ideas",
                "idea_versions",
                "evidence_artifacts",
                "decision_notes",
                "context_packets",
                "run_context_packets",
                "feedback",
                "usage_counters",
                "guest_workspaces",
            ):
                cursor.execute(
                    f"select count(*) from public.{table} where user_id = %s",
                    (graph["user_id"],),
                )
                assert cursor.fetchone()[0] == 0
            for table in ("checkpoints", "checkpoint_blobs", "checkpoint_writes"):
                cursor.execute(
                    f"select count(*) from public.{table} where thread_id = %s",
                    (graph["conversation_id"],),
                )
                assert cursor.fetchone()[0] == 0
            cursor.execute(
                "select user_id,conversation_id,run_id,message_id"
                " from public.route_receipts where id = %s",
                (graph["route_receipt_id"],),
            )
            assert cursor.fetchone() == (None, None, None, None)
            cursor.execute(
                "select user_id,conversation_id,message_id,backtest_run_id,"
                " backtest_job_id,route_receipt_id::text"
                " from public.cost_ledger_entries where id = %s",
                (graph["cost_ledger_id"],),
            )
            assert cursor.fetchone() == (
                None,
                None,
                None,
                None,
                None,
                graph["route_receipt_id"],
            )
            cursor.execute(
                "select count(*) from auth.users where id = %s",
                (graph["user_id"],),
            )
            assert cursor.fetchone()[0] == 0
        connection.rollback()


def test_cleanup_rolls_back_complete_graph_when_a_late_delete_fails() -> None:
    with _connect(autocommit=False) as connection:
        graph = _seed_complete_expired_guest_graph(connection)
        before = _complete_graph_state(connection, graph)
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                create function pg_temp.reject_guest_strategy_delete()
                returns trigger
                language plpgsql
                as $$
                begin
                  raise exception 'injected guest cleanup failure';
                end;
                $$;
                create trigger reject_guest_strategy_delete
                before delete on public.strategies
                for each row
                when (old.user_id = '{graph["user_id"]}'::uuid)
                execute function pg_temp.reject_guest_strategy_delete();
                savepoint cleanup_attempt;
                """
            )

        with pytest.raises(
            psycopg.errors.RaiseException,
            match="injected guest cleanup failure",
        ):
            _claim_cleanup(connection, dry_run=False)
        with connection.cursor() as cursor:
            cursor.execute("rollback to savepoint cleanup_attempt")
        assert _complete_graph_state(connection, graph) == before
        connection.rollback()


def test_cleanup_foreign_owner_injection_fails_closed_without_mutation() -> None:
    with _connect(autocommit=False) as connection:
        graph = _seed_complete_expired_guest_graph(connection)
        foreign_user_id = str(uuid.uuid4())
        foreign_message_id = str(uuid.uuid4())
        foreign_email = f"foreign-{foreign_user_id[:8]}@example.com"
        with connection.cursor() as cursor:
            cursor.execute(
                "insert into auth.users (id,email,is_anonymous)" " values (%s,%s,false)",
                (foreign_user_id, foreign_email),
            )
            cursor.execute(
                "insert into public.profiles (id,email) values (%s,%s)",
                (foreign_user_id, foreign_email),
            )
            cursor.execute(
                "insert into public.messages"
                " (id,conversation_id,user_id,role,content)"
                " values (%s,%s,%s,'assistant','foreign owner sentinel')",
                (
                    foreign_message_id,
                    graph["conversation_id"],
                    foreign_user_id,
                ),
            )
            cursor.execute("savepoint cleanup_attempt")
        before = _complete_graph_state(connection, graph)

        rows = _claim_cleanup(connection, dry_run=False)
        assert (graph["user_id"], graph["conversation_id"]) in rows
        with connection.cursor() as cursor:
            cursor.execute(
                "select user_id::text,conversation_id::text,content"
                " from public.messages where id = %s",
                (foreign_message_id,),
            )
            assert cursor.fetchone() == (
                foreign_user_id,
                graph["conversation_id"],
                "foreign owner sentinel",
            )
        assert _complete_graph_state(connection, graph) == before
        connection.rollback()


def test_poisoned_cleanup_candidate_does_not_wedge_healthy_expired_guest() -> None:
    with _connect(autocommit=False) as connection:
        poisoned = _seed_expired_guest(connection)
        healthy = _seed_expired_guest(connection)
        foreign_user_id = str(uuid.uuid4())
        foreign_message_id = str(uuid.uuid4())
        foreign_email = f"poison-{foreign_user_id[:8]}@example.com"
        with connection.cursor() as cursor:
            cursor.execute(
                "insert into auth.users (id,email,is_anonymous)" " values (%s,%s,false)",
                (foreign_user_id, foreign_email),
            )
            cursor.execute(
                "insert into public.profiles (id,email) values (%s,%s)",
                (foreign_user_id, foreign_email),
            )
            cursor.execute(
                "insert into public.messages"
                " (id,conversation_id,user_id,role,content)"
                " values (%s,%s,%s,'assistant','foreign poison sentinel')",
                (
                    foreign_message_id,
                    poisoned["conversation_id"],
                    foreign_user_id,
                ),
            )
            cursor.execute(
                "update public.guest_workspaces"
                " set updated_at=now()-interval '30 minutes'"
                " where user_id=%s",
                (poisoned["user_id"],),
            )
            cursor.execute(
                "update public.guest_workspaces"
                " set updated_at=now()-interval '20 minutes'"
                " where user_id=%s",
                (healthy["user_id"],),
            )
            cursor.execute(
                "select user_id::text,auth_deleted,cleanup_reason"
                " from public.claim_expired_guest_workspaces(2,true)",
            )
            dry_rows = [
                row
                for row in cursor.fetchall()
                if row[0] in {poisoned["user_id"], healthy["user_id"]}
            ]

        assert dry_rows == [
            (poisoned["user_id"], False, "expired_workspace"),
            (healthy["user_id"], False, "expired_workspace"),
        ]

        with connection.cursor() as cursor:
            cursor.execute(
                "select user_id::text,auth_deleted,cleanup_reason"
                " from public.claim_expired_guest_workspaces(2,false)",
            )
            real_rows = [
                row
                for row in cursor.fetchall()
                if row[0] in {poisoned["user_id"], healthy["user_id"]}
            ]

        assert real_rows == [
            (poisoned["user_id"], False, "unsafe_product_graph"),
            (healthy["user_id"], True, "expired_workspace"),
        ]
        with connection.cursor() as cursor:
            cursor.execute(
                "select count(*) from auth.users where id=%s",
                (poisoned["user_id"],),
            )
            assert cursor.fetchone()[0] == 1
            cursor.execute(
                "select count(*) from auth.users where id=%s",
                (healthy["user_id"],),
            )
            assert cursor.fetchone()[0] == 0
            cursor.execute(
                "select user_id::text,auth_deleted,cleanup_reason"
                " from public.claim_expired_guest_workspaces(1,false)",
            )
            repeat_rows = [
                row for row in cursor.fetchall() if row[0] == poisoned["user_id"]
            ]
            assert repeat_rows == [(poisoned["user_id"], False, "unsafe_product_graph")]

        healthy_first = _seed_expired_guest(connection)
        poisoned_later = _seed_expired_guest(connection)
        second_foreign_user_id = str(uuid.uuid4())
        second_foreign_message_id = str(uuid.uuid4())
        second_foreign_email = f"poison-later-{second_foreign_user_id[:8]}@example.com"
        with connection.cursor() as cursor:
            cursor.execute(
                "insert into auth.users (id,email,is_anonymous)" " values (%s,%s,false)",
                (second_foreign_user_id, second_foreign_email),
            )
            cursor.execute(
                "insert into public.profiles (id,email) values (%s,%s)",
                (second_foreign_user_id, second_foreign_email),
            )
            cursor.execute(
                "insert into public.messages"
                " (id,conversation_id,user_id,role,content)"
                " values (%s,%s,%s,'assistant','later poison sentinel')",
                (
                    second_foreign_message_id,
                    poisoned_later["conversation_id"],
                    second_foreign_user_id,
                ),
            )
            cursor.execute(
                "update public.guest_workspaces"
                " set updated_at=now()-interval '40 minutes'"
                " where user_id=%s",
                (healthy_first["user_id"],),
            )
            cursor.execute(
                "update public.guest_workspaces"
                " set updated_at=now()-interval '30 minutes'"
                " where user_id=%s",
                (poisoned_later["user_id"],),
            )
            cursor.execute(
                "select user_id::text,auth_deleted,cleanup_reason"
                " from public.claim_expired_guest_workspaces(2,false)",
            )
            ordered_rows = cursor.fetchall()

        assert ordered_rows == [
            (healthy_first["user_id"], True, "expired_workspace"),
            (poisoned_later["user_id"], False, "unsafe_product_graph"),
        ]
        with connection.cursor() as cursor:
            cursor.execute(
                "select count(*) from auth.users where id=%s",
                (healthy_first["user_id"],),
            )
            assert cursor.fetchone()[0] == 0
            cursor.execute(
                "select count(*) from auth.users where id=%s",
                (poisoned_later["user_id"],),
            )
            assert cursor.fetchone()[0] == 1
        connection.rollback()


def test_cleanup_foreign_relational_injection_fails_closed() -> None:
    with _connect(autocommit=False) as connection:
        graph = _seed_complete_expired_guest_graph(connection)
        foreign_user_id = str(uuid.uuid4())
        foreign_run_id = str(uuid.uuid4())
        foreign_email = f"foreign-run-{foreign_user_id[:8]}@example.com"
        with connection.cursor() as cursor:
            cursor.execute(
                "insert into auth.users (id,email,is_anonymous)" " values (%s,%s,false)",
                (foreign_user_id, foreign_email),
            )
            cursor.execute(
                "insert into public.profiles (id,email) values (%s,%s)",
                (foreign_user_id, foreign_email),
            )
            cursor.execute(
                "insert into public.backtest_runs"
                " (id,user_id,strategy_id,status,asset_class,symbols,"
                "  benchmark_symbol,config_snapshot)"
                " values (%s,%s,%s,'completed','equity',array['MSFT'],'SPY',"
                " '{}'::jsonb)",
                (foreign_run_id, foreign_user_id, graph["strategy_id"]),
            )
            cursor.execute("savepoint cleanup_attempt")

        rows = _claim_cleanup(connection, dry_run=False)
        assert (graph["user_id"], graph["conversation_id"]) in rows
        with connection.cursor() as cursor:
            cursor.execute(
                "select user_id::text,strategy_id::text"
                " from public.backtest_runs where id = %s",
                (foreign_run_id,),
            )
            assert cursor.fetchone() == (foreign_user_id, graph["strategy_id"])
            cursor.execute(
                "select count(*) from auth.users where id = %s",
                (graph["user_id"],),
            )
            assert cursor.fetchone()[0] == 1
        connection.rollback()


def test_cleanup_null_conversation_with_owned_graph_fails_closed() -> None:
    with _connect(autocommit=False) as connection:
        graph = _seed_complete_expired_guest_graph(connection)
        foreign_user_id = str(uuid.uuid4())
        foreign_run_id = str(uuid.uuid4())
        foreign_email = f"foreign-null-workspace-{foreign_user_id[:8]}@example.com"
        with connection.cursor() as cursor:
            cursor.execute(
                "insert into auth.users (id,email,is_anonymous)" " values (%s,%s,false)",
                (foreign_user_id, foreign_email),
            )
            cursor.execute(
                "insert into public.profiles (id,email) values (%s,%s)",
                (foreign_user_id, foreign_email),
            )
            cursor.execute(
                "insert into public.backtest_runs"
                " (id,user_id,strategy_id,status,asset_class,symbols,"
                "  benchmark_symbol,config_snapshot)"
                " values (%s,%s,%s,'completed','equity',array['MSFT'],'SPY',"
                " '{}'::jsonb)",
                (foreign_run_id, foreign_user_id, graph["strategy_id"]),
            )
            cursor.execute(
                "update public.guest_workspaces set conversation_id=null"
                " where user_id=%s",
                (graph["user_id"],),
            )
            cursor.execute("savepoint cleanup_attempt")
        before = _complete_graph_state(connection, graph)

        rows = _claim_cleanup(connection, dry_run=False)
        assert (graph["user_id"], None) in rows
        with connection.cursor() as cursor:
            cursor.execute(
                "select user_id::text,strategy_id::text"
                " from public.backtest_runs where id=%s",
                (foreign_run_id,),
            )
            assert cursor.fetchone() == (foreign_user_id, graph["strategy_id"])
            cursor.execute(
                "select conversation_id from public.guest_workspaces where user_id=%s",
                (graph["user_id"],),
            )
            assert cursor.fetchone()[0] is None
        assert _complete_graph_state(connection, graph) == before
        connection.rollback()


def test_cleanup_cross_owner_profile_references_fail_closed() -> None:
    with _connect(autocommit=False) as connection:
        candidate = _seed_expired_guest(connection)
        other_user_id = str(uuid.uuid4())
        other_conversation_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).replace(microsecond=0)
        with connection.cursor() as cursor:
            cursor.execute(
                "insert into auth.users (id,email,is_anonymous)" " values (%s,null,true)",
                (other_user_id,),
            )
            cursor.execute(
                "insert into public.profiles (id,email) values (%s,null)",
                (other_user_id,),
            )
            cursor.execute(
                "insert into public.guest_workspaces"
                " (user_id,created_at,expires_at)"
                " values (%s,%s,%s)",
                (other_user_id, now, now + timedelta(days=7)),
            )
            cursor.execute(
                "insert into public.conversations (id,user_id,title)"
                " values (%s,%s,'foreign profile reference')",
                (other_conversation_id, other_user_id),
            )
            cursor.execute(
                "update public.guest_workspaces set claimed_by=%s" " where user_id=%s",
                (candidate["user_id"], other_user_id),
            )
            cursor.execute(
                "insert into public.guest_workspace_handoffs"
                " (secret_hash,source_user_id,destination_user_id,"
                "  destination_email_hash,source_conversation_id)"
                " values (%s,%s,%s,%s,%s)",
                (
                    "a" * 64,
                    other_user_id,
                    candidate["user_id"],
                    "b" * 64,
                    other_conversation_id,
                ),
            )
            cursor.execute("savepoint cleanup_attempt")

        rows = _claim_cleanup(connection, dry_run=False)
        assert (candidate["user_id"], candidate["conversation_id"]) in rows
        with connection.cursor() as cursor:
            cursor.execute(
                "select claimed_by::text from public.guest_workspaces"
                " where user_id=%s",
                (other_user_id,),
            )
            assert cursor.fetchone()[0] == candidate["user_id"]
            cursor.execute(
                "select destination_user_id::text"
                " from public.guest_workspace_handoffs"
                " where source_user_id=%s",
                (other_user_id,),
            )
            assert cursor.fetchone()[0] == candidate["user_id"]
            cursor.execute(
                "select count(*) from auth.users where id=%s",
                (candidate["user_id"],),
            )
            assert cursor.fetchone()[0] == 1
        connection.rollback()


def test_replacing_empty_conversation_preserves_identity_expiry_and_counters() -> None:
    with _connect() as connection:
        user_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).replace(microsecond=0)
        with connection.cursor() as cursor:
            cursor.execute(
                "insert into auth.users (id, email, is_anonymous)"
                " values (%s, null, true)",
                (user_id,),
            )
            cursor.execute(
                "insert into public.profiles (id, email) values (%s, null)",
                (user_id,),
            )
            cursor.execute(
                "insert into public.guest_workspaces"
                " (user_id, created_at, expires_at) values (%s, %s, %s)",
                (user_id, created_at, created_at + timedelta(days=7)),
            )
            cursor.execute(
                "insert into public.conversations (user_id, title)"
                " values (%s, 'first empty chat') returning id::text",
                (user_id,),
            )
            original_conversation_id = cursor.fetchone()[0]
            cursor.execute(
                "insert into public.usage_counters"
                " (user_id, resource, period, period_start, period_end,"
                "  used_count, limit_count)"
                " values (%s, 'chat_messages', 'guest_session', %s, %s, 3, 10)",
                (user_id, created_at, created_at + timedelta(days=7)),
            )
            cursor.execute(
                "select id::text from public.replace_empty_guest_conversation("
                "%s, 'replacement chat', 'system_default', 'en')",
                (user_id,),
            )
            replacement_conversation_id = cursor.fetchone()[0]
            cursor.execute(
                "select user_id::text, conversation_id::text, created_at, expires_at"
                " from public.guest_workspaces where user_id = %s",
                (user_id,),
            )
            workspace = cursor.fetchone()
            cursor.execute(
                "select used_count from public.usage_counters"
                " where user_id = %s and resource = 'chat_messages'"
                " and period = 'guest_session'",
                (user_id,),
            )
            used_count = cursor.fetchone()[0]
            cursor.execute(
                "select count(*) from public.conversations where user_id = %s",
                (user_id,),
            )
            conversation_count = cursor.fetchone()[0]

        assert replacement_conversation_id != original_conversation_id
        assert workspace == (
            user_id,
            replacement_conversation_id,
            created_at,
            created_at + timedelta(days=7),
        )
        assert used_count == 3
        assert conversation_count == 1
        with connection.cursor() as cursor:
            cursor.execute("delete from auth.users where id = %s", (user_id,))


def test_start_over_replaces_complete_graph_but_preserves_guest_policy() -> None:
    with _connect() as connection:
        user_id = str(uuid.uuid4())
        conversation_id = str(uuid.uuid4())
        run_id = str(uuid.uuid4())
        idea_id = str(uuid.uuid4())
        version_id = str(uuid.uuid4())
        evidence_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).replace(microsecond=0)
        expires_at = created_at + timedelta(days=7)
        with connection.cursor() as cursor:
            cursor.execute(
                "insert into auth.users (id, email, is_anonymous)"
                " values (%s, null, true)",
                (user_id,),
            )
            cursor.execute(
                "insert into public.profiles (id, email) values (%s, null)",
                (user_id,),
            )
            cursor.execute(
                "insert into public.guest_workspaces"
                " (user_id, created_at, expires_at) values (%s, %s, %s)",
                (user_id, created_at, expires_at),
            )
            cursor.execute(
                "insert into public.conversations (id,user_id,title)"
                " values (%s,%s,'temporary result')",
                (conversation_id, user_id),
            )
            cursor.execute(
                "insert into public.messages (conversation_id,user_id,role,content)"
                " values (%s,%s,'user','test BTC')",
                (conversation_id, user_id),
            )
            cursor.execute(
                "insert into public.backtest_runs"
                " (id,user_id,conversation_id,status,asset_class,symbols,"
                "  benchmark_symbol,config_snapshot,conversation_result_card)"
                " values (%s,%s,%s,'completed','crypto',array['BTC'],'BTC',"
                " '{}'::jsonb,'{}'::jsonb)",
                (run_id, user_id, conversation_id),
            )
            cursor.execute(
                "insert into public.ideas"
                " (id,user_id,source_conversation_id,title)"
                " values (%s,%s,%s,'BTC idea')",
                (idea_id, user_id, conversation_id),
            )
            cursor.execute(
                "insert into public.idea_versions"
                " (id,user_id,idea_id,source_conversation_id,source_run_id,"
                "  title,canonical_spec,strategy_snapshot)"
                " values (%s,%s,%s,%s,%s,'BTC idea','{}'::jsonb,'{}'::jsonb)",
                (version_id, user_id, idea_id, conversation_id, run_id),
            )
            cursor.execute(
                "update public.ideas set active_version_id=%s where id=%s",
                (version_id, idea_id),
            )
            cursor.execute(
                "insert into public.evidence_artifacts"
                " (id,user_id,idea_id,idea_version_id,source_conversation_id,"
                "  source_run_id,title)"
                " values (%s,%s,%s,%s,%s,%s,'BTC result')",
                (
                    evidence_id,
                    user_id,
                    idea_id,
                    version_id,
                    conversation_id,
                    run_id,
                ),
            )
            cursor.execute(
                "insert into public.decision_notes"
                " (user_id,idea_id,idea_version_id,evidence_artifact_id,"
                "  source_conversation_id,decision_state)"
                " values (%s,%s,%s,%s,%s,'watching')",
                (user_id, idea_id, version_id, evidence_id, conversation_id),
            )
            cursor.execute(
                "insert into public.usage_counters"
                " (user_id,resource,period,period_start,period_end,"
                "  used_count,limit_count)"
                " values (%s,'chat_messages','guest_session',%s,%s,4,10)",
                (user_id, created_at, expires_at),
            )
            cursor.execute(
                "insert into public.checkpoints"
                " (thread_id,checkpoint_ns,checkpoint_id,checkpoint)"
                " values (%s,'','checkpoint-start-over','{}'::jsonb)",
                (conversation_id,),
            )

            cursor.execute(
                "select id::text from public.replace_guest_conversation("
                "%s,'New idea','system_default','en')",
                (user_id,),
            )
            replacement_id = cursor.fetchone()[0]
            cursor.execute(
                "select conversation_id::text,created_at,expires_at"
                " from public.guest_workspaces where user_id=%s",
                (user_id,),
            )
            workspace = cursor.fetchone()
            cursor.execute(
                "select used_count from public.usage_counters"
                " where user_id=%s and resource='chat_messages'"
                " and period='guest_session'",
                (user_id,),
            )
            used_count = cursor.fetchone()[0]
            counts = {}
            for table in (
                "messages",
                "backtest_runs",
                "ideas",
                "idea_versions",
                "evidence_artifacts",
                "decision_notes",
            ):
                cursor.execute(
                    f"select count(*) from public.{table} where user_id=%s",
                    (user_id,),
                )
                counts[table] = cursor.fetchone()[0]
            cursor.execute(
                "select count(*) from public.checkpoints where thread_id=%s",
                (conversation_id,),
            )
            checkpoint_count = cursor.fetchone()[0]
            cursor.execute(
                "select count(*) from public.conversations where user_id=%s",
                (user_id,),
            )
            conversation_count = cursor.fetchone()[0]
            cursor.execute(
                "select is_anonymous from auth.users where id=%s",
                (user_id,),
            )
            is_anonymous = cursor.fetchone()[0]

        assert replacement_id != conversation_id
        assert workspace == (replacement_id, created_at, expires_at)
        assert used_count == 4
        assert counts == {
            "messages": 0,
            "backtest_runs": 0,
            "ideas": 0,
            "idea_versions": 0,
            "evidence_artifacts": 0,
            "decision_notes": 0,
        }
        assert checkpoint_count == 0
        assert conversation_count == 1
        assert is_anonymous is True
        with connection.cursor() as cursor:
            cursor.execute("delete from auth.users where id=%s", (user_id,))


def test_cleanup_dry_run_is_bounded_and_changes_nothing() -> None:
    with _connect() as connection:
        guest = _seed_expired_guest(connection)
        rows = _claim_cleanup(connection, dry_run=True)
        assert (guest["user_id"], guest["conversation_id"]) in rows
        with connection.cursor() as cursor:
            cursor.execute(
                "select status, conversation_id from public.guest_workspaces"
                " where user_id = %s",
                (guest["user_id"],),
            )
            status, conversation_id = cursor.fetchone()
            assert status == "active"
            assert str(conversation_id) == guest["conversation_id"]
            cursor.execute("delete from auth.users where id = %s", (guest["user_id"],))


def test_cleanup_batch_limit_order_reasons_and_counts_are_stable() -> None:
    with _connect(autocommit=False) as connection:
        guests = [_seed_expired_guest(connection) for _ in range(3)]
        ordered = [
            (guests[0]["user_id"], 30),
            (guests[1]["user_id"], 20),
            (guests[2]["user_id"], 10),
        ]
        with connection.cursor() as cursor:
            for user_id, minutes in ordered:
                cursor.execute(
                    "update public.guest_workspaces"
                    " set updated_at = now() - make_interval(mins => %s)"
                    " where user_id = %s",
                    (minutes, user_id),
                )
            cursor.execute(
                "select user_id::text,conversation_id::text,auth_deleted,"
                " cleanup_reason"
                " from public.claim_expired_guest_workspaces(2,true)",
            )
            dry_run = cursor.fetchall()
            cursor.execute(
                "select user_id::text,conversation_id::text,auth_deleted,"
                " cleanup_reason"
                " from public.claim_expired_guest_workspaces(2,false)",
            )
            real_run = cursor.fetchall()

        expected_ids = [guests[0]["user_id"], guests[1]["user_id"]]
        assert [row[0] for row in dry_run] == expected_ids
        assert [row[0] for row in real_run] == expected_ids
        assert [row[2:] for row in dry_run] == [
            (False, "expired_workspace"),
            (False, "expired_workspace"),
        ]
        assert [row[2:] for row in real_run] == [
            (True, "expired_workspace"),
            (True, "expired_workspace"),
        ]
        with connection.cursor() as cursor:
            cursor.execute(
                "select count(*) from auth.users where id = %s",
                (guests[2]["user_id"],),
            )
            assert cursor.fetchone()[0] == 1
        connection.rollback()


def test_cleanup_dry_run_and_real_run_share_transition_grace_predicate() -> None:
    with psycopg.connect(DSN, autocommit=False) as connection:
        active = _seed_expired_guest(connection)
        stale_expired = _seed_expired_guest(connection)
        recent_expired = _seed_expired_guest(connection)
        permanent = _seed_expired_guest(connection)
        with connection.cursor() as cursor:
            cursor.execute(
                "update public.guest_workspaces"
                " set status = 'expired', updated_at = now() - interval '10 minutes'"
                " where user_id = %s",
                (stale_expired["user_id"],),
            )
            cursor.execute(
                "update public.guest_workspaces"
                " set status = 'expired', updated_at = now() - interval '1 minute'"
                " where user_id = %s",
                (recent_expired["user_id"],),
            )
            cursor.execute(
                "update auth.users" " set is_anonymous = false, email = %s where id = %s",
                (
                    f"permanent-{permanent['user_id'][:8]}@example.com",
                    permanent["user_id"],
                ),
            )
            cursor.execute(
                "update public.profiles set email = %s where id = %s",
                (
                    f"permanent-{permanent['user_id'][:8]}@example.com",
                    permanent["user_id"],
                ),
            )
            fixture_ids = [
                active["user_id"],
                stale_expired["user_id"],
                recent_expired["user_id"],
                permanent["user_id"],
            ]
            cursor.execute(
                "select user_id::text, status, conversation_id::text"
                " from public.guest_workspaces"
                " where user_id = any(%s::uuid[]) order by user_id",
                (fixture_ids,),
            )
            before = cursor.fetchall()
            cursor.execute(
                "select user_id::text, conversation_id::text"
                " from public.claim_expired_guest_workspaces(100, true)",
            )
            dry_ids = {row[0] for row in cursor.fetchall() if row[0] in set(fixture_ids)}
            cursor.execute(
                "select user_id::text, status, conversation_id::text"
                " from public.guest_workspaces"
                " where user_id = any(%s::uuid[]) order by user_id",
                (fixture_ids,),
            )
            assert cursor.fetchall() == before
            cursor.execute(
                "select user_id::text, conversation_id::text"
                " from public.claim_expired_guest_workspaces(100, false)",
            )
            real_ids = {row[0] for row in cursor.fetchall() if row[0] in set(fixture_ids)}

        assert (
            dry_ids
            == real_ids
            == {
                active["user_id"],
                stale_expired["user_id"],
            }
        )
        connection.rollback()


def test_cleanup_removes_empty_expired_workspace() -> None:
    with _connect(autocommit=False) as connection:
        user_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(days=8)
        with connection.cursor() as cursor:
            cursor.execute(
                "insert into auth.users (id,email,is_anonymous)" " values (%s,null,true)",
                (user_id,),
            )
            cursor.execute(
                "insert into public.profiles (id,email) values (%s,null)",
                (user_id,),
            )
            cursor.execute(
                "insert into public.guest_workspaces"
                " (user_id,created_at,expires_at)"
                " values (%s,%s,%s)",
                (user_id, created_at, created_at + timedelta(days=7)),
            )
            cursor.execute(
                "select user_id::text,conversation_id::text,auth_deleted,"
                " cleanup_reason"
                " from public.claim_expired_guest_workspaces(25,false)",
            )
            selected = next(row for row in cursor.fetchall() if row[0] == user_id)

        assert selected == (user_id, None, True, "expired_workspace")
        with connection.cursor() as cursor:
            cursor.execute("select count(*) from auth.users where id = %s", (user_id,))
            assert cursor.fetchone()[0] == 0
        connection.rollback()


def test_cleanup_removes_orphan_identity_feedback() -> None:
    with _connect(autocommit=False) as connection:
        user_id = str(uuid.uuid4())
        feedback_id = str(uuid.uuid4())
        with connection.cursor() as cursor:
            cursor.execute(
                "insert into auth.users (id,email,is_anonymous,created_at)"
                " values (%s,null,true,now()-interval '10 minutes')",
                (user_id,),
            )
            cursor.execute(
                "insert into public.profiles (id,email) values (%s,null)",
                (user_id,),
            )
            cursor.execute(
                "insert into public.feedback (id,user_id,type,message)"
                " values (%s,%s,'general','orphan private feedback')",
                (feedback_id, user_id),
            )
            cursor.execute(
                "select user_id::text,conversation_id::text,auth_deleted,"
                " cleanup_reason"
                " from public.claim_expired_guest_workspaces(25,false)",
            )
            selected = next(row for row in cursor.fetchall() if row[0] == user_id)

        assert selected == (user_id, None, True, "orphan_identity")
        with connection.cursor() as cursor:
            cursor.execute("select count(*) from auth.users where id=%s", (user_id,))
            assert cursor.fetchone()[0] == 0
            cursor.execute(
                "select count(*) from public.feedback where id=%s",
                (feedback_id,),
            )
            assert cursor.fetchone()[0] == 0
        connection.rollback()


def test_poisoned_orphan_does_not_roll_back_healthy_orphan_cleanup() -> None:
    with _connect(autocommit=False) as connection:
        poisoned_user_id = str(uuid.uuid4())
        healthy_user_id = str(uuid.uuid4())
        source_user_id = str(uuid.uuid4())
        with connection.cursor() as cursor:
            cursor.executemany(
                "insert into auth.users (id,email,is_anonymous,created_at)"
                " values (%s,null,true,%s)",
                (
                    (
                        poisoned_user_id,
                        datetime.now(timezone.utc) - timedelta(minutes=30),
                    ),
                    (
                        healthy_user_id,
                        datetime.now(timezone.utc) - timedelta(minutes=20),
                    ),
                    (
                        source_user_id,
                        datetime.now(timezone.utc) - timedelta(minutes=10),
                    ),
                ),
            )
            cursor.executemany(
                "insert into public.profiles (id,email) values (%s,null)",
                (
                    (poisoned_user_id,),
                    (healthy_user_id,),
                    (source_user_id,),
                ),
            )
            cursor.execute(
                "insert into public.guest_workspaces"
                " (user_id,status,created_at,expires_at,claimed_by,claimed_at)"
                " values (%s,'claimed',now(),now()+interval '7 days',%s,now())",
                (source_user_id, poisoned_user_id),
            )

        with connection.cursor() as cursor:
            cursor.execute(
                "select user_id::text,conversation_id::text,auth_deleted,"
                " cleanup_reason"
                " from public.claim_expired_guest_workspaces(2,false)",
            )
            rows = cursor.fetchall()
        selected = {
            row[0]: (row[2], row[3])
            for row in rows
            if row[0] in {poisoned_user_id, healthy_user_id}
        }

        assert selected == {
            healthy_user_id: (True, "orphan_identity"),
        }
        with connection.cursor() as cursor:
            cursor.execute(
                "select count(*) from auth.users where id=%s",
                (poisoned_user_id,),
            )
            assert cursor.fetchone()[0] == 1
            cursor.execute(
                "select count(*) from auth.users where id=%s",
                (healthy_user_id,),
            )
            assert cursor.fetchone()[0] == 0
        connection.rollback()


def test_cleanup_orphan_with_foreign_relational_reference_fails_closed() -> None:
    with _connect(autocommit=False) as connection:
        orphan_user_id = str(uuid.uuid4())
        strategy_id = str(uuid.uuid4())
        foreign_user_id = str(uuid.uuid4())
        foreign_run_id = str(uuid.uuid4())
        foreign_email = f"foreign-orphan-{foreign_user_id[:8]}@example.com"
        with connection.cursor() as cursor:
            cursor.execute(
                "insert into auth.users (id,email,is_anonymous,created_at)"
                " values (%s,null,true,now()-interval '10 minutes')",
                (orphan_user_id,),
            )
            cursor.execute(
                "insert into public.profiles (id,email) values (%s,null)",
                (orphan_user_id,),
            )
            cursor.execute(
                "insert into public.strategies"
                " (id,user_id,name,template,asset_class,symbols,benchmark_symbol)"
                " values (%s,%s,'orphan strategy','buy_and_hold','equity',"
                " array['AAPL'],'SPY')",
                (strategy_id, orphan_user_id),
            )
            cursor.execute(
                "insert into auth.users (id,email,is_anonymous)" " values (%s,%s,false)",
                (foreign_user_id, foreign_email),
            )
            cursor.execute(
                "insert into public.profiles (id,email) values (%s,%s)",
                (foreign_user_id, foreign_email),
            )
            cursor.execute(
                "insert into public.backtest_runs"
                " (id,user_id,strategy_id,status,asset_class,symbols,"
                "  benchmark_symbol,config_snapshot)"
                " values (%s,%s,%s,'completed','equity',array['MSFT'],'SPY',"
                " '{}'::jsonb)",
                (foreign_run_id, foreign_user_id, strategy_id),
            )
            cursor.execute("savepoint cleanup_attempt")

        rows = _claim_cleanup(connection, dry_run=False)
        assert all(row[0] != orphan_user_id for row in rows)
        with connection.cursor() as cursor:
            cursor.execute(
                "select user_id::text,strategy_id::text"
                " from public.backtest_runs where id=%s",
                (foreign_run_id,),
            )
            assert cursor.fetchone() == (foreign_user_id, strategy_id)
            cursor.execute(
                "select user_id::text from public.strategies where id=%s",
                (strategy_id,),
            )
            assert cursor.fetchone()[0] == orphan_user_id
            cursor.execute(
                "select count(*) from auth.users where id=%s",
                (orphan_user_id,),
            )
            assert cursor.fetchone()[0] == 1
        connection.rollback()


def test_cleanup_removes_expired_identity_after_conversation_graph() -> None:
    with _connect() as connection:
        guest = _seed_expired_guest(connection)
        with connection.cursor() as cursor:
            cursor.execute(
                "insert into public.feedback (user_id, type, message)"
                " values (%s, 'general', 'private guest feedback')",
                (guest["user_id"],),
            )
        rows = _claim_cleanup(connection, dry_run=False)
        assert rows == [(guest["user_id"], guest["conversation_id"])]
        with connection.cursor() as cursor:
            cursor.execute(
                "select count(*) from public.guest_workspaces" " where user_id = %s",
                (guest["user_id"],),
            )
            assert cursor.fetchone()[0] == 0
            cursor.execute(
                "select count(*) from public.conversations where id = %s",
                (guest["conversation_id"],),
            )
            assert cursor.fetchone()[0] == 0
            cursor.execute(
                "select count(*) from public.messages where user_id = %s",
                (guest["user_id"],),
            )
            assert cursor.fetchone()[0] == 0
            cursor.execute(
                "select count(*) from public.feedback where user_id = %s",
                (guest["user_id"],),
            )
            assert cursor.fetchone()[0] == 0
            cursor.execute(
                "select count(*) from auth.users where id = %s",
                (guest["user_id"],),
            )
            assert cursor.fetchone()[0] == 0


def test_cleanup_deletes_expired_auth_identity_inside_the_database_claim() -> None:
    with _connect() as connection:
        guest = _seed_expired_guest(connection)
        with connection.cursor() as cursor:
            cursor.execute(
                "select user_id::text, conversation_id::text, auth_deleted,"
                " cleanup_reason"
                " from public.claim_expired_guest_workspaces(25, false)",
            )
            rows = cursor.fetchall()
            selected = next(row for row in rows if row[0] == guest["user_id"])
            assert selected == (
                guest["user_id"],
                guest["conversation_id"],
                True,
                "expired_workspace",
            )
            cursor.execute(
                "select count(*) from auth.users where id = %s",
                (guest["user_id"],),
            )
            assert cursor.fetchone()[0] == 0


def test_cleanup_removes_claimed_source_identity_without_destination_graph() -> None:
    with _connect() as connection:
        source = _seed_expired_guest(connection)
        destination_user_id = str(uuid.uuid4())
        destination_email = f"destination-{destination_user_id[:8]}@example.com"
        with connection.cursor() as cursor:
            cursor.execute(
                "insert into auth.users (id,email,is_anonymous)" " values (%s,%s,false)",
                (destination_user_id, destination_email),
            )
            cursor.execute(
                "insert into public.profiles (id,email) values (%s,%s)",
                (destination_user_id, destination_email),
            )
            cursor.execute(
                "update public.conversations set user_id=%s where id=%s",
                (destination_user_id, source["conversation_id"]),
            )
            cursor.execute(
                "update public.messages set user_id=%s where conversation_id=%s",
                (destination_user_id, source["conversation_id"]),
            )
            cursor.execute(
                "update public.guest_workspaces"
                " set status='claimed',claimed_by=%s,claimed_at=now()-interval '20 minutes',"
                " updated_at=now()-interval '20 minutes'"
                " where user_id=%s",
                (destination_user_id, source["user_id"]),
            )
            cursor.execute(
                "insert into public.feedback (user_id,type,message)"
                " values (%s,'general','claimed guest feedback')",
                (source["user_id"],),
            )
            cursor.execute(
                "select user_id::text,auth_deleted,cleanup_reason"
                " from public.claim_expired_guest_workspaces(25,false)",
            )
            selected = next(
                row for row in cursor.fetchall() if row[0] == source["user_id"]
            )
            assert selected == (source["user_id"], True, "claimed_identity")
            cursor.execute(
                "select user_id::text from public.conversations where id=%s",
                (source["conversation_id"],),
            )
            assert cursor.fetchone()[0] == destination_user_id
            cursor.execute(
                "select count(*) from auth.users where id=%s",
                (source["user_id"],),
            )
            assert cursor.fetchone()[0] == 0
            cursor.execute(
                "select count(*) from public.feedback"
                " where message='claimed guest feedback'",
            )
            assert cursor.fetchone()[0] == 0
            cursor.execute("delete from auth.users where id=%s", (destination_user_id,))


def test_cleanup_claimed_workspace_with_source_rows_fails_closed() -> None:
    with _connect(autocommit=False) as connection:
        source = _seed_expired_guest(connection)
        destination_user_id = str(uuid.uuid4())
        destination_email = f"destination-{destination_user_id[:8]}@example.com"
        with connection.cursor() as cursor:
            cursor.execute(
                "insert into auth.users (id,email,is_anonymous)" " values (%s,%s,false)",
                (destination_user_id, destination_email),
            )
            cursor.execute(
                "insert into public.profiles (id,email) values (%s,%s)",
                (destination_user_id, destination_email),
            )
            cursor.execute(
                "update public.guest_workspaces"
                " set status='claimed',claimed_by=%s,"
                " claimed_at=now()-interval '20 minutes',"
                " updated_at=now()-interval '20 minutes'"
                " where user_id=%s",
                (destination_user_id, source["user_id"]),
            )
            cursor.execute("savepoint cleanup_attempt")

        with connection.cursor() as cursor:
            cursor.execute(
                "select user_id::text,auth_deleted,cleanup_reason"
                " from public.claim_expired_guest_workspaces(25,false)",
            )
            selected = next(
                row for row in cursor.fetchall() if row[0] == source["user_id"]
            )
        assert selected == (
            source["user_id"],
            False,
            "claimed_identity_has_product_rows",
        )
        with connection.cursor() as cursor:
            cursor.execute(
                "select status,conversation_id::text,claimed_by::text"
                " from public.guest_workspaces where user_id=%s",
                (source["user_id"],),
            )
            assert cursor.fetchone() == (
                "claimed",
                source["conversation_id"],
                destination_user_id,
            )
            cursor.execute(
                "select count(*) from auth.users where id=%s",
                (source["user_id"],),
            )
            assert cursor.fetchone()[0] == 1
        connection.rollback()


def test_cleanup_removes_conversation_checkpoint_graph() -> None:
    with _connect() as connection:
        guest = _seed_expired_guest(connection)
        with connection.cursor() as cursor:
            cursor.execute(
                "insert into public.checkpoints"
                " (thread_id, checkpoint_ns, checkpoint_id, checkpoint)"
                " values (%s, '', 'checkpoint-1', '{}'::jsonb)",
                (guest["conversation_id"],),
            )
            cursor.execute(
                "insert into public.checkpoint_blobs"
                " (thread_id, checkpoint_ns, channel, version, type, blob)"
                " values (%s, '', 'messages', '1', 'msgpack', null)",
                (guest["conversation_id"],),
            )
            cursor.execute(
                "insert into public.checkpoint_writes"
                " (thread_id, checkpoint_ns, checkpoint_id, task_id,"
                "  idx, channel, type, blob)"
                " values (%s, '', 'checkpoint-1', 'task-1', 0,"
                "  'messages', 'msgpack', %s)",
                (guest["conversation_id"], b"checkpoint"),
            )

        rows = _claim_cleanup(connection, dry_run=False)
        assert rows == [(guest["user_id"], guest["conversation_id"])]
        with connection.cursor() as cursor:
            for table in ("checkpoints", "checkpoint_blobs", "checkpoint_writes"):
                cursor.execute(
                    f"select count(*) from public.{table} where thread_id = %s",
                    (guest["conversation_id"],),
                )
                assert cursor.fetchone()[0] == 0
            cursor.execute("delete from auth.users where id = %s", (guest["user_id"],))


def test_cleanup_cannot_select_a_converted_or_permanent_account() -> None:
    with _connect() as connection:
        guest = _seed_expired_guest(connection)
        verified_email = f"converted-{guest['user_id'][:8]}@example.com"
        with connection.cursor() as cursor:
            cursor.execute(
                "update auth.users set is_anonymous = false, email = %s" " where id = %s",
                (verified_email, guest["user_id"]),
            )
            cursor.execute(
                "update public.profiles set email = %s where id = %s",
                (verified_email, guest["user_id"]),
            )

        rows = _claim_cleanup(connection, dry_run=False)
        assert all(row[0] != guest["user_id"] for row in rows)
        with connection.cursor() as cursor:
            cursor.execute(
                "select count(*) from auth.users where id = %s",
                (guest["user_id"],),
            )
            assert cursor.fetchone()[0] == 1
            cursor.execute(
                "select status, conversation_id from public.guest_workspaces"
                " where user_id = %s",
                (guest["user_id"],),
            )
            status, conversation_id = cursor.fetchone()
            assert status == "claimed"
            assert str(conversation_id) == guest["conversation_id"]
            cursor.execute("delete from auth.users where id = %s", (guest["user_id"],))


def test_auth_identity_link_finalizes_profile_and_workspace_in_auth_transaction() -> None:
    with _connect() as connection:
        guest = _seed_expired_guest(connection)
        verified_email = f"linked-{guest['user_id'][:8]}@example.com"
        with connection.cursor() as cursor:
            cursor.execute(
                "update auth.users set is_anonymous=false,email=%s where id=%s",
                (verified_email, guest["user_id"]),
            )
            cursor.execute(
                "select email from public.profiles where id=%s",
                (guest["user_id"],),
            )
            assert cursor.fetchone()[0] == verified_email
            cursor.execute(
                "select status,claimed_by::text,claimed_at is not null"
                " from public.guest_workspaces where user_id=%s",
                (guest["user_id"],),
            )
            assert cursor.fetchone() == ("claimed", guest["user_id"], True)
            cursor.execute(
                "select user_id::text from public.claim_expired_guest_workspaces(25,false)",
            )
            assert guest["user_id"] not in {row[0] for row in cursor.fetchall()}
            cursor.execute("delete from auth.users where id=%s", (guest["user_id"],))


def test_concurrent_cleanup_claims_each_guest_at_most_once() -> None:
    with _connect() as connection:
        guests = [_seed_expired_guest(connection), _seed_expired_guest(connection)]
    barrier = Barrier(2)

    def claim() -> list[tuple[str, str | None]]:
        with _connect() as connection:
            barrier.wait(timeout=10)
            return _claim_cleanup(connection, dry_run=False)

    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(lambda _: claim(), range(2)))

    claimed_ids = [user_id for rows in claims for user_id, _ in rows]
    expected_ids = {guest["user_id"] for guest in guests}
    assert set(claimed_ids) == expected_ids
    assert len(claimed_ids) == len(set(claimed_ids))
    with _connect() as connection:
        assert _claim_cleanup(connection, dry_run=False) == []
        with connection.cursor() as cursor:
            cursor.execute(
                "delete from auth.users where id = any(%s::uuid[])",
                ([guest["user_id"] for guest in guests],),
            )


def test_guest_privileged_functions_are_service_role_executable() -> None:
    signatures = (
        "public.bind_guest_conversation(uuid,uuid)",
        "public.replace_empty_guest_conversation(uuid,text,text,text)",
        "public.claim_expired_guest_workspaces(integer,boolean)",
        (
            "public.create_feedback_settling_usage("
            "uuid,uuid,text,text,jsonb,text,jsonb)"
        ),
    )
    with _connect() as connection:
        with connection.cursor() as cursor:
            for signature in signatures:
                cursor.execute(
                    "select has_function_privilege('service_role', %s, 'execute')",
                    (signature,),
                )
                assert cursor.fetchone() == (True,), signature
            cursor.execute(
                "select routine.prosecdef, routine.proconfig"
                " from pg_proc as routine"
                " join pg_namespace as namespace"
                "   on namespace.oid = routine.pronamespace"
                " where namespace.nspname='public'"
                "   and routine.proname='claim_expired_guest_workspaces'"
                "   and pg_get_function_identity_arguments(routine.oid)"
                "       = 'p_limit integer, p_dry_run boolean'"
            )
            security_definer, settings = cursor.fetchone()
            assert security_definer is True
            assert settings == ['search_path=""']
