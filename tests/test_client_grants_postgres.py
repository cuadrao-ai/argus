"""Real-Postgres owner of every client grant in ``public`` and ``argus_private``.

The allow-lists below are the single statement of what ``anon`` and
``authenticated`` may do. They are compared to the catalog in both directions,
so a migration that adds a relation, a grant or a client-executable function
fails here until the list says so. The image a database is built on must not
change the result (#811).

Set ``ARGUS_DISPOSABLE_DATABASE_URL`` only to an isolated Supabase Postgres
database with every checked-in migration applied; never point it at shared or
production data.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from uuid import uuid4

import pytest

DSN = os.getenv("ARGUS_DISPOSABLE_DATABASE_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not DSN,
    reason="ARGUS_DISPOSABLE_DATABASE_URL is not configured",
)

psycopg = pytest.importorskip("psycopg")

CLIENT_ROLES = ("anon", "authenticated")
SCHEMAS = ("public", "argus_private")
# Migrations run as this role, so its default privileges decide the grants a
# new relation or function is born with.
MIGRATION_OWNER = "postgres"

TABLE_PRIVILEGES = (
    "SELECT",
    "INSERT",
    "UPDATE",
    "DELETE",
    "TRUNCATE",
    "REFERENCES",
    "TRIGGER",
    "MAINTAIN",
)
COLUMN_PRIVILEGES = ("SELECT", "INSERT", "UPDATE", "REFERENCES")

CLIENT_SCHEMA_PRIVILEGES: dict[str, dict[str, frozenset[str]]] = {
    "public": {
        "anon": frozenset({"USAGE"}),
        "authenticated": frozenset({"USAGE"}),
    },
    "argus_private": {},
}

CLIENT_RELATION_PRIVILEGES: dict[str, dict[str, frozenset[str]]] = {
    "public.backtest_jobs": {"authenticated": frozenset({"SELECT"})},
    "public.business_consent_acceptances": {"authenticated": frozenset({"SELECT"})},
    "public.chat_turn_lifecycles": {"authenticated": frozenset({"SELECT"})},
    "public.conversation_read_states": {"authenticated": frozenset({"SELECT"})},
    "public.financial_accounts": {"authenticated": frozenset({"SELECT"})},
    "public.financial_activity_groups": {"authenticated": frozenset({"SELECT"})},
    "public.financial_activity_memberships": {"authenticated": frozenset({"SELECT"})},
    "public.financial_activity_revisions": {"authenticated": frozenset({"SELECT"})},
    "public.financial_asset_changes": {"authenticated": frozenset({"SELECT"})},
    "public.financial_asset_details": {"authenticated": frozenset({"SELECT"})},
    "public.financial_budgets": {"authenticated": frozenset({"SELECT"})},
    "public.financial_debt_plans": {"authenticated": frozenset({"SELECT"})},
    "public.financial_expectations": {"authenticated": frozenset({"SELECT"})},
    "public.financial_goal_allocations": {"authenticated": frozenset({"SELECT"})},
    "public.financial_goals": {"authenticated": frozenset({"SELECT"})},
    "public.financial_import_account_links": {"authenticated": frozenset({"SELECT"})},
    "public.financial_import_events": {"authenticated": frozenset({"SELECT"})},
    "public.financial_import_observations": {"authenticated": frozenset({"SELECT"})},
    "public.financial_observation_coverage": {"authenticated": frozenset({"SELECT"})},
    "public.financial_plan_links": {"authenticated": frozenset({"SELECT"})},
    "public.financial_plan_selections": {"authenticated": frozenset({"SELECT"})},
    "public.financial_record_revisions": {"authenticated": frozenset({"SELECT"})},
    "public.financial_records": {"authenticated": frozenset({"SELECT"})},
    "public.guest_workspaces": {"authenticated": frozenset({"SELECT"})},
}

# Column grants that are not covered by a table-level grant above.
CLIENT_COLUMN_PRIVILEGES: dict[str, dict[str, dict[str, frozenset[str]]]] = {
    "public.business_consent_acceptances": {
        "authenticated": {"INSERT": frozenset({"copy_version", "space_id", "user_id"})},
    },
    "public.financial_source_connections": {
        "authenticated": {
            "SELECT": frozenset(
                {
                    "attention_at",
                    "attention_code",
                    "created_at",
                    "disconnected_at",
                    "id",
                    "label",
                    "last_attempt_at",
                    "last_error_code",
                    "last_success_at",
                    "source",
                    "status",
                    "updated_at",
                    "user_id",
                    "version",
                }
            ),
        },
    },
    "public.financial_source_gmail_senders": {
        "authenticated": {
            "SELECT": frozenset(
                {"backfilled_at", "connection_id", "created_at", "sender", "user_id"}
            ),
        },
    },
    "public.profiles": {
        "authenticated": {
            "SELECT": frozenset(
                {"avatar_theme", "country", "currency_override", "id", "preferred_name"}
            ),
            "UPDATE": frozenset(
                {"avatar_theme", "country", "currency_override", "preferred_name"}
            ),
        },
    },
}

# Every other relation in the two schemas: no client table privilege, though a
# column grant above may apply. An unlisted relation fails the inventory test.
RELATIONS_WITHOUT_CLIENT_TABLE_GRANTS = frozenset(
    {
        "argus_private.account_deletion_placeholders",
        "argus_private.account_deletion_revocations",
        "argus_private.account_deletion_runs",
        "argus_private.account_placeholders",
        "argus_private.business_custody_changes",
        "argus_private.business_custody_deferred_keys",
        "argus_private.business_custody_moves",
        "argus_private.business_custody_objects",
        "argus_private.business_custody_reservations",
        "argus_private.business_departure_aliases",
        "argus_private.business_invitation_commands",
        "argus_private.business_purge_objects",
        "argus_private.business_purge_runs",
        "argus_private.business_report_view_commands",
        "argus_private.business_saved_report_views",
        "argus_private.business_workspace_assets",
        "argus_private.business_workspace_commands",
        "argus_private.invite_code_digests",
        "argus_private.retention_policies",
        "argus_private.retention_sweeps",
        "public.apple_sign_in_credentials",
        "public.argus_memory_vectors",
        "public.backtest_runs",
        "public.beta_admissions",
        "public.beta_invitations",
        "public.beta_invite_quota_grants",
        "public.business_access_invites",
        "public.business_action_receipts",
        "public.business_ai_consents",
        "public.business_bank_accounts",
        "public.business_bank_imports",
        "public.business_bank_line_outcomes",
        "public.business_bank_lines",
        "public.business_bank_suggestions",
        "public.business_client_grants",
        "public.business_close_mail_outbox",
        "public.business_document_settlement_revisions",
        "public.business_document_settlements",
        "public.business_draft_revisions",
        "public.business_draft_sources",
        "public.business_email_address_events",
        "public.business_email_daily_usage",
        "public.business_email_deliveries",
        "public.business_email_parts",
        "public.business_email_retired_aliases",
        "public.business_email_routes",
        "public.business_fiscal_observations",
        "public.business_fiscal_observations_id_seq",
        "public.business_fiscal_operations",
        "public.business_lifecycle_commands",
        "public.business_ownership_transfers",
        "public.business_email_senders",
        "public.business_logos",
        "public.business_questions",
        "public.business_receipt_activity_baseline",
        "public.business_receipt_consent_commands",
        "public.business_receipt_read_states",
        "public.business_receipt_reading_consents",
        "public.business_search_opens",
        "public.business_search_recents",
        "public.business_sender_leases",
        "public.business_sources",
        "public.business_transfer_mail_outbox",
        "public.business_turns",
        "public.business_turns_arrival_sequence_seq",
        "public.business_whatsapp_ai_consents",
        "public.checkpoint_blobs",
        "public.checkpoint_migrations",
        "public.checkpoint_writes",
        "public.checkpoints",
        "public.collection_strategies",
        "public.collections",
        "public.context_packets",
        "public.conversations",
        "public.cost_ledger_entries",
        "public.cuadrao_early_access_signups",
        "public.decision_notes",
        "public.dgii_rnc",
        "public.dgii_rnc_load",
        "public.evidence_artifacts",
        "public.feedback",
        "public.financial_account_idempotency",
        "public.financial_activity_receipts",
        "public.financial_document_extractions",
        "public.financial_goal_allocation_revisions",
        "public.financial_operation_receipts",
        "public.financial_plan_definition_revisions",
        "public.financial_plan_receipts",
        "public.financial_plan_responsibilities",
        "public.financial_shortcut_device_tokens",
        "public.financial_source_connections",
        "public.financial_source_gmail_senders",
        "public.guest_funnel_milestones",
        "public.guest_workspace_handoffs",
        "public.household_account_grants",
        "public.household_command_receipts",
        "public.household_deletion_events",
        "public.household_invitations",
        "public.household_members",
        "public.household_plan_archived_activities",
        "public.household_plan_archived_allocations",
        "public.household_plan_archived_claims",
        "public.household_plan_bindings",
        "public.household_plan_participants",
        "public.household_plan_receipts",
        "public.households",
        "public.idea_versions",
        "public.ideas",
        "public.invite_referrals",
        "public.invite_sender_refs",
        "public.memory_candidates",
        "public.memory_consent_actions",
        "public.memory_prompt_history",
        "public.memory_provenance",
        "public.memory_provider_cleanup",
        "public.memory_provider_projections",
        "public.memory_reconciliations",
        "public.memory_records",
        "public.memory_settings",
        "public.messages",
        "public.private_alpha_access_welcome_claims",
        "public.private_alpha_access_welcome_deliveries",
        "public.private_alpha_allowlist",
        "public.profile_photos",
        "public.profiles",
        "public.public_excerpt_snapshots",
        "public.refusal_log",
        "public.refusal_observations",
        "public.route_receipts",
        "public.run_context_packets",
        "public.spaces",
        "public.strategies",
        "public.usage_counters",
        "public.visitor_usage_counters",
        "public.whatsapp_inbound_messages",
        "public.whatsapp_inbound_messages_arrival_sequence_seq",
        "public.whatsapp_link_codes",
        "public.whatsapp_outbox",
        "public.whatsapp_reply_attempts",
        "public.whatsapp_reply_days",
        "public.whatsapp_reply_groups",
        "public.whatsapp_sender_links",
    }
)

# Functions a client role can execute, directly or through PUBLIC. Extension
# members are excluded.
CLIENT_EXECUTABLE_FUNCTIONS: dict[str, frozenset[str]] = {
    "argus_private.business_bank_has_capability(uuid, text)": frozenset(
        {"authenticated"}
    ),
    "argus_private.business_custody_client_allowed()": frozenset({"authenticated"}),
    "public.argus_search_symbol_casefold(text)": frozenset({"anon", "authenticated"}),
    "public.is_active_household_member(uuid, uuid)": frozenset({"authenticated"}),
    # The historical staging adoption retains this existing helper grant.
    "public.set_updated_at()": frozenset({"anon", "authenticated"}),
}

# (schema or "*" for every schema, object type, grantee, privilege) entries the
# migration owner's default privileges hand to a client role.
CLIENT_DEFAULT_PRIVILEGES: frozenset[tuple[str, str, str, str]] = frozenset()


def _relations(cursor) -> list[str]:
    cursor.execute(
        """
        select format('%%s.%%s', n.nspname, c.relname)
        from pg_class c
        join pg_namespace n on n.oid = c.relnamespace
        where n.nspname = any(%s)
          and c.relkind in ('r', 'p', 'v', 'm', 'S', 'f')
        order by 1
        """,
        (list(SCHEMAS),),
    )
    return [row[0] for row in cursor.fetchall()]


def _schema_privileges(cursor) -> dict[str, dict[str, frozenset[str]]]:
    cursor.execute(
        """
        select schema_name, role_name, privilege
        from unnest(%s::text[]) as schema_name
        cross join unnest(%s::text[]) as role_name
        cross join unnest(array['USAGE', 'CREATE']) as privilege
        where has_schema_privilege(role_name, schema_name, privilege)
        """,
        (list(SCHEMAS), list(CLIENT_ROLES)),
    )
    matrix: dict[str, dict[str, set[str]]] = {schema: {} for schema in SCHEMAS}
    for schema, role, privilege in cursor.fetchall():
        matrix[schema].setdefault(role, set()).add(privilege)
    return _freeze(matrix)


def _relation_privileges(cursor) -> dict[str, dict[str, frozenset[str]]]:
    cursor.execute(
        """
        select relation, role_name, privilege
        from unnest(%s::text[]) as relation
        cross join unnest(%s::text[]) as role_name
        cross join unnest(%s::text[]) as privilege
        where has_table_privilege(role_name, relation, privilege)
        """,
        (_relations(cursor), list(CLIENT_ROLES), list(TABLE_PRIVILEGES)),
    )
    matrix: dict[str, dict[str, set[str]]] = {}
    for relation, role, privilege in cursor.fetchall():
        matrix.setdefault(relation, {}).setdefault(role, set()).add(privilege)
    return _freeze(matrix)


def _column_privileges(cursor) -> dict[str, dict[str, dict[str, frozenset[str]]]]:
    cursor.execute(
        """
        select format('%%s.%%s', n.nspname, c.relname), role_name, privilege,
               a.attname
        from pg_class c
        join pg_namespace n on n.oid = c.relnamespace
        join pg_attribute a on a.attrelid = c.oid
        cross join unnest(%s::text[]) as role_name
        cross join unnest(%s::text[]) as privilege
        where n.nspname = any(%s)
          and c.relkind in ('r', 'p', 'v', 'm', 'f')
          and a.attnum > 0
          and not a.attisdropped
          and has_column_privilege(role_name, c.oid, a.attnum, privilege)
          and not has_table_privilege(role_name, c.oid, privilege)
        """,
        (list(CLIENT_ROLES), list(COLUMN_PRIVILEGES), list(SCHEMAS)),
    )
    matrix: dict[str, dict[str, dict[str, set[str]]]] = {}
    for relation, role, privilege, column in cursor.fetchall():
        by_privilege = matrix.setdefault(relation, {}).setdefault(role, {})
        by_privilege.setdefault(privilege, set()).add(column)
    return {relation: _freeze(roles) for relation, roles in matrix.items()}


def _executable_functions(cursor) -> dict[str, frozenset[str]]:
    cursor.execute(
        """
        select format('%%s.%%s(%%s)', n.nspname, p.proname,
                      oidvectortypes(p.proargtypes)),
               role_name
        from pg_proc p
        join pg_namespace n on n.oid = p.pronamespace
        cross join unnest(%s::text[]) as role_name
        where n.nspname = any(%s)
          and not exists (
            select 1
            from pg_depend d
            where d.classid = 'pg_proc'::regclass
              and d.objid = p.oid
              and d.deptype = 'e'
          )
          and has_function_privilege(role_name, p.oid, 'EXECUTE')
        """,
        (list(CLIENT_ROLES), list(SCHEMAS)),
    )
    matrix: dict[str, set[str]] = {}
    for signature, role in cursor.fetchall():
        matrix.setdefault(signature, set()).add(role)
    return {signature: frozenset(roles) for signature, roles in matrix.items()}


def _default_privileges(cursor) -> frozenset[tuple[str, str, str, str]]:
    cursor.execute(
        """
        select coalesce(n.nspname, '*'), d.defaclobjtype,
               case acl.grantee when 0 then 'PUBLIC'
                    else acl.grantee::regrole::text end,
               acl.privilege_type
        from pg_default_acl d
        left join pg_namespace n on n.oid = d.defaclnamespace
        cross join lateral aclexplode(d.defaclacl) as acl
        where d.defaclrole = %s::regrole
          and (d.defaclnamespace = 0 or n.nspname = any(%s))
          and (acl.grantee = 0 or acl.grantee::regrole::text = any(%s))
        """,
        (MIGRATION_OWNER, list(SCHEMAS), list(CLIENT_ROLES)),
    )
    return frozenset(tuple(row) for row in cursor.fetchall())


def _freeze(matrix: dict) -> dict:
    return {
        key: frozenset(value) if isinstance(value, set) else _freeze(value)
        for key, value in matrix.items()
    }


@pytest.fixture(scope="module")
def catalog() -> Iterator:
    with psycopg.connect(DSN, autocommit=True) as connection:
        with connection.cursor() as cursor:
            yield cursor


def test_every_relation_is_listed_exactly_once(catalog) -> None:
    client = set(CLIENT_RELATION_PRIVILEGES)
    assert not client & RELATIONS_WITHOUT_CLIENT_TABLE_GRANTS
    assert set(_relations(catalog)) == client | RELATIONS_WITHOUT_CLIENT_TABLE_GRANTS


def test_client_schema_privileges_match_the_allow_list(catalog) -> None:
    assert _schema_privileges(catalog) == CLIENT_SCHEMA_PRIVILEGES


def test_client_relation_privileges_match_the_allow_list(catalog) -> None:
    assert _relation_privileges(catalog) == CLIENT_RELATION_PRIVILEGES


def test_client_column_privileges_match_the_allow_list(catalog) -> None:
    assert _column_privileges(catalog) == CLIENT_COLUMN_PRIVILEGES


def test_client_executable_functions_match_the_allow_list(catalog) -> None:
    assert _executable_functions(catalog) == CLIENT_EXECUTABLE_FUNCTIONS


@pytest.mark.parametrize("role", CLIENT_ROLES)
def test_rls_event_trigger_is_not_client_executable(catalog, role) -> None:
    catalog.execute(
        "select has_function_privilege(%s, 'public.rls_auto_enable()', 'EXECUTE')",
        (role,),
    )
    assert catalog.fetchone() == (False,)


def test_revoked_rls_helper_still_enables_new_public_table_rls(catalog) -> None:
    with catalog.connection.transaction(force_rollback=True):
        catalog.execute("create table public.security_rls_probe (id integer)")
        catalog.execute(
            "select relrowsecurity from pg_class where oid='public.security_rls_probe'::regclass"
        )
        assert catalog.fetchone() == (True,)


def test_migration_owner_default_privileges_give_clients_nothing(catalog) -> None:
    assert _default_privileges(catalog) == CLIENT_DEFAULT_PRIVILEGES


def test_service_role_can_call_dgii_rnc_lookup(catalog) -> None:
    catalog.execute(
        """
        select prosecdef
        from pg_proc
        join pg_namespace on pg_namespace.oid = pg_proc.pronamespace
        where nspname = 'public' and proname = 'dgii_rnc_lookup'
        """
    )
    assert catalog.fetchone() == (False,)
    catalog.execute(
        """
        select role_name,
               has_function_privilege(role_name, 'public.dgii_rnc_lookup(text)', 'execute')
        from unnest(array['anon', 'authenticated', 'service_role']) as role_name
        """
    )
    assert dict(catalog.fetchall()) == {
        "anon": False,
        "authenticated": False,
        "service_role": True,
    }
    try:
        with catalog.connection.transaction(force_rollback=True):
            catalog.execute(
                """
                insert into public.dgii_rnc (rnc, name, trade_name, status, file_date)
                values ('101234567', 'Casa Norte', null, 'ACTIVO', '2026-10-18')
                """
            )
            catalog.execute("set role service_role")
            catalog.execute("select rnc from public.dgii_rnc_lookup('1-01-23456-7')")
            assert catalog.fetchone() == ("101234567",)
            catalog.execute("reset role")
    finally:
        catalog.execute("reset role")


def test_business_space_is_never_client_visible(catalog) -> None:
    connections = _column_privileges(catalog)["public.financial_source_connections"]
    assert "owner_space_id" not in connections["authenticated"]["SELECT"]
    catalog.execute(
        "select role_name, has_function_privilege(role_name,"
        " 'public.business_space_of(uuid)', 'EXECUTE')"
        " from unnest(array['anon', 'authenticated', 'service_role']) as role_name"
    )
    assert dict(catalog.fetchall()) == {
        "anon": False,
        "authenticated": False,
        "service_role": True,
    }


# Behavior on a real write. A signed-in user owns these rows and the owner
# policies would admit the write, so only the missing grant refuses it.

REFUSED_CLIENT_WRITES = {
    "profile admin flag": (
        "update public.profiles set is_admin = true where id = %(user_id)s"
    ),
    "usage counter reset": (
        "update public.usage_counters set used_count = 0" " where user_id = %(user_id)s"
    ),
    "usage counter delete": (
        "delete from public.usage_counters where user_id = %(user_id)s"
    ),
    "conversation insert": (
        "insert into public.conversations (user_id, title)"
        " values (%(user_id)s, 'client written')"
    ),
    "conversation rename": (
        "update public.conversations set title = 'client renamed'"
        " where id = %(conversation_id)s"
    ),
    "simulation result insert": (
        "insert into public.backtest_runs"
        " (user_id, conversation_id, status, asset_class, symbols,"
        "  benchmark_symbol, config_snapshot)"
        " values (%(user_id)s, %(conversation_id)s, 'completed', 'equity',"
        "  array['AAPL'], 'SPY', '{}'::jsonb)"
    ),
    "simulation result edit": (
        "update public.backtest_runs set status = 'failed'" " where id = %(run_id)s"
    ),
    "simulation job edit": (
        "update public.backtest_jobs set status = 'succeeded'" " where id = %(job_id)s"
    ),
}


def _act_as(cursor, role: str, *, user_id: str | None = None) -> None:
    cursor.execute(f"set local role {role}")
    claims = {"role": role}
    if user_id is not None:
        claims |= {"sub": user_id, "is_anonymous": False}
    cursor.execute(
        "select set_config('request.jwt.claims', %s, true)",
        (json.dumps(claims),),
    )


@pytest.fixture
def owned_rows() -> Iterator[tuple]:
    user_id = str(uuid4())
    email = f"client-grants-{user_id}@example.test"
    with psycopg.connect(DSN) as connection:
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "insert into auth.users (id, email, is_anonymous)"
                    " values (%s, %s, false)",
                    (user_id, email),
                )
                cursor.execute(
                    "insert into public.profiles (id, email, username)"
                    " values (%s, %s, %s)",
                    (user_id, email, f"client-grants-{user_id[:8]}"),
                )
                cursor.execute(
                    "insert into public.usage_counters"
                    " (user_id, resource, period, period_start, period_end,"
                    "  used_count, limit_count)"
                    " values (%s, 'backtest_runs', 'day', now(),"
                    "  now() + interval '1 day', 3, 5)",
                    (user_id,),
                )
                cursor.execute(
                    "insert into public.conversations (user_id, title)"
                    " values (%s, 'owned') returning id",
                    (user_id,),
                )
                (conversation_id,) = cursor.fetchone()
                cursor.execute(
                    "insert into public.backtest_runs"
                    " (user_id, conversation_id, status, asset_class, symbols,"
                    "  benchmark_symbol, config_snapshot)"
                    " values (%s, %s, 'completed', 'equity', array['AAPL'],"
                    "  'SPY', '{}'::jsonb) returning id",
                    (user_id, conversation_id),
                )
                (run_id,) = cursor.fetchone()
                cursor.execute(
                    "insert into public.backtest_jobs"
                    " (user_id, conversation_id, operation_scope,"
                    "  idempotency_key, payload_hash, launch_payload, status)"
                    " values (%s, %s, 'chat.run_backtest', %s, 'hash',"
                    "  '{}'::jsonb, 'queued') returning id",
                    (user_id, conversation_id, str(uuid4())),
                )
                (job_id,) = cursor.fetchone()
            ids = {
                "user_id": user_id,
                "conversation_id": conversation_id,
                "run_id": run_id,
                "job_id": job_id,
            }
            yield connection, ids
        finally:
            connection.rollback()


@pytest.mark.parametrize(
    "statement", REFUSED_CLIENT_WRITES.values(), ids=REFUSED_CLIENT_WRITES
)
@pytest.mark.parametrize("role", CLIENT_ROLES)
def test_client_roles_cannot_write_backend_owned_rows(
    owned_rows, role, statement
) -> None:
    connection, ids = owned_rows
    with connection.cursor() as cursor:
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            with connection.transaction():
                _act_as(cursor, role, user_id=ids["user_id"])
                cursor.execute(statement, ids)


def test_signed_in_owner_keeps_preferences_and_job_reads(owned_rows) -> None:
    connection, ids = owned_rows
    with connection.cursor() as cursor:
        with connection.transaction():
            _act_as(cursor, "authenticated", user_id=ids["user_id"])
            cursor.execute(
                "update public.profiles"
                " set avatar_theme = 'plum', preferred_name = 'Ana',"
                "     country = 'DO', currency_override = 'USD'"
                " where id = %(user_id)s"
                " returning avatar_theme, preferred_name, country, currency_override",
                ids,
            )
            assert cursor.fetchone() == ("plum", "Ana", "DO", "USD")
            cursor.execute(
                "select id, status from public.backtest_jobs where id = %(job_id)s",
                ids,
            )
            assert cursor.fetchone() == (ids["job_id"], "queued")


def test_service_role_still_writes_backend_owned_rows(owned_rows) -> None:
    connection, ids = owned_rows
    with connection.cursor() as cursor:
        with connection.transaction():
            _act_as(cursor, "service_role")
            for statement in REFUSED_CLIENT_WRITES.values():
                cursor.execute(statement, ids)
            cursor.execute(
                "select is_admin from public.profiles where id = %(user_id)s", ids
            )
            assert cursor.fetchone() == (True,)
            cursor.execute(
                "select count(*) from public.usage_counters where user_id = %(user_id)s",
                ids,
            )
            assert cursor.fetchone() == (0,)
            cursor.execute(
                "select status from public.backtest_jobs where id = %(job_id)s", ids
            )
            assert cursor.fetchone() == ("succeeded",)


@pytest.fixture
def consent_people() -> Iterator[tuple]:
    """Ana and Beto each own a Business; neither holds a grant on the other's."""

    with psycopg.connect(DSN) as connection:
        try:
            people = {}
            with connection.cursor() as cursor:
                for name in ("ana", "beto"):
                    user_id = str(uuid4())
                    cursor.execute(
                        "insert into auth.users (id, email, is_anonymous)"
                        " values (%s, %s, false)",
                        (user_id, f"consent-{name}-{user_id}@example.test"),
                    )
                    cursor.execute(
                        "insert into public.spaces (kind, name, created_by)"
                        " values ('business', %s, %s) returning id::text",
                        (name, user_id),
                    )
                    (space_id,) = cursor.fetchone()
                    cursor.execute(
                        "insert into public.business_client_grants"
                        " (space_id, grantee_id, issuer_id, capabilities)"
                        " values (%s, %s, %s, array['read', 'prepare', 'approve'])",
                        (space_id, user_id, user_id),
                    )
                    people[name] = (user_id, space_id)
            yield connection, people
        finally:
            connection.rollback()


