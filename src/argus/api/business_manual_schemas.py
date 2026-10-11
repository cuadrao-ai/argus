from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from argus.domain.business.contracts.facts import Contract


class ManualCapture(Contract):
    draft_id: UUID
    version: int = Field(ge=1)
    source_id: UUID
    text: str = Field(min_length=1, max_length=20000)
    received_at: datetime
    review_state: Literal["open", "accepting", "accepted", "dismissed"]


class ManualCapturePage(Contract):
    items: tuple[ManualCapture, ...]
