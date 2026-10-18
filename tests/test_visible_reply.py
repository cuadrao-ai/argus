"""Model-written replies never show an em dash, in any language.

The rule is founder-locked (AGENTS.md "Copy") and used to live
in one prompt out of many. One owner applies it at the point a reply becomes
visible, covers every chat reply, and records when it fired.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from argus.api.chat.visible_reply import (
    EM_DASH,
    REPLY_REWRITES_METADATA_KEY,
    rewrite_visible_reply,
)
from argus.api.main import app
from fastapi.testclient import TestClient


@pytest.mark.parametrize(
    ("text", "expected", "count"),
    [
        (
            "Got it — $1,000 starting capital, $100 monthly buys, no cap. Which asset?",
            "Got it, $1,000 starting capital, $100 monthly buys, no cap. Which asset?",
            1,
        ),
        (
            "Listo — capital inicial de $1,000 — aportes mensuales de $100.",
            "Listo, capital inicial de $1,000, aportes mensuales de $100.",
            2,
        ),
        ("Argus can run it—no cap needed.", "Argus can run it, no cap needed.", 1),
        ("— starts with a dash", "starts with a dash", 1),
        ("ends with a dash —", "ends with a dash.", 1),
        ("Comma already, — twice", "Comma already, twice", 1),
        # Adjacent dashes are one dash; every dash is still counted.
        ("Wait——actually, no cap.", "Wait, actually, no cap.", 2),
        ("Espera——en realidad, sin tope.", "Espera, en realidad, sin tope.", 2),
        ("Wait— —actually, no cap.", "Wait, actually, no cap.", 2),
        ("Espera — — en realidad, sin tope.", "Espera, en realidad, sin tope.", 2),
        # A dash set directly between two figures is the model's range
        # notation; a comma would change the fact, so it keeps a hyphen.
        ("Expect 5%—10% a year.", "Expect 5%-10% a year.", 1),
        ("Between $1,000—$2,000 a month.", "Between $1,000-$2,000 a month.", 1),
        ("Espera 5%—10% al año.", "Espera 5%-10% al año.", 1),
        ("Entre $1,000—$2,000 al mes.", "Entre $1,000-$2,000 al mes.", 1),
        # Any currency sign opens a figure, not only the ones we happen to name.
        ("Between ¥1,000—¥2,000 a month.", "Between ¥1,000-¥2,000 a month.", 1),
        ("Entre ₹1,000—₹2,000 al mes.", "Entre ₹1,000-₹2,000 al mes.", 1),
        ("Expect 5‰—10‰ a year.", "Expect 5‰-10‰ a year.", 1),
        # A currency sign placed after the amount closes the figure too.
        ("Entre 1.000€—2.000€ al mes.", "Entre 1.000€-2.000€ al mes.", 1),
        ("Between 1,000kr—2,000kr a month.", "Between 1,000kr, 2,000kr a month.", 1),
        ("Between 1.000€—2.000€ a month.", "Between 1.000€-2.000€ a month.", 1),
        # A spaced dash between figures is an aside, not a range.
        ("It returned 12% — 3% above SPY.", "It returned 12%, 3% above SPY.", 1),
        (
            "No dash here, only a hyphen-joined word.",
            "No dash here, only a hyphen-joined word.",
            0,
        ),
        ("", "", 0),
    ],
)
def test_rewrite_visible_reply_replaces_every_em_dash(
    text: str, expected: str, count: int
) -> None:
    rewritten = rewrite_visible_reply(text, surface="test")

    assert rewritten.text == expected
    assert rewritten.em_dash_count == count
    assert EM_DASH not in rewritten.text


def test_rewrite_visible_reply_keeps_none() -> None:
    rewritten = rewrite_visible_reply(None, surface="test")

    assert rewritten.text is None
    assert rewritten.em_dash_count == 0


def _client() -> TestClient:
    client = TestClient(app)
    client.post("/api/v1/dev/reset")
    return client


def _data_events(stream: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for part in stream.split("\n\n"):
        data_line = next(
            (line for line in part.splitlines() if line.startswith("data: ")), None
        )
        if data_line is None:
            continue
        raw = data_line.removeprefix("data: ").strip()
        if raw == "[DONE]":
            continue
        events.append(json.loads(raw))
    return events


def test_chat_stream_shows_and_persists_replies_without_em_dashes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api.routers import agent as agent_router

    reply = "Got it — $1,000 starting capital, $100 monthly buys, no cap. Which asset and date window should we use?"

    async def _fake_stream_agent_turn_events(**_: Any):
        yield {"type": "stage_start", "stage": "clarify"}
        yield {"type": "token", "content": "Got it —"}
        yield {"type": "token", "content": " $1,000 starting capital"}
        yield {"type": "stage_outcome", "outcome": "await_user_reply"}
        yield {
            "type": "final",
            "payload": {
                "stage_outcome": "await_user_reply",
                "assistant_prompt": reply,
                "assistant_response": reply,
            },
        }

    monkeypatch.setattr(
        agent_router, "stream_agent_turn_events", _fake_stream_agent_turn_events
    )
    client = _client()
    conversation = client.post("/api/v1/conversations", json={}).json()["conversation"]

    response = client.post(
        "/api/v1/chat/stream",
        json={
            "conversation_id": conversation["id"],
            "message": "Use $1,000 as starting capital only.",
            "language": "en",
        },
    )

    assert response.status_code == 200
    assert EM_DASH not in response.text
    events = _data_events(response.text)
    tokens = "".join(event["content"] for event in events if event.get("type") == "token")
    assert tokens == "Got it, $1,000 starting capital"
    final = next(event for event in events if event.get("type") == "final")["payload"]
    assert final["assistant_response"].startswith("Got it, $1,000 starting capital")
    assert final["assistant_prompt"] == final["assistant_response"]
    assert final[REPLY_REWRITES_METADATA_KEY] == {"em_dash": 1}

    messages = client.get(f"/api/v1/conversations/{conversation['id']}/messages").json()[
        "items"
    ]
    assistant = next(message for message in messages if message["role"] == "assistant")
    assert EM_DASH not in assistant["content"]
    assert assistant["content"].startswith("Got it, $1,000 starting capital")
    assert assistant["metadata"][REPLY_REWRITES_METADATA_KEY] == {"em_dash": 1}


def test_chat_stream_records_nothing_when_no_em_dash_was_shown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api.routers import agent as agent_router

    async def _fake_stream_agent_turn_events(**_: Any):
        yield {"type": "stage_start", "stage": "clarify"}
        yield {"type": "stage_outcome", "outcome": "await_user_reply"}
        yield {
            "type": "final",
            "payload": {
                "stage_outcome": "await_user_reply",
                "assistant_prompt": "Which asset should we use?",
            },
        }

    monkeypatch.setattr(
        agent_router, "stream_agent_turn_events", _fake_stream_agent_turn_events
    )
    client = _client()
    conversation = client.post("/api/v1/conversations", json={}).json()["conversation"]

    response = client.post(
        "/api/v1/chat/stream",
        json={"conversation_id": conversation["id"], "message": "hi", "language": "en"},
    )

    assert response.status_code == 200
    final = next(
        event for event in _data_events(response.text) if event.get("type") == "final"
    )
    assert REPLY_REWRITES_METADATA_KEY not in final["payload"]
    messages = client.get(f"/api/v1/conversations/{conversation['id']}/messages").json()[
        "items"
    ]
    assistant = next(message for message in messages if message["role"] == "assistant")
    assert REPLY_REWRITES_METADATA_KEY not in assistant["metadata"]


# --- Codex round 2 on PR #591 -------------------------------------------------


@pytest.mark.parametrize(
    ("chunks", "expected"),
    [
        (["Hello", " —", " world"], "Hello, world"),
        (["Hello ", "—", " world"], "Hello, world"),
        (["Hello —", " world"], "Hello, world"),
        (
            ["Hola", " —", " mundo, ", "listo —", " capital inicial de $1,000."],
            "Hola, mundo, listo, capital inicial de $1,000.",
        ),
        (["Comma already,", " — twice"], "Comma already, twice"),
        (["Wait——", "actually"], "Wait, actually"),
        (["Wait—", "—actually"], "Wait, actually"),
        (["Espera", "——en realidad"], "Espera, en realidad"),
        (["Wait— ", "—actually"], "Wait, actually"),
        (["Espera —", " — en realidad"], "Espera, en realidad"),
        (["First line\n", "— second"], "First line\nsecond"),
        (["Expect 5%", "—10%", " a year."], "Expect 5%-10% a year."),
        (["Expect 5%—", "10% a year."], "Expect 5%-10% a year."),
        (["Entre $1,000", "—", "$2,000 al mes."], "Entre $1,000-$2,000 al mes."),
        (["Between ₹1,000—", "₹2,000."], "Between ₹1,000-₹2,000."),
        (["Entre 1.000€", "—2.000€ al mes."], "Entre 1.000€-2.000€ al mes."),
    ],
)
def test_streamed_chunks_render_exactly_what_the_final_reply_persists(
    chunks: list[str], expected: str
) -> None:
    from argus.api.chat.visible_reply import ReplyRewrites

    rewrites = ReplyRewrites(surface="test")
    live = "".join(rewrites.token(chunk) for chunk in chunks)
    full = "".join(chunks)
    runtime_result = {"assistant_response": full}
    metadata: dict[str, object] = {}
    final_text, _ = rewrites.finalize(
        runtime_result=runtime_result,
        metadata=metadata,
        assistant_text=full,
        persisted_text=full,
    )

    assert live == expected
    assert final_text == expected
    assert runtime_result["assistant_response"] == expected
    assert metadata[REPLY_REWRITES_METADATA_KEY] == {"em_dash": full.count(EM_DASH)}


# --- Codex round 3 on PR #591 -------------------------------------------------


@pytest.mark.parametrize(
    ("chunks", "expected"),
    [
        (["Hello", " —"], "Hello."),
        (["Hola, capital inicial de $1,000 —"], "Hola, capital inicial de $1,000."),
        (["Trailing space", " "], "Trailing space "),
    ],
)
def test_a_reply_that_ends_on_a_held_boundary_is_flushed_when_the_stream_closes(
    chunks: list[str], expected: str
) -> None:
    from argus.api.chat.visible_reply import ReplyRewrites

    rewrites = ReplyRewrites(surface="test")
    live = "".join(rewrites.token(chunk) for chunk in chunks) + rewrites.flush()
    full = "".join(chunks)
    final_text, _ = rewrites.finalize(
        runtime_result={"assistant_response": full},
        metadata={},
        assistant_text=full,
        persisted_text=full,
    )

    assert live == expected
    assert final_text == expected
    assert rewrites.flush() == ""


def test_chat_stream_flushes_a_trailing_em_dash_before_the_final_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from argus.api.routers import agent as agent_router

    async def _fake_stream_agent_turn_events(**_: Any):
        yield {"type": "stage_start", "stage": "clarify"}
        yield {"type": "token", "content": "Hello"}
        yield {"type": "token", "content": " —"}
        yield {"type": "stage_outcome", "outcome": "await_user_reply"}
        yield {
            "type": "final",
            "payload": {
                "stage_outcome": "await_user_reply",
                "assistant_response": "Hello —",
            },
        }

    monkeypatch.setattr(
        agent_router, "stream_agent_turn_events", _fake_stream_agent_turn_events
    )
    client = _client()
    conversation = client.post("/api/v1/conversations", json={}).json()["conversation"]

    response = client.post(
        "/api/v1/chat/stream",
        json={"conversation_id": conversation["id"], "message": "hi", "language": "en"},
    )

    assert response.status_code == 200
    events = _data_events(response.text)
    tokens = "".join(event["content"] for event in events if event.get("type") == "token")
    final = next(event for event in events if event.get("type") == "final")["payload"]
    assert tokens == "Hello."
    assert final["assistant_response"] == "Hello."
    messages = client.get(f"/api/v1/conversations/{conversation['id']}/messages").json()[
        "items"
    ]
    assistant = next(message for message in messages if message["role"] == "assistant")
    assert assistant["content"] == "Hello."
