"""Email receiving runtime: one capture worker per process, off unless configured."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from datetime import datetime

import httpx
from loguru import logger

from argus.api import state as api_state
from argus.api.documents import documents_service
from argus.api.ingestion import ingestion_enabled
from argus.domain.business.config import business_pilot_enabled
from argus.domain.ingestion.documents.config import load_document_extraction_settings
from argus.domain.ingestion.email_intake.config import EmailIntakeSettings
from argus.domain.ingestion.email_intake.models import EmailDelivery, EmailDeliveryPart
from argus.domain.ingestion.email_intake.provider import ResendReceivingClient
from argus.domain.ingestion.email_intake.service import (
    EmailCapture,
    grant_route_authority,
)
from argus.domain.ingestion.email_intake.standing import (
    EmailStanding,
    email_standing,
)
from argus.domain.ingestion.email_intake.store import EmailRelation, PostgresEmailStore

RESEND_DOWNLOAD_HOSTS = ("cdn.resend.app",)

_runtime: EmailCapture | None = None


def email_intake() -> EmailCapture | None:
    return _runtime


def configure_email_intake(runtime: EmailCapture | None) -> None:
    global _runtime
    _runtime = runtime


def capture_enabled() -> bool:
    return (
        EmailIntakeSettings().capture_enabled
        and business_pilot_enabled()
        and ingestion_enabled()
        and load_document_extraction_settings().enabled
    )


def webhook_enabled() -> bool:
    settings = EmailIntakeSettings()
    return (
        capture_enabled()
        and settings.receiving_enabled
        and bool(settings.webhook_secret.get_secret_value())
    )


async def _drain(runtime: EmailCapture) -> None:
    while True:
        try:
            did_work = await runtime.next()
        except Exception:
            logger.warning("Email intake worker could not complete a delivery")
            did_work = False
        await asyncio.sleep(0.05 if did_work else 2)


def intake_conditions(app) -> dict[str, bool]:  # noqa: ANN001
    """Every condition email receiving needs, by name, so a startup log can say
    which one failed. Names only: no value is read into the result."""

    settings = EmailIntakeSettings()
    return {
        "email_capture_flag": settings.capture_enabled,
        "business_pilot_flag": business_pilot_enabled(),
        "ingestion_flag": ingestion_enabled(),
        "document_extraction_flag": load_document_extraction_settings().enabled,
        "persistence_supabase": api_state.PERSISTENCE_MODE == "supabase",
        "financial_accounts_pool": getattr(
            getattr(app, "state", None), "financial_accounts_pool", None
        )
        is not None,
        "documents_service": documents_service() is not None,
        "receiving_flag": settings.receiving_enabled,
        "webhook_secret_present": bool(settings.webhook_secret.get_secret_value()),
        "api_key_present": bool(settings.api_key.get_secret_value()),
    }


# The queue and the routes need these; without them nothing starts.
_RUNTIME_CONDITIONS = (
    "email_capture_flag",
    "persistence_supabase",
    "financial_accounts_pool",
    "documents_service",
)


def _queued_email_reader(route, connection_id: str):
    from uuid import UUID

    from argus.api.business_drafts import bind_to_grant
    from argus.domain.business.contracts.authority import TrustedActor
    from argus.domain.owner_scope import BusinessSpace

    documents = documents_service()
    scope = BusinessSpace(route.space_id)
    current = documents.get(
        user_id=route.principal_id, connection_id=connection_id, scope=scope
    )
    if current.status != "queued":
        return None
    actions = documents.business_actions
    context = actions.resolve_actor(
        TrustedActor(
            actor_id=UUID(route.granted_by),
            actor_kind="member",
            space_id=UUID(route.space_id),
        ),
        grant_id=UUID(route.grant_id),
    )
    service, _ = bind_to_grant(documents, documents.hub, actions, context, "prepare")
    return service, scope


async def _read_receipt(route, connection_id: str) -> None:
    from fastapi import BackgroundTasks

    from argus.api.documents import dispatch_preparation

    reader = await asyncio.to_thread(_queued_email_reader, route, connection_id)
    if reader is None:
        return
    service, scope = reader
    tasks = BackgroundTasks()
    try:
        await dispatch_preparation(
            service, route.principal_id, connection_id, tasks, scope=scope
        )
    except Exception as error:
        await asyncio.to_thread(
            service.release_queued,
            user_id=route.principal_id,
            connection_id=connection_id,
            scope=scope,
            code=getattr(error, "code", "document_delivery_failed"),
        )
        raise
    await tasks()


def start_email_intake(app) -> None:  # noqa: ANN001
    configure_email_intake(None)
    conditions = intake_conditions(app)
    missing = [name for name, held in conditions.items() if not held]
    if not conditions["email_capture_flag"]:
        return
    if any(name in missing for name in _RUNTIME_CONDITIONS):
        # Routes and the queue are Postgres rows; the in-memory app has no receiving.
        logger.warning(
            "Email intake did not start; missing: " + ", ".join(missing),
            missing=missing,
        )
        return
    pool = app.state.financial_accounts_pool
    documents = documents_service()
    client = httpx.AsyncClient(timeout=20, follow_redirects=False, trust_env=False)
    key = EmailIntakeSettings().api_key.get_secret_value()
    provider = (
        ResendReceivingClient(client, key, RESEND_DOWNLOAD_HOSTS)
        if key and webhook_enabled()
        else None
    )
    if provider is None:
        # The names go in the text: hosted log viewers show the message, not the fields.
        logger.warning(
            "Email intake started without a receiving provider;"
            " the Resend webhook answers 404; missing: " + ", ".join(missing),
            missing=missing,
        )
    else:
        logger.info("Email intake started with the receiving provider")
    configure_email_intake(
        EmailCapture(
            PostgresEmailStore(pool),
            documents,
            grant_route_authority(pool),
            provider,
            capture_enabled,
            webhook_enabled,
            _read_receipt,
        )
    )
    app.state.email_intake_client = client
    app.state.email_intake_task = asyncio.create_task(_drain(_runtime))


async def stop_email_intake(app) -> None:  # noqa: ANN001
    task = getattr(app.state, "email_intake_task", None)
    if task is not None:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        app.state.email_intake_task = None
    client = getattr(app.state, "email_intake_client", None)
    if client is not None:
        await client.aclose()
        app.state.email_intake_client = None
    configure_email_intake(None)


def email_receipt_flags(
    space_id: str,
) -> dict[str, tuple[tuple[str, ...], bool, datetime | None]]:
    """Per document: the deliveries it arrived in, earliest first; whether it is
    a grouped email original; and when the earliest delivery arrived. Empty
    when email receiving is off."""

    if _runtime is None:
        return {}
    return {
        document: (
            tuple(relation["delivery_ids"]),
            relation["grouped"],
            relation["first_received_at"],
        )
        for document, relation in _runtime.store.membership(space_id).items()
    }


def email_review_note(space_id: str, delivery_ids, store=None) -> str | None:  # noqa: ANN001
    """The review note of the first of these deliveries that carries one, from
    ``store`` or the running intake's store."""

    if store is None and _runtime is None:
        return None
    store = store or _runtime.store
    for delivery_id in sorted(delivery_ids):
        delivery = store.get(delivery_id, space_id)
        if delivery is not None and delivery.review_note:
            return delivery.review_note
    return None


