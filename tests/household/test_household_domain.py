"""Domain-level household permission package checks."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from argus.domain.household.errors import InvitationExpired, InvitationRevoked
from argus.domain.household.repository import InMemoryHouseholdRepository
from argus.domain.household.schemas import (
    CreateAccountGrantRequest,
    CreateHouseholdRequest,
    OwnedAccountRef,
)
from argus.domain.household.service import HouseholdService


class DictAccounts:
    def __init__(self) -> None:
        self._items: dict[str, OwnedAccountRef] = {}

    def add(self, *, user_id: str, nickname: str = "A") -> OwnedAccountRef:
        ref = OwnedAccountRef(
            id=str(uuid4()),
            user_id=user_id,
            type="checking",
            currency="DOP",
            nickname=nickname,
            archived=False,
            ownership_share_bps=10_000,
        )
        self._items[ref.id] = ref
        return ref

    def owned_account(self, *, user_id: str, account_id: str) -> OwnedAccountRef | None:
        item = self._items.get(account_id)
        if item is None or item.user_id != user_id:
            return None
        return item

    def account_by_id(self, *, account_id: str) -> OwnedAccountRef | None:
        return self._items.get(account_id)


def test_invitation_expiry_and_revoke() -> None:
    clock = {"now": datetime(2026, 10, 1, tzinfo=timezone.utc)}

    def now() -> datetime:
        return clock["now"]

    accounts = DictAccounts()
    service = HouseholdService(InMemoryHouseholdRepository(accounts, clock=now))
    alice = str(uuid4())
    bob = str(uuid4())
    household = service.create(user_id=alice, request=CreateHouseholdRequest(name="Casa"))
    invite = service.invite(user_id=alice, household_id=household.id)

    clock["now"] = clock["now"] + timedelta(days=8)
    with pytest.raises(InvitationExpired):
        service.accept(user_id=bob, token=invite.token)

    clock["now"] = datetime(2026, 10, 1, tzinfo=timezone.utc)
    invite2 = service.invite(user_id=alice, household_id=household.id)
    service.revoke_invitation(
        user_id=alice, household_id=household.id, invitation_id=invite2.id
    )
    with pytest.raises(InvitationRevoked):
        service.accept(user_id=bob, token=invite2.token)


def test_share_defaults_to_view() -> None:
    accounts = DictAccounts()
    service = HouseholdService(InMemoryHouseholdRepository(accounts))
    alice = str(uuid4())
    household = service.create(user_id=alice, request=CreateHouseholdRequest())
    invite = service.invite(user_id=alice, household_id=household.id)
    member = service.accept(user_id=str(uuid4()), token=invite.token)
    account = accounts.add(user_id=alice)
    grant = service.create_grant(
        user_id=alice,
        household_id=household.id,
        request=CreateAccountGrantRequest(
            account_id=account.id,
            recipient_membership_id=member.membership_id,
            expected_version=household.version,
        ),
    )
    assert grant.permission == "view"
