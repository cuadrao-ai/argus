"""The durable reader hands Search the newest computed answer per conversation."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from argus.domain.owner_scope import PERSONAL
from argus.domain.supabase_computed_answers import SupabaseComputedAnswerReadMixin
from faker import Faker

fake = Faker()


class _Table:
    def __init__(self, client: _Client, table_name: str) -> None:
        self.client = client
        self.table_name = table_name
        self.filters: list[tuple[str, str, Any]] = []
        self.orders: list[tuple[str, bool]] = []
        self.limit_value: int | None = None
        self.offset = 0
        self.negate = False

    def select(self, *_args: object) -> _Table:
        return self

    @property
    def not_(self) -> _Table:
        self.negate = True
        return self

    def eq(self, key: str, value: object) -> _Table:
        self.filters.append(("eq", key, value))
        return self

    def lte(self, key: str, value: object) -> _Table:
        self.filters.append(("lte", key, value))
        return self

    def in_(self, key: str, values: list[Any]) -> _Table:
        self.filters.append(("in", key, list(values)))
        return self

    def is_(self, key: str, value: object) -> _Table:
        self.filters.append(("not_is" if self.negate else "is", key, value))
        self.negate = False
        return self

    def order(self, key: str, desc: bool = False) -> _Table:
        self.orders.append((key, desc))
        return self

    def limit(self, value: int) -> _Table:
        self.limit_value = value
        return self

    def range(self, start: int, end: int) -> _Table:
        self.offset, self.limit_value = start, end - start + 1
        return self

    def execute(self) -> SimpleNamespace:
        self.client.queries.append(self)
        source = self.client.tables.get(self.table_name, [])
        rows = [row for row in source if self._matches(row)]
        for key, desc in reversed(self.orders):
            rows.sort(key=lambda row: str(row.get(key)), reverse=desc)
        if self.limit_value is not None:
            rows = rows[self.offset : self.offset + self.limit_value]
        return SimpleNamespace(data=[dict(row) for row in rows])

    def _matches(self, row: dict[str, Any]) -> bool:
        for kind, key, value in self.filters:
            if kind == "eq" and row.get(key) != value:
                return False
            if kind == "lte" and not str(row.get(key)) <= str(value):
                return False
            if kind == "in" and row.get(key) not in value:
                return False
            if kind in {"is", "not_is"}:
                current: Any = row
                for part in key.split("->"):
                    current = current.get(part) if isinstance(current, dict) else None
                if (current is None) != (kind == "is"):
                    return False
        return True


class _Client:
    def __init__(
        self,
        messages: list[dict[str, Any]],
        conversations: list[dict[str, Any]] | None = None,
    ) -> None:
        self.tables = {"messages": messages, "conversations": conversations or []}
        self.queries: list[_Table] = []

    def table(self, table_name: str) -> _Table:
        return _Table(self, table_name)


class _Reader(SupabaseComputedAnswerReadMixin):
    def __init__(self, client: _Client) -> None:
        self.client = client  # type: ignore[assignment]


def _message(
    conversation_id: str, role: str, created_at: str, **metadata: Any
) -> dict[str, Any]:
    return {
        "id": fake.uuid4(),
        "conversation_id": conversation_id,
        "role": role,
        "content": fake.sentence(),
        "metadata": metadata,
        "created_at": created_at,
        "user_id": "owner",
    }


def _conversation(
    conversation_id: str, *, deleted_at: str | None = None
) -> dict[str, Any]:
    return {"id": conversation_id, "user_id": "owner", "deleted_at": deleted_at}


def test_latest_computed_answer_per_conversation_with_its_question() -> None:
    first, second = fake.uuid4(), fake.uuid4()
    rows = [
        _message(first, "user", "2026-09-10T10:00:00+00:00"),
        _message(
            first,
            "assistant",
            "2026-09-10T10:01:00+00:00",
            computation={"kind": "time_value", "inputs": {}},
        ),
        _message(first, "user", "2026-09-10T11:00:00+00:00"),
        _message(
            first,
            "assistant",
            "2026-09-10T11:01:00+00:00",
            computation={"kind": "time_value", "inputs": {"payment": 1}},
        ),
        _message(second, "assistant", "2026-09-10T09:00:00+00:00"),
    ]
    reader = _Reader(_Client(rows))

    latest = reader.latest_computed_answers(
        user_id="owner", conversation_ids=[first, second]
    )

    assert set(latest) == {first}
    assert latest[first]["metadata"]["computation"]["inputs"] == {"payment": 1}
    question = reader.question_before_message(
        user_id="owner", conversation_id=first, created_at=latest[first]["created_at"]
    )
    assert question is not None and question["created_at"] == "2026-09-10T11:00:00+00:00"
    query = reader.client.queries[0]
    assert ("eq", "user_id", "owner") in query.filters
    assert ("not_is", "metadata->computation", "null") in query.filters
    assert reader.latest_computed_answers(user_id="owner", conversation_ids=[]) == {}


def test_symbol_rows_are_owner_scoped_live_and_optionally_one_conversation() -> None:
    mine, other, deleted = fake.uuid4(), fake.uuid4(), fake.uuid4()
    apple = {"kind": "price_multiple", "inputs": {}, "symbols": ["AAPL"]}
    rows = [
        _message(mine, "assistant", "2026-09-10T10:00:00+00:00", computation=apple),
        _message(
            other,
            "assistant",
            "2026-09-10T10:00:00+00:00",
            computation={"kind": "price_multiple", "inputs": {}, "symbols": ["MSFT"]},
        ),
        _message(
            other,
            "assistant",
            "2026-09-10T10:00:00+00:00",
            computation={"kind": "time_value", "inputs": {}},
        ),
        _message(deleted, "assistant", "2026-09-10T11:00:00+00:00", computation=apple),
    ]
    conversations = [
        _conversation(mine),
        _conversation(other),
        _conversation(deleted, deleted_at="2026-09-11T00:00:00+00:00"),
    ]
    reader = _Reader(_Client(rows, conversations))

    everything = reader.computed_answer_rows_for_symbols(scope=PERSONAL, user_id="owner")

    assert sorted(row["conversation_id"] for row in everything) == sorted([mine, other])
    messages, live = reader.client.queries
    assert messages.table_name == "messages"
    assert ("not_is", "metadata->computation->symbols", "null") in messages.filters
    assert live.table_name == "conversations"
    assert ("eq", "user_id", "owner") in live.filters
    assert ("is", "deleted_at", "null") in live.filters
    asked = next(
        value for kind, key, value in live.filters if (kind, key) == ("in", "id")
    )
    assert set(asked) == {mine, other, deleted}
    scoped = reader.computed_answer_rows_for_symbols(
        scope=PERSONAL, user_id="owner", conversation_id=mine
    )
    assert [row["conversation_id"] for row in scoped] == [mine]
    assert (
        reader.computed_answer_rows_for_symbols(
            scope=PERSONAL, user_id="owner", conversation_id=deleted
        )
        == []
    )


def test_no_symbol_row_skips_the_conversation_read() -> None:
    client = _Client([])
    assert (
        _Reader(client).computed_answer_rows_for_symbols(scope=PERSONAL, user_id="owner")
        == []
    )
    assert [query.table_name for query in client.queries] == ["messages"]


def test_symbol_rows_read_past_answers_in_deleted_conversations(monkeypatch) -> None:
    from argus.domain import supabase_computed_answers as reads

    monkeypatch.setattr(reads, "_COMPUTED_ANSWER_LIMIT", 2)
    live, deleted = fake.uuid4(), fake.uuid4()
    apple = {"kind": "price_multiple", "inputs": {}, "symbols": ["AAPL"]}
    rows = [
        _message(deleted, "assistant", "2026-09-10T12:00:00+00:00", computation=apple),
        _message(deleted, "assistant", "2026-09-10T11:00:00+00:00", computation=apple),
        _message(live, "assistant", "2026-09-10T10:00:00+00:00", computation=apple),
    ]
    conversations = [
        _conversation(live),
        _conversation(deleted, deleted_at="2026-09-11T00:00:00+00:00"),
    ]
    found = _Reader(_Client(rows, conversations)).computed_answer_rows_for_symbols(
        scope=PERSONAL, user_id="owner"
    )
    assert [row["conversation_id"] for row in found] == [live]


def test_every_selected_conversation_gets_its_latest_answer(monkeypatch) -> None:
    from argus.domain import supabase_computed_answers as reads

    monkeypatch.setattr(reads, "_COMPUTED_ANSWER_LIMIT", 2)
    busy, quiet = fake.uuid4(), fake.uuid4()
    computation = {"kind": "time_value", "inputs": {}}
    rows = [
        _message(
            busy, "assistant", f"2026-09-10T1{hour}:00:00+00:00", computation=computation
        )
        for hour in (2, 3, 4)
    ]
    rows.append(
        _message(quiet, "assistant", "2026-09-10T09:00:00+00:00", computation=computation)
    )
    latest = _Reader(_Client(rows)).latest_computed_answers(
        user_id="owner", conversation_ids=[busy, quiet]
    )
    assert set(latest) == {busy, quiet}
    assert latest[busy]["created_at"] == "2026-09-10T14:00:00+00:00"
