"""A permit for one provider call, and the turn budget that may refuse it.

Outside a chat turn every call gets a permit at its own timeout. The chat
runtime installs its turn budget here, so the transport never imports it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

DEFAULT_PROVIDER_TIMEOUT_SECONDS = 120.0


@dataclass(frozen=True)
class ProviderCallPermit:
    task: str
    timeout_seconds: float


Reserve = Callable[[str, float | None], "ProviderCallPermit | None"]
BlockReason = Callable[[], "str | None"]


def _unbudgeted(
    task: str, task_timeout_seconds: float | None = None
) -> ProviderCallPermit:
    return ProviderCallPermit(
        task=str(task),
        timeout_seconds=(
            float(task_timeout_seconds)
            if task_timeout_seconds is not None
            else DEFAULT_PROVIDER_TIMEOUT_SECONDS
        ),
    )


def _never_blocked() -> str | None:
    return None


_budget: tuple[Reserve, BlockReason] = (_unbudgeted, _never_blocked)


def install_turn_budget(reserve: Reserve, block_reason: BlockReason) -> None:
    global _budget
    _budget = (reserve, block_reason)


def reserve_provider_call(
    task: str, task_timeout_seconds: float | None = None
) -> ProviderCallPermit | None:
    return _budget[0](task, task_timeout_seconds)


def turn_budget_block_reason() -> str | None:
    return _budget[1]()
