"""Versioned Business permission for email, WhatsApp and uploaded document reads."""

from __future__ import annotations

import hashlib
import json
import threading
from contextlib import nullcontext
from datetime import datetime, timezone
from uuid import uuid4

from psycopg import Connection
from psycopg.types.json import Jsonb

from argus.domain.business.authority import ActionError, authorize
from argus.domain.business.contracts.authority import TrustedActor
from argus.domain.business.roles import ROLE_PERMISSIONS, Permission

RECEIPT_READING_PERMISSION: Permission = "approve"
# Scope, route and disclosure record what the approver accepted.
# Changing the disclosure does not revoke an existing consent.
SCOPE_VERSION = 3
DISCLOSURES = {
    "en": "We use artificial intelligence to read the documents that come in by email or WhatsApp, or that you upload to Cuadrao (invoices, receipts and PDFs), and prepare a draft of each one. You review it and accept it. If you turn it off, they are saved unread; if you turn it back on, the ones left unread are read too. Details in the privacy notice.",
    "es-419": "Leemos con inteligencia artificial los documentos que llegan por correo, por WhatsApp o que subes en Cuadrao (facturas, recibos y PDF), y preparamos un borrador de cada uno. Tú lo revisas y lo aceptas. Si lo apagas, se guardan sin leer; si lo vuelves a activar, también se leen los que quedaron sin leer. Detalles en el aviso de privacidad.",
}
_COLUMNS = (
    "id",
    "scope_version",
    "consented_at",
    "revoked_at",
    "route",
    "disclosure",
    "approver_live",
)


def _row(db, space_id, *, lock: bool = False):
    found = db.execute(
        "select id::text,scope_version,consented_at,revoked_at,route,disclosure,"
        " exists(select 1 from public.business_client_grants g"
        " where g.space_id=c.space_id and g.grantee_id=c.owner_id and %s=any(g.capabilities)"
        " and g.created_at<=c.consented_at and g.revoked_at is null"
        " and (g.expires_at is null or g.expires_at>clock_timestamp()))"
        " from public.business_receipt_reading_consents c"
        " where space_id=%s order by consented_at desc,id desc limit 1"
        + (" for share" if lock else ""),
        (RECEIPT_READING_PERMISSION, space_id),
    ).fetchone()
    return dict(zip(_COLUMNS, found, strict=True)) if found else None


def _view(row, space_id, owner_id, route, language):
    disclosure = DISCLOSURES[language]
    token = (
        hashlib.sha256(
            json.dumps(
                [str(space_id), str(owner_id), SCOPE_VERSION, route, disclosure],
                sort_keys=True,
            ).encode()
        ).hexdigest()
        if route
        else None
    )
    return {
        "scope_version": SCOPE_VERSION,
        "disclosure": disclosure,
        "route": route,
        "disclosure_token": token,
        "available": route is not None,
        "enabled": bool(row and row["revoked_at"] is None and row["approver_live"]),
        "consent_id": row["id"] if row else None,
        "consented_at": row["consented_at"] if row else None,
        "revoked_at": row["revoked_at"] if row else None,
    }


