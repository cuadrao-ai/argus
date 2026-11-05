"""One public boundary for preparation, one-shot contact, and private reads."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from typing import Literal
from uuid import UUID

from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.authority import TrustedActor

from .config import Settings
from .contracts import Case, FiscalOperation, Observation, digest
from .provider import Provider, ProviderError, observation
from .store import Store


class Service:
    def __init__(
        self, store: Store, provider: Provider, settings: Settings, cases: dict[str, Case]
    ) -> None:
        self.store, self.provider, self.settings, self.cases = (
            store,
            provider,
            settings,
            cases,
        )

    def _scope(self, actor: TrustedActor) -> None:
        if (
            str(actor.space_id) != self.settings.business_id
            or actor.actor_kind != "member"
        ):
            raise ActionError("not_found", "business_record_not_found")

    async def prepare(
        self, actor: TrustedActor, grant: UUID | None, case_id: str
    ) -> FiscalOperation:
        self._scope(actor)
        case = self.cases.get(case_id)
        if case is None:
            raise ActionError("invalid_input", "fiscal_case_unavailable")
        return await asyncio.to_thread(self.store.prepare, actor, grant, case)

    async def get(
        self, actor: TrustedActor, grant: UUID | None, operation_id: UUID
    ) -> FiscalOperation:
        self._scope(actor)
        return await asyncio.to_thread(self.store.get, actor, grant, operation_id)

    async def submit(
        self,
        actor: TrustedActor,
        grant: UUID | None,
        operation_id: UUID,
        expected_digest: str,
    ) -> FiscalOperation:
        self._scope(actor)
        if not self.settings.contact_enabled:
            raise ActionError("permission_denied", "fiscal_contact_disabled")
        # Cancellation of to_thread cannot cancel its commit. It can lose a permit,
        # which stays unknown; the recovery loop never obtains a create permit.
        _, case = await asyncio.to_thread(
            self.store.claim, actor, grant, operation_id, expected_digest
        )
        if case is not None:
            manifest = self.cases.get(case.case_id)
            matches = (
                manifest == case
                if case.invoice_revision_id is None
                else (
                    manifest is not None
                    and digest(manifest.model_dump(mode="json")) == case.manifest_digest
                    and await asyncio.to_thread(
                        self.store.saved_revision_matches, case, operation_id
                    )
                )
            )
            if not matches:
                await asyncio.to_thread(
                    self.store.record,
                    operation_id,
                    Observation(source="unknown", code="manifest_changed"),
                )
            else:
                try:
                    event = await self.provider.create(case)
                except asyncio.CancelledError:
                    await asyncio.shield(
                        asyncio.to_thread(
                            self.store.record,
                            operation_id,
                            Observation(source="unknown", code="contact_cancelled"),
                        )
                    )
                    raise
                except Exception:
                    event = Observation(source="unknown", code="contact_uncertain")
                await asyncio.to_thread(self.store.record, operation_id, event)
        return await self.get(actor, grant, operation_id)

    def authenticate(self, supplied: str) -> None:
        secret = self.settings.callback_secret.get_secret_value()
        if (
            not secret
            or len(supplied) > 1024
            or not hmac.compare_digest(supplied.encode(), secret.encode())
        ):
            raise PermissionError("fiscal_callback_authentication")

    async def callback(self, raw: bytes) -> str:
        if len(raw) > 32768:
            raise ValueError("fiscal_callback_size")
        try:
            data = json.loads(raw)
        except ValueError:
            raise ValueError("fiscal_callback_json") from None
        if data == {"message": "Test message"}:
            return "probe"
        if not isinstance(data, dict):
            raise ValueError("fiscal_callback_json")
        if data.get("type") != "documents.emissionFinished":
            event = Observation(
                source="callback",
                code="unsupported_event",
                evidence_digest=hashlib.sha256(raw).hexdigest(),
            )
            await asyncio.to_thread(self.store.quarantine, event)
            return "quarantined"
        try:
            event = observation(raw, "callback")
        except ProviderError:
            event = Observation(
                source="callback",
                code="invalid_event",
                evidence_digest=hashlib.sha256(raw).hexdigest(),
            )
        cases = [
            c
            for c in self.cases.values()
            if c.issuer == event.issuer and c.number == event.number
        ]
        if len(cases) != 1 or not event.provider_id:
            await asyncio.to_thread(self.store.quarantine, event)
            return "quarantined"
        await asyncio.to_thread(self.store.callback, cases[0], event)
        return "stored"

    async def reconcile(self) -> None:
        work = await asyncio.to_thread(
            self.store.recovery, UUID(self.settings.business_id), self.settings.poll_limit
        )
        # Serial bounded GETs; no create method is reachable from recovery.
        started = asyncio.get_running_loop().time()
        for operation_id, case, provider_id, token in work:
            if asyncio.get_running_loop().time() - started > 15:
                break
            if provider_id is None:
                event = Observation(source="unknown", code="identity_missing")
            else:
                try:
                    event = await self.provider.status(case, provider_id)
                except Exception:
                    event = Observation(
                        source="unknown", code="reconciliation_unavailable"
                    )
            await asyncio.to_thread(self.store.record, operation_id, event, lease=token)

    async def artifact(
        self,
        actor: TrustedActor,
        grant: UUID | None,
        operation_id: UUID,
        kind: Literal["xml", "pdf"],
    ) -> bytes:
        self._scope(actor)
        case, provider_id, _ = await asyncio.to_thread(
            self.store.locator, actor, grant, operation_id, kind
        )
        if provider_id is None:
            raise ActionError("stale_version", "fiscal_identity_missing")
        try:
            # Exact-ID refresh avoids using expired one-hour credentials.
            event = await self.provider.status(case, provider_id)
            await asyncio.to_thread(self.store.record, operation_id, event)
            url = event.xml_url if kind == "xml" else event.pdf_url
            # Store validation may have rejected a mismatched status identity.
            if (
                event.issuer != case.issuer
                or event.number != case.number
                or event.provider_id != provider_id
                or not url
            ):
                raise ProviderError("artifact_unavailable")
            content = await self.provider.artifact(case, provider_id, kind, url)
        except Exception:
            await asyncio.to_thread(
                self.store.record,
                operation_id,
                Observation(
                    source="artifact",
                    **{kind: "retrieval_failed"},
                    code="artifact_retrieval_failed",
                ),
            )
            raise ActionError("stale_version", "fiscal_artifact_unavailable") from None
        await asyncio.to_thread(
            self.store.record,
            operation_id,
            Observation(source="artifact", **{kind: "available"}),
        )
        await self.get(actor, grant, operation_id)  # Live read authority after network.
        return content
