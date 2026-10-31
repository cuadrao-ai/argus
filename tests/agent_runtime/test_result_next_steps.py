"""One ordered list of next steps after an answer about a result: the model's
order, each runnable test's exact typed row, and clean questions, in both
workspace languages."""

from __future__ import annotations

import pytest
from argus.agent_runtime.result_next_steps import (
    MAX_NEXT_STEPS,
    NEXT_STEPS_VERSION,
    QUESTION_STEP,
    NextStep,
    accepted_next_steps,
    next_steps_patch,
    offered_test_steps,
)

ROWS = {
    "version": "argus_next_experiments/v1",
    "source_run_id": "run-docn",
    "rows": [
        {
            "kind": "change_date_range",
            "label": "Test a different date range",
            "label_key": "chat.next_experiments.labels.change_date_range",
            "why": {"code": "deep_drawdown", "params": {"drawdown": -44.9}},
        },
        {
            "kind": "recurring_monthly_buys",
            "label": "Try monthly recurring buys",
            "label_key": "chat.next_experiments.labels.recurring_monthly_buys",
            "send_text": "Try monthly recurring buys of DOCN from 2023-09-01 to 2026-09-10 with $1000 each month.",
        },
        {
            "kind": "supported_ma_crossover",
            "label": "Try a moving average crossover",
            "label_key": "chat.next_experiments.labels.supported_ma_crossover",
        },
    ],
}
KINDS = tuple(row["kind"] for row in ROWS["rows"])
QUESTIONS = {
    "en": "What drove DOCN's drop between February and August 2025?",
    "es-419": "¿Qué impulsó la caída de DOCN entre febrero y agosto de 2025?",
}


@pytest.mark.parametrize("language", sorted(QUESTIONS))
def test_the_list_keeps_the_models_order_and_each_test_keeps_its_typed_row(
    language: str,
) -> None:
    question = QUESTIONS[language]

    steps = accepted_next_steps(
        [
            {"kind": "recurring_monthly_buys", "text": ""},
            {"kind": QUESTION_STEP, "text": question},
            {"kind": "change_date_range", "text": ""},
        ],
        test_kinds=KINDS,
    )
    patch = next_steps_patch(ROWS, steps)

    assert patch["next_steps"] == {
        "version": NEXT_STEPS_VERSION,
        "items": [
            {"type": "test", "kind": "recurring_monthly_buys"},
            {"type": "question", "text": question},
            {"type": "test", "kind": "change_date_range"},
        ],
    }
    rows = patch["next_experiments"]["rows"]
    assert [row["kind"] for row in rows] == [
        "recurring_monthly_buys",
        "change_date_range",
    ]
    # A runnable step sends exactly what its Try next row sends.
    assert rows[0]["send_text"] == ROWS["rows"][1]["send_text"]
    assert patch["next_experiments"]["source_run_id"] == "run-docn"
    # The answer above gives the reasons; rows under it carry no caption.
    assert all("why" not in row for row in rows)


def test_questions_lose_invisible_characters_and_repeats_and_unoffered_tests_drop() -> (
    None
):
    steps = accepted_next_steps(
        [
            {
                "kind": QUESTION_STEP,
                "text": "Should I compare it with a moving average crossover?​​",
            },
            {
                "kind": QUESTION_STEP,
                "text": "should i compare it with a  moving average crossover?",
            },
            {"kind": "same_rule_peer_asset", "text": ""},
            {"kind": "change_date_range", "text": ""},
            {"kind": "change_date_range", "text": ""},
            {"kind": QUESTION_STEP, "text": "   "},
            {"kind": QUESTION_STEP, "text": "x" * 200},
            "not a step",
        ],
        test_kinds=KINDS,
    )

    assert steps == (
        NextStep(QUESTION_STEP, "Should I compare it with a moving average crossover?"),
        NextStep("change_date_range"),
    )


def test_the_list_holds_at_most_five_steps() -> None:
    values = [
        {"kind": QUESTION_STEP, "text": f"Question {number}?"} for number in range(8)
    ]

    assert len(accepted_next_steps(values, test_kinds=KINDS)) == MAX_NEXT_STEPS


def test_a_tests_only_list_is_the_rows_in_their_order() -> None:
    patch = next_steps_patch(ROWS, offered_test_steps(ROWS))

    assert [item["kind"] for item in patch["next_steps"]["items"]] == list(KINDS)
    assert [row["kind"] for row in patch["next_experiments"]["rows"]] == list(KINDS)


def test_a_test_the_result_does_not_offer_never_reaches_the_list() -> None:
    assert next_steps_patch(None, offered_test_steps(None)) == {}
    assert next_steps_patch(None, (NextStep("change_date_range"),)) == {}


def test_a_questions_only_list_carries_no_rows() -> None:
    patch = next_steps_patch(ROWS, (NextStep(QUESTION_STEP, QUESTIONS["es-419"]),))

    assert patch["next_steps"]["items"] == [
        {"type": "question", "text": QUESTIONS["es-419"]}
    ]
    assert "next_experiments" not in patch


def test_a_research_answer_lists_its_tests_then_two_to_four_questions() -> None:
    from argus.agent_runtime.result_next_steps import research_next_steps

    rows = {
        "version": "argus_next_experiments/v1",
        "rows": [
            {"kind": "research_test_single", "label": "a"},
            {"kind": "research_test_single", "label": "b"},
            {"kind": "research_test_versus", "label": "c"},
        ],
    }
    follow_up = {
        "questions": [
            "What is an APR?",
            "what is an apr?",
            "",
            "How are annual fees charged?",
            "Do rewards expire?",
            "What is a balance transfer?",
            "How is interest compounded?",
        ]
    }
    items = research_next_steps(follow_up, rows)["next_steps"]["items"]
    assert [item["type"] for item in items] == ["test"] * 3 + ["question"] * 2
    assert [item["text"] for item in items[3:]] == [
        "What is an APR?",
        "How are annual fees charged?",
    ]
    questions_only = research_next_steps(follow_up, None)
    assert len(questions_only["next_steps"]["items"]) == 4
    assert "next_experiments" not in questions_only
    assert research_next_steps(None, None) == {}
