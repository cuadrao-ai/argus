"""Backend-owned narrow-screen copy for the mobile shell.

The backend owns user-facing copy, so a narrow screen gets a shorter Try next
label and a shorter generated title composed here, never clipped in the client.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from argus.agent_runtime.next_experiments import (
    NEXT_EXPERIMENT_ACTION_LABELS,
    NEXT_EXPERIMENT_SHORT_LABELS,
    next_experiment_label_key,
    next_experiment_short_label_key,
    next_experiments_sidecar,
)
from argus.api import artifact_naming, naming
from argus.api import state as api_state
from argus.api.message_store import memory_conversation
from argus.api.naming import (
    NARROW_TITLE_MAX_WORDS,
    WIDE_TITLE_MAX_WORDS,
    NameSuggestion,
    title_word_budget,
)
from argus.api.schemas import ChatStreamRequest, Conversation
from argus.domain.owner_scope import PERSONAL

LANGUAGES = ("en", "es-419")
_LABEL_PREFIX = "chat.next_experiments.labels."
_LOCALES = Path(__file__).resolve().parents[1] / "web" / "public" / "locales"


def _kinds() -> set[str]:
    return {
        key.removeprefix(_LABEL_PREFIX) for key in NEXT_EXPERIMENT_ACTION_LABELS["en"]
    }


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_row_kind_has_a_short_form(language: str) -> None:
    assert set(NEXT_EXPERIMENT_SHORT_LABELS[language]) == _kinds()


@pytest.mark.parametrize("language", LANGUAGES)
def test_short_form_is_shorter_than_the_full_label(language: str) -> None:
    for kind, short in NEXT_EXPERIMENT_SHORT_LABELS[language].items():
        full = NEXT_EXPERIMENT_ACTION_LABELS[language][next_experiment_label_key(kind)]
        assert len(short) < len(full), kind
        assert short.strip() == short


@pytest.mark.parametrize("language", LANGUAGES)
def test_short_form_carries_no_em_dash(language: str) -> None:
    assert not [
        value for value in NEXT_EXPERIMENT_SHORT_LABELS[language].values() if "—" in value
    ]


def test_english_and_spanish_short_forms_stay_equivalent() -> None:
    assert set(NEXT_EXPERIMENT_SHORT_LABELS["en"]) == set(
        NEXT_EXPERIMENT_SHORT_LABELS["es-419"]
    )


@pytest.mark.parametrize("language", LANGUAGES)
def test_short_labels_are_published_to_the_client_locale(language: str) -> None:
    bundle = json.loads((_LOCALES / language / "common.json").read_text())
    published = bundle["chat"]["next_experiments"]["labels_short"]
    assert published == NEXT_EXPERIMENT_SHORT_LABELS[language]


def test_sidecar_rows_carry_the_short_form() -> None:
    facts = {
        "strategy_family": "buy_and_hold",
        "symbols": ["AAPL"],
        "benchmark_symbol": "SPY",
        "start_date": "2025-08-01",
        "end_date": "2026-08-01",
    }
    sidecar = next_experiments_sidecar(facts)
    if sidecar is None:
        pytest.skip("no experiments offered for this result shape")
    for row in sidecar["rows"]:
        assert row["label_short"] == NEXT_EXPERIMENT_SHORT_LABELS["en"][row["kind"]]
        assert row["label_short_key"] == next_experiment_short_label_key(row["kind"])
        assert len(row["label_short"]) < len(row["label"])


def test_narrow_titles_are_generated_short_not_clipped() -> None:
    assert title_word_budget("narrow") == NARROW_TITLE_MAX_WORDS
    assert title_word_budget("wide") == WIDE_TITLE_MAX_WORDS
    assert title_word_budget(None) == WIDE_TITLE_MAX_WORDS
    assert NARROW_TITLE_MAX_WORDS < WIDE_TITLE_MAX_WORDS


_DEV_USER_ID = "00000000-0000-0000-0000-000000000001"
_OVERLONG = "Apple versus SPY across the last twelve months"


def _fake_model_names(
    monkeypatch: pytest.MonkeyPatch, *names: str
) -> list[list[dict[str, str]]]:
    requests: list[list[dict[str, str]]] = []
    replies = iter(names)

    def _invoke(**kwargs: Any) -> NameSuggestion:
        requests.append(kwargs["messages"])
        return NameSuggestion(name=next(replies))

    monkeypatch.setattr(naming, "invoke_openrouter_json_schema_sync", _invoke)
    return requests


def _generate_title(
    monkeypatch: pytest.MonkeyPatch, *, viewport: str, language: str = "en"
) -> tuple[str | None, Conversation]:
    monkeypatch.setattr(api_state, "supabase_gateway", None)
    api_state.store.reset()
    api_state.store.get_or_create_dev_user()
    conversation = memory_conversation(
        scope=PERSONAL, title="New idea", title_source="system_default", language=language
    )
    title = artifact_naming.maybe_generate_conversation_title(
        user_id=_DEV_USER_ID,
        conversation_id=conversation.id,
        language=language,
        user_message="Compare Apple with SPY over the last twelve months.",
        assistant_message="Apple returned 12% while SPY returned 18%.",
        viewport=viewport,
    )
    return title, api_state.store.conversations[conversation.id]


def test_a_title_inside_the_budget_is_saved_from_one_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests = _fake_model_names(monkeypatch, "Apple vs SPY")

    title, saved = _generate_title(monkeypatch, viewport="narrow")

    assert title == "Apple vs SPY"
    assert (saved.title, saved.title_source) == ("Apple vs SPY", "ai_generated")
    assert len(requests) == 1
    assert [message["role"] for message in requests[0]] == ["system", "user"]
    assert requests[0][0]["content"] == (
        "Generate a concise user-facing name for Argus Alpha. "
        f"Max {NARROW_TITLE_MAX_WORDS} words. "
        "No punctuation-only output. "
        "Entity type: conversation. Language: en."
    )


@pytest.mark.parametrize(
    ("viewport", "language", "overlong", "short"),
    [
        ("narrow", "en", _OVERLONG, "Apple versus SPY"),
        (
            "wide",
            "es-419",
            "Comparación de DOCN y SPY con compras semanales",
            "Comparación de DOCN y SPY",
        ),
    ],
)
def test_an_overlong_title_is_requested_again_never_clipped(
    monkeypatch: pytest.MonkeyPatch,
    viewport: str,
    language: str,
    overlong: str,
    short: str,
) -> None:
    """A model may ignore the word limit; clipping its title saved half a phrase."""

    requests = _fake_model_names(monkeypatch, overlong, short)

    title, saved = _generate_title(monkeypatch, viewport=viewport, language=language)

    assert title == short
    assert (saved.title, saved.title_source) == (short, "ai_generated")
    assert len(requests) == 2
    assert requests[1][: len(requests[0])] == requests[0]
    assert overlong in requests[1][-2]["content"]
    assert str(title_word_budget(viewport)) in requests[1][-1]["content"]


def test_a_title_still_overlong_after_one_retry_saves_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests = _fake_model_names(
        monkeypatch, _OVERLONG, "Apple versus SPY over twelve months"
    )

    title, saved = _generate_title(monkeypatch, viewport="narrow")

    assert title is None
    assert (saved.title, saved.title_source) == ("New idea", "system_default")
    assert len(requests) == 2


def test_turn_request_carries_an_optional_viewport_band() -> None:
    assert ChatStreamRequest(conversation_id="c1", message="hi").viewport is None
    assert (
        ChatStreamRequest(conversation_id="c1", message="hi", viewport="narrow").viewport
        == "narrow"
    )
    with pytest.raises(ValueError):
        ChatStreamRequest(conversation_id="c1", message="hi", viewport="phone")
