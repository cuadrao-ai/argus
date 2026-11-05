from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from argus.domain.owner_scope import PERSONAL, BusinessSpace
from argus.domain.recording.money_reads import current_activities
from argus.domain.recording.money_schemas import MoneyRequest, OwnerFunds, UnstatedFunding
from argus.domain.recording.money_service import MoneyService
from argus.domain.recording.repository import InMemoryFinancialAccountRepository
from argus.domain.recording.schemas import CreateFinancialAccountRequest
from argus.domain.recording.service import FinancialAccountService

NOW = datetime(2026, 10, 6, 12, tzinfo=timezone.utc)


@pytest.fixture
def lookup_scene():
    repository = InMemoryFinancialAccountRepository(lambda: NOW)
    yield (
        MoneyService(FinancialAccountService(repository, lambda: NOW)),
        str(uuid4()),
        BusinessSpace(str(uuid4())),
    )


def save_activity(money, user, scope, funding, *, kind="expense"):
    fields = {}
    if funding == "account":
        fields["account_id"] = money.accounts.create(
            user_id=user,
            scope=scope,
            idempotency_key=str(uuid4()),
            request=CreateFinancialAccountRequest(type="checking", currency="DOP"),
        ).stored.account.id
    elif funding == "owner":
        fields["owner_funding"] = OwnerFunds(
            owner_space_id=scope.space_id, currency="DOP"
        )
    else:
        fields["unstated_funding"] = UnstatedFunding(
            owner_space_id=scope.space_id, currency="DOP"
        )
    return money.write_entered(
        user_id=user,
        scope=scope,
        idempotency_key=str(uuid4()),
        request=MoneyRequest(
            kind=kind, amount="250.50", occurred_at=NOW - timedelta(days=1), **fields
        ),
    )["activity"]


@pytest.mark.parametrize("funding", ["account", "owner", "unstated"])
def test_lookup_matches_existing_projection_without_listing(
    lookup_scene, funding, monkeypatch
):
    money, user, scope = lookup_scene
    saved = save_activity(money, user, scope, funding)
    save_activity(money, user, scope, funding)
    expected = next(
        a
        for a in current_activities(
            money.accounts.list_accounts(user_id=user, scope=scope)
        )
        if a["activity_id"] == saved["activity_id"]
    )
    monkeypatch.setattr(
        money.repository,
        "list_accounts",
        lambda **kwargs: pytest.fail("lookup listed all accounts"),
    )
    assert (
        money.repository.get_activity(
            user_id=user, scope=scope, activity_id=saved["activity_id"]
        )
        == expected
    )


@pytest.mark.parametrize("funding", ["account", "owner", "unstated"])
@pytest.mark.parametrize(
    "outside", ["missing", "business", "person", "personal", "malformed"]
)
def test_lookup_returns_none_outside_scope(lookup_scene, funding, outside):
    money, user, scope = lookup_scene
    saved = save_activity(money, user, scope, funding)
    activity_id = saved["activity_id"]
    if outside == "missing":
        activity_id = str(uuid4())
    elif outside == "business":
        scope = BusinessSpace(str(uuid4()))
    elif outside == "person":
        user = str(uuid4())
    elif outside == "personal":
        scope = PERSONAL
    else:
        activity_id = "not-an-id"
    assert (
        money.repository.get_activity(user_id=user, scope=scope, activity_id=activity_id)
        is None
    )
