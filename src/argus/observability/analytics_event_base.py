"""The base every registered analytics event model extends.

Kept apart from the registry so an owner that declares its own events (the
Business pilot) can extend it while the registry imports that owner's models.
"""

from __future__ import annotations

from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, model_validator


class AnalyticsEvent(BaseModel):
    """One analytics event. Subclasses set ``event_name`` and their properties."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    event_name: ClassVar[str]
    # Only ``signed_in`` links an account to the guest it came from (C3).
    carries_guest_id_hash: ClassVar[bool] = False

    @model_validator(mode="before")
    @classmethod
    def _reject_lookalike_numbers(cls, data: Any) -> Any:
        # ``True == 1 == 1.0``, so a literal like ``step: 1`` would otherwise
        # accept a bool or a float. No property is a float, and only a
        # ``bool`` field takes a bool.
        if isinstance(data, dict):
            for name, value in data.items():
                field = cls.model_fields.get(name)
                if field is None or field.annotation is bool:
                    continue
                if isinstance(value, bool | float):
                    raise ValueError(f"{name} does not take a {type(value).__name__}")
        return data
