from __future__ import annotations

import re

from tests.evals.business_variety import load_variety_cases


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
