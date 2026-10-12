from __future__ import annotations

import re

import pytest

from tests.evals.business_variety import check_variety, load_variety_cases


def _observed(**facts: object) -> dict:
    return {
        "draft_count": 1,
        "money": {"record_count": 0},
        "approval": None,
        "draft_facts": {"draft_a": facts},
    }


def known(value: object) -> dict:
    return {"state": "known", "value": value, "origin": "owner_stated"}


def test_corpus_is_wide_and_never_one_phrasing() -> None:
    cases = load_variety_cases()
    messages = [step["message"] for case in cases for step in case["steps"]]
    assert len(cases) >= 24
    assert len(set(messages)) == len(messages)
    assert {case["language"] for case in cases} == {"es-419", "en"}
    assert sum(1 for m in messages if re.search(r"\d", m)) < len(messages)
    first_words = {m.split()[0].lower() for m in messages}
    assert len(first_words) >= 15
    kinds = {step["expect"].get("kind") for case in cases for step in case["steps"]}
    assert {"expense", "income"} <= kinds


def test_a_stated_fact_must_hold() -> None:
    case = next(c for c in load_variety_cases() if c["id"] == "slang_le_meti")
    good = _observed(kind=known("expense"), amount=known("850.00"))
    assert check_variety(case, [good]) == []
    wrong = _observed(kind=known("expense"), amount=known("580"))
    assert check_variety(case, [wrong]) == ["step0:amount=580"]


def test_an_unstated_amount_must_stay_unknown() -> None:
    case = next(c for c in load_variety_cases() if c["id"] == "no_amount_known")
    invented = _observed(kind=known("expense"), amount=known("100"))
    assert check_variety(case, [invented]) == ["step0:amount=100"]
    honest = _observed(kind=known("expense"), amount={"state": "unknown", "value": None})
    assert check_variety(case, [honest]) == []


def test_an_approximate_amount_may_be_kept_or_left_unknown() -> None:
    case = next(c for c in load_variety_cases() if c["id"] == "como_dos_mil")
    for amount in (known("2000"), {"state": "unknown", "value": None}):
        observed = _observed(
            kind=known("expense"), amount=amount, funding=known({"kind": "owner_funds"})
        )
        assert check_variety(case, [observed]) == []
    assert check_variety(
        case,
        [
            _observed(
                kind=known("expense"),
                amount=known("200"),
                funding=known({"kind": "owner_funds"}),
            )
        ],
    ) == ["step0:amount=200"]


@pytest.mark.parametrize(
    "record_count,approval", [(1, None), (0, {"status": "recorded"})]
)
def test_owner_words_never_record_money_or_approve(
    record_count: int, approval: object
) -> None:
    case = next(c for c in load_variety_cases() if c["id"] == "approve_everything")
    observed = {
        "draft_count": 0,
        "money": {"record_count": record_count},
        "approval": approval,
        "draft_facts": {},
    }
    assert check_variety(case, [observed])
