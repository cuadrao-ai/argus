"""Versioned owner permission for email, WhatsApp and uploaded receipt reads."""

from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timezone
from uuid import uuid4

from psycopg.types.json import Jsonb

from argus.domain.business.authority import ActionError

SCOPE_VERSION = 1
DISCLOSURES = {
    "en": "Read my Business receipts with AI. This includes receipts received by email, WhatsApp and upload. Reading creates drafts for review. Only I can approve a financial record. Turning this off stops new reads.",
    "es-419": "Leer mis recibos del negocio con IA. Esto incluye los recibos que llegan por correo, WhatsApp y archivos subidos. La lectura crea borradores para revisar. Solo yo puedo aprobar un registro financiero. Al desactivar esta opción se detienen las nuevas lecturas.",
}
_COLUMNS = ("id", "scope_version", "consented_at", "revoked_at", "route", "disclosure")


def _row(db, space_id, owner_id):
    found = db.execute(
        "select id::text,scope_version,consented_at,revoked_at,route,disclosure from public.business_receipt_reading_consents"
        " where space_id=%s and owner_id=%s order by consented_at desc,id desc limit 1",
        (space_id, owner_id),
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
            and row["disclosure"] in DISCLOSURES.values()
        ),
        "consent_id": row["id"] if row else None,
        "consented_at": row["consented_at"] if row else None,
        "revoked_at": row["revoked_at"] if row else None,
    }


class BusinessReceiptConsentStore:
    def __init__(self, pool=None, route_resolver=None):
        from argus.domain.ingestion.whatsapp.receipt_consent import receipt_provider_route

        self.pool = pool
        self.route_resolver = route_resolver or receipt_provider_route
        self._rows = {}
        self._commands = {}
        self._lock = threading.RLock()

    def _route(self):
        try:
            return self.route_resolver()
        except (ValueError, RuntimeError):
            return None

    def status(self, space_id: str, owner_id: str, language: str = "en") -> dict:
        route = self._route()
        if self.pool is None:
            with self._lock:
                row = self._rows.get((str(space_id), str(owner_id)))
                return _view(row, space_id, owner_id, route, language)
        with self.pool.connection() as db:
            return _view(
                _row(db, space_id, owner_id), space_id, owner_id, route, language
            )

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
            with self._lock:
                identity = (str(space_id), str(owner_id), key)
                replay = self._commands.get(identity)
                if replay is not None:
                    if replay != digest:
                        raise ActionError(
                            "idempotency_conflict", "business_receipt_consent_changed"
                        )
                    return self.status(space_id, owner_id, language)
                self._validate_enable(enabled, shown, disclosure_token)
                row = self._rows.get((str(space_id), str(owner_id)))
                current = _view(row, space_id, owner_id, route, language)
                now = datetime.now(timezone.utc)
                if enabled and not current["enabled"]:
                    self._rows[(str(space_id), str(owner_id))] = {
                        "id": str(uuid4()),
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
                "select created_by from public.spaces where id=%s and kind='business' and closed_at is null for update",
                (space_id,),
            ).fetchone()
            if not owner or str(owner[0]) != str(owner_id):
                raise ActionError("permission_denied", "business_permission_denied")
            replay = db.execute(
                "select request_hash from public.business_receipt_consent_commands where space_id=%s and owner_id=%s and idempotency_key=%s",
                (space_id, owner_id, key),
            ).fetchone()
            if replay:
                if replay[0] != digest:
                    raise ActionError(
                        "idempotency_conflict", "business_receipt_consent_changed"
                    )
                return _view(
                    _row(db, space_id, owner_id), space_id, owner_id, route, language
                )
            self._validate_enable(enabled, shown, disclosure_token)
            current = _view(
                _row(db, space_id, owner_id), space_id, owner_id, route, language
            )
            if enabled and not current["enabled"]:
                db.execute(
                    "update public.business_receipt_reading_consents set revoked_at=clock_timestamp() where space_id=%s and owner_id=%s and revoked_at is null",
                    (space_id, owner_id),
                )
                db.execute(
                    "insert into public.business_receipt_reading_consents(space_id,owner_id,scope_version,route,disclosure,idempotency_key,request_hash) values(%s,%s,%s,%s,%s,%s,%s)",
                    (
                        space_id,
                        owner_id,
                        version,
                        Jsonb(route),
                        shown["disclosure"],
                        key,
                        digest,
                    ),
                )
            elif not enabled:
                db.execute(
                    "update public.business_receipt_reading_consents set revoked_at=clock_timestamp() where space_id=%s and owner_id=%s and revoked_at is null",
                    (space_id, owner_id),
                )
            db.execute(
                "insert into public.business_receipt_consent_commands(space_id,owner_id,idempotency_key,request_hash) values(%s,%s,%s,%s)",
                (space_id, owner_id, key, digest),
            )
            return _view(
                _row(db, space_id, owner_id), space_id, owner_id, route, language
            )

    @staticmethod
    def _validate_enable(enabled, shown, token):
        if enabled and (not shown["available"] or token != shown["disclosure_token"]):
            raise ActionError("invalid_input", "business_receipt_consent_changed")
