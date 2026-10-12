"""Email receiving runtime: one capture worker per process, off unless configured."""

from __future__ import annotations

import asyncio
from contextlib import suppress

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


def start_email_intake(app) -> None:  # noqa: ANN001
    configure_email_intake(None)
    if not EmailIntakeSettings().capture_enabled:
        return
    pool = getattr(getattr(app, "state", None), "financial_accounts_pool", None)
    documents = documents_service()
    # Routes and the queue are Postgres rows; the in-memory app has no receiving.
    if pool is None or documents is None or api_state.PERSISTENCE_MODE != "supabase":
        return
    client = httpx.AsyncClient(timeout=20, follow_redirects=False, trust_env=False)
    key = EmailIntakeSettings().api_key.get_secret_value()
    provider = (
        ResendReceivingClient(client, key, RESEND_DOWNLOAD_HOSTS)
        if key and webhook_enabled()
        else None
    )
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


def email_receipt_flags(space_id: str) -> dict[str, tuple[tuple[str, ...], bool]]:
    """Per document: the deliveries it arrived in, and whether it is a grouped
    email original. Empty when email receiving is off."""

    if _runtime is None:
        return {}
    return {
        document: (tuple(sorted(relation["delivery_ids"])), relation["grouped"])
        for document, relation in _runtime.store.membership(space_id).items()
    }
