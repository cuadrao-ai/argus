"""Deletion-only Business custody movement, after verified object preparation."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from psycopg import sql
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool
from pydantic import TypeAdapter

from argus.domain.business.contracts.actions import Command, canonical_input_hash
from argus.domain.business.custody_objects import CustodyReservation


class CustodyGraphError(RuntimeError):
    pass


#: The name every departure rewrite stores over an erased member's rows; SQL
#: business_custody_identity_json holds the same literal.
ERASED_NAME = "Exmiembro"


@dataclass(frozen=True)
class CustodyMoveResult:
    space_id: str
    custodian_id: str
    moved: bool


# Each selector derives from the locked roots, never from all rows owned by U.
FAMILIES = {
    "financial_accounts": "owner_space_id=%(s)s",
    "financial_source_connections": "owner_space_id=%(s)s",
    "financial_import_events": "owner_space_id=%(s)s",
    "financial_records": "id=any(%(records)s)",
    "financial_record_revisions": "record_id=any(%(records)s)",
    "financial_activity_groups": "id=any(%(activities)s)",
    "financial_activity_revisions": "activity_id=any(%(activities)s)",
    "financial_activity_memberships": "activity_id=any(%(activities)s)",
    "financial_activity_receipts": "activity_id=any(%(activities)s)",
    "financial_operation_receipts": "record_id=any(%(records)s)",
    "financial_observation_coverage": "account_id=any(%(accounts)s)",
    "financial_asset_details": "account_id=any(%(accounts)s)",
    "financial_asset_changes": "account_id=any(%(accounts)s)",
    "financial_account_idempotency": "account_id=any(%(accounts)s)",
    "financial_import_account_links": "connection_id=any(%(connections)s) or account_id=any(%(accounts)s)",
    "financial_document_extractions": "connection_id=any(%(connections)s)",
    "financial_import_observations": "event_id=any(%(events)s) or connection_id=any(%(connections)s)",
    "conversations": "owner_space_id=%(s)s",
    "messages": "conversation_id=any(%(conversations)s)",
    "chat_turn_lifecycles": "conversation_id=any(%(conversations)s)",
    "conversation_read_states": "conversation_id=any(%(conversations)s)",
    "business_fiscal_operations": "space_id=%(s)s",
    "business_fiscal_observations": "space_id=%(s)s",
    "business_sources": "space_id=%(s)s",
    "business_draft_revisions": "space_id=%(s)s",
    "business_draft_sources": "space_id=%(s)s",
    "business_questions": "space_id=%(s)s",
    "business_turns": "space_id=%(s)s",
    "business_action_receipts": "space_id=%(s)s",
    "business_client_grants": "space_id=%(s)s",
    "business_access_invites": "space_id=%(s)s",
    "business_receipt_reading_consents": "space_id=%(s)s",
    "business_receipt_consent_commands": "space_id=%(s)s",
    "business_ai_consents": "space_id=%(s)s",
    "business_lifecycle_commands": "space_id=%(s)s",
    "business_ownership_transfers": "space_id=%(s)s",
    "whatsapp_sender_links": "destination_space_id=%(s)s",
    "business_whatsapp_ai_consents": "space_id=%(s)s",
    "business_document_settlements": "space_id=%(s)s",
}

ACTOR_KEYS = {
    "recipient_id",
    "actor_id",
    "issuer_id",
    "consenting_actor_id",
    "revoked_by",
}
CUSTODY_KEYS = {
    "user_id",
    "owner_id",
    "record_owner_id",
    "reversal_of_owner_id",
    "activity_owner_id",
    "account_owner_id",
    "goal_owner_id",
    "destination_owner_id",
}


def _identity(value: Any, old: str, custodian: str, actor: str) -> Any:
    """Rewrite typed identity fields; source text and durable IDs are untouched."""
    if isinstance(value, list):
        return [_identity(v, old, custodian, actor) for v in value]
    if not isinstance(value, dict):
        return value
    result = {k: _identity(v, old, custodian, actor) for k, v in value.items()}
    for key in ACTOR_KEYS:
        if value.get(key) == old:
            result[key] = actor
    for key in CUSTODY_KEYS:
        if value.get(key) == old:
            result[key] = custodian
    if value.get("actor_id") == old and "display_name" in value:
        result["display_name"] = ERASED_NAME
    if value.get("issuer_id") == old and "issuer_display_name" in value:
        result["issuer_display_name"] = ERASED_NAME
    return result


def _hash(command: dict[str, Any]) -> str:
    return canonical_input_hash(TypeAdapter(Command).validate_python(command))


def retained_dependencies(connection: Any, departing_user_id: str) -> tuple[str, ...]:
    """Deletion must stop before Storage/Auth erase while any Business depends on U."""
    dependencies = []
    for table, predicate in (
        ("spaces", "kind='business' and (created_by=%s or current_owner_id=%s)"),
        ("business_client_grants", "issuer_id=%s or grantee_id=%s"),
        ("business_access_invites", "issuer_id=%s or recipient_id=%s"),
        ("business_turns", "actor_id=%s"),
        ("business_action_receipts", "actor_id=%s"),
        ("business_receipt_reading_consents", "owner_id=%s"),
        ("business_receipt_consent_commands", "owner_id=%s"),
        (
            "business_ai_consents",
            "owner_id=%s or consenting_actor_id=%s or issuer_id=%s or revoked_by=%s",
        ),
        ("business_close_mail_outbox", "owner_id=%s or recipient_id=%s"),
        ("business_lifecycle_commands", "owner_id=%s"),
        ("business_ownership_transfers", "owner_id=%s or target_id=%s"),
        (
            "business_transfer_mail_outbox",
            "owner_id=%s or target_id=%s or recipient_id=%s",
        ),
    ):
        if connection.execute(
            sql.SQL("select exists(select 1 from public.{} where ").format(
                sql.Identifier(table)
            )
            + sql.SQL(predicate)
            + sql.SQL(")"),
            (departing_user_id,) * predicate.count("%s"),
        ).fetchone()[0]:
            dependencies.append(table)
    for table in (
        "financial_accounts",
        "financial_source_connections",
        "financial_import_events",
        "financial_records",
        "conversations",
    ):
        if connection.execute(
            sql.SQL(
                "select exists(select 1 from public.{} where owner_space_id is not null and user_id=%s)"
            ).format(sql.Identifier(table)),
            (departing_user_id,),
        ).fetchone()[0]:
            dependencies.append(table)
    spaces = connection.execute(
        "select id::text from public.spaces where kind='business' order by id"
    ).fetchall()
    for (space,) in spaces:
        scope = PostgresBusinessCustodyGraph._scope(
            connection, space, departing_user_id, lock=False
        )
        for table, predicate in FAMILIES.items():
            for name in (
                "records",
                "activities",
                "accounts",
                "connections",
                "events",
                "conversations",
            ):
                predicate = predicate.replace(
                    f"any(%({name})s)", f"any(%({name})s::uuid[])"
                )
            rows = connection.execute(
                sql.SQL("select to_jsonb(t) from public.{} t where ").format(
                    sql.Identifier(table)
                )
                + sql.SQL(predicate),
                scope,
            ).fetchall()
            for (row,) in rows:
                if (
                    _identity(row, departing_user_id, "custody", "actor") != row
                    or any(
                        row.get(k) == departing_user_id
                        for k in ("recorded_by", "target_id", "historical_issuer_id")
                    )
                    or row.get("source_key", "").startswith(f"web:{departing_user_id}:")
                    or any(
                        f"/{departing_user_id}/" in (row.get(k) or "")
                        or (row.get(k) or "").startswith(f"{departing_user_id}/")
                        for k in ("source_path", "rebuilt_path")
                    )
                ):
                    dependencies.append(table)
                    break
    return tuple(sorted(set(dependencies)))


class PostgresBusinessCustodyGraph:
    def __init__(self, pool: ConnectionPool) -> None:
        self.pool = pool

    def detach(
        self,
        *,
        space_id: str,
        departing_user_id: str,
        reservation: CustodyReservation,
        deletion_run_id: str,
        claim_id: str,
    ) -> CustodyMoveResult:
        with self.pool.connection() as db, db.transaction():
            db.execute("set local lock_timeout='5s'; set local statement_timeout='60s'")
            self._claim(db, departing_user_id, deletion_run_id, claim_id)
            space = db.execute(
                "select created_by::text,current_owner_id::text,closed_at from public.spaces where id=%s and kind='business' for update",
                (space_id,),
            ).fetchone()
            saved = db.execute(
                "select custodian_id::text,deleted_actor_id::text,moved_at from argus_private.business_custody_reservations where space_id=%s for update",
                (space_id,),
            ).fetchone()
            if (
                reservation.space_id != space_id
                or not saved
                or saved[:2] != (reservation.custodian_id, reservation.deleted_actor_id)
            ):
                raise CustodyGraphError("business_custody_reservation_mismatch")
            if not space or space[0] not in (departing_user_id, reservation.custodian_id):
                raise CustodyGraphError("business_custody_scope_mismatch")
            if space[0] == reservation.custodian_id:
                if saved[2] is None:
                    raise CustodyGraphError("business_custody_incomplete")
                return CustodyMoveResult(space_id, reservation.custodian_id, False)
            if space[1] == departing_user_id and space[2] is None:
                raise CustodyGraphError("business_owner_must_exit")
            if not db.execute(
                "select u.id from auth.users u join argus_private.account_placeholders p on p.id=u.id where u.id=%s and not coalesce(u.is_anonymous,false) and u.email_confirmed_at is not null and u.banned_until>clock_timestamp() and u.raw_app_meta_data->>'placeholder'='true' and u.email like 'exmiembro+%%@cuadrao.invalid' and u.phone is null and coalesce(u.encrypted_password,'')='' for share of u,p",
                (reservation.custodian_id,),
            ).fetchone():
                raise CustodyGraphError("business_custody_placeholder_invalid")
            db.execute(
                "update public.business_access_invites set revoked_at=clock_timestamp() where space_id=%s and (recipient_id=%s or issuer_id=%s) and accepted_at is null and revoked_at is null",
                (space_id, departing_user_id, departing_user_id),
            )
            db.execute(
                "delete from public.business_client_grants where space_id=%s and grantee_id=%s",
                (space_id, departing_user_id),
            )
            scope = self._scope(db, space_id, departing_user_id)
            graph = self._lock_graph(db, scope, departing_user_id)
            copies = self._copies(db, space_id, graph)
            db.execute(
                "insert into argus_private.business_custody_moves(space_id,departing_user_id,deletion_run_id,claim_id) values(%s,%s,%s,%s) on conflict(space_id) do update set claim_id=excluded.claim_id where business_custody_moves.departing_user_id=excluded.departing_user_id and business_custody_moves.deletion_run_id=excluded.deletion_run_id",
                (space_id, departing_user_id, deletion_run_id, claim_id),
            )
            deletion_at = db.execute(
                "select to_jsonb(started_at)#>>'{}' from argus_private.business_custody_moves where space_id=%s",
                (space_id,),
            ).fetchone()[0]
            db.execute(
                "select set_config('argus.business_custody_space',%s,true)", (space_id,)
            )
            db.execute("select set_config('argus.locked_history_writer','deletion',true)")
            keys = db.execute(
                "select constraint_name from argus_private.business_custody_deferred_keys"
            ).fetchall()
            db.execute(
                sql.SQL("set constraints {} deferred").format(
                    sql.SQL(",").join(sql.Identifier(k[0]) for k in keys)
                )
            )
            # A minimal nameless profile is required by existing Business chat keys.
            db.execute(
                "insert into public.profiles(id,email,username) select id,email,%s from auth.users where id=%s on conflict(id) do nothing",
                ("exmiembro-" + reservation.custodian_id[:8], reservation.custodian_id),
            )
            self._remove_transport(db, scope, departing_user_id)
            for table, rows in graph.items():
                for tid, old in rows:
                    if (
                        table == "business_client_grants"
                        and old["grantee_id"] == departing_user_id
                    ):
                        continue
                    new = self._rewrite(
                        table,
                        old,
                        departing_user_id,
                        reservation,
                        space[1],
                        copies,
                        deletion_at,
                    )
                    self._update(db, table, tid, old, new, space_id)
            if db.execute(
                "select 1 from public.business_action_receipts r join public.business_turns t on t.turn_key=r.turn_key where r.space_id=%s and (r.actor_id<>t.actor_id or r.actor is distinct from t.plan_actor or r.command is distinct from t.plan->'actions'->r.action_index) limit 1",
                (space_id,),
            ).fetchone():
                raise CustodyGraphError("business_custody_plan_mismatch")
            old = db.execute(
                "select ctid::text,to_jsonb(s) from public.spaces s where id=%s",
                (space_id,),
            ).fetchone()
            new = dict(old[1], created_by=reservation.custodian_id)
            if space[1] == departing_user_id:
                new["current_owner_id"] = None
            self._update(db, "spaces", old[0], old[1], new, space_id)
            db.execute("set constraints all immediate")
            db.execute(
                "update argus_private.business_custody_reservations set moved_at=clock_timestamp() where space_id=%s",
                (space_id,),
            )
            db.execute(
                "delete from argus_private.business_custody_changes where space_id=%s",
                (space_id,),
            )
            return CustodyMoveResult(space_id, reservation.custodian_id, True)

    @staticmethod
    def _claim(db: Any, user: str, run: str, claim: str) -> None:
        if (
            db.execute(
                "select 1 from argus_private.account_deletion_runs where id=%s and user_id=%s and claim_id=%s and status<>'done' and claimed_until>clock_timestamp() for update",
                (run, user, claim),
            ).fetchone()
            is None
        ):
            raise CustodyGraphError("business_custody_claim_lost")

    @staticmethod
    def _scope(db: Any, space: str, user: str, *, lock: bool = True) -> dict[str, Any]:
        def ids(table: str, predicate: str, params: tuple[Any, ...]) -> list[str]:
            return [
                r[0]
                for r in db.execute(
                    sql.SQL("select id::text from public.{} where ").format(
                        sql.Identifier(table)
                    )
                    + sql.SQL(predicate)
                    + sql.SQL(" order by id for update" if lock else " order by id"),
                    params,
                )
            ]

        scope = {"s": space}
        for table, name in (
            ("financial_accounts", "accounts"),
            ("financial_source_connections", "connections"),
            ("financial_import_events", "events"),
            ("conversations", "conversations"),
        ):
            scope[name] = ids(table, "owner_space_id=%s", (space,))
        scope["records"] = ids(
            "financial_records",
            "account_id=any(%s::uuid[]) or owner_space_id=%s",
            (scope["accounts"], space),
        )
        scope["activities"] = [
            r[0]
            for r in db.execute(
                "select distinct activity_id::text from public.financial_activity_memberships where record_id=any(%s::uuid[]) union select activity_id::text from public.financial_import_events where id=any(%s::uuid[]) and activity_id is not null union select purchase_activity_id::text from public.financial_record_revisions where record_id=any(%s::uuid[]) and purchase_activity_id is not null union select reversal_of_activity_id::text from public.financial_record_revisions where record_id=any(%s::uuid[]) and reversal_of_activity_id is not null",
                (scope["records"], scope["events"], scope["records"], scope["records"]),
            )
        ]
        if not lock:
            return scope
        for table, column, values in (
            ("household_account_grants", "account_id", scope["accounts"]),
            ("financial_goal_allocations", "account_id", scope["accounts"]),
            ("financial_goal_allocation_revisions", "account_id", scope["accounts"]),
            ("financial_plan_links", "activity_id", scope["activities"]),
            ("household_plan_archived_activities", "activity_id", scope["activities"]),
            ("household_plan_archived_claims", "activity_id", scope["activities"]),
        ):
            if db.execute(
                sql.SQL(
                    "select exists(select 1 from public.{} where {}=any(%s::uuid[]))"
                ).format(sql.Identifier(table), sql.Identifier(column)),
                (values,),
            ).fetchone()[0]:
                raise CustodyGraphError("business_custody_cross_scope_link")
        return scope

    @staticmethod
    def _lock_graph(db: Any, scope: dict[str, Any], user: str) -> dict[str, list[Any]]:
        graph = {}
        # UUID arrays need explicit casts even when the scoped set is empty.
        for table, predicate in FAMILIES.items():
            for name in (
                "records",
                "activities",
                "accounts",
                "connections",
                "events",
                "conversations",
            ):
                predicate = predicate.replace(
                    f"any(%({name})s)", f"any(%({name})s::uuid[])"
                )
            rows = db.execute(
                sql.SQL("select ctid::text,to_jsonb(t) from public.{} t where ").format(
                    sql.Identifier(table)
                )
                + sql.SQL(predicate)
                + sql.SQL(" order by ctid for update"),
                scope,
            ).fetchall()
            for _, row in rows:
                if "user_id" in row and row["user_id"] != user:
                    raise CustodyGraphError("business_custody_cross_scope_owner")
                for field, name in (
                    ("record_id", "records"),
                    ("record_owner_id", None),
                    ("related_debt_account_id", "accounts"),
                    ("previous_debt_account_id", "accounts"),
                    ("connection_id", "connections"),
                    ("event_id", "events"),
                    ("account_id", "accounts"),
                ):
                    value = row.get(field)
                    if value is not None and (
                        (name and value not in scope[name])
                        or (field == "record_owner_id" and value != user)
                    ):
                        raise CustodyGraphError("business_custody_cross_scope_link")
            graph[table] = rows
        return graph

    @staticmethod
    def _copies(db: Any, space: str, graph: dict[str, list[Any]]) -> dict[str, str]:
        copies = {}
        custodian = db.execute(
            "select custodian_id::text from argus_private.business_custody_reservations where space_id=%s",
            (space,),
        ).fetchone()[0]
        for _, row in graph["financial_document_extractions"]:
            if row["source_bytes"] is not None:
                if hashlib.sha256(
                    bytes.fromhex(row["source_bytes"][2:])
                ).hexdigest() != row["draft"].get("sha256"):
                    raise CustodyGraphError("business_source_integrity_failed")
            for prefix in ("source", "rebuilt"):
                path = row[f"{prefix}_path"]
                if path is None:
                    continue
                saved = db.execute(
                    "select destination_path from argus_private.business_custody_objects where space_id=%s and source_path=%s and sha256=%s and size_bytes=%s and media_type=%s and verified_at is not null for share",
                    (
                        space,
                        path,
                        row[f"{prefix}_sha256"],
                        row[f"{prefix}_size_bytes"],
                        row[f"{prefix}_media_type"],
                    ),
                ).fetchone()
                kind = "sealed" if prefix == "source" else "rebuilt"
                expected = f"{kind}/{custodian}/{row['draft']['sha256']}"
                if (
                    not saved
                    or saved[0] != expected
                    or row[f"{prefix}_bucket"] != "financial-document-sources"
                ):
                    raise CustodyGraphError("business_custody_copy_unverified")
                copies[path] = saved[0]
        return copies

    @staticmethod
    def _rewrite(
        table: str,
        old: dict[str, Any],
        user: str,
        reservation: CustodyReservation,
        owner: str | None,
        copies: dict[str, str],
        deletion_at: str,
    ) -> dict[str, Any]:
        p, a = reservation.custodian_id, reservation.deleted_actor_id
        new = _identity(old, user, p, a)
        if table in (
            "business_receipt_reading_consents",
            "business_receipt_consent_commands",
            "business_ai_consents",
            "business_lifecycle_commands",
            "business_ownership_transfers",
        ):
            for key in ("owner_id", "target_id"):
                if old.get(key) == user:
                    new[key] = a
        if table == "financial_record_revisions" and old.get("recorded_by") == user:
            new["recorded_by"] = None
        if table == "financial_asset_changes" and old.get("recorded_by") == user:
            new["recorded_by"] = a
        if table == "business_turns" and old.get("actor_id") == user:
            new["sender_hash"] = hashlib.sha256(a.encode()).hexdigest()
        if table == "financial_document_extractions":
            for key in ("source_path", "rebuilt_path"):
                if old[key] is not None:
                    new[key] = copies[old[key]]
            # A departed person's pending provider job has no surviving authority.
            new["preparation_job"] = None
        if table == "financial_source_connections":
            for key in (
                "secret_ciphertext",
                "secret_key_fingerprint",
                "sync_cursor",
                "lease_holder",
                "lease_until",
            ):
                new[key] = None
            new["external_ref"] = "retained:" + old["id"]
        if (
            table
            in (
                "business_receipt_reading_consents",
                "business_ai_consents",
                "business_whatsapp_ai_consents",
            )
            and old.get("owner_id") == user
            and old.get("revoked_at") is None
        ):
            new["revoked_at"] = deletion_at
            if table in ("business_ai_consents", "business_whatsapp_ai_consents"):
                new["revoked_by"] = a
        if table == "whatsapp_sender_links":
            new.update(
                wa_id_hash="\\x" + hashlib.sha256(a.encode()).hexdigest(),
                last4="0000",
                status="revoked",
                revoked_at=old["revoked_at"] or deletion_at,
            )
        if table == "business_whatsapp_ai_consents":
            new["sender_hash"] = "\\x" + hashlib.sha256(a.encode()).hexdigest()
        if (
            table in ("business_client_grants", "business_access_invites")
            and old.get("issuer_id") == user
        ):
            new["issuer_id"] = owner if owner and owner != user else p
            new["historical_issuer_id"] = a
        if table == "business_sources" and old.get("source_key", "").startswith(
            f"web:{user}:"
        ):
            new["source_key"] = f"web:{a}:" + old["source_key"].split(":", 2)[2]
        if table == "business_action_receipts" and new["command"] != old["command"]:
            new["input_hash"] = _hash(new["command"])
        return new

    @staticmethod
    def _update(
        db: Any,
        table: str,
        tid: str,
        old: dict[str, Any],
        new: dict[str, Any],
        space: str,
    ) -> None:
        changes = [key for key in new if new[key] != old.get(key)]
        if not changes:
            return
        # Generated financial owner references derive from the rewritten details.
        changes = [key for key in changes if key != "reversal_of_owner_id"]
        db.execute(
            "insert into argus_private.business_custody_changes(space_id,table_name,old_row,new_row) values(%s,%s,%s,%s)",
            (space, table, Jsonb(old), Jsonb(new)),
        )
        columns = sql.SQL(",").join(map(sql.Identifier, changes))
        db.execute(
            sql.SQL(
                "update public.{table} set ({columns})=(select {columns} from jsonb_populate_record(null::public.{table},%s)) where ctid=%s::tid"
            ).format(table=sql.Identifier(table), columns=columns),
            (Jsonb(new), tid),
        )

    @staticmethod
    def _remove_transport(db: Any, scope: dict[str, Any], user: str) -> None:
        db.execute(
            "delete from public.business_close_mail_outbox where space_id=%s or owner_id=%s or recipient_id=%s",
            (scope["s"], user, user),
        )
        db.execute(
            "delete from public.business_transfer_mail_outbox where transfer_id in"
            " (select id from public.business_ownership_transfers where space_id=%s)",
            (scope["s"],),
        )
        for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
            db.execute(
                sql.SQL("delete from public.{} where thread_id=any(%s)").format(
                    sql.Identifier(table)
                ),
                (scope["conversations"],),
            )
        # Canonical sources/documents were locked first. Transport is not retained authority.
        db.execute(
            "delete from public.business_email_deliveries where space_id=%s",
            (scope["s"],),
        )
        db.execute(
            "delete from public.business_email_routes where space_id=%s", (scope["s"],)
        )
        db.execute(
            "delete from public.whatsapp_inbound_messages where destination_space_id=%s or connection_id=any(%s::uuid[])",
            (scope["s"], scope["connections"]),
        )
        for table in ("whatsapp_reply_attempts", "whatsapp_reply_groups"):
            db.execute(
                sql.SQL(
                    "delete from public.{} where link_id in (select id from public.whatsapp_sender_links where destination_space_id=%s)"
                ).format(sql.Identifier(table)),
                (scope["s"],),
            )
        db.execute(
            "delete from public.whatsapp_reply_days d where sender_hash in (select wa_id_hash from public.whatsapp_sender_links where destination_space_id=%s) and not exists(select 1 from public.whatsapp_reply_attempts a where a.sender_hash=d.sender_hash and a.day=d.day)",
            (scope["s"],),
        )
        for table in (
            "financial_source_gmail_senders",
            "financial_shortcut_device_tokens",
        ):
            db.execute(
                sql.SQL(
                    "delete from public.{} where connection_id=any(%s::uuid[])"
                ).format(sql.Identifier(table)),
                (scope["connections"],),
            )
        db.execute(
            "delete from public.business_receipt_read_states where space_id=%s and person_id=%s",
            (scope["s"], user),
        )
        db.execute(
            "delete from public.business_sender_leases where space_id=%s", (scope["s"],)
        )

    def complete_identity_cleanup(
        self, *, space_id: str, deletion_run_id: str, claim_id: str
    ) -> None:
        with self.pool.connection() as db, db.transaction():
            db.execute("set local lock_timeout='5s'; set local statement_timeout='60s'")
            move = db.execute(
                "select departing_user_id::text from argus_private.business_custody_moves where space_id=%s and deletion_run_id=%s for update",
                (space_id, deletion_run_id),
            ).fetchone()
            if not move:
                raise CustodyGraphError("business_custody_move_missing")
            run = db.execute(
                "select 1 from argus_private.account_deletion_runs where id=%s and claim_id=%s and claimed_until>clock_timestamp() for update",
                (deletion_run_id, claim_id),
            ).fetchone()
            if not run:
                raise CustodyGraphError("business_custody_claim_lost")
            if (
                move[0] is not None
                and db.execute(
                    "select 1 from auth.users where id=%s", (move[0],)
                ).fetchone()
            ):
                raise CustodyGraphError("business_custody_auth_not_deleted")
            if move[0] is not None and retained_dependencies(db, move[0]):
                raise CustodyGraphError("business_custody_retained_dependency")
            db.execute(
                "update argus_private.business_custody_objects set source_path=null where space_id=%s",
                (space_id,),
            )
            db.execute(
                "update argus_private.business_custody_moves set departing_user_id=null,claim_id=null,identity_cleaned_at=coalesce(identity_cleaned_at,clock_timestamp()) where space_id=%s",
                (space_id,),
            )
