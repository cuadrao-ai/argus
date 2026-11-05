"""The owner's permission to read the receipts they send by WhatsApp.

It is the same one switch and the same table as the agent permission, with its
own scope, so a receipt permission never counts as an agent permission (the
route and the scope differ, and the agent checks both).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from argus.domain.ingestion.whatsapp.ai_consent import RECEIPT_SCOPE, AIConsentStore
from argus.llm.openrouter import resolve_openrouter_model


def receipt_provider_route() -> dict[str, Any]:
    """The model that reads a receipt. The web shows it under the disclosure."""

    model = resolve_openrouter_model(task="document_extraction")
    if not model:
        raise ValueError("no receipt reading model is configured")
    return {"gateway": "openrouter", "interpretation": [{"model": model}], "reply": []}


def receipt_consent_store(pool) -> AIConsentStore:  # noqa: ANN001
    return AIConsentStore(pool, receipt_provider_route, RECEIPT_SCOPE)


def receipt_reading_enabled(store: AIConsentStore, owner_id: str) -> bool:
    """True only while the owner's permission is on, current and unrevoked."""

    return bool(store.status(UUID(owner_id))["enabled"])