CONSENT_INSERT = (
    "insert into public.business_consent_acceptances (user_id, space_id, copy_version)"
    " values (%s, %s, %s)"
)
CONSENT_VERSION = "0123456789abcdef"


def test_a_signed_in_person_writes_and_reads_only_their_own_consent(
    consent_people,
) -> None:
    connection, people = consent_people
    ana, ana_space = people["ana"]
    beto, beto_space = people["beto"]
    with connection.cursor() as cursor:
        with connection.transaction():
            _act_as(cursor, "authenticated", user_id=ana)
            cursor.execute(CONSENT_INSERT, (ana, ana_space, CONSENT_VERSION))
            cursor.execute(
                "select user_id::text, space_id::text, copy_version,"
                " accepted_at is not null from public.business_consent_acceptances"
            )
            assert cursor.fetchall() == [(ana, ana_space, CONSENT_VERSION, True)]
            cursor.execute("reset role")

        refused = {
            "someone else's acceptance": (CONSENT_INSERT, (beto, beto_space, "f" * 16)),
            "a Business without a grant": (CONSENT_INSERT, (ana, beto_space, "e" * 16)),
            "a chosen time": (
                "insert into public.business_consent_acceptances"
                " (user_id, space_id, copy_version, accepted_at)"
                " values (%s, %s, %s, now() - interval '1 year')",
                (ana, ana_space, "d" * 16),
            ),
            "an edit": (
                "update public.business_consent_acceptances set copy_version = %s"
                " where user_id = %s",
                ("c" * 16, ana),
            ),
            "a delete": (
                "delete from public.business_consent_acceptances where user_id = %s",
                (ana,),
            ),
        }
        for label, (statement, params) in refused.items():
            with (
                pytest.raises(psycopg.errors.InsufficientPrivilege),
                connection.transaction(),
            ):
                _act_as(cursor, "authenticated", user_id=ana)
                cursor.execute(statement, params)
                pytest.fail(f"{label} was written")

        with connection.transaction():
            _act_as(cursor, "authenticated", user_id=beto)
            cursor.execute("select count(*) from public.business_consent_acceptances")
            assert cursor.fetchone() == (0,)
            cursor.execute("reset role")
        with (
            pytest.raises(psycopg.errors.InsufficientPrivilege),
            connection.transaction(),
        ):
            _act_as(cursor, "anon")
            cursor.execute("select count(*) from public.business_consent_acceptances")

        # Ana's Business still names her, so only the account-deletion
        # command may remove her; the bare Auth delete is refused.
        with (
            pytest.raises(
                psycopg.errors.CheckViolation,
                match="business_custody_identity_detachment_required",
            ),
            connection.transaction(),
        ):
            cursor.execute("delete from auth.users where id = %s", (ana,))