class BusinessReceiptConsentStore:
    def __init__(self, pool=None, route_resolver=None, access_resolver=None):
        from argus.domain.ingestion.whatsapp.receipt_consent import receipt_provider_route

        self.pool = pool
        self.access_resolver = access_resolver
        self.route_resolver = route_resolver or receipt_provider_route
        self._rows = {}
        self._commands = {}
        self._lock = threading.RLock()

    def _memory_guard(self):
        access = self.access_resolver() if self.access_resolver else None
        return access._lock if access is not None else nullcontext()

    def _memory_approving_grant(
        self, space_id: str, actor_id: str
    ) -> tuple[str, int | None] | None:
        access = self.access_resolver() if self.access_resolver else None
        if access is None:
            return None
        for grant in access.spaces_for(actor_id):
            if (
                grant.space_id != space_id
                or RECEIPT_READING_PERMISSION not in grant.permissions
            ):
                continue
            # A promotion can reuse the same grant ID after an intervening demotion.
            losses = (
                event.membership_version
                for event in reversed(access.ledger)
                if str(event.grant_id) == grant.grant_id
                and event.action == "change_role"
                and event.business_role is not None
                and RECEIPT_READING_PERMISSION not in ROLE_PERMISSIONS[event.business_role]
            )
            return grant.grant_id, next(losses, None)
        return None

    def _route(self):
        try:
            return self.route_resolver()
        except (ValueError, RuntimeError):
            return None

    def status(self, space_id: str, owner_id: str, language: str = "en") -> dict:
        route = self._route()
        if self.pool is None:
            with self._lock, self._memory_guard():
                row = self._rows.get((str(space_id), str(owner_id)))
                if row:
                    row = {
                        **row,
                        "approver_live": row["approval_period"]
                        == self._memory_approving_grant(space_id, row["actor_id"]),
                    }
                return _view(row, space_id, owner_id, route, language)
        with self.pool.connection() as db:
            return self.status_on_connection(db, space_id, owner_id, language)

    def status_on_connection(
        self,
        db: Connection,
        space_id: str,
        owner_id: str,
        language: str = "en",
        *,
        lock: bool = False,
    ) -> dict:
        route = self._route()
        owner = db.execute(
            "select created_by::text from public.spaces where id=%s and created_by=%s and kind='business' and closed_at is null",
            (space_id, owner_id),
        ).fetchone()
        if owner is None:
            return _view(None, space_id, owner_id, route, language)
        return _view(_row(db, space_id, lock=lock), space_id, owner[0], route, language)

    def enabled(
        self, space_id: str, owner_id: str, consent_id: str | None = None,
        *, db: Connection | None = None,
    ) -> bool:
        """Check the captured generation, holding it through an existing transaction."""
        state = (
            self.status(space_id, owner_id)
            if db is None
            else self.status_on_connection(db, space_id, owner_id, lock=True)
        )
        return state["enabled"] and (
            consent_id is None or state["consent_id"] == consent_id
        )

    def set(
        self,
        space_id: str,
        owner_id: str,
        *,
        actor_id: str | None = None,
        enabled: bool,
        version: int,
        disclosure_token: str | None = None,
        language: str = "en",
        idempotency_key: str | None = None,
    ) -> dict:
        if version != SCOPE_VERSION:
            raise ActionError("invalid_input", "business_receipt_consent_changed")
        key = idempotency_key or str(uuid4())
        digest = hashlib.sha256(
            json.dumps(
                [enabled, version, disclosure_token, language], sort_keys=True
            ).encode()
        ).hexdigest()
        route = self._route()
        shown = _view(None, space_id, owner_id, route, language)
        if self.pool is None:
            acting_person = str(actor_id or owner_id)
            with self._lock, self._memory_guard():
                approval_period = self._memory_approving_grant(space_id, acting_person)
                if approval_period is None:
                    raise ActionError("permission_denied", "business_permission_denied")
                identity = (str(space_id), acting_person, key)
                replay = self._commands.get(identity)
                if replay is not None:
                    if replay != digest:
                        raise ActionError(
                            "idempotency_conflict", "business_receipt_consent_changed"
                        )
                    return self.status(space_id, owner_id, language)
                self._validate_enable(enabled, shown, disclosure_token)
                row = self._rows.get((str(space_id), str(owner_id)))
                current = self.status(space_id, owner_id, language)
                now = datetime.now(timezone.utc)
                if enabled and not current["enabled"]:
                    self._rows[(str(space_id), str(owner_id))] = {
                        "id": str(uuid4()),
                        "actor_id": acting_person,
                        "approval_period": approval_period,
                        "scope_version": version,
                        "consented_at": now,
                        "revoked_at": None,
                        "route": route,
                        "disclosure": shown["disclosure"],
                    }
                elif not enabled and row and row["revoked_at"] is None:
                    row["revoked_at"] = now
                self._commands[identity] = digest
                return self.status(space_id, owner_id, language)
        with self.pool.connection() as db, db.transaction():
            owner = db.execute(
                "select created_by::text from public.spaces where id=%s and created_by=%s and kind='business' and closed_at is null for update",
                (space_id, owner_id),
            ).fetchone()
            acting_person = owner_id if actor_id is None else actor_id
            if owner is None:
                raise ActionError("permission_denied", "business_permission_denied")
            try:
                authorize(
                    db,
                    TrustedActor(
                        actor_id=acting_person, actor_kind="member", space_id=space_id
                    ),
                ).require(RECEIPT_READING_PERMISSION)
            except ActionError:
                raise ActionError(
                    "permission_denied", "business_permission_denied"
                ) from None
            owner_id = owner[0]
            shown = _view(None, space_id, owner_id, route, language)
            replay = db.execute(
                "select request_hash from public.business_receipt_consent_commands where space_id=%s and owner_id=%s and idempotency_key=%s",
                (space_id, acting_person, key),
            ).fetchone()
            if replay:
                if replay[0] != digest:
                    raise ActionError(
                        "idempotency_conflict", "business_receipt_consent_changed"
                    )
                return _view(_row(db, space_id), space_id, owner_id, route, language)
            self._validate_enable(enabled, shown, disclosure_token)
            current = _view(_row(db, space_id), space_id, owner_id, route, language)
            if enabled and not current["enabled"]:
                db.execute(
                    "update public.business_receipt_reading_consents set revoked_at=clock_timestamp() where space_id=%s and revoked_at is null",
                    (space_id,),
                )
                db.execute(
                    "insert into public.business_receipt_reading_consents(space_id,owner_id,scope_version,route,disclosure,idempotency_key,request_hash) values(%s,%s,%s,%s,%s,%s,%s)",
                    (
                        space_id,
                        acting_person,
                        version,
                        Jsonb(route),
                        shown["disclosure"],
                        key,
                        digest,
                    ),
                )
            elif not enabled:
                db.execute(
                    "update public.business_receipt_reading_consents set revoked_at=clock_timestamp() where space_id=%s and revoked_at is null",
                    (space_id,),
                )
            db.execute(
                "insert into public.business_receipt_consent_commands(space_id,owner_id,idempotency_key,request_hash) values(%s,%s,%s,%s)",
                (space_id, acting_person, key, digest),
            )
            return _view(_row(db, space_id), space_id, owner_id, route, language)

    @staticmethod
    def _validate_enable(enabled, shown, token):
        if enabled and (not shown["available"] or token != shown["disclosure_token"]):
            raise ActionError("invalid_input", "business_receipt_consent_changed")
