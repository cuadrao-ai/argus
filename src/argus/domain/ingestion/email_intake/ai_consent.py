"""The owner's permission to read the receipts that reach the Business address.

One switch per Business, the same shape as the WhatsApp receipt permission:
the text shown is the text stored and hashed with the provider route, so a
changed wording or model no longer matches and the owner is asked again. Only
the Business owner may turn it on, turn it off, or decline the one-time
notice; anyone with a live grant may read where it stands. Every answer is
read fresh from the database at the moment it matters."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import Field, model_validator

from argus.domain.business.access import _profiles
from argus.domain.business.authority import ActionError, authorize
from argus.domain.business.contracts.authority import TrustedActor
from argus.domain.business.contracts.facts import Contract
from argus.domain.ingestion.whatsapp.ai_consent import (
    ConsentError,
    ConsentScope,
    digest,
)

# The one short disclosure for reading emailed receipts. The legal wording
# pass changes only these sentences.
EMAIL_RECEIPT_SCOPE = ConsentScope(
    1,
    "business_email_receipt_reading",
    "Cuadrao will read receipts that reach this address with AI. Forwarded "
    "emails may include other people's details; attachments are sent to "
    "OpenRouter and the model named below. You can turn this off in Settings.",
    "Cuadrao leerá con IA los recibos que lleguen a esta dirección. Los correos "
    "reenviados pueden incluir datos de otras personas; los adjuntos se envían a "
    "OpenRouter y al modelo indicado abajo. Puedes apagarlo en Ajustes.",
)
DECLINED_ACTION = "email_ai_consent_declined"

ConsentState = Literal["on", "off", "unseen"]


class EmailConsentRequest(Contract):
    """Turn the permission on against the exact text shown, or decline the
    one-time notice. A decline stores no permission."""

    action: Literal["enable", "decline"]
    disclosure_token: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    language: str | None = Field(default=None, max_length=16)

    @model_validator(mode="after")
    def _enable_names_its_text(self) -> EmailConsentRequest:
        if self.action == "enable" and not self.disclosure_token:
            raise ValueError("enable needs the disclosure token of the text shown")
        return self


class EmailConsentStore:
    def __init__(
        self,
        pool,  # noqa: ANN001
        route: Callable[[], dict[str, Any]],
        scope: ConsentScope = EMAIL_RECEIPT_SCOPE,
    ) -> None:
        self.pool, self.route, self.scope = pool, route, scope

    def _route(self) -> dict[str, Any]:
        try:
            route = self.route()
        except ValueError as error:
            raise ConsentError("email_ai_route_unavailable", 503) from error
        if not route:
            raise ConsentError("email_ai_route_unavailable", 503)
        return route

    # --- reads ---------------------------------------------------------------

    @staticmethod
    def _address(connection, space_id: str, *, lock: bool = False):  # noqa: ANN001, ANN202
        return connection.execute(
            "select id::text, principal_id::text from public.business_email_routes"
            " where space_id=%s and active order by created_at limit 1"
            + (" for update" if lock else ""),
            (space_id,),
        ).fetchone()

    @staticmethod
    def _latest(connection, space_id: str):  # noqa: ANN001, ANN202
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                "select * from public.business_email_ai_consents where space_id=%s"
                " order by consented_at desc, id desc limit 1",
                (space_id,),
            )
            return cursor.fetchone()

    @staticmethod
    def _declined_at(connection, space_id: str) -> datetime | None:  # noqa: ANN001
        row = connection.execute(
            "select max(created_at) from public.business_action_receipts"
            " where space_id=%s and turn_key is null and command->>'action'=%s",
            (space_id, DECLINED_ACTION),
        ).fetchone()
        return row[0] if row else None

    def _matches_disclosure(self, row, route) -> bool:  # noqa: ANN001
        return (
            row["scope_version"] == self.scope.version
            and row["disclosure"] in self.scope.texts()
            and row["route_hash"] == digest(route)
        )

    @staticmethod
    def _valid_grant(connection, row) -> bool:  # noqa: ANN001
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

    def _on(self, connection, latest, route) -> bool:  # noqa: ANN001
        return bool(
            latest
            and latest["revoked_at"] is None
            and route is not None
            and self._matches_disclosure(latest, route)
            and self._valid_grant(connection, latest)
        )

    def _token(self, space_id: str, address, latest, route, language) -> str:  # noqa: ANN001
        return digest(
            {
                "space": space_id,
                "address": address[0] if address else None,
                "scope": self.scope.version,
                "disclosure": self.scope.text(language),
                "route": route,
                "previous": str(latest["id"]) if latest else None,
                "revoked": str(latest["revoked_at"]) if latest else None,
            }
        )

    def _state(self, connection, space_id: str, latest, route) -> ConsentState:  # noqa: ANN001
        if self._on(connection, latest, route):
            return "on"
        if latest is not None:
            return "off"
        return "off" if self._declined_at(connection, space_id) else "unseen"

    def status(
        self, space_id: str, actor_id: str, language: str | None = None
    ) -> dict[str, Any]:
        """Where the permission stands for this Business, as the caller may see
        it. Only the owner gets a token to act on."""

        with self.pool.connection() as connection, connection.transaction():
            try:
                route = self._route()
                reason = None
            except ConsentError:
                route, reason = None, "email_ai_route_unavailable"
            address = self._address(connection, space_id)
            latest = self._latest(connection, space_id)
            owner = (
                connection.execute(
                    "select 1 from public.spaces where id=%s and created_by=%s"
                    " and kind='business' and closed_at is null",
                    (space_id, actor_id),
                ).fetchone()
                is not None
            )
            if owner:
                try:
                    authorize(
                        connection,
                        TrustedActor(
                            actor_id=UUID(actor_id),
                            space_id=UUID(space_id),
                            actor_kind="member",
                        ),
                    ).require("prepare")
                except ActionError:
                    reason = reason or "business_permission_denied"
            else:
                reason = reason or "business_owner_required"
            state = self._state(connection, space_id, latest, route)
            labels = (
                _profiles(connection, str(latest["consenting_actor_id"]))
                if latest
                else {}
            )
            return {
                "state": state,
                "available": reason is None,
                "reason": reason,
                "owner": owner,
                "scope_version": self.scope.version,
                "purpose": self.scope.purpose,
                "disclosure": self.scope.text(language),
                "route": route,
                "disclosure_token": self._token(
                    space_id, address, latest, route, language
                )
                if reason is None
                else None,
                "consented_at": latest["consented_at"] if state == "on" else None,
                "consented_by": labels.get(str(latest["consenting_actor_id"]))
                if state == "on"
                else None,
                "revoked_at": latest["revoked_at"] if latest else None,
            }

    def reading_allowed(self, space_id: str) -> bool:
        """Fresh at the moment of a read: the address is live and the owner's
        permission is on, current and backed by a live grant."""

        try:
            route = self._route()
        except ConsentError:
            return False
        with self.pool.connection() as connection, connection.transaction():
            if self._address(connection, space_id) is None:
                return False
            return self._on(connection, self._latest(connection, space_id), route)

    # --- writes --------------------------------------------------------------

    def _owner(self, connection, space_id: str, owner_id: str):  # noqa: ANN001, ANN202
        """The owner acting on their own live Business, with prepare, else a typed refusal."""

        held = connection.execute(
            "select 1 from public.spaces where id=%s and created_by=%s"
            " and kind='business' and closed_at is null for share",
            (space_id, owner_id),
        ).fetchone()
        if held is None:
            raise ConsentError("business_owner_required")
        auth = authorize(
            connection,
            TrustedActor(
                actor_id=UUID(owner_id), space_id=UUID(space_id), actor_kind="member"
            ),
        )
        auth.require("prepare")
        return auth

    def enable(
        self, space_id: str, owner_id: str, request: EmailConsentRequest, key: str
    ) -> dict[str, Any]:
        if not 1 <= len(key) <= 80 or "\x00" in key:
            raise ConsentError("invalid_idempotency_key", 422)
        if request.action != "enable" or not request.disclosure_token:
            raise ConsentError("email_consent_token_required", 422)
        route = self._route()
        input_hash = digest(request.model_dump(mode="json"))
        with self.pool.connection() as connection, connection.transaction():
            auth = self._owner(connection, space_id, owner_id)
            address = self._address(connection, space_id, lock=True)
            if address is None:
                raise ConsentError("email_address_required", 409)
            with connection.cursor(row_factory=dict_row) as cursor:
                cursor.execute(
                    "select * from public.business_email_ai_consents"
                    " where owner_id=%s and idempotency_key=%s",
                    (owner_id, key),
                )
                prior = cursor.fetchone()
            if prior:
                if (
                    prior["input_hash"] != input_hash
                    or str(prior["space_id"]) != space_id
                ):
                    raise ConsentError("email_consent_idempotency_conflict", 409)
                return self.status(space_id, owner_id, request.language)
            latest = self._latest(connection, space_id)
            if self._on(connection, latest, route):
                # Already on: the answer is the state, not a refusal.
                return self.status(space_id, owner_id, request.language)
            expected = self._token(space_id, address, latest, route, request.language)
            if request.disclosure_token != expected:
                raise ConsentError("email_consent_disclosure_stale", 409)
            if latest and latest["revoked_at"] is None:
                # A stale permission (changed text or model) gives way to the new one.
                connection.execute(
                    "update public.business_email_ai_consents"
                    " set revoked_at=clock_timestamp(), revoked_by=%s where id=%s",
                    (owner_id, latest["id"]),
                )
            connection.execute(
                "insert into public.business_email_ai_consents"
                " (route_id, space_id, owner_id, consenting_actor_id, grant_id, issuer_id,"
                " scope_version, purpose, disclosure, route, route_hash, idempotency_key, input_hash)"
                " values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    address[0],
                    space_id,
                    owner_id,
                    owner_id,
                    auth.context.grant_id,
                    auth.provenance.issuer_id,
                    self.scope.version,
                    self.scope.purpose,
                    self.scope.text(request.language),
                    Jsonb(route),
                    digest(route),
                    key,
                    input_hash,
                ),
            )
        return self.status(space_id, owner_id, request.language)

    def decline(self, space_id: str, owner_id: str, key: str) -> dict[str, Any]:
        """The owner saw the one-time notice and chose not to read with AI: one
        ledger row, no permission row, and any permission that was on goes off."""

        if not 1 <= len(key) <= 80 or "\x00" in key:
            raise ConsentError("invalid_idempotency_key", 422)
        with self.pool.connection() as connection, connection.transaction():
            auth = self._owner(connection, space_id, owner_id)
            address = self._address(connection, space_id, lock=True)
            if address is None:
                raise ConsentError("email_address_required", 409)
            self._revoke(connection, space_id, owner_id)
            command = {"action": DECLINED_ACTION, "route_id": address[0]}
            connection.execute(
                "insert into public.business_action_receipts"
                " (space_id, actor_id, actor, idempotency_key, input_hash, command, outcome)"
                " values (%s,%s,%s,%s,%s,%s,%s) on conflict do nothing",
                (
                    space_id,
                    owner_id,
                    Jsonb(auth.provenance.model_dump(mode="json")),
                    f"email_ai_consent:declined:{address[0]}",
                    digest(command),
                    Jsonb(command),
                    Jsonb({"outcome": "applied"}),
                ),
            )
        return self.status(space_id, owner_id)

    @staticmethod
    def _revoke(connection, space_id: str, owner_id: str) -> None:  # noqa: ANN001
        connection.execute(
            "update public.business_email_ai_consents"
            " set revoked_at=clock_timestamp(), revoked_by=%s"
            " where space_id=%s and owner_id=%s and revoked_at is null",
            (owner_id, space_id, owner_id),
        )

    def revoke(self, space_id: str, owner_id: str) -> None:
        with self.pool.connection() as connection, connection.transaction():
            self._owner(connection, space_id, owner_id)
            self._revoke(connection, space_id, owner_id)


def email_receipt_route() -> dict[str, Any]:
    """The model that reads an emailed receipt: the same one WhatsApp names."""

    from argus.domain.ingestion.whatsapp.receipt_consent import receipt_provider_route

    return receipt_provider_route()


def email_consent_store(pool) -> EmailConsentStore:  # noqa: ANN001
    return EmailConsentStore(pool, email_receipt_route)
