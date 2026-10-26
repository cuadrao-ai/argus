"""A process-bound arm, one signed PDF observation, then a permanent seal."""

from __future__ import annotations

import asyncio
import json
import re
import secrets
import time
from collections.abc import Callable
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings

from argus.domain.ingestion.whatsapp.config import (
    WhatsAppSettings,
    load_whatsapp_settings,
)
from argus.domain.ingestion.whatsapp.media import GraphMedia

Digits = Annotated[str, Field(pattern=r"^[0-9]{1,32}$", strict=True)]
SafeName = Annotated[str, Field(pattern=r"^[A-Za-z0-9_-]{1,80}$", strict=True)]
SHA = Annotated[str, Field(pattern=r"^[a-f0-9]{40}$", strict=True)]
UUIDText = Annotated[
    str, Field(pattern=r"^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$", strict=True)
]
ZERO_EFFECTS = dict(
    downloads=0,
    uploads=0,
    deletes=0,
    replies=0,
    model_calls=0,
    database_writes=0,
    expenses=0,
    drafts=0,
    sources=0,
)


class WorkerIdentity(BaseSettings):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)
    release_sha: str = Field(default="", validation_alias="RENDER_GIT_COMMIT")
    instance_id: str = Field(default="", validation_alias="RENDER_INSTANCE_ID")
    workers: int = Field(default=1, validation_alias="WEB_CONCURRENCY")


class Arm(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)
    diagnostic_id: SafeName
    nonce: SafeName
    release_sha: SHA
    instance_id: SafeName
    deployment_id: SafeName
    topology_observed_at: int
    instances: int = Field(strict=True, ge=1, le=1)
    workers: int = Field(strict=True, ge=1, le=1)
    expires_at: int
    sender: Digits = Field(repr=False)
    app_id: Digits
    subject_id: Digits
    waba_id: Digits
    phone_id: Digits
    owner_id: UUIDText
    business_id: UUIDText


class DiagnosticHeld(Exception):
    """Ordinary intake must retry while this worker holds diagnostics."""


def _event(body: bytes, arm: Arm, now: float, armed_at: float) -> dict:
    def unique(pairs: list) -> dict:
        found = dict(pairs)
        if len(found) != len(pairs):
            raise ValueError
        return found

    envelope = json.loads(body, object_pairs_hook=unique)
    [entry] = envelope["entry"]
    [change] = entry["changes"]
    value = change["value"]
    [message] = value["messages"]
    document = message["document"]
    ids = (entry["id"], value["metadata"]["phone_number_id"], document["id"])
    if not all(isinstance(i, str) and re.fullmatch(r"[0-9]{1,32}", i) for i in ids):
        raise ValueError
    message_id, stamp = message["id"], message["timestamp"]
    if not isinstance(message_id, str) or not re.fullmatch(
        r"[A-Za-z0-9_.=-]{1,256}", message_id
    ):
        raise ValueError
    if not isinstance(stamp, str) or not re.fullmatch(r"[0-9]{1,10}", stamp):
        raise ValueError
    if not int(armed_at) <= int(stamp) <= min(now + 30, arm.expires_at):
        raise ValueError
    if (
        envelope["object"] != "whatsapp_business_account"
        or change["field"] != "messages"
        or value.get("statuses")
        or message["type"] != "document"
        or document["mime_type"] != "application/pdf"
        or "image" in message
    ):
        raise ValueError
    return dict(
        waba_id=ids[0],
        phone_id=ids[1],
        media_id=ids[2],
        message_id=message_id,
        provider_timestamp=stamp,
        sender_match=message["from"] == arm.sender,
    )


