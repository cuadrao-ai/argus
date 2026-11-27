from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from argus.domain.business.access import GrantedSpace
from argus.domain.business.authority import authorize
from argus.domain.business.contracts.authority import TrustedActor
from argus.domain.ingestion.whatsapp.senders import postgres_senders


@dataclass(frozen=True)
class ConsentScope:
    version: int
    purpose: str


RECEIPT_SCOPE = ConsentScope(2, "business_whatsapp_receipt_reading")

LINK_DISCLOSURES = {
    "es-419": (
        "Al vincular tu número, aceptas que la foto o el PDF que envíes se lea con IA "
        "para saber a qué negocio va."
    ),
    "en": (
        "By linking your number, you agree that the photo or PDF you send is read by AI "
        "to find which business it belongs to."
    ),
}


class ConsentError(PermissionError):
    def __init__(self, code: str, status: int = 403) -> None:
        self.code, self.status = code, status
        super().__init__(code)


def link_disclosure(person_id: str, language: str) -> tuple[str, str]:
    notice = LINK_DISCLOSURES[language]
    return notice, digest([person_id, RECEIPT_SCOPE.version, language, notice])


def accepted_link_disclosure(person_id: str, language: str, token: str) -> str:
    notice, current_token = link_disclosure(person_id, language)
    if token != current_token:
        raise ConsentError("whatsapp_consent_disclosure_stale", 409)
    return notice


def matches_link_disclosure(language: str, disclosure: str | None) -> bool:
    return disclosure is not None and disclosure == LINK_DISCLOSURES.get(language)


def require_link_disclosure(language: str, disclosure: str) -> None:
    if not matches_link_disclosure(language, disclosure):
        raise ConsentError("whatsapp_consent_disclosure_stale", 409)


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()


class AIConsentStore:
    def __init__(self, pool, route: Callable[[], dict[str, Any]]) -> None:
        self.pool, self.route = pool, route

    def status(self, owner_id: UUID, *, expected_link_id: str | None = None) -> dict:
        from argus.domain.ingestion.whatsapp.store_postgres import PostgresWhatsAppStore
        from argus.domain.postgres_connection import BorrowedConnection

        with self.pool.connection() as db, db.transaction():
            current = PostgresWhatsAppStore(BorrowedConnection(db)).destination_link(
                destination_owner_id=str(owner_id)
            )
            link = None
            if current and (expected_link_id is None or current.id == expected_link_id):
                if db.execute(
                    "select 1 from auth.users where id=%s and not coalesce(is_anonymous,false)",
                    (owner_id,),
                ).fetchone():
                    link = current
            latest = None
            route = None
            reason = "whatsapp_link_required"
            if link:
                with db.cursor(row_factory=dict_row) as cursor:
                    latest = cursor.execute(
                        "select scope_version,disclosure,route_hash,consented_at,revoked_at"
                        " from public.business_whatsapp_ai_consents where sender_link_id=%s"
                        " order by consented_at desc,id desc limit 1 for share",
                        (link.id,),
                    ).fetchone()
                try:
                    route = self.route()
                except ValueError:
                    route = None
                if not route:
                    reason = "whatsapp_ai_route_unavailable"
                elif not postgres_senders(db).eligible_businesses(str(owner_id)):
                    reason = "whatsapp_setup_required"
                else:
                    reason = None

            active = bool(latest and latest["revoked_at"] is None)
            return {
                "linked": link is not None,
                "available": reason is None,
                "reason": reason,
                "last4": link.last4 if link else None,
                "scope_version": RECEIPT_SCOPE.version,
                "purpose": RECEIPT_SCOPE.purpose,
                "active_scope_version": latest["scope_version"] if active else None,
                "disclosure": latest["disclosure"] if latest else None,
                "route": route,
                "enabled": bool(
                    reason is None and active
                    and latest["scope_version"] == RECEIPT_SCOPE.version
                    and matches_link_disclosure(link.reply_language, latest["disclosure"])
                    and latest["route_hash"] == digest(route)
                ),
                "consented_at": latest["consented_at"] if latest else None,
                "revoked_at": latest["revoked_at"] if latest else None,
            }

    def revoke(self, owner_id: UUID) -> None:
        with self.pool.connection() as connection, connection.transaction():
            connection.execute(
                "select id from public.whatsapp_sender_links where destination_owner_id=%s for update",
                (owner_id,),
            ).fetchall()
            connection.execute(
                "update public.business_whatsapp_ai_consents set revoked_at=clock_timestamp(),revoked_by=%s"
                " where owner_id=%s and revoked_at is null",
                (owner_id, owner_id),
            )


def record_link_consent(
    connection: Connection,
    *,
    grant: GrantedSpace,
    link_id: UUID,
    sender_hash: bytes,
    language: str,
    disclosure: str,
) -> None:
    """Write the notice accepted at issuance inside the new link's transaction."""
    from argus.domain.ingestion.whatsapp.receipt_consent import receipt_provider_route

    require_link_disclosure(language, disclosure)
    actor = TrustedActor(
        actor_id=UUID(grant.grantee_id),
        space_id=UUID(grant.space_id),
        actor_kind="member",
    )
    auth = authorize(connection, actor, UUID(grant.grant_id))
    auth.require("prepare")
    try:
        route = receipt_provider_route()
    except ValueError:
        # The Business can still have reading on during a routing outage.
        # Bind this notice to its last approved route. The status reader requires
        # an available, matching route before allowing any held-file read.
        row = connection.execute(
            "select route from public.business_receipt_reading_consents"
            " where space_id=%s and revoked_at is null",
            (grant.space_id,),
        ).fetchone()
        if row is None:
            raise ConsentError("whatsapp_ai_route_unavailable", 503) from None
        route = row[0]
    connection.execute(
        "insert into public.business_whatsapp_ai_consents"
        " (sender_link_id,space_id,owner_id,sender_hash,consenting_actor_id,grant_id,issuer_id,"
        " scope_version,purpose,disclosure,route,route_hash,idempotency_key,input_hash)"
        " values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            link_id,
            auth.context.actor.space_id,
            auth.context.actor.actor_id,
            sender_hash,
            auth.context.actor.actor_id,
            auth.context.grant_id,
            auth.provenance.issuer_id,
            RECEIPT_SCOPE.version,
            RECEIPT_SCOPE.purpose,
            disclosure,
            Jsonb(route),
            digest(route),
            str(link_id),
            digest([language, disclosure]),
        ),
    )
