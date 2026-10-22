"""Remove a departing member without attributing their history to another person."""

from __future__ import annotations

import hashlib
from typing import Any
from uuid import uuid4

from psycopg import sql

from argus.domain.business.custody_graph import (
    FAMILIES,
    PostgresBusinessCustodyGraph,
    _hash,
    _identity,
)


def anonymous_history(table: str, old: dict, user: str, alias: str, issuer: str) -> dict:
    new = _identity(old, user, user, alias)
    for key in ("owner_id", "target_id", "historical_issuer_id"):
        if old.get(key) == user:
            new[key] = alias
    if table in ("business_client_grants", "business_access_invites"):
        if old.get("issuer_id") == user:
            new.update(issuer_id=issuer, historical_issuer_id=alias)
    if table == "business_turns" and old.get("actor_id") == user:
        new["sender_hash"] = hashlib.sha256(alias.encode()).hexdigest()
    if table == "business_sources" and old.get("source_key", "").startswith(
        f"web:{user}:"
    ):
        new["source_key"] = f"web:{alias}:" + old["source_key"].split(":", 2)[2]
    if table == "business_action_receipts" and new["command"] != old["command"]:
        new["input_hash"] = _hash(new["command"])
    return new


class PostgresBusinessDepartures:
    def __init__(self, connections: Any):
        self.connections = connections

    def detach(self, *, user_id: str, run_id: str, claim_id: str) -> None:
        with self.connections.connection() as db, db.transaction():
            db.execute("set local lock_timeout='5s'; set local statement_timeout='60s'")
            PostgresBusinessCustodyGraph._claim(db, user_id, run_id, claim_id)
            db.execute(
                "delete from public.business_transfer_mail_outbox where recipient_id=%s or owner_id=%s or target_id=%s",
                (user_id, user_id, user_id),
            )
            db.execute(
                "delete from public.business_close_mail_outbox where recipient_id=%s or owner_id=%s",
                (user_id, user_id),
            )
            spaces = db.execute(
                "select id::text,created_by::text,current_owner_id::text from public.spaces where kind='business' and created_by<>%s order by id for update",
                (user_id,),
            ).fetchall()
            for space, custodian, owner in spaces:
                if owner == user_id:
                    db.execute(
                        "update public.spaces set current_owner_id=null where id=%s and closed_at is not null",
                        (space,),
                    )
                    owner = None
                db.execute(
                    "delete from public.business_client_grants where space_id=%s and grantee_id=%s",
                    (space, user_id),
                )
                db.execute(
                    "delete from public.business_receipt_read_states where space_id=%s and person_id=%s",
                    (space, user_id),
                )
                db.execute(
                    "update public.business_ownership_transfers set status='cancelled',resolved_at=clock_timestamp() where space_id=%s and status='pending' and (owner_id=%s or target_id=%s)",
                    (space, user_id, user_id),
                )
                alias = str(uuid4())
                changes = []
                for table, predicate in FAMILIES.items():
                    if not table.startswith("business_") or "space_id=%(s)s" != predicate:
                        continue
                    rows = db.execute(
                        sql.SQL(
                            "select ctid::text,to_jsonb(t) from public.{} t where space_id=%s order by ctid for update"
                        ).format(sql.Identifier(table)),
                        (space,),
                    ).fetchall()
                    for tid, old in rows:
                        new = anonymous_history(
                            table, old, user_id, alias, owner or custodian
                        )
                        if new != old:
                            changes.append((table, tid, old, new))
                if not changes:
                    continue
                db.execute(
                    "insert into argus_private.business_departure_aliases(space_id,actor_id,departing_user_id,deletion_run_id,claim_id) values(%s,%s,%s,%s,%s)",
                    (space, alias, user_id, run_id, claim_id),
                )
                db.execute(
                    "select set_config('argus.business_departure_actor',%s,true)",
                    (alias,),
                )
                db.execute(
                    "set constraints business_action_receipts_turn_key_space_id_actor_id_fkey deferred"
                )
                for table, tid, old, new in changes:
                    PostgresBusinessCustodyGraph._update(db, table, tid, old, new, space)
                db.execute("set constraints all immediate")
                db.execute(
                    "delete from argus_private.business_custody_changes where space_id=%s",
                    (space,),
                )

    def complete(self, *, user_id: str, run_id: str, claim_id: str) -> None:
        with self.connections.connection() as db, db.transaction():
            PostgresBusinessCustodyGraph._claim(db, user_id, run_id, claim_id)
            if db.execute("select 1 from auth.users where id=%s", (user_id,)).fetchone():
                raise RuntimeError("business_custody_auth_not_deleted")
            db.execute(
                "update argus_private.business_departure_aliases set departing_user_id=null,claim_id=null,identity_cleaned_at=coalesce(identity_cleaned_at,clock_timestamp()) where deletion_run_id=%s",
                (run_id,),
            )
