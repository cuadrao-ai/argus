"""Versioned owner permission for email, WhatsApp and uploaded document reads."""

from __future__ import annotations

import hashlib
import json
import threading
from contextlib import nullcontext
from datetime import datetime, timezone
from uuid import uuid4

from psycopg.types.json import Jsonb

from argus.domain.business.authority import ActionError

# Bump the scope only when what we do with the documents changes: an owner who
# agreed to an earlier scope reads as off until they accept this one. A consent
# stores the exact words shown as its record, and new words for the same scope
# keep it on.
SCOPE_VERSION = 3
DISCLOSURES = {
    "en": "We use artificial intelligence to read the documents that come in by email or WhatsApp, or that you upload to Cuadrao (invoices, receipts and PDFs), and prepare a draft of each one. You review it and approve it. If you turn it off, they are saved unread; if you turn it back on, the ones left unread are read too. Details in the privacy notice.",
    "es-419": "Leemos con inteligencia artificial los documentos que llegan por correo, por WhatsApp o que subes en Cuadrao (facturas, recibos y PDF), y preparamos un borrador de cada uno. Tú lo revisas y lo apruebas. Si lo apagas, se guardan sin leer; si lo vuelves a activar, también se leen los que quedaron sin leer. Detalles en el aviso de privacidad.",
}
_COLUMNS = ("id", "scope_version", "consented_at", "revoked_at", "route", "disclosure")


def _row(db, space_id):
    found = db.execute(
        "select id::text,scope_version,consented_at,revoked_at,route,disclosure from public.business_receipt_reading_consents"
        " where space_id=%s order by consented_at desc,id desc limit 1",
        (space_id,),
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
        "enabled": bool(
            row
            and row["scope_version"] == SCOPE_VERSION
            and row["revoked_at"] is None
            and row["route"] == route
        ),
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

    def _is_memory_owner(self, space_id: str, actor_id: str) -> bool:
        access = self.access_resolver() if self.access_resolver else None
        return access is not None and any(
            grant.space_id == space_id and "approve" in grant.permissions
            for grant in access.spaces_for(actor_id)
        )

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
                result = _view(row, space_id, owner_id, route, language)
                if (
                    row
                    and self.access_resolver
                    and not self._is_memory_owner(space_id, row.get("actor_id", owner_id))
                ):
                    result["enabled"] = False
                return result
        with self.pool.connection() as db:
            return self.status_on_connection(db, space_id, owner_id, language)

    def status_on_connection(
        self, db, space_id: str, owner_id: str, language: str = "en"
    ) -> dict:  # noqa: ANN001
        route = self._route()
        owner = db.execute(
            "select created_by::text from public.spaces where id=%s and created_by=%s and kind='business' and closed_at is null",
            (space_id, owner_id),
        ).fetchone()
        if owner is None:
            return _view(None, space_id, owner_id, route, language)
        return _view(_row(db, space_id), space_id, owner[0], route, language)

    def enabled(
        self, space_id: str, owner_id: str, consent_id: str | None = None
    ) -> bool:
        state = self.status(space_id, owner_id)
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
                allowed = (
                    self._is_memory_owner(space_id, acting_person)
                    if self.access_resolver
                    else acting_person == str(owner_id)
                )
                if not allowed:
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
            if (
                not owner
                or not db.execute(
                    "select 1 from public.business_client_grants where space_id=%s and grantee_id=%s"
                    " and business_role='owner' and revoked_at is null and expires_at is null",
                    (space_id, acting_person),
                ).fetchone()
            ):
                raise ActionError("permission_denied", "business_permission_denied")
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
