"""A chat turn recalls saved memory only in a Personal conversation.

The turn reads its conversation's stored side; the request carries none. The
completed turn runs through the real chat route with the scripted gateway the
allowance tests use, so a Business conversation proves the recall never runs.
"""

from __future__ import annotations

from typing import cast

import pytest
from argus.api.personalization_memory import configure_memory_service
from argus.domain.owner_scope import PERSONAL, BusinessSpace, OwnerScope
from argus.memory.service import MemoryService

from tests.test_allowance_accounting import (  # noqa: F401
    _conversation,
    client,
    mock_gateway,
)

CONVERSATION_ID = "00000000-0000-4000-8000-00000000c0c1"


class _CountingMemoryService:
    def __init__(self) -> None:
        self.calls = 0

    def retrieve(self, *args: object, **kwargs: object) -> list[object]:
        self.calls += 1
        return []


@pytest.mark.parametrize(
    ("scope", "recalls"), [(PERSONAL, 1), (BusinessSpace("space-1"), 0)]
)
def test_a_turn_recalls_memory_only_in_a_personal_conversation(
    monkeypatch: pytest.MonkeyPatch,
    mock_gateway,  # noqa: F811, ANN001
    scope: OwnerScope,
    recalls: int,
) -> None:
    monkeypatch.setenv("ARGUS_ENABLE_PERSONALIZATION_MEMORY", "true")
    mock_gateway.private_alpha_role_for_email.return_value = "developer"
    mock_gateway.get_conversation.return_value = _conversation(CONVERSATION_ID)
    mock_gateway.conversation_scope.return_value = scope
    service = _CountingMemoryService()
    configure_memory_service(cast(MemoryService, service))
    try:
        response = client.post(
            "/api/v1/chat/stream",
            json={"conversation_id": CONVERSATION_ID, "message": "Test TSLA dip idea"},
            headers={"Authorization": "Bearer test-token"},
        )
    finally:
        configure_memory_service(None)

    assert response.status_code == 200
    assert mock_gateway.finalize_chat_turn.call_count >= 1
    assert service.calls == recalls
    mock_gateway.conversation_scope.assert_called_with(
        user_id="00000000-0000-0000-0000-000000000001",
        conversation_id=CONVERSATION_ID,
    )
