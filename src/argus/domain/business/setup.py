"""The Business's setup steps, from its saved facts. The only owner of the step
list: which steps there are, which are required and whether each is done. Inicio
renders the answer and counts nothing of its own.

A step whose feature is off on this server is not sent: its fact is ``None``.
Optional steps never hold setup open."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, TypedDict

SetupStepKey = Literal[
    "created",
    "fiscal_identity",
    "receiving_address",
    "receipt_reading",
    "first_document",
    "team",
    "whatsapp",
]

REQUIRED: frozenset[SetupStepKey] = frozenset(
    {"created", "fiscal_identity", "receiving_address", "receipt_reading"}
)


class SetupStep(TypedDict):
    key: SetupStepKey
    required: bool
    done: bool


@dataclass(frozen=True)
class SetupFacts:
    """Whether each step is done; ``None`` while its feature is off.

    ``fiscal_identity``: the RNC or cédula and a legal name other than the
    default are saved. ``receiving_address``: the email receiving address can
    receive. ``receipt_reading``: the owner turned reading on. ``first_document``:
    the Business received a document; opening upload, copying the address or
    linking a phone does not count. ``team``: someone was invited or holds access.
    ``whatsapp``: a number is linked."""

    fiscal_identity: bool
    receiving_address: bool | None
    receipt_reading: bool | None
    first_document: bool
    team: bool | None
    whatsapp: bool | None


def setup_steps(facts: SetupFacts) -> list[SetupStep]:
    """The steps in the order Inicio lists them, the Business itself first."""

    states: tuple[tuple[SetupStepKey, bool | None], ...] = (
        ("created", True),
        ("fiscal_identity", facts.fiscal_identity),
        ("receiving_address", facts.receiving_address),
        ("receipt_reading", facts.receipt_reading),
        ("first_document", facts.first_document),
        ("team", facts.team),
        ("whatsapp", facts.whatsapp),
    )
    return [
        {"key": key, "required": key in REQUIRED, "done": done}
        for key, done in states
        if done is not None
    ]
