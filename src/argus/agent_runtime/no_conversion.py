"""Argus never converts between currencies.

A request to convert an amount gets one fixed reply, written here rather than by
a model, so no rate, search or conversion math can reach the answer. Each amount
stays in the currency it was paid or collected in.
"""

from __future__ import annotations

from loguru import logger

from argus.agent_runtime.stages.interpret_types import (
    StageResult,
    StructuredInterpretation,
)
from argus.agent_runtime.state.models import UserState

CURRENCY_CONVERSION_DECLINED = "currency_conversion_declined"
NO_CONVERSION_REPLIES = {
    "es-419": (
        "No convierto entre monedas. Cada monto se queda en la moneda en que lo "
        "pagaste o lo cobraste. Puedo mostrarte tus montos guardados por moneda, "
        "o sumar una moneda a la vez."
    ),
    "en": (
        "I don't convert between currencies. Each amount stays in the currency "
        "you paid or collected it in. I can show your stored amounts by currency, "
        "or total one currency at a time."
    ),
}


def no_conversion_reply(language: str | None) -> str:
    return NO_CONVERSION_REPLIES[
        "es-419" if str(language or "").startswith("es") else "en"
    ]


def no_conversion_stage_result(
    interpretation: StructuredInterpretation, *, user: UserState
) -> StageResult | None:
    """The fixed reply when the primary read typed a conversion request."""
    query = interpretation.research_query
    if query is None or not query.currency_conversion:
        return None
    from argus.agent_runtime.research_grounded import research_decision

    logger.info(
        "Currency conversion declined",
        failure_classification=CURRENCY_CONVERSION_DECLINED,
    )
    return StageResult(
        outcome="ready_to_respond",
        decision=research_decision(interpretation, user, CURRENCY_CONVERSION_DECLINED),
        stage_patch={"assistant_response": no_conversion_reply(user.language_preference)},
    )
