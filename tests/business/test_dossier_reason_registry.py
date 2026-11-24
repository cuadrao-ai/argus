from argus.domain.business.bandeja_group import RULE
from argus.domain.business.missing_reasons import REASONS


def test_every_gap_the_bandeja_rule_can_emit_is_registered() -> None:
    assert {gap.reason for gap in RULE} <= REASONS.keys()