@pytest.mark.owner_acts
def test_a_deleted_owner_keeps_no_consent_acceptance() -> None:
    from psycopg_pool import ConnectionPool

    from tests.test_business_account_deletion_postgres import (
        erase_open_owner,
        release_custodian,
    )

    ana = str(uuid4())
    with psycopg.connect(DSN) as connection:
        connection.execute(
            "insert into auth.users (id, email, is_anonymous) values (%s, %s, false)",
            (ana, f"consent-ana-{ana}@example.test"),
        )
        (space_id,) = connection.execute(
            "insert into public.spaces (kind, name, created_by)"
            " values ('business', 'ana', %s) returning id::text",
            (ana,),
        ).fetchone()
        connection.execute(CONSENT_INSERT, (ana, space_id, CONSENT_VERSION))
    try:
        with ConnectionPool(DSN, min_size=1, max_size=4) as pool:
            assert erase_open_owner(pool, ana).status == "done"
        with psycopg.connect(DSN) as connection:
            assert connection.execute(
                "select count(*) from public.business_consent_acceptances where user_id = %s",
                (ana,),
            ).fetchone() == (0,), "a deleted account keeps no acceptance"
            assert connection.execute(
                "select count(*) from public.spaces where id = %s and closed_at is not null",
                (space_id,),
            ).fetchone() == (1,), "the Business stays with its custodian"
    finally:
        release_custodian(space_id)
        with psycopg.connect(DSN) as connection:
            connection.execute(
                "delete from argus_private.account_deletion_runs where user_id = %s",
                (ana,),
            )
            connection.execute("delete from auth.users where id = %s", (ana,))


