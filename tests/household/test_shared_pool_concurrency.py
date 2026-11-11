"""Household reads and grant writes reuse their checked-out business client."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, local

import pytest
from argus.domain.household.schemas import Recipient

from tests.household.financial_fixtures import DSN, account, setup, share

pytestmark = pytest.mark.skipif(not DSN, reason="Disposable PostgreSQL required")


@pytest.mark.parametrize("operation", ["list", "create", "replace"])
def test_two_household_requests_finish_with_two_shared_connections(
    lane, monkeypatch: pytest.MonkeyPatch, operation: str
) -> None:
    service, records, (owner, recipient, _) = lane
    household_id, membership_id, _ = setup(lane)
    account_id = account(records, owner)
    share(service, owner, household_id, account_id, membership_id)
    repository = service._repository
    pool = records._pool
    pool.resize(min_size=2, max_size=2)
    pool.timeout = 0.5
    ready = Barrier(2, timeout=3)
    thread_state = local()
    require_member = repository._require_member_row

    def hold_both_connections(connection, **kwargs):
        if not getattr(thread_state, "ready", False):
            thread_state.ready = True
            ready.wait()
        return require_member(connection, **kwargs)

    monkeypatch.setattr(repository, "_require_member_row", hold_both_connections)

    def request():
        if operation == "list":
            result = repository.list_shared_accounts(
                user_id=recipient, household_id=household_id
            )
            assert [view.account_id for view in result] == [account_id]
        elif operation == "create":
            result = repository.create_grant(
                user_id=owner,
                household_id=household_id,
                account_id=account_id,
                permission="view",
                recipient_membership_id=membership_id,
            )
            assert result.account_id == account_id
        else:
            repository.replace_grants(
                user_id=owner,
                household_id=household_id,
                account_id=account_id,
                recipients=[Recipient(membership_id=membership_id)],
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(request) for _ in range(2)]
        for future in futures:
            future.result(timeout=4)
    assert pool.get_stats().get("requests_waiting", 0) == 0