class DiagnosticOnce:
    def __init__(
        self,
        *,
        media: GraphMedia | None,
        settings: WhatsAppSettings,
        scope_check: Callable[[Arm], bool] | None,
        identity: WorkerIdentity | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.media, self.settings, self.scope_check = media, settings, scope_check
        self.identity, self.clock = identity or WorkerIdentity(), clock
        self.nonce = secrets.token_hex(16)
        self.state = "disarmed"
        self.arm_record: Arm | None = None
        self.armed_at = 0.0
        self.result: dict | None = None
        self.lock = asyncio.Lock()
        self.control = None

    def status(self) -> dict:
        identity = self.identity
        valid = re.fullmatch(
            r"[a-f0-9]{40}", identity.release_sha or ""
        ) and re.fullmatch(r"[A-Za-z0-9_-]{1,80}", identity.instance_id or "")
        return dict(
            state=self.state,
            nonce=self.nonce,
            release_sha=identity.release_sha if valid else "unavailable",
            instance_id=identity.instance_id if valid else "unavailable",
            topology="operator_must_verify_one_instance",
            workers=identity.workers,
        )

    def arm(self, payload: dict) -> bool:
        if self.state != "disarmed":
            if self.state == "armed":
                self.seal("repeat_arm_rejected")
            return False
        try:
            record = Arm.model_validate(payload)
            now = self.clock()
            if (
                record.nonce != self.nonce
                or record.release_sha != self.identity.release_sha
                or record.instance_id != self.identity.instance_id
                or self.identity.workers != 1
                or not now - 60 <= record.topology_observed_at <= now
                or not now < record.expires_at <= now + 600
                or self.media is None
                or record.phone_id != self.settings.phone_number_id
                or self.control is None
                or not self.control.exclusive()
            ):
                raise ValueError
        except Exception:
            self.seal("arm_rejected")
            return False
        self.arm_record, self.armed_at, self.state = record, now, "armed"
        self.control.schedule_expiry(record.expires_at - now)
        return True

    def seal(self, reason: str) -> None:
        self.state = "sealed"
        if self.result is None:
            self.result = dict(outcome=reason, worker=self.status(), get_attempts=0)
        self.result["side_effects"] = ZERO_EFFECTS.copy()
        self.result["worker"] = self.status()
        self.result.setdefault("outcome", reason)
        if self.control is not None:
            self.control.finish(self.result)

    async def observe(self, body: bytes) -> None:
        """Called only after HMAC success. Every enabled-state branch quarantines intake."""
        async with self.lock:
            arm = self.arm_record
            target = False
            try:
                envelope = json.loads(body)
                senders = [
                    message.get("from")
                    for entry in envelope["entry"]
                    for change in entry["changes"]
                    for message in change["value"].get("messages", [])
                ]
                target = bool(
                    arm is not None
                    and senders
                    and all(sender == arm.sender for sender in senders)
                )
            except Exception:
                pass
            if self.state != "armed":
                if not target:
                    raise DiagnosticHeld from None
                return
            self.state = "consumed"
            self.result = dict(
                diagnostic_id=arm.diagnostic_id,
                worker=self.status(),
                received_at=int(self.clock()),
                operator_verified_deployment_id=arm.deployment_id,
                topology_observed_at=arm.topology_observed_at,
                signature_verified=True,
                owner_id=arm.owner_id,
                business_id=arm.business_id,
                runtime_selector="CUADRAO_WHATSAPP_ACCESS_TOKEN_then_ARGUS_WHATSAPP_ACCESS_TOKEN",
                get_attempts=0,
                side_effects=ZERO_EFFECTS.copy(),
            )
            try:
                if self.clock() >= arm.expires_at or not self.control.exclusive():
                    raise ValueError
                self.control.close_socket()
                captured = _event(body, arm, self.clock(), self.armed_at)
                self.result["event"] = captured
                if (
                    captured["waba_id"] != arm.waba_id
                    or captured["phone_id"] != arm.phone_id
                    or not captured["sender_match"]
                ):
                    raise ValueError
                # This callback only reads sender link, open scope and reading permission.
                self.result["scope_match_reading_off"] = await asyncio.to_thread(
                    self.scope_check, arm
                )
                if self.result["scope_match_reading_off"] is not True:
                    raise ValueError
                selected = load_whatsapp_settings().access_token
                probe = await self.media.diagnose_once(
                    media_id=captured["media_id"],
                    app_id=arm.app_id,
                    subject_id=arm.subject_id,
                    runtime_token=self.settings.access_token.get_secret_value(),
                    selected_token=selected.get_secret_value()
                    if selected is not None
                    else "",
                    expires_at=arm.expires_at,
                    on_attempt=lambda count: self.result.update(get_attempts=count),
                )
                self.result.update(probe)
            except Exception:
                self.result["outcome"] = "scope_payload_or_runtime_stopped"
            finally:
                self.seal("stopped")
            if not target:
                raise DiagnosticHeld from None
