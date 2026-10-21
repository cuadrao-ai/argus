"""The durable reader lists an owner's computed answers of one kind in live conversations."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from argus.domain.owner_scope import PERSONAL
from argus.domain.supabase_computed_answers import SupabaseComputedAnswerReadMixin


class _Query:
    def __init__(self, client: _Client, table: str) -> None:
        self.client, self.table = client, table
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def __getattr__(self, name: str):
        def record(*args: Any, **kwargs: Any) -> _Query:
            self.calls.append((name, args + tuple(sorted(kwargs.items()))))
            return self

        return record

    def execute(self) -> SimpleNamespace:
        self.client.queries.append(self)
        rows = self.client.data[self.table]
        bounds = [args for name, args in self.calls if name == "range"]
        if bounds:
            start, end = bounds[-1]
            rows = rows[start : end + 1]
        return SimpleNamespace(data=rows)


class _Client:
    def __init__(self, data: dict[str, list[dict[str, Any]]]) -> None:
        self.data = data
        self.queries: list[_Query] = []

    def table(self, name: str) -> _Query:
        return _Query(self, name)


class _Reader(SupabaseComputedAnswerReadMixin):
    def __init__(self, client: _Client) -> None:
        self.client = client  # type: ignore[assignment]


def test_the_kind_filter_reads_the_marker_and_drops_deleted_conversations() -> None:
    client = _Client(
        {
            "messages": [
                {"id": "m1", "conversation_id": "live", "role": "assistant"},
                {"id": "m2", "conversation_id": "deleted", "role": "assistant"},
            ],
            "conversations": [{"id": "live"}],
        }
    )
    rows = _Reader(client).computed_answers_of_kind(
        scope=PERSONAL, user_id="owner", kind="price_multiple", limit=11
    )
    assert [row["id"] for row in rows] == ["m1"]
    messages, conversations = client.queries
    assert ("eq", ("metadata->computation->>kind", "price_multiple")) in messages.calls
    assert ("eq", ("user_id", "owner")) in messages.calls
    assert ("range", (0, 10)) in messages.calls
    assert ("is_", ("deleted_at", "null")) in conversations.calls
    assert ("in_", ("id", ["live", "deleted"])) in conversations.calls


def test_no_matching_message_skips_the_conversation_read() -> None:
    client = _Client({"messages": [], "conversations": []})
    assert (
        _Reader(client).computed_answers_of_kind(
            scope=PERSONAL, user_id="o", kind="k", limit=3
        )
        == []
    )
    assert len(client.queries) == 1


def test_answers_in_deleted_conversations_do_not_crowd_out_older_live_ones() -> None:
    client = _Client(
        {
            "messages": [
                {"id": "m1", "conversation_id": "deleted", "role": "assistant"},
                {"id": "m2", "conversation_id": "deleted", "role": "assistant"},
                {"id": "m3", "conversation_id": "live", "role": "assistant"},
            ],
            "conversations": [{"id": "live"}],
        }
    )
    rows = _Reader(client).computed_answers_of_kind(
        scope=PERSONAL, user_id="owner", kind="k", limit=2
    )
    assert [row["id"] for row in rows] == ["m3"]
    first, _, second, _ = client.queries
    assert ("range", (0, 1)) in first.calls
    assert ("range", (2, 5)) in second.calls


def test_the_refill_reads_on_until_a_live_answer_or_the_end() -> None:
    deleted = [
        {"id": f"d{index}", "conversation_id": "deleted", "role": "assistant"}
        for index in range(20)
    ]
    live = {"id": "m-live", "conversation_id": "live", "role": "assistant"}
    client = _Client({"messages": [*deleted, live], "conversations": [{"id": "live"}]})
    rows = _Reader(client).computed_answers_of_kind(
        scope=PERSONAL, user_id="owner", kind="k", limit=1
    )
    assert [row["id"] for row in rows] == ["m-live"]
    assert len([query for query in client.queries if query.table == "messages"]) == 5
