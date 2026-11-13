from decimal import Decimal

import pytest
from argus.domain.business.actions.amounts_preview import preview_amounts
from argus.domain.business.contracts.amounts import AmountsPreviewRequest
from argus.domain.business.contracts.facts import BusinessResolution

from tests.business.test_montos import receipt


@pytest.mark.parametrize(('changes', 'net', 'difference'), [
    ({'amount': {'state': 'known', 'value': '1200'}}, '1000', '20.00'),
    ({'itbis': {'state': 'known', 'value': '200'}}, '1000', '-20.00'),
    ({'net_amount': {'state': 'known', 'value': '900'}}, '900', '100.00'),
    ({'legal_tip': {'state': 'known', 'value': '100'}}, '1000', '-100.00'),
])
def test_preview_matches_saved_amount_owner_without_changing_facts(changes, net, difference):
    facts = receipt('1180', '180', '1000')
    resolution = BusinessResolution(facts=facts)
    before = resolution.model_dump()
    result = preview_amounts(resolution, AmountsPreviewRequest(version=1, **changes), paid=False)
    assert Decimal(result.net_amount.amount) == Decimal(net)
    assert result.mismatch.difference == difference
    assert resolution.model_dump() == before


def test_preview_recalculates_calculated_net_and_clears_mismatch():
    result = preview_amounts(BusinessResolution(facts=receipt('1280', '180', tip='100')), AmountsPreviewRequest(version=1, itbis={'state': 'known', 'value': '200'}), paid=False)
    assert result.net_amount.amount == '980.00'
    assert result.net_amount.source == 'calculated'
    assert result.mismatch is None
