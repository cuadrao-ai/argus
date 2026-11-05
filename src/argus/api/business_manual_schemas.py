from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from argus.domain.business.contracts.facts import Contract


class ManualCapture(Contract):
    draft_id: UUID
    version: int = Field(ge=1)
    # The revision this note created: the number the draft's history lists.
    # ``version`` is the draft's current version, which also counts later actions.
    revision: int = Field(ge=1)
    source_id: UUID
    text: str = Field(min_length=1, max_length=20000)
    received_at: datetime
    review_state: Literal["open", "accepting", "accepted", "dismissed"]
    # How many notes of the same draft came before this one, over every note
    # of the draft, not only the page or the search.
    earlier_count: int = Field(default=0, ge=0)


class ManualCapturePage(Contract):
    items: tuple[ManualCapture, ...]
    # More notes exist past ``limit``; the page is not the whole list.
    has_more: bool = False
