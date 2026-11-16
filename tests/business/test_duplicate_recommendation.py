from __future__ import annotations

import pytest
from argus.domain.business.duplicates import recommendation


@pytest.mark.parametrize(
    ("one", "other", "expected"),
    [
        ("B0100000001", "B0100000002", "different_purchase"),
        ("B0100000001", " b0100000001", "same_purchase"),
        ("E310000000001", "E310000000001", "same_purchase"),
        (None, None, None),
        ("B0100000001", None, None),
        (None, "B0100000001", None),
        ("  ", "B0100000001", None),
    ],
)
def test_the_fiscal_number_decides_the_recommendation(one, other, expected):
    assert recommendation(one, other) == expected
