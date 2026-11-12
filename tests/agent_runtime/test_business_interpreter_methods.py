from __future__ import annotations

from inspect import iscoroutinefunction

import pytest
from argus.agent_runtime.business.interpreter import BusinessTurnInterpreter
from argus.agent_runtime.llm_interpreter import OpenRouterStructuredInterpreter

from tests.evals.run_business_live import LiveInterpreter


@pytest.mark.parametrize(
    "interpreter_type",
    [LiveInterpreter, OpenRouterStructuredInterpreter, BusinessTurnInterpreter],
)
@pytest.mark.parametrize("method_name", ["ainterpret_business", "acompose_business"])
def test_business_interpreters_expose_async_turn_methods(
    interpreter_type: type, method_name: str
) -> None:
    assert iscoroutinefunction(getattr(interpreter_type, method_name, None))
