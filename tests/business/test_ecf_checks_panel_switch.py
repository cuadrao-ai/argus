"""The e-CF checks card in review sits behind one server switch, off unless set."""

from __future__ import annotations

import pytest
from argus.domain.business.config import ecf_checks_panel_enabled

SWITCH = "CUADRAO_ECF_CHECKS_PANEL_ENABLED"


@pytest.mark.parametrize(
    ("value", "shown"), [(None, False), ("false", False), ("true", True)]
)
def test_review_shows_the_card_only_while_the_switch_is_on(
    monkeypatch: pytest.MonkeyPatch, value: str | None, shown: bool
) -> None:
    if value is None:
        monkeypatch.delenv(SWITCH, raising=False)
    else:
        monkeypatch.setenv(SWITCH, value)
    assert ecf_checks_panel_enabled() is shown
