"""Post-turn memory recall annotation for the chat surface.

S10 boundary: this runs only after interpretation, routing, and any
simulation have fully completed, and it only annotates the final assistant
message. Memory never reaches the interpreter's input, a routing decision, or
a simulation parameter. Recall failures never break the turn. Only a Personal
conversation recalls: memory is Personal and a Business chat never reads it.
"""

from __future__ import annotations

import asyncio
from typing import Any

from loguru import logger

from argus.api.conversation_surface import conversation_scope
from argus.api.guest_access import AccountContext
from argus.api.personalization_memory import (
    memory_service,
    personalization_memory_exposed,
)
from argus.api.schemas import User
from argus.domain.owner_scope import PERSONAL
from argus.memory.contracts import MemoryUsePurpose
from argus.memory.subject import (
    MemoryAccountKind,
    MemorySubject,
    PersonalizationMemoryUnavailable,
)

MEMORY_RECALL_LIMIT = 2


def memory_recalls_for_turn(
    *,
    user: User,
    account: AccountContext,
    conversation_id: str,
    user_message: str | None,
    memory_opt_out: bool,
) -> list[dict[str, Any]] | None:
    """Bounded saved-decision recall for the completed turn, or None."""

    if account.kind != "registered" or memory_opt_out:
        return None
    query = (user_message or "").strip()
    if not query:
        return None
    if not personalization_memory_exposed(user):
        return None
    service = memory_service()
    if service is None:
        return None
    subject = MemorySubject(
        owner_id=account.user_id,
        kind=MemoryAccountKind.REGISTERED,
    )
    try:
        scope = conversation_scope(
            user_id=account.user_id, conversation_id=conversation_id
        )
        if scope != PERSONAL:
            return None
        retrieved = service.retrieve(
            subject,
            query,
            MemoryUsePurpose.REVISIT_SAVED_DECISION,
            limit=MEMORY_RECALL_LIMIT,
        )
    except PersonalizationMemoryUnavailable:
        return None
    except Exception as exc:
        logger.warning(
            "Memory recall skipped after error; turn continues without it",
            failure_mode=type(exc).__name__,
        )
        return None
    if not retrieved:
        return None
    return [
        {
            "record_id": memory.record.id,
            "label": memory.record.label,
            "value": memory.record.value,
            "category": memory.record.category.value,
        }
        for memory in retrieved
    ]


async def memory_recalls_for_turn_async(
    *,
    user: User,
    account: AccountContext,
    conversation_id: str,
    user_message: str | None,
    memory_opt_out: bool,
) -> list[dict[str, Any]] | None:
    """Same recall, off the event loop.

    Retrieval makes synchronous network calls; the API runs one worker.
    """

    return await asyncio.to_thread(
        memory_recalls_for_turn,
        user=user,
        account=account,
        conversation_id=conversation_id,
        user_message=user_message,
        memory_opt_out=memory_opt_out,
    )


async def annotate_memory_recalls(
    *targets: dict[str, Any],
    user: User,
    account: AccountContext,
    conversation_id: str,
    user_message: str | None,
    memory_opt_out: bool,
) -> None:
    """Write the turn's recalls, when there are any, into each target payload."""

    recalls = await memory_recalls_for_turn_async(
        user=user,
        account=account,
        conversation_id=conversation_id,
        user_message=user_message,
        memory_opt_out=memory_opt_out,
    )
    if recalls:
        for target in targets:
            target["memory_recalls"] = recalls
