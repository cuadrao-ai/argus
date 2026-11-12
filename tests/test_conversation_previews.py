from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from argus.api import state as api_state
from argus.api.conversation_previews import conversation_previews
from argus.api.schemas import Message
from argus.domain.conversation_previews import project_conversation_preview
from argus.domain.store import AlphaStore


@pytest.mark.parametrize(
    "marker,kind",
    [
        ("result_card", "result"),
        ("confirmation_card", "confirmation"),
        ("result_fact_bank", "result"),
    ],
)
def test_old_artifact_prose_never_enters_preview(marker, kind):
    projected = project_conversation_preview(
        {
            "role": "assistant",
            "content": "Saved English prose",
            "metadata": {marker: {"symbols": ["NVDA"]}},
        }
    )
    assert projected.kind == kind
    assert projected.text is None
    assert "Saved English" not in projected.model_dump_json()


def test_user_text_remains_verbatim_even_with_artifact_metadata():
    projected = project_conversation_preview(
        {"role": "user", "content": "My English idea", "metadata": {"result_card": {}}}
    )
    assert projected.kind == "text"
    assert projected.text == "My English idea"


def test_confirmation_preview_symbols_come_from_canonical_payload():
    symbols = ["AAPL", "MSFT"]
    projected = project_conversation_preview(
        {
            "role": "assistant",
            "content": "PRIVATE CONFIRMATION PROSE",
            "metadata": {
                "confirmation_card": {
                    "title": "Wrong rendered asset label",
                    "symbols": ["STALE"],
                    "strategy_type": "dca_accumulation",
                },
                "confirmation_payload": {"strategy": {"asset_universe": symbols}},
            },
        }
    )
    assert projected.kind == "confirmation"
    assert projected.symbols == symbols
    assert projected.template == "dca_accumulation"
    assert projected.text is None
    assert "Wrong rendered asset label" not in projected.model_dump_json()


@pytest.mark.parametrize("role", ["system", "tool"])
def test_internal_message_content_is_never_a_public_preview(role):
    projected = project_conversation_preview(
        {"role": role, "content": "INTERNAL PROVIDER DETAILS", "metadata": {}}
    )
    assert projected.kind == "unavailable"
    assert projected.text is None
    assert "INTERNAL PROVIDER DETAILS" not in projected.model_dump_json()


def test_batch_read_failure_returns_unavailable_without_error_detail(monkeypatch, capfd):
    calls = []

    def failing_read(**kwargs):
        calls.append(kwargs)
        raise RuntimeError("PRIVATE DATABASE ERROR DETAIL")

    monkeypatch.setattr(
        api_state,
        "supabase_gateway",
        SimpleNamespace(read_conversation_preview_messages=failing_read),
    )
    previews = conversation_previews(user_id="owner", conversation_ids=["a", "b"])
    assert len(calls) == 1
    assert set(previews) == {"a", "b"}
    assert all(preview.kind == "unavailable" for preview in previews.values())
    assert all(preview.text is None for preview in previews.values())
    assert "PRIVATE DATABASE ERROR DETAIL" not in capfd.readouterr().err


def test_memory_preview_selects_latest_owned_message(monkeypatch):
    now = datetime.now(timezone.utc)
    messages = {
        "owned": [
            Message(
                id="a",
                conversation_id="owned",
                role="assistant",
                content="English",
                metadata={"result_card": {}},
                created_at=now,
            )
        ],
        "other": [
            Message(
                id="b",
                conversation_id="other",
                role="user",
                content="Private",
                created_at=now,
            )
        ],
    }
    monkeypatch.setattr(api_state, "supabase_gateway", None)
    monkeypatch.setattr(
        api_state,
        "store",
        AlphaStore(
            messages=messages,
            conversation_owners={"owned": "owner", "other": "someone-else"},
        ),
    )
    previews = conversation_previews(user_id="owner", conversation_ids=["owned", "other"])
    assert previews["owned"].kind == "result"
    assert previews["other"].kind == "unavailable"


def test_persistent_projection_is_one_bounded_batch(monkeypatch):
    calls = []

    def read(**kwargs):
        calls.append(kwargs)
        return [
            {
                "conversation_id": value,
                "role": "assistant",
                "metadata": {"confirmation_card": {}},
            }
            for value in kwargs["conversation_ids"]
        ]

    monkeypatch.setattr(
        api_state,
        "supabase_gateway",
        SimpleNamespace(read_conversation_preview_messages=read),
    )
    previews = conversation_previews(user_id="owner", conversation_ids=["a", "b", "a"])
    assert len(calls) == 1
    assert calls[0] == {"user_id": "owner", "conversation_ids": ["a", "b"]}
    assert all(item.kind == "confirmation" for item in previews.values())
    with pytest.raises(ValueError):
        conversation_previews(
            user_id="owner", conversation_ids=[str(index) for index in range(101)]
        )


