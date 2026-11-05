"""Provider-free browser fixture using the production receipt API and memory store.

Run from the repository root with PYTHONPATH=src:.:web and the local .venv.
Only this standalone process gets synthetic conversations; no shared DB is used.
"""

# ruff: noqa: E402
from __future__ import annotations

import os

# Never load this checkout's linked .env or contact a provider/shared database.
os.environ.update(
    {
        "PYTHON_DOTENV_DISABLED": "1",
        "CUADRAO_PERSISTENCE_MODE": "memory",
        "CUADRAO_CHECKPOINTER_MODE": "memory",
        "ARGUS_DEV_MEMORY_FALLBACK": "true",
        "NEXT_PUBLIC_MOCK_AUTH": "true",
        "CUADRAO_EVIDENCE_RECEIPT_SHARING_ENABLED": "true",
        "ARGUS_CONTEXT_PACKETS_ENABLED": "false",
        "ARGUS_MARKET_DATA_PROVIDER_MODE": "synthetic_unit_fixture",
        "CUADRAO_CORS_ALLOW_ORIGINS": "http://127.0.0.1:3604,http://localhost:3604",
        "OPENROUTER_API_KEY": "",
        "ALPACA_API_KEY": "",
        "ALPACA_SECRET_KEY": "",
        "PERPLEXITY_API_KEY": "",
        "POSTHOG_API_KEY": "",
    }
)

import argus.env

# The installed dotenv predates PYTHON_DOTENV_DISABLED. Disable project loading
# explicitly before importing the API, in this fixture process only.
argus.env.load_project_dotenv = lambda *args, **kwargs: False

from argus.api import state
from argus.api.main import app
from argus.api.public_excerpts import revoke_receipts_for_conversation
from argus.api.routers.evidence_receipts import reset_receipt_create_limiter_for_tests
from argus.api.schemas import Message
from argus.domain.backtest_job_scopes import CHAT_RUN_SCOPE
from argus.domain.backtest_message_projection import result_fact_bank
from argus.domain.backtesting.cards import build_result_card as generate_result_card
from argus.domain.computation_marker import computation_from_tool_card
from fastapi import HTTPException

from tests.domain.calculations.support import run_calculation
from tests.public_excerpt_factories import (
    build_artifact,
    build_conversation,
    build_run,
    generated_card_config,
    generated_card_metrics,
    generated_card_snapshot,
    stable_uuid,
    utc,
)

PUBLISHER_URL = (
    "https://investors.coca-colacompany.com/news-events/press-releases/detail/1112/"
    "coca-cola-reports-second-quarter-2024-results-and-raises-full-year-guidance"
)
BUNDLES = {}
state.supabase_gateway = None
state.store.reset()
user = state.store.get_or_create_dev_user()


