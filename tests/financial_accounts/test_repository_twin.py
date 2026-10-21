"""The in-memory twin honors the same storage bases the Postgres functions do."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from argus.domain.owner_scope import PERSONAL
from argus.domain.recording.errors import StaleVersion
from argus.domain.recording.records import OpeningWrite
from argus.domain.recording.repository import (
    InMemoryFinancialAccountRepository,
    NewAccount,
)

NOW = datetime(2026, 9, 1, 13, 0, tzinfo=timezone.utc)


def test_an_opening_write_is_stale_once_the_account_moved() -> None:
    repository = InMemoryFinancialAccountRepository()
    owner = "owner"
    created = repository.create(
        user_id=owner,
        idempotency_key="k",
        identity_hash="h",
        account=NewAccount("cash", "USD", None, 10_000),
        opening=None,
        scope=PERSONAL,
    ).stored
    repository.update_account(
        user_id=owner,
        account_id=created.account.id,
        expected_version=1,
        changes={"currency": "JPY"},
        scope=PERSONAL,
    )
    with pytest.raises(StaleVersion):
        repository.write_opening(
            user_id=owner,
            account_id=created.account.id,
            expected_revision=None,
            expected_version=1,
            write=OpeningWrite(123, NOW, "America/Santo_Domingo", None),
            scope=PERSONAL,
        )
    assert (
        repository.get_account(
            user_id=owner, account_id=created.account.id, scope=PERSONAL
        ).opening
        is None
    )

    written = repository.write_opening(
        user_id=owner,
        account_id=created.account.id,
        expected_revision=None,
        expected_version=2,
        write=OpeningWrite(123, NOW, "America/Santo_Domingo", None),
        scope=PERSONAL,
    )
    assert written.opening is not None
    assert written.account.version == 3