# Storage. Buckets no client may reach, and every storage.objects policy; an
# empty policy list means only the service role reads or writes any object.

PRIVATE_BUCKETS = frozenset({"financial-document-sources", "profile-images"})
STORAGE_OBJECT_POLICIES: frozenset[str] = frozenset()


def test_private_buckets_exist_and_are_not_public(catalog) -> None:
    catalog.execute(
        "select id, public from storage.buckets where id = any(%s)",
        (list(PRIVATE_BUCKETS),),
    )
    assert dict(catalog.fetchall()) == dict.fromkeys(PRIVATE_BUCKETS, False)


def test_storage_object_policies_match_the_allow_list(catalog) -> None:
    catalog.execute(
        "select policyname from pg_policies"
        " where schemaname = 'storage' and tablename = 'objects'"
    )
    assert {row[0] for row in catalog.fetchall()} == STORAGE_OBJECT_POLICIES


@pytest.mark.parametrize("role", CLIENT_ROLES)
def test_client_roles_cannot_see_their_own_private_objects(owned_rows, role) -> None:
    connection, ids = owned_rows
    name = f"{ids['user_id']}/{uuid4()}/{'a' * 64}"
    with connection.cursor() as cursor:
        with connection.transaction():
            cursor.execute(
                "insert into storage.objects (bucket_id, name, owner_id)"
                " values ('financial-document-sources', %s, %s)",
                (name, ids["user_id"]),
            )
            _act_as(cursor, role, user_id=ids["user_id"])
            cursor.execute(
                "select count(*) from storage.objects where name = %s", (name,)
            )
            assert cursor.fetchone() == (0,)


def test_service_role_cannot_rewrite_address_events(catalog) -> None:
    catalog.execute(
        "select has_table_privilege('service_role',"
        " 'public.business_email_address_events', 'SELECT'),"
        " has_table_privilege('service_role',"
        " 'public.business_email_address_events', 'INSERT'),"
        " has_table_privilege('service_role',"
        " 'public.business_email_address_events', 'UPDATE'),"
        " has_table_privilege('service_role',"
        " 'public.business_email_address_events', 'DELETE')"
    )
    assert catalog.fetchone() == (True, True, False, False)
    with psycopg.connect(DSN) as connection:
        with connection.cursor() as cursor:
            for statement in (
                "update public.business_email_address_events set event_type = event_type",
                "delete from public.business_email_address_events",
            ):
                with pytest.raises(psycopg.errors.InsufficientPrivilege):
                    with connection.transaction():
                        _act_as(cursor, "service_role")
                        cursor.execute(statement)
