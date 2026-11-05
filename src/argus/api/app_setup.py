from __future__ import annotations

import functools
import os
from contextlib import asynccontextmanager
from typing import get_args

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger
from pydantic_core import ErrorType

from argus.api import state as api_state
from argus.api.age_confirmation import age_confirmation_response_code
from argus.api.apple_sign_in import AppleCaptureFlagGateMiddleware
from argus.api.dependencies import (
    request_id_middleware,
    validate_startup_configuration,
    validation_problem_body,
)
from argus.api.public_excerpts import EvidenceReceiptFlagGateMiddleware
from argus.llm.openrouter_key_policy import validate_hosted_openrouter_configuration
from argus.log_sink import configure_logging

configure_logging()

DEFAULT_CORS_ALLOW_ORIGINS = (
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
)


@functools.lru_cache(maxsize=16)
def _cors_allow_origins_for(configured: str) -> tuple[str, ...]:
    extra_origins = [
        origin.strip()
        for origin in configured.replace("\n", ",").split(",")
        if origin.strip()
    ]
    return tuple(dict.fromkeys([*DEFAULT_CORS_ALLOW_ORIGINS, *extra_origins]))


def cors_allow_origins() -> list[str]:
    configured = os.getenv("CUADRAO_CORS_ALLOW_ORIGINS", "")
    return list(_cors_allow_origins_for(configured))


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_startup_configuration()
    validate_hosted_openrouter_configuration()
    checkpointer_cm = None
    if api_state.CHECKPOINTER_MODE == "postgres":
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        checkpointer_cm = AsyncPostgresSaver.from_conn_string(
            api_state.DATABASE_URL,
            serde=api_state.build_agent_runtime_checkpoint_serde(),
        )
        checkpointer = await checkpointer_cm.__aenter__()
        await checkpointer.setup()
    else:
        if api_state.PERSISTENCE_MODE == "supabase":
            logger.info(
                "Using Supabase product persistence with memory LangGraph checkpointer",
                checkpointer_mode=api_state.CHECKPOINTER_MODE,
            )
        checkpointer = api_state.build_agent_runtime_checkpointer()

    app.state.agent_runtime_checkpointer = checkpointer
    app.state.agent_runtime_checkpointer_cm = checkpointer_cm
    app.state.agent_runtime_workflow = None
    from argus.api.personalization_memory import (
        start_personalization_memory,
        stop_personalization_memory,
    )

    start_personalization_memory(app)
    from argus.api.financial_accounts import (
        start_financial_accounts,
        stop_financial_accounts,
    )

    start_financial_accounts(app)
    from argus.api.fiscal_operations import start_fiscal, stop_fiscal

    start_fiscal(app)
    from argus.api.profile_images import start_profile_images, stop_profile_images

    start_profile_images(app)
    from argus.api.ingestion import start_ingestion, stop_ingestion

    start_ingestion(app)
    from argus.api.bank_matching import start_bank_matching, stop_bank_matching

    start_bank_matching(app)
    from argus.api.email_intake import start_email_intake, stop_email_intake

    start_email_intake(app)
    from argus.api.whatsapp_worker import start_worker, stop_worker

    start_worker(app)
    from argus.api.households import start_households, stop_households

    start_households(app)
    from argus.api.apple_sign_in import start_apple_sign_in, stop_apple_sign_in

    start_apple_sign_in(app)
    from argus.api.chat.research_pricing_evidence import ResearchPricingRecorder
    from argus.domain.research.billing import set_unpriced_spend_recorder

    research_pricing_recorder = ResearchPricingRecorder()
    set_unpriced_spend_recorder(research_pricing_recorder)
    try:
        yield
    finally:
        set_unpriced_spend_recorder(None)
        await research_pricing_recorder.close()
        stop_personalization_memory(app)
        stop_households(app)
        stop_apple_sign_in(app)
        await stop_email_intake(app)
        from argus.api.whatsapp import drain_whatsapp

        await drain_whatsapp()
        await stop_worker(app)
        stop_ingestion(app)
        stop_bank_matching(app)
        stop_profile_images(app)
        await stop_fiscal(app)
        stop_financial_accounts(app)
        if checkpointer_cm is not None:
            await checkpointer_cm.__aexit__(None, None, None)


async def http_exception_handler(request: Request, exc: HTTPException):  # type: ignore[no-untyped-def]
    if isinstance(exc.detail, dict) and "code" in exc.detail:
        body = exc.detail
    else:
        body = {
            "type": "https://api.argus.app/problems/http-error",
            "title": "Request Failed",
            "status": exc.status_code,
            "detail": str(exc.detail),
            "code": "http_error",
            "request_id": request.state.request_id,
        }

    origin = request.headers.get("origin")
    headers = dict(exc.headers or {})
    if origin in cors_allow_origins():
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"
    return JSONResponse(body, status_code=exc.status_code, headers=headers)


async def validation_exception_handler(  # type: ignore[no-untyped-def]
    request: Request,
    exc: RequestValidationError,
):
    if request.method == "POST" and request.url.path == "/api/v1/business/receipts":
        fields = {
            "header",
            "query",
            "body",
            "path",
            "x-document-filename",
            "x-extraction-consent",
            "idempotency-key",
            "x-business-grant",
        }
        for error in exc.errors():
            location = ".".join(
                part.lower()
                if isinstance(part, str) and part.lower() in fields
                else "unknown"
                for part in error.get("loc", ())
            )
            error_type = error.get("type")
            logger.warning(
                "receipt_upload_validation_failed field={} type={}",
                location or "unknown",
                error_type if error_type in get_args(ErrorType) else "unknown",
            )
    body = validation_problem_body(
        getattr(request.state, "request_id", api_state.store.new_id()),
        exc.errors(),
    )
    code = age_confirmation_response_code(exc.errors())
    if code is not None:
        body["code"] = code

    origin = request.headers.get("origin")
    headers: dict[str, str] = {}
    if origin in cors_allow_origins():
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"
    return JSONResponse(body, status_code=422, headers=headers)


def add_core_middleware_and_handlers(app: FastAPI) -> None:
    # Added before request_id_middleware so it sits inside it: a gated 404 still
    # carries X-Request-Id, exactly as a genuine unmatched route does.
    app.add_middleware(EvidenceReceiptFlagGateMiddleware)
    app.add_middleware(AppleCaptureFlagGateMiddleware)
    app.middleware("http")(request_id_middleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_allow_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Retry-After", "X-Request-Id"],
    )
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
