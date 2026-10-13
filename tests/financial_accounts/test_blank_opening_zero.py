from uuid import uuid4

import pytest
from argus.domain.owner_scope import PERSONAL, BusinessSpace
from argus.domain.planning.schemas import SelectionWrite
from argus.domain.planning.service import PlanService
from argus.domain.recording.loop_reads import home_response
from argus.domain.recording.schemas import CreateFinancialAccountRequest

from tests.financial_accounts import test_loop_commands as shared

scene = shared.scene

MONEY_TYPES = ["cash", "checking", "savings", "investment", "credit_card", "other_debt"]
OPTIONAL_ASSETS = ["property", "vehicle", "other_asset"]


def create(scene, kind, amount=None, scope=PERSONAL, currency="DOP"):
    service, user, _ = scene
    return service.create(
        user_id=user,
        idempotency_key=str(uuid4()),
        request=CreateFinancialAccountRequest(
            type=kind, currency=currency, amount=amount
        ),
        scope=scope,
    ).stored


@pytest.mark.parametrize("kind", MONEY_TYPES)
def test_blank_money_account_records_an_opening_of_zero(scene, kind):
    stored = create(scene, kind)
    assert stored.opening is not None
    assert stored.opening.current.amount_minor == 0
    service, user, _ = scene
    balance = service.get(user_id=user, account_id=stored.account.id, scope=PERSONAL)
    assert balance.opening.current.amount_minor == 0


@pytest.mark.parametrize("kind", MONEY_TYPES)
def test_blank_and_typed_zero_read_the_same(scene, kind):
    blank, typed = create(scene, kind), create(scene, kind, "0")
    service, user, _ = scene
    rows = {
        row["currency"]: row
        for row in home_response(service.list_accounts(user_id=user, scope=PERSONAL))[
            "currencies"
        ]
    }
    assert blank.opening.current.amount_minor == typed.opening.current.amount_minor == 0
    assert rows["DOP"]["unknown_accounts"] == 0


@pytest.mark.parametrize("kind", OPTIONAL_ASSETS)
def test_blank_asset_value_stays_unknown(scene, kind):
    assert create(scene, kind).opening is None


def test_business_blank_account_stays_unknown():
    from argus.domain.recording.repository import InMemoryFinancialAccountRepository
    from argus.domain.recording.service import FinancialAccountService

    service = FinancialAccountService(InMemoryFinancialAccountRepository())
    business = (service, str(uuid4()), None)
    assert create(business, "checking", scope=BusinessSpace(str(uuid4()))).opening is None


def test_home_total_counts_blank_accounts_as_zero(scene):
    service, user, _ = scene
    create(scene, "cash", currency="USD")
    create(scene, "checking", "100", currency="USD")
    create(scene, "credit_card", currency="USD")
    usd = next(
        row
        for row in home_response(service.list_accounts(user_id=user, scope=PERSONAL))[
            "currencies"
        ]
        if row["currency"] == "USD"
    )
    assert usd["net_worth_minor"] == "10000"
    assert usd["known_accounts"] == 3 and usd["unknown_accounts"] == 0


def test_plan_totals_read_the_recorded_zero(scene):
    service, user, _ = scene
    funded = create(scene, "checking", "100")
    blank = create(scene, "cash")
    planner = PlanService(service)
    planner.selection(
        user,
        SelectionWrite(
            expected_version=0,
            account_ids=[funded.account.id, blank.account.id],
            time_zone="America/Santo_Domingo",
        ),
        str(uuid4()),
    )
    dop = planner.read(user)["currencies"][0]
    assert dop["starting_minor"] == "10000"
    assert dop["unknown_account_ids"] == []


def test_blank_create_retried_across_the_rule_change_replays(scene, monkeypatch):
    from argus.domain.recording import service as module

    service, user, _ = scene
    request = CreateFinancialAccountRequest(type="cash", currency="DOP")
    with monkeypatch.context() as before:
        before.setattr(module, "blank_opening", lambda scope, account_type: None)
        first = service.create(
            user_id=user, idempotency_key="blank", request=request, scope=PERSONAL
        )
    retry = service.create(
        user_id=user, idempotency_key="blank", request=request, scope=PERSONAL
    )
    assert first.created and not retry.created
    assert retry.stored.account.id == first.stored.account.id
