"""Replay a recorded production receipt through the real emitter, without a call."""

import json
import os
from pathlib import Path

from argus.llm.openrouter import record_openrouter_route_receipt

snapshot = json.loads(Path(__file__).with_name("production-receipt.json").read_text())
receipt = snapshot["receipt"]
os.environ["CUADRAO_CHAT_FALLBACK_MODEL"] = receipt["fallback_model"]
record_openrouter_route_receipt(
    task=receipt["task"],
    model_name=receipt["model"],
    mode=receipt["mode"],
    schema_name=receipt["schema_name"],
    latency_ms=receipt["latency_ms"],
    outcome=receipt["outcome"],
    failure_mode=receipt["failure_mode"],
    token_usage=receipt["token_usage"],
    usage_cost_usd=receipt["usage_cost_usd"],
    context_packet_ids=receipt["context_packet_ids"],
)
