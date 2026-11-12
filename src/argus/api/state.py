from __future__ import annotations

import os

from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from argus.domain.store import AlphaStore
from argus.domain.supabase_gateway import SupabaseGateway
from argus.env import load_project_dotenv

load_project_dotenv()

PERSISTENCE_MODE = os.getenv("CUADRAO_PERSISTENCE_MODE", "memory").strip().lower()
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
CHECKPOINTER_MODE = os.getenv("CUADRAO_CHECKPOINTER_MODE", "").strip().lower()
if not CHECKPOINTER_MODE:
    CHECKPOINTER_MODE = (
        "postgres" if PERSISTENCE_MODE == "supabase" and DATABASE_URL else "memory"
    )
store = AlphaStore()
supabase_gateway = SupabaseGateway.from_env() if PERSISTENCE_MODE == "supabase" else None


def build_agent_runtime_checkpoint_serde() -> JsonPlusSerializer:
    # Runtime checkpoints are process-local and may include Pydantic state
    # objects that LangGraph's default msgpack serializer cannot encode.
    return JsonPlusSerializer(
        pickle_fallback=True,
        allowed_msgpack_modules=[
            ("argus.agent_runtime.state.models", "ArtifactReference"),
            ("argus.agent_runtime.state.models", "ConfirmationPayload"),
            ("argus.agent_runtime.state.models", "ConversationMessage"),
            ("argus.agent_runtime.state.models", "FinalResponsePayload"),
            ("argus.agent_runtime.state.models", "ResolutionProvenance"),
            ("argus.agent_runtime.state.models", "ResponseIntent"),
            ("argus.agent_runtime.state.models", "ResponseProfile"),
            ("argus.agent_runtime.state.models", "ResponseProfileOverrides"),
            ("argus.agent_runtime.state.models", "RunState"),
            ("argus.agent_runtime.state.models", "StrategySummary"),
            ("argus.agent_runtime.state.models", "StructuredActionContext"),
            ("argus.agent_runtime.state.models", "TaskSnapshot"),
            ("argus.agent_runtime.state.models", "ToolCallRecord"),
            ("argus.agent_runtime.state.models", "UserState"),
            ("argus.agent_runtime.state.models", "UnsupportedConstraint"),
        ],
    )


def build_agent_runtime_checkpointer() -> MemorySaver:
    return MemorySaver(serde=build_agent_runtime_checkpoint_serde())
