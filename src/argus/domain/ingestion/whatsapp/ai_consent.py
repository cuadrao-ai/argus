from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import Field

from argus.domain.business.access import GrantedSpace
from argus.domain.business.authority import ActionError, Authorization, authorize
from argus.domain.business.contracts.authority import TrustedActor
from argus.domain.business.contracts.facts import Contract


@dataclass(frozen=True)
class ConsentScope:
    """What a permission covers. The text the owner was shown, in their language,
    is the one stored and hashed; a change to either text asks for consent again."""

    version: int
    purpose: str
    disclosure: str | None = None
    disclosure_es: str | None = None

    def text(self, language: str | None) -> str | None:
        spanish = bool(language) and language.lower().startswith("es")
        return self.disclosure_es if spanish and self.disclosure_es else self.disclosure

    def texts(self) -> tuple[str, ...]:
        return tuple(t for t in (self.disclosure, self.disclosure_es) if t)


# The link step supplies the text the person actually saw. A historical row
# retains its original text even after a different notice is approved.
RECEIPT_SCOPE = ConsentScope(2, "business_whatsapp_receipt_reading")


class EnableAIConsent(Contract):
    action: Literal["enable"]
    disclosure_token: str = Field(pattern=r"^[0-9a-f]{64}$")
    language: str | None = Field(default=None, max_length=16)


class ConsentError(PermissionError):
    def __init__(self, code: str, status: int = 403) -> None:
        self.code, self.status = code, status
        super().__init__(code)


# Fingerprints of the approved settings.whatsapp.consent_notice translations.
_LINK_NOTICE_HASHES = {
    "en": "cbe68f34f1eca83dfd5d2a2e2ea1a574fe8bc32a1e800d2a7ed5a0b678a9f82c",
    "es-419": "9b8f38b1006ed9f0db35f4a59bb35f5951d169717f2fb0ae93567d4575f396ad"
}


def matches_link_disclosure(language: str, disclosure: str | None) -> bool:
    if disclosure is None:
        return False
    return hashlib.sha256(disclosure.encode()).hexdigest() == _LINK_NOTICE_HASHES.get(language)


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
    def __init__(
        self,
        pool,
        route: Callable[[], dict[str, Any]],
        scope: ConsentScope = RECEIPT_SCOPE,
    ) -> None:
        self.pool, self.route, self.scope = pool, route, scope

    def _route(self) -> dict[str, Any]:
        try:
            route = self.route()
        except ValueError as error:
            raise ConsentError("whatsapp_ai_route_unavailable", 503) from error
        if not route:
            raise ConsentError("whatsapp_ai_route_unavailable", 503)
        return route

    @staticmethod
    def _link(connection, person_id: UUID, *, lock: bool = False):
        return connection.execute(
            "select id,wa_id_hash,last4 from public.whatsapp_sender_links"
            " where destination_owner_id=%s and status='active'"
            + (" for update" if lock else ""),
            (person_id,),
        ).fetchone()

    @staticmethod
    def _latest(connection, link_id):
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                "select * from public.business_whatsapp_ai_consents where sender_link_id=%s"
                " order by consented_at desc,id desc limit 1",
                (link_id,),
            )
            return cursor.fetchone()

    def _view(self, link, latest, route, language: str | None = None):
        disclosure = self.scope.text(language)
        token = digest(
            {
                "link": str(link[0]),
                "scope": self.scope.version,
                "disclosure": disclosure,
                "route": route,
                "previous": str(latest["id"]) if latest else None,
                "revoked": str(latest["revoked_at"]) if latest else None,
            }
        )
        return {
            "linked": True,
            "available": True,
            "reason": None,
            "last4": link[2],
            "scope_version": self.scope.version,
            "purpose": self.scope.purpose,
            "active_scope_version": latest["scope_version"]
            if latest and latest["revoked_at"] is None
            else None,
            "disclosure": disclosure or (latest and latest["disclosure"]),
            "route": route,
            "disclosure_token": token if disclosure else None,
            "enabled": bool(
                latest
                and latest["revoked_at"] is None
                and self._matches_disclosure(latest, route)
            ),
            "consented_at": latest["consented_at"] if latest else None,
            "revoked_at": latest["revoked_at"] if latest else None,
        }

    def _matches_disclosure(self, row, route) -> bool:
        return (
            row["scope_version"] == self.scope.version
            and (
                row["disclosure"] in self.scope.texts()
                if self.scope.texts()
                else hashlib.sha256(row["disclosure"].encode()).hexdigest()
                in _LINK_NOTICE_HASHES.values()
            )
            and row["route_hash"] == digest(route)
        )

    def status(
        self,
        owner_id: UUID,
        space_id: UUID | None = None,
        unavailable_reason: str | None = None,
        language: str | None = None,
    ) -> dict:
        with self.pool.connection() as connection, connection.transaction():
            link = self._link(connection, owner_id)
            if link is None:
                return {
                    "linked": False,
                    "available": False,
                    "reason": "whatsapp_link_required",
                    "last4": None,
                    "scope_version": self.scope.version,
                    "purpose": self.scope.purpose,
                    "active_scope_version": None,
                    "disclosure": self.scope.text(language),
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
            view = self._view(link, latest, route, language)
            view["enabled"] = view["enabled"] and self._valid_grant(connection, latest)
            selected = space_id or (latest and latest["space_id"])
            if selected is None:
                unavailable_reason = "business_unavailable"
            else:
                try:
                    authorize(
                        connection,
                        TrustedActor(
                            actor_id=owner_id, space_id=selected, actor_kind="member"
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

    def enable(
        self, owner_id: UUID, space_id: UUID, request: EnableAIConsent, key: str
    ) -> dict:
        if not 1 <= len(key) <= 80 or "\x00" in key:
            raise ConsentError("invalid_idempotency_key", 422)
        route = self._route()
        input_hash = digest(request.model_dump(mode="json"))
        with self.pool.connection() as connection, connection.transaction():
            link = self._link(connection, owner_id, lock=True)
            if link is None:
                raise ConsentError("whatsapp_link_required", 409)
            auth = authorize(
                connection,
                TrustedActor(actor_id=owner_id, space_id=space_id, actor_kind="member"),
            )
            auth.require("prepare")
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
            view = self._view(link, latest, route, request.language)
            if request.disclosure_token != view["disclosure_token"]:
                raise ConsentError("whatsapp_consent_disclosure_stale", 409)
            if latest and latest["revoked_at"] is None:
                if view["enabled"] and self._valid_grant(connection, latest):
                    raise ConsentError("whatsapp_consent_already_enabled", 409)
                # Keep the prior consent as history when its grant or disclosure changed.
                connection.execute(
                    "update public.business_whatsapp_ai_consents"
                    " set revoked_at=clock_timestamp(),revoked_by=%s where id=%s",
                    (owner_id, latest["id"]),
                )
            _insert_consent(
                connection,
                link[0],
                link[1],
                auth,
                self.scope,
                self.scope.text(request.language),
                route,
                key,
                input_hash,
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


def _insert_consent(
    connection: Connection,
    link_id: UUID,
    sender_hash: bytes,
    auth: Authorization,
    scope: ConsentScope,
    disclosure: str,
    route: dict[str, Any],
    key: str,
    input_hash: str,
) -> None:
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
            scope.version,
            scope.purpose,
            disclosure,
            Jsonb(route),
            digest(route),
            key,
            input_hash,
        ),
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
    _insert_consent(
        connection,
        link_id,
        sender_hash,
        auth,
        RECEIPT_SCOPE,
        disclosure,
        route,
        str(link_id),
        digest([language, disclosure]),
    )
