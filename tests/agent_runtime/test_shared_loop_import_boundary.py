"""Lane C's catalog guard, promoted to CI for the reusable containers.

Each probe runs in a fresh process: pytest collection cannot preload the catalog
and conceal an eager import. The guard refuses imports rather than stubbing them.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
GENERAL_MODULES = (
    "argus.agent_runtime",
    "argus.agent_runtime.state",
    "argus.agent_runtime.state.models",
    "argus.agent_runtime.capabilities",
    "argus.agent_runtime.capabilities.contract",
    "argus.agent_runtime.profile",
    "argus.agent_runtime.profile.response_profile",
    "argus.api.schemas",
    "argus.api.artifact_presentation",
)


@pytest.mark.parametrize("module", GENERAL_MODULES)
def test_general_container_import_does_not_load_backtest_catalog(module: str) -> None:
    _run_probe(module)


def test_general_envelopes_round_trip_and_publish_schemas_without_catalog() -> None:
    _run_probe("round_trip")


def _run_probe(mode: str) -> None:
    completed = subprocess.run(
        [sys.executable, "-c", _PROBE, mode],
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


_PROBE = """
import importlib
import importlib.abc
import sys

FORBIDDEN = (
    "argus.domain.backtesting",
    "argus.domain.engine_launch",
    "argus.agent_runtime.strategy_contract",
    "argus.domain.strategy_capabilities",
)

class Guard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if any(fullname == root or fullname.startswith(root + ".") for root in FORBIDDEN):
            raise ImportError("backtest_dependency: " + fullname)

def refuse_network(event, args):
    if event in ("socket.connect", "socket.getaddrinfo"):
        raise RuntimeError("network_forbidden_in_import_proof")

sys.addaudithook(refuse_network)
sys.meta_path.insert(0, Guard())
if sys.argv[1] != "round_trip":
    importlib.import_module(sys.argv[1])
else:
    from faker import Faker
    from argus.agent_runtime.state.models import (
        ArtifactReference, ConversationMessage, FinalResponsePayload, ResponseIntent,
        TaskSnapshot, ThreadState,
    )
    from argus.api.schemas import Message

    fake = Faker()
    # Open facts include zero and an unknown; neither can be lost to defaults.
    facts = {fake.word(): {"known": 0, "unknown": None, "answer": fake.pyfloat()}}
    reference = ArtifactReference(
        artifact_id=fake.uuid4(), artifact_kind=fake.word(), metadata=facts,
    )
    final = FinalResponsePayload(result=facts)
    message = Message(
        id=fake.uuid4(), conversation_id=fake.uuid4(), role="assistant",
        content=fake.sentence(), created_at=fake.date_time(), metadata=facts,
    )
    intent = ResponseIntent(kind="artifact_assumptions", facts=facts)
    snapshot = TaskSnapshot(artifact_references=[reference])
    thread = ThreadState(thread_id=fake.uuid4(), latest_task_snapshot=snapshot)
    for instance in (reference, final, message, intent, snapshot, thread):
        assert type(instance).model_validate_json(instance.model_dump_json()) == instance
    for model in (ArtifactReference, FinalResponsePayload, Message, ResponseIntent,
                  ConversationMessage):
        assert model.model_json_schema()["type"] == "object"
    assert reference.metadata == final.result == message.metadata == intent.facts == facts

assert not any(
    name == root or name.startswith(root + ".")
    for name in sys.modules for root in FORBIDDEN
)
"""