def part_repeat(
    runtime: EmailCapture,
    delivery: EmailDelivery,
    part: EmailDeliveryPart,
    relations: dict[str, EmailRelation],
) -> tuple[str | None, bool]:
    """Whether a part's document was already saved: ``(repeat_of_delivery_id,
    repeat_of_upload)``. An earlier delivery brought it, or it was saved another
    way, a web upload, before this email arrived."""

    earlier = relations.get(part.document_id or "", {}).get("delivery_ids") or []
    first = earlier[0] if earlier else None
    repeat_of_delivery = first if first and first != delivery.id else None
    if not part.document_id or repeat_of_delivery is not None:
        return repeat_of_delivery, False
    # The Business, not the person, is the unit: a file anyone saved in this
    # Business before the email came makes the email the repeat.
    draft = runtime.documents.store.draft(
        user_id=delivery.principal_id, connection_id=part.document_id
    )
    earliest = (
        runtime.documents.store.earliest_saved(
            space_id=delivery.space_id, sha256=draft.sha256
        )
        if draft is not None
        else None
    )
    return None, earliest is not None and earliest < delivery.received_at


def email_standings(space_id: str) -> list[EmailStanding]:
    """The standing of every email in this Business that is a Bandeja row of its
    own. Empty when email receiving is off."""

    if _runtime is None:
        return []
    runtime = _runtime
    relations = runtime.store.membership(space_id)
    parts = runtime.store.parts_by_delivery(space_id)
    standings = (
        email_standing(
            delivery,
            parts.get(delivery.id, []),
            lambda part, delivery=delivery: any(
                part_repeat(runtime, delivery, part, relations)
            ),
        )
        for delivery in runtime.store.list(space_id, limit=None)
    )
    return [standing for standing in standings if standing is not None]


def arrived_by_email(saved_at: datetime, first_received_at: datetime | None) -> bool:
    """A document whose earliest email arrived before it was saved was saved by
    that email. One saved before any email came by another way (a web upload),
    and the email that brought the same bytes later is a repeat of it."""

    return first_received_at is not None and first_received_at <= saved_at
