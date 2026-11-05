"""Local Argus API for the Any grounded math browser evidence.

Memory persistence, mock auth, the real interpreter and research provider,
live asset and market data so any ticker resolves, and receipt sharing on.
Provider keys come from GM_ENV_FILE, which is only read. Scenes a live turn
cannot produce on demand are seeded from real code, never hand-written JSON:
a long transcript for the conversation rail, a provider outage card, a
decision whose stored inputs no longer run, and a withheld retrieval with its
inputs typeable. Their ids are written to GM_SEED_OUT. With GM_RESTORE_TURNS,
the recorded smoke conversations in that folder are restored as they were
stored (drivers/restore_turns.py), since a restart empties the memory store.
API on 8620; the web dev server runs on 3620.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv

TREE = Path(os.environ["GM_TREE"]).resolve()
sys.path.insert(0, str(TREE / "src"))
sys.path.insert(0, str(TREE))
load_dotenv(os.environ.get("GM_ENV_FILE") or TREE / ".env", override=False)
API_PORT = int(os.getenv("GM_API_PORT", "8620"))
WEB_PORT = int(os.getenv("GM_WEB_PORT", "3620"))
WEB_ORIGIN = f"http://127.0.0.1:{WEB_PORT}"
os.environ.update(
    {
        "CUADRAO_PERSISTENCE_MODE": "memory",
        "ARGUS_DEV_MEMORY_FALLBACK": "true",
        "CUADRAO_CHECKPOINTER_MODE": "memory",
        "CUADRAO_MOCK_AUTH": "true",
        "ARGUS_MARKET_DATA_PROVIDER_MODE": "live_provider",
        "ARGUS_ASSET_PROVIDER_MODE": "live_provider",
        "ARGUS_RESEARCH_RAIL_ENABLED": "true",
        "CUADRAO_EVIDENCE_RECEIPT_SHARING_ENABLED": "true",
        "ARGUS_ENABLE_PERSONALIZATION_MEMORY": "false",
        "CUADRAO_CORS_ALLOW_ORIGINS": f"{WEB_ORIGIN},http://localhost:{WEB_PORT}",
        "ARGUS_APP_ORIGIN": WEB_ORIGIN,
        "ARGUS_BACKTEST_JOBS_SHADOW_ENABLED": "false",
        "ARGUS_BACKTEST_JOBS_DISPATCH_ENABLED": "false",
        "ARGUS_BACKTEST_WORKFLOW_EXECUTION_ENABLED": "false",
        "ENABLE_MARKET_DATA_CACHE": "false",
        "DATABASE_URL": "",
        "POSTHOG_PROJECT_TOKEN": "",
    }
)
import httpx  # noqa: E402
import uvicorn  # noqa: E402
from argus.api.main import app  # noqa: E402
from argus.domain.research import perplexity_agent as _agent  # noqa: E402

_parse_packet = _agent._packet_from_response


def _recorded_packet(*args, **kwargs):
    """Every parsed research packet, kept under GM_PACKETS_OUT so a typed answer
    can be replayed through the publisher without paying for it again."""
    packet = _parse_packet(*args, **kwargs)
    folder = os.environ.get("GM_PACKETS_OUT")
    if folder:
        Path(folder).mkdir(parents=True, exist_ok=True)
        name = f"{time.strftime('%Y%m%dT%H%M%S')}-{uuid4().hex[:6]}.json"
        (Path(folder) / name).write_text(packet.model_dump_json(indent=2))
    return packet


_agent._packet_from_response = _recorded_packet


def _seed() -> None:
    base = f"http://127.0.0.1:{API_PORT}/api/v1"
    for _ in range(120):
        try:
            if httpx.get(f"{base}/me", timeout=2).status_code == 200:
                break
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    from argus.agent_runtime import research_grounded as grounded
    from argus.agent_runtime.stages.interpret_types import StructuredInterpretation
    from argus.agent_runtime.state.models import StrategySummary, UserState
    from argus.api import state as api_state
    from argus.api.message_store import create_message, memory_conversation
    from argus.domain.capability_registry import get_tool_catalog
    from argus.domain.computation_marker import (
        computation_from_tool_card,
        computation_from_tool_cards,
    )
    from argus.domain.research.contracts import ResearchPacket
    from argus.domain.tool_contracts import (
        ToolCall,
        ToolFailure,
        ToolOutcome,
        ToolResultCard,
    )

    from tests.domain.calculations.support import run_calculation

    owner = httpx.get(f"{base}/me", timeout=5).json()["user"]["id"]
    catalog = get_tool_catalog()
    seeds: dict[str, dict[str, str]] = {}
    if os.environ.get("GM_RESTORE_TURNS"):
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from restore_turns import restore_recorded_turns

        seeds["restored"] = restore_recorded_turns(
            Path(os.environ["GM_RESTORE_TURNS"]), owner=owner
        )
        print("restored", len(seeds["restored"]), flush=True)

    def conversation(title: str, language: str) -> str:
        return memory_conversation(
            title=title, title_source="user_renamed", language=language, user_id=owner
        ).id

    def say(
        conversation_id: str, role: str, content: str, metadata: dict | None = None
    ) -> str:
        return create_message(
            user_id=owner,
            conversation_id=conversation_id,
            role=role,
            content=content,
            metadata=metadata or {},
        ).id

    def answer(
        conversation_id: str,
        card: ToolResultCard,
        content: str,
        extra: dict | None = None,
    ) -> str:
        card = card.model_copy(update={"artifact_id": str(uuid4())})
        metadata = {
            "tool_result_cards": [card.model_dump(mode="json")],
            "computation": computation_from_tool_card(card).model_dump(mode="json"),
            "agent_runtime_turn": {"terminal": True, "status": "completed"},
            **(extra or {}),
        }
        return say(conversation_id, "assistant", content, metadata)

    loan = {
        "direction": "borrow",
        "currency": "USD",
        "present_value": 30000,
        "payment": None,
        "future_value": 0,
        "annual_rate_pct": 7,
        "periods": 60,
    }
    multiple = {
        "currency": "USD",
        "symbol": "AAPL",
        "price": 230,
        "per_share": 6.5,
        "multiple": None,
    }
    growth = {
        "currency": "USD",
        "start_value": 10000,
        "contribution": 200,
        "end_value": None,
        "annual_rate_pct": 5,
        "periods": 120,
        "inflation_rate_pct": 3,
    }
    below_interest = {
        "direction": "borrow",
        "currency": "USD",
        "present_value": 180000,
        "payment": 2000,
        "future_value": 0,
        "annual_rate_pct": 14,
        "periods": None,
    }

    for language, lead in (
        ("en", "Here is that calculation."),
        ("es-419", "Aquí está ese cálculo."),
    ):
        rail = conversation(
            "Rail: three computed answers" if language == "en" else "Riel: tres cálculos",
            language,
        )
        turns = [
            (
                "What would a 30,000 car loan at 7% for five years cost a month?",
                run_calculation("time_value", loan),
            ),
            (
                "And is Apple expensive at 230 with 6.50 in earnings?",
                run_calculation("price_multiple", multiple),
            ),
            (
                "If I keep 10,000 and add 200 a month at 5% for ten years?",
                run_calculation("growth_projection", growth),
            ),
            (
                "I owe 180,000 at 14% and pay 2,000 a month. When is it paid?",
                run_calculation("time_value", below_interest),
            ),
        ]
        for question, card in turns:
            say(rail, "user", question)
            answer(rail, card, lead)
            say(rail, "user", "Thanks, that helps.")
            say(
                rail,
                "assistant",
                "Glad it helps. Change any input on the card to recompute it.",
            )
        seeds[f"rail-{language}"] = {"conversation_id": rail}

        unsolved = conversation(
            "Inputs with no solution" if language == "en" else "Datos sin solución",
            language,
        )
        say(
            unsolved,
            "user",
            "I owe 180,000 at 14% and pay 2,000 a month. When is it paid?",
        )
        seeds[f"no-solution-{language}"] = {
            "conversation_id": unsolved,
            "message_id": answer(
                unsolved, run_calculation("time_value", below_interest), lead
            ),
        }

        outage = conversation(
            "Outage card" if language == "en" else "Tarjeta con falla del proveedor",
            language,
        )
        say(
            outage,
            "user",
            "What would a 30,000 car loan at 7% for five years cost a month?",
        )
        declaration = catalog.get("time_value")
        card = declaration.result_card(
            call=ToolCall(
                tool_name="time_value", call_id=f"seed-{uuid4()}", arguments=loan
            ),
            outcome=ToolOutcome(
                status="unavailable", failure=ToolFailure(code="tool_execution_failed")
            ),
            artifact_id=str(uuid4()),
        )
        seeds[f"outage-{language}"] = {
            "conversation_id": outage,
            "message_id": answer(outage, card, lead),
        }

        stale = conversation(
            "Decision that cannot re-run"
            if language == "en"
            else "Decisión que no se puede recalcular",
            language,
        )
        say(
            stale,
            "user",
            "What would a 30,000 car loan at 7% for five years cost a month?",
        )
        stale_message = answer(stale, run_calculation("time_value", loan), lead)
        decided = httpx.post(
            f"{base}/conversations/{stale}/messages/{stale_message}/decision",
            json={"decision_state": "watching"},
            timeout=10,
        ).json()["decision"]
        stored = api_state.store.decision_notes[decided["id"]]
        broken = stored.computation.model_copy(
            update={
                "calculations": [
                    calculation.model_copy(
                        update={"inputs": {**calculation.inputs, "periods": 0}}
                    )
                    for calculation in stored.computation.calculations
                ]
            }
        )
        api_state.store.decision_notes[decided["id"]] = stored.model_copy(
            update={"computation": broken}
        )
        seeds[f"stale-decision-{language}"] = {
            "conversation_id": stale,
            "message_id": stale_message,
            "decision_id": decided["id"],
        }

        withheld = conversation(
            "Withheld retrieval" if language == "en" else "Recuperación retenida",
            language,
        )
        question = (
            "What will $10,000 in NVDA be worth in ten years?"
            if language == "en"
            else "¿Cuánto valdrán $10,000 en NVDA dentro de diez años?"
        )
        say(withheld, "user", question)
        interpretation = StructuredInterpretation(
            intent="conversation_followup",
            task_relation="new_task",
            user_goal_summary="scenario",
            semantic_turn_act="educational_question",
            candidate_strategy_draft=StrategySummary(),
        )
        # A failed lookup: nothing was retrieved and the calculation cites pages
        # this answer never read, so the answer step answers without the lookup.
        not_retrieved = "https://example.com/not-retrieved"
        uncited = {
            "kind": "valuation_scenarios",
            "inputs": [
                {"name": "symbol", "value": "NVDA", "source": "user"},
                {"name": "price", "value": None, "source": "market_data"},
                {
                    "name": "per_share",
                    "value": 4.5,
                    "source": "page",
                    "source_url": not_retrieved,
                    "as_of": "2026-09-10",
                },
                {
                    "name": "growth_base_pct",
                    "value": 25,
                    "source": "page",
                    "source_url": not_retrieved,
                    "as_of": "2026-09-10",
                },
                {"name": "amount", "value": 10000, "source": "user"},
                {"name": "horizon_years", "value": 10, "source": "user"},
            ],
        }
        result = grounded._packet_stage_result(
            packet=ResearchPacket(
                answer_markdown="NVIDIA in ten years: {{price_at_horizon_base}}.",
                calculations=(uncited,),
            ),
            subjects=[{"symbol": "NVDA", "name": "NVIDIA", "asset_class": "equity"}],
            shape="balanced",
            capability_class="balanced_lookup",
            language=language,
            interpretation=interpretation,
            user=UserState(user_id=owner, language_preference=language, currency="USD"),
            cache_status="miss",
            question_kind="company_lookup",
            scenario=True,
            message=question,
        )
        patch = result.stage_patch
        cards = (patch.get("final_response_payload") or {}).get("tool_result_cards") or []
        metadata = {
            "research": patch["research"],
            "agent_runtime_turn": {"terminal": True, "status": "completed"},
            **(
                {"next_experiments": patch["next_experiments"]}
                if patch.get("next_experiments")
                else {}
            ),
        }
        if patch.get("clarification"):
            # A figure only the reader knows is asked for, as the chat stores it.
            metadata["clarification"] = patch["clarification"]
            metadata["requested_field"] = patch.get("requested_field")
        if cards:
            marker = computation_from_tool_cards(
                [ToolResultCard.model_validate(card) for card in cards]
            )
            metadata["tool_result_cards"] = cards
            if marker is not None:
                metadata["computation"] = marker.model_dump(mode="json")
            if patch.get("answer_text_template"):
                metadata["answer_text_template"] = patch["answer_text_template"]
            if patch.get("answer_assumptions"):
                metadata["answer_assumptions"] = patch["answer_assumptions"]
        seeds[f"withheld-{language}"] = {
            "conversation_id": withheld,
            "message_id": say(
                withheld,
                "assistant",
                patch.get("assistant_response") or patch["assistant_prompt"],
                metadata,
            ),
        }

    Path(os.environ.get("GM_SEED_OUT", "seeds.json")).write_text(
        json.dumps(seeds, indent=2) + "\n"
    )
    print("seeded", json.dumps(seeds), flush=True)


threading.Thread(target=_seed, daemon=True).start()
uvicorn.run(app, host="127.0.0.1", port=API_PORT, log_level="info")
