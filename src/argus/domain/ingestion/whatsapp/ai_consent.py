from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from typing import Any, Literal
from uuid import UUID

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import Field

from argus.domain.business.authority import ActionError, authorize
from argus.domain.business.contracts.authority import TrustedActor
from argus.domain.business.contracts.facts import Contract
from argus.domain.ingestion.whatsapp.business_store import BusinessTurnStore

SCOPE_VERSION = 1
PURPOSE = "business_whatsapp_draft_assistance"
DISCLOSURE = (
    "Allow AI assistance for this Business's linked WhatsApp number: send your "
    "message text and necessary authorized draft context through the disclosed "
    "provider routes to understand, clarify and prepare drafts. You can revoke "
    "this permission. Recording an expense still requires separate human approval."
)


class EnableAIConsent(Contract):
    action: Literal["enable"]
    disclosure_token: str = Field(pattern=r"^[0-9a-f]{64}$")


class ConsentError(PermissionError):
    def __init__(self, code: str, status: int = 403) -> None:
        self.code, self.status = code, status
        super().__init__(code)


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()


class AIConsentStore:
    def __init__(self, pool, route: Callable[[], dict[str, Any]]) -> None:
        self.pool, self.route = pool, route

    def _route(self) -> dict[str, Any]:
        try:
            route = self.route()
        except ValueError as error:
            raise ConsentError("whatsapp_ai_route_unavailable", 503) from error
        if not route:
            raise ConsentError("whatsapp_ai_route_unavailable", 503)
        return route

    def _link(self, connection, owner_id: UUID, *, prepare: bool):
        row = connection.execute(
            "select l.id,l.destination_space_id,l.destination_owner_id,l.wa_id_hash,l.last4"
            " from public.whatsapp_sender_links l join public.spaces s"
            " on s.id=l.destination_space_id and s.created_by=l.destination_owner_id"
            " where l.destination_owner_id=%s and l.status='active'"
            " and s.kind='business' and s.closed_at is null for update of l",
            (owner_id,),
        ).fetchone()
        if row is None:
            raise ConsentError("whatsapp_link_required", 409)
        auth = authorize(
            connection,
            TrustedActor(actor_id=owner_id, space_id=row[1], actor_kind="member"),
        )
        auth.require("prepare" if prepare else "read")
        return row, auth

    @staticmethod
    def _latest(connection, link_id):
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                "select * from public.business_whatsapp_ai_consents where sender_link_id=%s"
                " order by consented_at desc,id desc limit 1",
                (link_id,),
            )
            return cursor.fetchone()

    def _view(self, link, latest, route):
        token = digest(
            {
                "link": str(link[0]),
                "scope": SCOPE_VERSION,
                "disclosure": DISCLOSURE,
                "route": route,
                "previous": str(latest["id"]) if latest else None,
                "revoked": str(latest["revoked_at"]) if latest else None,
            }
        )
        return {
            "linked": True,
            "available": True,
            "reason": None,
            "last4": link[4],
            "scope_version": SCOPE_VERSION,
            "purpose": PURPOSE,
            "disclosure": DISCLOSURE,
            "route": route,
            "disclosure_token": token,
            "enabled": bool(
                latest
                and latest["revoked_at"] is None
                and self._matches_disclosure(latest, route)
            ),
            "consented_at": latest["consented_at"] if latest else None,
            "revoked_at": latest["revoked_at"] if latest else None,
        }

    @staticmethod
    def _matches_disclosure(row, route) -> bool:
        return (
            row["scope_version"] == SCOPE_VERSION
            and row["disclosure"] == DISCLOSURE
            and row["route_hash"] == digest(route)
        )

    def status(self, owner_id: UUID, unavailable_reason: str | None = None) -> dict:
        with self.pool.connection() as connection, connection.transaction():
            link = connection.execute(
                "select id,destination_space_id,destination_owner_id,wa_id_hash,last4"
                " from public.whatsapp_sender_links where destination_owner_id=%s and status='active'",
                (owner_id,),
            ).fetchone()
            if link is None:
                return {
                    "linked": False,
                    "available": False,
                    "reason": "whatsapp_link_required",
                    "last4": None,
                    "scope_version": SCOPE_VERSION,
                    "purpose": PURPOSE,
                    "disclosure": DISCLOSURE,
                    "route": None,
                    "disclosure_token": None,
                    "enabled": False,
                    "consented_at": None,
                    "revoked_at": None,
                }
            try:
                route = self._route()
            except ConsentError:
                route = None
                unavailable_reason = "whatsapp_ai_route_unavailable"
            latest = self._latest(connection, link[0])
            view = self._view(link, latest, route)
            view["enabled"] = view["enabled"] and self._valid_grant(connection, latest)
            owner = connection.execute(
                "select 1 from public.spaces where id=%s and created_by=%s"
                " and kind='business' and closed_at is null",
                (link[1], owner_id),
            ).fetchone()
            if owner is None:
                unavailable_reason = "business_unavailable"
            else:
                try:
                    authorize(
                        connection,
                        TrustedActor(
                            actor_id=owner_id, space_id=link[1], actor_kind="member"
                        ),
                    ).require("prepare")
                except ActionError:
                    unavailable_reason = "business_permission_denied"
            if unavailable_reason:
                view.update(
                    available=False, reason=unavailable_reason, disclosure_token=None
                )
            return view

    @staticmethod
    def _valid_grant(connection, row) -> bool:
        try:
            auth = authorize(
                connection,
                TrustedActor(
                    actor_id=row["owner_id"],
                    space_id=row["space_id"],
                    actor_kind="member",
                ),
                row["grant_id"],
            )
            auth.require("prepare")
            return auth.provenance.issuer_id == row["issuer_id"]
        except ActionError:
            return False

    def enable(self, owner_id: UUID, request: EnableAIConsent, key: str) -> dict:
        if not 1 <= len(key) <= 80 or "\x00" in key:
            raise ConsentError("invalid_idempotency_key", 422)
        route = self._route()
        input_hash = digest(request.model_dump(mode="json"))
        with self.pool.connection() as connection, connection.transaction():
            link, auth = self._link(connection, owner_id, prepare=True)
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    "select * from public.business_whatsapp_ai_consents"
                    " where owner_id=%s and idempotency_key=%s",
                    (owner_id, key),
                )
                prior = cursor.fetchone()
            if prior:
                if (
                    prior["input_hash"] != input_hash
                    or prior["sender_link_id"] != link[0]
                ):
                    raise ConsentError("whatsapp_consent_idempotency_conflict", 409)
                if not self._valid_grant(connection, prior):
                    raise ConsentError("whatsapp_ai_consent_authority_changed")
                return self._view(link, prior, route)
            latest = self._latest(connection, link[0])
            view = self._view(link, latest, route)
            if request.disclosure_token != view["disclosure_token"]:
                raise ConsentError("whatsapp_consent_disclosure_stale", 409)
            if latest and latest["revoked_at"] is None:
                raise ConsentError("whatsapp_consent_already_enabled", 409)
            connection.execute(
                "insert into public.business_whatsapp_ai_consents"
                " (sender_link_id,space_id,owner_id,sender_hash,consenting_actor_id,grant_id,issuer_id,"
                " scope_version,purpose,disclosure,route,route_hash,idempotency_key,input_hash)"
                " values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    link[0],
                    link[1],
                    owner_id,
                    link[3],
                    owner_id,
                    auth.context.grant_id,
                    auth.provenance.issuer_id,
                    SCOPE_VERSION,
                    PURPOSE,
                    DISCLOSURE,
                    Jsonb(route),
                    digest(route),
                    key,
                    input_hash,
                ),
            )
            return self._view(link, self._latest(connection, link[0]), route)

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

    def capture_consent(self, connection, link_id: UUID) -> UUID | None:
        try:
            route = self._route()
        except ConsentError:
            return None
        row = self._latest(connection, link_id)
        if (
            row
            and row["revoked_at"] is None
            and self._matches_disclosure(row, route)
            and self._valid_grant(connection, row)
        ):
            return row["id"]
        return None

    def original_grant(self, captured) -> UUID | None:
        if captured.ai_consent_id is None:
            return None
        with self.pool.connection() as connection:
            row = connection.execute(
                "select grant_id from public.business_whatsapp_ai_consents"
                " where id=%s and sender_link_id=%s and owner_id=%s and space_id=%s",
                (
                    captured.ai_consent_id,
                    captured.link_id,
                    captured.owner_id,
                    captured.space_id,
                ),
            ).fetchone()
        return row[0] if row else None

    def require_access(self, captured, authorization, *, lease) -> None:
        if captured.ai_consent_id is None:
            raise ConsentError("whatsapp_ai_consent_required")
        if (
            authorization.actor.actor_id != captured.owner_id
            or authorization.actor.space_id != captured.space_id
            or lease.space_id != captured.space_id
            or lease.sender_hash != captured.sender_hash.hex()
        ):
            raise ConsentError("whatsapp_ai_consent_authority_changed")
        route = self._route()
        with self.pool.connection() as connection, connection.transaction():
            BusinessTurnStore.require_lease(connection, lease)
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    "select c.* from public.business_whatsapp_ai_consents c"
                    " join public.whatsapp_sender_links l on l.id=c.sender_link_id"
                    " where c.id=%s and c.sender_link_id=%s and c.space_id=%s and c.owner_id=%s"
                    " and c.sender_hash=%s and c.revoked_at is null and l.status='active'"
                    " for share of c,l",
                    (
                        captured.ai_consent_id,
                        captured.link_id,
                        captured.space_id,
                        captured.owner_id,
                        captured.sender_hash,
                    ),
                )
                row = cursor.fetchone()
            if row is None or not self._matches_disclosure(row, route):
                raise ConsentError("whatsapp_ai_consent_required")
            auth = authorize(connection, authorization.actor, authorization.grant_id)
            auth.require("prepare")
            if (
                str(auth.context.owner_id) != str(captured.owner_id)
                or auth.context.grant_id != row["grant_id"]
                or auth.provenance.issuer_id != row["issuer_id"]
            ):
                raise ConsentError("whatsapp_ai_consent_authority_changed")
            BusinessTurnStore.require_lease(connection, lease)
