"""One transaction boundary for canonical and legacy activity writers."""

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from typing import Any

from argus.domain.owner_scope import OwnerScope
from argus.domain.recording.errors import IdempotencyConflict
from argus.domain.recording.loop_storage import apply
from argus.domain.recording.money_plan import MoneyPlan
from argus.domain.recording.repository import (
    InMemoryFinancialAccountRepository,
    StoredAccount,
)


def transact(
    repository: Any,
    user_id: str,
    key: str,
    identity: str,
    planner: Callable[[list[StoredAccount]], MoneyPlan],
    now: datetime,
    legacy_account: str | None = None,
    *,
    scope: OwnerScope,
) -> tuple[list[StoredAccount], str, int, tuple[str, ...], bool]:
    if not isinstance(repository, InMemoryFinancialAccountRepository):
        from argus.domain.recording.money_postgres import transact_postgres

        return transact_postgres(
            repository, user_id, key, identity, planner, now, legacy_account, scope=scope
        )
    with repository._lock:
        owned = repository.held(user_id, scope)
        receipts = repository._money_receipts
        receipt = receipts.get((user_id, legacy_account, key))
        if receipt:
            old_hash, aid, revision, affected = receipt
            if old_hash != identity:
                raise IdempotencyConflict()
            return owned, aid, revision, affected, True
        if legacy_account:
            previous = repository._operations.get((user_id, legacy_account, key))
            if previous:
                old_hash, aid, revision, _ = previous
                if old_hash != identity:
                    raise IdempotencyConflict()
                return owned, aid, revision, (legacy_account,), True
        result = planner(owned)
        updates = {}
        for stored in owned:
            aid = stored.account.id
            if aid in result.mutations:
                updates[aid] = apply(stored, result.mutations[aid], now)
            elif aid in result.affected:
                updates[aid] = replace(
                    stored,
                    account=replace(
                        stored.account, version=stored.account.version + 1, updated_at=now
                    ),
                )
        repository._accounts.update(updates)
        receipts[(user_id, legacy_account, key)] = (
            identity,
            result.activity_id,
            result.revision,
            result.affected,
        )
        if legacy_account:
            repository._operations[(user_id, legacy_account, key)] = (
                identity,
                result.activity_id,
                result.revision,
                "expense",
            )
        return (
            [updates.get(s.account.id, s) for s in owned],
            result.activity_id,
            result.revision,
            result.affected,
            False,
        )
