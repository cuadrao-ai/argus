"""A read hashes the same before and after it is saved, in any process (#2064)."""

import json
import os
import subprocess
import sys
import typing
from pathlib import Path

import pytest
from argus.domain.business.access import AccessCommand
from argus.domain.business.contracts.actions import Command
from argus.domain.ingestion.documents.models import ExtractionBatch
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[2]
HASHED_ROOTS = (Command, AccessCommand, ExtractionBatch)

_HASH_IN_CHILD = """
import json, sys
from argus.domain.business.contracts.actions import canonical_input_hash
from argus.domain.ingestion.documents.models import ExtractionBatch
read = ExtractionBatch.model_validate(json.loads(sys.argv[1]))
saved = ExtractionBatch.model_validate_json(read.model_dump_json())
print(json.dumps([canonical_input_hash(read), canonical_input_hash(saved)]))
"""


def _hashes_in_process(seed: int, read: dict) -> list[str]:
    env = {**os.environ, "PYTHONHASHSEED": str(seed), "OPENROUTER_API_KEY": ""}
    done = subprocess.run(
        [sys.executable, "-c", _HASH_IN_CHILD, json.dumps(read)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
        timeout=120,
    )
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_a_read_with_several_uncertain_fields_hashes_the_same_saved_and_in_any_process(
    faker,
) -> None:
    read = {
        "candidates": [
            {
                "source": {
                    "source": "statement",
                    "connection_id": faker.uuid4(),
                    "external_id": "page-1-row-1",
                    "observed_at": "2026-11-13T12:00:00+00:00",
                },
                "evidence": "unclassified",
                "merchant": faker.company(),
                "uncertain": ["merchant", "amount", "occurred_on", "currency", "kind"],
            }
        ]
    }

    hashes = {seed: _hashes_in_process(seed, read) for seed in range(6)}

    assert len({digest for pair in hashes.values() for digest in pair}) == 1, hashes


def _set_fields(
    annotation: object, seen: set[type], found: list[tuple[type, str, object]]
) -> None:
    origin = typing.get_origin(annotation)
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        if annotation in seen:
            return
        seen.add(annotation)
        for name, field in annotation.model_fields.items():
            item = field.annotation
            if typing.get_origin(item) in (set, frozenset):
                found.append((annotation, name, typing.get_args(item)[0]))
            _set_fields(item, seen, found)
        return
    if origin is typing.Annotated:
        _set_fields(typing.get_args(annotation)[0], seen, found)
        return
    for arg in typing.get_args(annotation):
        _set_fields(arg, seen, found)


def _hashed_set_fields() -> list[tuple[type, str, object]]:
    found: list[tuple[type, str, object]] = []
    seen: set[type] = set()
    for root in HASHED_ROOTS:
        _set_fields(root, seen, found)
    return found


def test_the_guard_sees_the_uncertain_fields_of_a_read() -> None:
    assert ("ImportCandidate", "uncertain") in {
        (model.__name__, name) for model, name, _ in _hashed_set_fields()
    }


@pytest.mark.parametrize(
    ("model", "name", "item"),
    _hashed_set_fields(),
    ids=lambda value: getattr(value, "__name__", str(value)),
)
def test_every_set_in_a_hashed_contract_is_written_sorted(
    model: type[BaseModel], name: str, item: object
) -> None:
    """A set written in iteration order makes the same value hash differently
    after a save or in another process. Every set field a hashed contract can
    reach writes its members sorted."""

    choices = typing.get_args(item) if typing.get_origin(item) is typing.Literal else ()
    members = list(choices) or [f"member-{index:02d}" for index in range(20)]
    value = model.model_construct(**{name: frozenset(reversed(members))})

    written = value.model_dump(mode="json", include={name})[name]

    assert written == sorted(members), f"{model.__name__}.{name} is written unsorted"