def seed(language: str, index: int) -> None:
    spanish = language == "es-419"
    conversation_id = stable_uuid(index, prefix=604)
    conversation = build_conversation(conversation_id=conversation_id, language=language)
    conversation.title = (
        "Compras mensuales de Apple" if spanish else "Monthly Apple purchases"
    )
    state.store.conversations[conversation_id] = conversation
    state.store.conversation_owners[conversation_id] = user.id
    artifact = build_artifact(
        artifact_id=stable_uuid(index, prefix=605), title=conversation.title
    )
    run = build_run(run_id=stable_uuid(index, prefix=606))
    artifact.source_conversation_id = conversation_id
    artifact.source_run_id = run.id
    run.conversation_id = conversation_id
    run.config_snapshot.update(generated_card_snapshot("dca_accumulation"))
    run.config_snapshot["resolved_strategy"]["entry_rule"] = {
        "type": "periodic",
        "cadence": "monthly",
    }
    run.metrics = generated_card_metrics()
    run.conversation_result_card = generate_result_card(
        generated_card_config("dca_accumulation"), run.metrics, language=language
    )
    run.conversation_result_card.update(
        {
            "evidence_artifact_id": artifact.id,
            "idea_id": artifact.idea_id,
            "idea_version_id": artifact.idea_version_id,
        }
    )
    state.store.evidence_artifacts[artifact.id] = artifact
    state.store.evidence_artifact_owners[artifact.id] = user.id
    state.store.backtest_runs[run.id] = run
    state.store.backtest_run_owners[run.id] = user.id
    messages = []

    def pair(question: str, answer: str, metadata: dict) -> None:
        for role, text in (("user", question), ("assistant", answer)):
            position = len(messages)
            messages.append(
                Message(
                    id=stable_uuid(index * 100 + position, prefix=607),
                    conversation_id=conversation_id,
                    role=role,
                    content=text,
                    metadata=metadata if role == "assistant" else {},
                    created_at=utc(position),
                )
            )

    completed = {"agent_runtime_turn": {"terminal": True, "status": "completed"}}
    pair(
        "Prueba compras de AAPL de $200 al mes."
        if spanish
        else "Test buying $200 of AAPL each month.",
        (
            "El resultado histórico está listo. "
            if spanish
            else "The historical result is ready. "
        )
        + f"[Coca-Cola]({PUBLISHER_URL})",
        {
            "chat_action": {"type": "run_backtest"},
            "result_run_id": run.id,
            "result_card": run.conversation_result_card,
            "result_fact_bank": result_fact_bank(run),
            "conversation_mode": "result_review",
        },
    )
    job_id = stable_uuid(index, prefix=608)
    state.store.backtest_jobs[job_id] = {
        "id": job_id,
        "user_id": user.id,
        "conversation_id": conversation_id,
        "request_message_id": messages[0].id,
        "result_run_id": run.id,
        "operation_scope": CHAT_RUN_SCOPE,
        "status": "succeeded",
        "updated_at": messages[-1].created_at.isoformat(),
        "finished_at": messages[-1].created_at.isoformat(),
    }
    research = {
        "schema_version": "argus_research/v1",
        "shape": "balanced",
        "sources": [
            {
                "title": "Coca-Cola results",
                "domain": "investors.coca-colacompany.com",
                "url": PUBLISHER_URL,
                "source_date": "2024-07-23",
            }
        ],
        "retrieved_at": utc().isoformat(),
        "anchor_symbols": ["AAPL"],
        "asset_class": "equity",
    }
    pair(
        "Explica el resultado." if spanish else "Explain the result.",
        (
            "Las compras mensuales continuaron durante las caídas. "
            if spanish
            else "Monthly purchases continued during declines. "
        )
        + f"[Coca-Cola]({PUBLISHER_URL})",
        {**completed, "research": research},
    )
    pair(
        "¿Cuál fue la diferencia con SPY?"
        if spanish
        else "What was the gap against SPY?",
        "La diferencia fue de 9.3 puntos porcentuales."
        if spanish
        else "The gap was 9.3 percentage points.",
        {**completed, "research": {**research, "sources": []}},
    )
    pair(
        "Dame el contexto completo." if spanish else "Give me the full context.",
        (
            (
                "Las fuentes describen los resultados de la empresa y sus riesgos. "
                if spanish
                else "The sources describe the company results and the risks that remain. "
            )
            * 75
        )
        + f"[Coca-Cola]({PUBLISHER_URL})",
        {**completed, "research": research},
    )
    pair(
        "¿Qué significa diversificar?" if spanish else "What does diversification mean?",
        "Es distribuir el dinero entre distintas inversiones."
        if spanish
        else "It means spreading money across different investments.",
        completed,
    )
    calculation = run_calculation(
        "price_multiple",
        {
            "currency": "USD",
            "symbol": "AAPL",
            "price": 150,
            "per_share": 6.25,
            "multiple": None,
            "sources": {
                "price": {
                    "kind": "page",
                    "title": "Apple quote",
                    "url": "https://www.nasdaq.com/market-activity/stocks/aapl",
                    "date": utc().date().isoformat(),
                }
            },
        },
    ).model_copy(update={"artifact_id": stable_uuid(index, prefix=609)})
    pair(
        "¿Cuál es el múltiplo a $150 y ganancias de $6.25 por acción?"
        if spanish
        else "What is the multiple at $150 and earnings of $6.25 per share?",
        "El múltiplo es 24 veces las ganancias."
        if spanish
        else "The multiple is 24 times earnings.",
        {
            **completed,
            "tool_result_cards": [calculation.model_dump(mode="json")],
            "computation": computation_from_tool_card(calculation).model_dump(
                mode="json"
            ),
        },
    )
    pair(
        "Cambia el aporte a $300." if spanish else "Change the contribution to $300.",
        "Confirma el cambio antes de ejecutar."
        if spanish
        else "Confirm the change before running.",
        {**completed, "conversation_mode": "confirmation", "confirmation": {}},
    )
    state.store.messages[conversation_id] = messages
    BUNDLES[language] = {
        "conversation": conversation.model_dump(mode="json"),
        "messages": [m.model_dump(mode="json") for m in messages],
        "user_id": user.id,
    }


seed("en", 1)
seed("es-419", 2)


@app.post("/__fixture/reset")
def reset_fixture():
    """Reset only this isolated process so interrupted browser runs are repeatable."""
    global user
    state.store.reset()
    user = state.store.get_or_create_dev_user()
    reset_receipt_create_limiter_for_tests()
    seed("en", 1)
    seed("es-419", 2)
    return {"reset": True}


@app.get("/__fixture/{language}")
def fixture(language: str):
    if language not in BUNDLES:
        raise HTTPException(404)
    return BUNDLES[language]


@app.post("/__fixture/{language}/delete")
def delete_fixture(language: str):
    conversation_id = BUNDLES[language]["conversation"]["id"]
    state.store.conversations[conversation_id].deleted_at = utc(999)
    return {
        "revoked": revoke_receipts_for_conversation(
            user_id=user.id, conversation_id=conversation_id
        )
    }


# Disallow accidental provider work even if a browser fixture is incomplete.
@app.middleware("http")
async def provider_free(request, call_next):
    if request.url.path.endswith("/chat/stream") or request.url.path.endswith(
        "/backtests/run"
    ):
        from fastapi.responses import JSONResponse

        return JSONResponse(
            {"detail": "Provider calls are disabled in this fixture."}, status_code=403
        )
    return await call_next(request)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8604)
