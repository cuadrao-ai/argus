"""Shortcuts device enrollment and event intake.

Enrollment is a signed-in route under ``/financial-connections/shortcuts``.
Intake (``/ingestion/shortcuts/events``) is called by the shortcut itself with
only its device token. Neither response ever repeats a stored token; the
enrollment response is the one place the token appears, once.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from argus.api.dependencies import problem
from argus.api.routers.financial_connections_schemas import (
    FinancialConnectionResponse,
    connection_response,
)
from argus.api.shortcuts import (
    DeviceContext,
    ShortcutsContext,
    device_unauthorized_problem,
    events_not_saved_problem,
    intake_unavailable_problem,
    require_shortcuts_context,
    require_shortcuts_device,
    spend_event_budget,
)
from argus.domain.ingestion.shortcuts.connector import (
    ConnectionEnded,
    DeviceLimitReached,
    EventsNotSaved,
    IntakeUnavailable,
    Receipt,
)
from argus.domain.ingestion.shortcuts.events import (
    MAX_BATCH_BYTES,
    MAX_BATCH_EVENTS,
    MAX_EVENT_BYTES,
    ShortcutEvent,
    ShortcutEventBatch,
)

INTAKE_PATH = "/api/v1/ingestion/shortcuts/events"

devices_router = APIRouter(prefix="/shortcuts")
intake_router = APIRouter(prefix="/ingestion/shortcuts", tags=["financial-connections"])


# Intake reads its body itself (size cap before parsing), so the request shape
# is declared for the OpenAPI document here.
_EVENT_SCHEMA = ShortcutEvent.model_json_schema()
_EVENT_BODY = {
    "requestBody": {
        "required": True,
        "content": {"application/json": {"schema": _EVENT_SCHEMA}},
    }
}
_BATCH_BODY = {
    "requestBody": {
        "required": True,
        "content": {
            "application/json": {
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["events"],
                    "properties": {
                        "events": {
                            "type": "array",
                            "minItems": 1,
                            "maxItems": MAX_BATCH_EVENTS,
                            "items": _EVENT_SCHEMA,
                        }
                    },
                }
            }
        },
    }
}


class DeviceEnrollmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_name: str = Field(min_length=1, max_length=80)


class DeviceEnrollmentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    connection: FinancialConnectionResponse
    # Shown once. The server keeps only a digest and cannot show it again.
    device_token: str
    intake_url: str


class EventReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    receipt_id: str
    external_id: str
    # Only recorded and unchanged mean the capture is held. out_of_window and
    # rejected can never be saved; not_saved may be sent again.
    outcome: Literal["recorded", "unchanged", "out_of_window", "rejected", "not_saved"]


class BatchReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    receipts: list[EventReceipt]


@devices_router.post("/devices", response_model=DeviceEnrollmentResponse, status_code=201)
def enroll_shortcuts_device(
    request: Request,
    body: DeviceEnrollmentRequest,
    context: ShortcutsContext = Depends(require_shortcuts_context),  # noqa: B008
) -> DeviceEnrollmentResponse:
    try:
        enrollment = context.connector.enroll(
            user_id=context.user_id, device_name=body.device_name
        )
    except DeviceLimitReached:
        raise problem(
            request,
            status_code=409,
            code="shortcuts_device_limit",
            title="Conflict",
            detail="Disconnect a device you no longer use before adding another.",
        ) from None
    return DeviceEnrollmentResponse(
        connection=connection_response(enrollment.connection),
        device_token=enrollment.token,
        intake_url=INTAKE_PATH,
    )


@intake_router.post("/events", response_model=EventReceipt, openapi_extra=_EVENT_BODY)
async def receive_shortcuts_event(
    request: Request,
    device: DeviceContext = Depends(require_shortcuts_device),  # noqa: B008
) -> EventReceipt:
    """Device-token only. Re-sending the same event returns the same receipt.

    A receipt is returned only for a held capture; anything else is an error,
    so a recipe that checks for ``receipt_id`` never mistakes it for saved.
    """

    event = await _json_body(request, MAX_EVENT_BYTES, ShortcutEvent)
    [receipt] = await _intake(request, device, [event])
    if receipt.outcome == "out_of_window":
        raise problem(
            request,
            status_code=422,
            code="shortcuts_event_out_of_window",
            title="Unprocessable Content",
            detail="The capture time is in the future or more than 30 days old.",
        )
    if receipt.outcome == "rejected":
        raise problem(
            request,
            status_code=422,
            code="shortcuts_event_invalid",
            title="Unprocessable Content",
            detail="The capture could not be accepted.",
        )
    if receipt.outcome == "not_saved":
        raise events_not_saved_problem(request)
    return receipt


@intake_router.post(
    "/events/batch", response_model=BatchReceipt, openapi_extra=_BATCH_BODY
)
async def receive_shortcuts_event_batch(
    request: Request,
    device: DeviceContext = Depends(require_shortcuts_device),  # noqa: B008
) -> BatchReceipt:
    """Pending captures saved while offline; idempotent per event."""

    batch = await _json_body(request, MAX_BATCH_BYTES, ShortcutEventBatch)
    return BatchReceipt(receipts=await _intake(request, device, batch.events))


async def _json_body(request: Request, cap: int, model: type[BaseModel]):  # noqa: ANN202
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > cap:
            raise problem(
                request,
                status_code=413,
                code="shortcuts_event_too_large",
                title="Content Too Large",
                detail="The capture is larger than allowed.",
            )
    try:
        return model.model_validate_json(bytes(body))
    except ValidationError as error:
        raise problem(
            request,
            status_code=422,
            code="shortcuts_event_invalid",
            title="Unprocessable Content",
            detail="The capture does not match the expected format.",
            context={"fields": sorted({_field(e) for e in error.errors()})},
        ) from None


def _field(error: dict) -> str:
    return ".".join(str(part) for part in error.get("loc", ())) or "body"


async def _intake(
    request: Request, device: DeviceContext, events: list[ShortcutEvent]
) -> list[EventReceipt]:
    if device.connector.hub.sink is None:
        raise intake_unavailable_problem(request)
    spend_event_budget(request, device, len(events))
    try:
        receipts: list[Receipt] = await run_in_threadpool(
            device.connector.intake, device.connection, events
        )
    except IntakeUnavailable:
        raise intake_unavailable_problem(request) from None
    except EventsNotSaved:
        raise events_not_saved_problem(request) from None
    except ConnectionEnded:
        raise device_unauthorized_problem(request) from None
    return [
        EventReceipt(
            receipt_id=r.receipt_id, external_id=r.external_id, outcome=r.outcome
        )
        for r in receipts
    ]
