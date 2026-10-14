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
from argus.domain.ingestion.email_intake.provider import ResendReceivingClient
from argus.domain.ingestion.email_intake.service import (
    EmailCapture,
    grant_route_authority,
)
from argus.domain.ingestion.email_intake.store import PostgresEmailStore

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


def arrived_by_email(saved_at: datetime, first_received_at: datetime | None) -> bool:
    """A document whose earliest email arrived before it was saved was saved by
    that email. One saved before any email came by another way (a web upload),
    and the email that brought the same bytes later is a repeat of it."""

    return first_received_at is not None and first_received_at <= saved_at
