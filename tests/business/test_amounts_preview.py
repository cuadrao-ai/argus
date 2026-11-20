from dataclasses import replace
from decimal import Decimal

import pytest
from argus.domain.business.actions.amounts_preview import preview_amounts
from argus.domain.business.amount_inheritance import written_from
from argus.domain.business.authority import ActionError
from argus.domain.business.contracts.amounts import AmountsPreviewRequest
from argus.domain.business.contracts.facts import BusinessResolution
from argus.domain.business.purchase_review import declaration_from_facts
from faker import Faker

from tests.business import test_fiscal_links as links
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
    result = preview_amounts(resolution, AmountsPreviewRequest(version=1, **changes))
    assert Decimal(result.net_amount.amount) == Decimal(net)
    assert result.mismatch.difference == difference
    assert resolution.model_dump() == before


def test_preview_recalculates_calculated_net_and_clears_mismatch():
    result = preview_amounts(BusinessResolution(facts=receipt('1280', '180', tip='100')), AmountsPreviewRequest(version=1, itbis={'state': 'known', 'value': '200'}))
    assert result.net_amount.amount == '980.00'
    assert result.net_amount.source == 'calculated'
    assert result.mismatch is None


def test_preview_warns_while_typing_a_net_the_total_cannot_hold_with_itbis_unknown():
    fake = Faker()
    fake.seed_instance(2288)
    total = Decimal(fake.random_int(100, 10_000_000)) / 100
    excess = Decimal(fake.random_int(2, 1_000_000)) / 100
    typed = format(total + excess, ".2f")
    result = preview_amounts(BusinessResolution(facts=receipt(format(total, ".2f"), None)), AmountsPreviewRequest(version=1, net_amount={'state': 'known', 'value': typed}))
    assert result.net_amount.amount == typed
    assert result.mismatch.difference == format(-excess, ".2f")


def _linked(facts):
    """What an open expense's review reads: remembered answers beside the declaration its facts state."""

    return replace(links.suggested(category="09", payment_method="01"), built=declaration_from_facts(facts, None))


def _preview(*, typed: dict, held: tuple = (), put_back: tuple = (), overrides: tuple | None = None):
    """The links of a draft typed over the shown declaration, saved before when ``overrides`` says so."""

    facts = links.read()
    linked = _linked(facts)
    shown = written_from(facts, None, None, None, linked)
    resolution = BusinessResolution(facts=facts, dgii=shown if overrides is not None else None, fiscal_overrides=overrides, amount_derived=True)
    request = AmountsPreviewRequest(version=1, declaration=shown.model_copy(update=typed), override_inherited=held, restore_inherited=put_back)
    return preview_amounts(resolution, request, linked).inheritance


@pytest.mark.parametrize(("change", "linked"), [
    ({"typed": {"goods_amount": "400.00"}, "held": ("goods_amount",)}, {"goods_amount": False, "services_amount": False, "paid_on": True, "itbis": True, "id_type": True}),
    ({"typed": {"services_amount": "600.00"}, "held": ("services_amount",), "put_back": ("goods_amount",)}, {"goods_amount": True, "services_amount": True}),
    ({"typed": {}, "put_back": ("services_amount",), "overrides": ("goods_amount", "services_amount")}, {"goods_amount": True, "services_amount": True}),
    ({"typed": {"paid_on": links.DAY.replace(day=20)}, "held": ("paid_on",)}, {"paid_on": False, "goods_amount": True, "services_amount": True}),
], ids=["one side typed", "one side restored beside the other typed", "a saved split restored", "fecha pago typed"])
def test_preview_links_follow_the_drafts_overrides_and_restores(change, linked):
    previewed = _preview(**change)
    assert {name: previewed[name].inherited for name in linked} == linked
    assert previewed["goods_amount"].value == "1000.00"


@pytest.mark.parametrize(("method", "day"), [("04", None), ("02", links.DAY.isoformat())])
def test_preview_fecha_pago_follows_the_drafts_forma_de_pago(method, day):
    paid_on = _preview(typed={"payment_method": method})["paid_on"]
    assert (paid_on.value, paid_on.inherited) == (day, True)


def test_preview_refuses_a_link_change_on_a_field_that_follows_nothing():
    with pytest.raises(ActionError) as refused:
        preview_amounts(BusinessResolution(facts=links.read()), AmountsPreviewRequest(version=1, restore_inherited=("category",)))
    assert refused.value.result.code == "business_amount_inheritance_invalid"


def test_preview_of_amounts_alone_shows_the_links_follow_the_typed_amount():
    facts = links.read()
    linked = _linked(facts)
    result = preview_amounts(
        BusinessResolution(facts=facts, dgii=written_from(facts, None, None, None, linked), fiscal_overrides=(), amount_derived=True),
        AmountsPreviewRequest(version=1, itbis={"state": "known", "value": "200"}),
        linked,
    )
    assert (result.inheritance["itbis"].value, result.inheritance["itbis"].inherited) == ("200", True)
