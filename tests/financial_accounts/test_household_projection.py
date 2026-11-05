from uuid import uuid4

import pytest
from argus.domain.household.access import (
    AccountAccess,
    HouseholdFinancialScope,
    dependencies,
    require_edit,
)
from argus.domain.household.errors import HouseholdNotFound as HouseholdUnavailable
from argus.domain.household.projection import activity
from argus.domain.owner_scope import PERSONAL
from argus.domain.recording.money_schemas import MoneyRequest

from tests.financial_accounts.test_loop_commands import NOW
from tests.financial_accounts.test_loop_commands import scene as scene
from tests.financial_accounts.test_personal_money import account, save


@pytest.mark.parametrize("visible_role", ["source", "destination"])
def test_canonical_history_is_redacted_after_rendering(scene, visible_role):  # noqa: F811
    service, owner, _ = scene
    source = account(scene, "checking", amount="1000")
    destination = account(scene, "other_debt", amount="1000")
    result = save(
        scene,
        kind="debt_payment",
        source_account_id=source,
        destination_account_id=destination,
        amount="110",
        principal="100",
        interest="8",
        fees="2",
    )
    aid = result["activity"]["activity_id"]
    visible = source if visible_role == "source" else destination
    records = service.list_accounts(user_id=owner, scope=PERSONAL)
    scope = HouseholdFinancialScope(
        str(uuid4()),
        str(uuid4()),
        str(uuid4()),
        1,
        {visible: AccountAccess(owner, "Owner", "edit")},
        {owner: "Owner"},
    )
    rendered = activity(scope, records, aid, all_owner_records=records)
    assert rendered["private_counterpart"] and not rendered["can_edit"]
    assert rendered["activity"]["amount_minor"] == (
        11000 if visible_role == "source" else None
    )
    assert rendered["activity"]["interest_minor"] is None
    assert [leg["account_id"] for leg in rendered["activity"]["legs"]] == [visible]
    command = MoneyRequest(
        kind="debt_payment",
        source_account_id=source,
        destination_account_id=destination,
        amount="110",
        occurred_at=NOW,
    )
    with pytest.raises(HouseholdUnavailable):
        require_edit(scope, dependencies(records, command, aid))
