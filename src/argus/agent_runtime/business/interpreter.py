from __future__ import annotations

from typing import Any


class BusinessInterpreterMethods:
    model_name: str | None

    async def ainterpret_business(self, payload: dict[str, Any]) -> Any:
        from argus.agent_runtime.business.interpretation import interpret_business_turn

        return await interpret_business_turn(payload, model_name=self.model_name)

    async def acompose_business(self, payload: dict[str, Any]) -> str:
        from argus.agent_runtime.business.interpretation import compose_business_reply

        return await compose_business_reply(payload, model_name=self.model_name)
