import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from argus.domain.owner_scope import PERSONAL
from argus.domain.recording.asset_schemas import AssetDetailsRequest, AssetEstimateRequest
from argus.domain.recording.assets import AssetService
from argus.domain.recording.errors import (
    AccountNotFound,
    IdempotencyConflict,
    RecordingInputError,
    StaleVersion,
)
from argus.domain.recording.loop_reads import home_response
from argus.domain.recording.repository import InMemoryFinancialAccountRepository
from argus.domain.recording.schemas import (
    CreateFinancialAccountRequest,
    EditFinancialAccountRequest,
    account_response,
)
from argus.domain.recording.service import FinancialAccountService
from faker import Faker

fake = Faker()
NOW = datetime(2026, 9, 30, 12, tzinfo=timezone.utc)


@pytest.fixture(params=["memory", "postgres"])
def assets(request):
    pool = None
    owner = str(uuid4())
    if request.param == "postgres":
        dsn = os.getenv("ARGUS_DISPOSABLE_DATABASE_URL")
        if not dsn:
            pytest.skip("ARGUS_DISPOSABLE_DATABASE_URL is not configured")
        from argus.domain.recording.postgres_repository import (
            PostgresFinancialAccountRepository,
        )
        from psycopg_pool import ConnectionPool

        pool = ConnectionPool(dsn, min_size=0, max_size=4)
        repository = PostgresFinancialAccountRepository(pool)
        with pool.connection() as connection:
            connection.execute(
                "insert into auth.users(id,email,is_anonymous) values(%s,%s,false)",
                (owner, f"assets-{owner}@example.test"),
            )
    else:
        repository = InMemoryFinancialAccountRepository(lambda: NOW)
    service = FinancialAccountService(repository, lambda: NOW)
    try:
        yield service, AssetService(service), owner
    finally:
        if pool:
            with pool.connection() as connection:
                connection.execute("delete from auth.users where id=%s", (owner,))
            pool.close()


def create(service, owner, kind="property", amount="8000000", share=5000, currency="DOP"):
    return service.create(
        user_id=owner,
        idempotency_key=str(uuid4()),
        request=CreateFinancialAccountRequest(
            type=kind,
            amount=amount,
            currency=currency,
            nickname=fake.word(),
            ownership_share_bps=share,
            as_of=NOW - timedelta(days=10),
        ),
        scope=PERSONAL,
    ).stored


def estimate(asset_service, owner, stored, amount, days, selected=None, key=None):
    request = AssetEstimateRequest(
        expected_version=stored.account.version,
        amount=amount,
        as_of=NOW - timedelta(days=days),
        time_zone="America/Santo_Domingo",
        estimate_basis=fake.sentence(),
        record_id=selected.record_id if selected else None,
        expected_revision=selected.revision if selected else None,
        reason="Correct amount" if selected else None,
    )
    preview = asset_service.preview(owner, stored.account.id, request)
    request.preview_token = preview.preview_token
    return asset_service.write(
        owner, stored.account.id, request, key or str(uuid4())
    ), request


@pytest.mark.parametrize("kind", ["property", "vehicle", "other_asset"])
@pytest.mark.parametrize("amount,expected", [(None, None), ("0", 0), ("0.03", 2)])
def test_optional_asset_values_and_half_share(assets, kind, amount, expected):
    service, _, owner = assets
    stored = create(service, owner, kind, amount)
    response = account_response(stored)
    assert response.asset.personal_position_minor == expected
    assert (response.asset.current_estimate is None) == (amount is None)
    totals = home_response([stored], now=NOW)["currencies"][0]
    assert totals["cash_minor"] == "0"
    assert totals["net_worth_minor"] == str(expected or 0)
    assert totals["unknown_accounts"] == int(amount is None)


def test_old_correction_keeps_current_estimate_and_revision_basis(assets):
    service, api, owner = assets
    original = create(service, owner)
    first, _ = estimate(api, owner, original, "9000000", 5)
    second, _ = estimate(api, owner, first.stored, "10000000", 1)
    old = account_response(second.stored).asset.estimates[1]
    corrected, request = estimate(api, owner, second.stored, "9100000", 5, old)
    projection = account_response(corrected.stored).asset
    assert projection.personal_position_minor == 500000000
    assert projection.current_estimate.record_id == second.record_id
    assert projection.estimates[1].revision == 2
    assert projection.estimates[1].revisions[0].amount_minor == 900000000
    assert projection.estimates[1].estimate_basis == request.estimate_basis
    assert projection.estimates[1].revisions[0].estimate_basis != request.estimate_basis
    assert len(corrected.stored.checks) == 2


def test_link_share_replay_and_debt_count_once(assets):
    service, api, owner = assets
    house = create(service, owner)
    debt = create(service, owner, "other_debt", "1000000", 10000)
    request = AssetDetailsRequest(
        expected_version=1,
        ownership_share_bps=5000,
        related_debt_account_id=debt.account.id,
    )
    key = str(uuid4())
    linked = api.details(owner, house.account.id, request, key)
    car = create(service, owner, "vehicle", "100000", 10000)
    api.details(owner, car.account.id, request, str(uuid4()))
    later, _ = estimate(api, owner, linked.stored, "9000000", 1)
    replay = api.details(owner, house.account.id, request, key)
    assert replay.replayed and replay.change_version == 2
    assert replay.stored.account.version == later.stored.account.version
    assert len(replay.stored.asset_changes) == 1
    totals = home_response(service.list_accounts(user_id=owner, scope=PERSONAL), now=NOW)[
        "currencies"
    ][0]
    assert totals["net_worth_minor"] == "355000000"
    assert totals["cash_minor"] == "0"
    assert totals["debts_minor"] == "100000000"
    with pytest.raises(IdempotencyConflict):
        api.details(
            owner,
            house.account.id,
            request.model_copy(update={"ownership_share_bps": 10000}),
            key,
        )
    with pytest.raises(StaleVersion):
        api.details(owner, house.account.id, request, str(uuid4()))
    with pytest.raises(AccountNotFound):
        api.details(str(uuid4()), house.account.id, request, str(uuid4()))


def test_estimate_replay_after_newer_write_and_opening_correction(assets):
    service, api, owner = assets
    asset = create(service, owner)
    original = account_response(asset).asset.current_estimate
    key = str(uuid4())
    corrected, body = estimate(api, owner, asset, "8100000", 10, original, key)
    newer, _ = estimate(api, owner, corrected.stored, "9000000", 1)
    replay = api.write(owner, asset.account.id, body, key)
    assert replay.replayed and replay.revision == 2
    assert replay.stored.account.version == newer.stored.account.version
    assert account_response(replay.stored).asset.personal_position_minor == 450000000
    assert replay.stored.opening.revisions[0].amount_minor == 800000000
    assert replay.stored.opening.current.estimate_basis == body.estimate_basis
    with pytest.raises(StaleVersion):
        api.write(owner, asset.account.id, body, str(uuid4()))
    with pytest.raises(IdempotencyConflict):
        api.write(
            owner,
            asset.account.id,
            body.model_copy(update={"estimate_basis": "Changed basis"}),
            key,
        )


@pytest.mark.usefixtures("legacy_blank_accounts")
def test_unknown_cross_currency_link_archive_restore_and_unlink_history(assets):
    from argus.domain.recording.schemas import EditFinancialAccountRequest

    service, api, owner = assets
    asset = create(service, owner, amount=None)
    debt = create(service, owner, "other_debt", None, 10000, "USD")
    api.details(
        owner,
        asset.account.id,
        AssetDetailsRequest(
            expected_version=1,
            ownership_share_bps=3333,
            related_debt_account_id=debt.account.id,
        ),
        str(uuid4()),
    )
    archived = service.edit(
        user_id=owner,
        account_id=asset.account.id,
        request=EditFinancialAccountRequest(expected_version=2, archived=True),
        scope=PERSONAL,
    )
    restored = service.edit(
        user_id=owner,
        account_id=asset.account.id,
        request=EditFinancialAccountRequest(expected_version=3, archived=False),
        scope=PERSONAL,
    )
    assert archived.account.archived and restored.account.id == asset.account.id
    assert restored.related_debt_account_id == debt.account.id
    unlinked = api.details(
        owner,
        asset.account.id,
        AssetDetailsRequest(
            expected_version=4, ownership_share_bps=10000, related_debt_account_id=None
        ),
        str(uuid4()),
    )
    assert len(unlinked.stored.asset_changes) == 2
    assert unlinked.stored.asset_changes[1].previous_debt_account_id == debt.account.id
    assert unlinked.stored.related_debt_account_id is None
    groups = {
        g["currency"]: g
        for g in home_response(
            service.list_accounts(user_id=owner, scope=PERSONAL), now=NOW
        )["currencies"]
    }
    assert set(groups) == {"DOP", "USD"}
    assert all(
        g["net_worth_minor"] == "0" and g["unknown_accounts"] == 1
        for g in groups.values()
    )


def test_concurrent_link_and_estimate_accept_only_one_version(assets):
    from concurrent.futures import ThreadPoolExecutor

    service, api, owner = assets
    asset = create(service, owner)
    request = AssetDetailsRequest(
        expected_version=1, ownership_share_bps=7500, related_debt_account_id=None
    )

    def change():
        try:
            return api.details(owner, asset.account.id, request, str(uuid4()))
        except StaleVersion:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: change(), range(2)))
    assert sum(r is not None for r in results) == 1
    assert (
        service.get(
            user_id=owner, account_id=asset.account.id, scope=PERSONAL
        ).account.version
        == 2
    )


@pytest.mark.parametrize("kind", ["property", "vehicle", "other_asset"])
@pytest.mark.parametrize("share,personal_minor", [(5000, 500000), (3333, 333300)])
def test_unknown_asset_details_lock_type_and_preserve_history(
    assets, client, monkeypatch, kind, share, personal_minor
):
    from argus.api.financial_accounts import (
        FinancialAccountsContext,
        require_financial_accounts_context,
    )

    service, api, owner = assets
    asset = create(service, owner, kind=kind, amount=None)
    request = AssetDetailsRequest(
        expected_version=1, ownership_share_bps=share, related_debt_account_id=None
    )
    key = str(uuid4())
    accepted = api.details(owner, asset.account.id, request, key)
    history = accepted.stored.asset_changes
    assert accepted.stored.opening is None
    assert not accepted.stored.has_records and not accepted.stored.has_activity
    assert accepted.stored.related_debt_account_id is None
    assert len(history) == 1
    edit = EditFinancialAccountRequest(expected_version=2, type="checking")
    with pytest.raises(RecordingInputError, match="type_locked"):
        service.edit(
            user_id=owner, account_id=asset.account.id, request=edit, scope=PERSONAL
        )

    monkeypatch.setitem(
        client.app.dependency_overrides,
        require_financial_accounts_context,
        lambda: FinancialAccountsContext(service=service, user_id=owner),
    )
    response = client.patch(
        "/api/v1/financial-accounts/" + asset.account.id,
        json=edit.model_dump(exclude_none=True),
    )
    assert response.status_code == 422, response.text
    assert response.json()["code"] == "type_locked"
    unchanged = service.get(user_id=owner, account_id=asset.account.id, scope=PERSONAL)
    assert unchanged.account.type == kind
    assert unchanged.account.version == 2
    assert unchanged.asset_changes == history
    archived = service.edit(
        user_id=owner,
        account_id=asset.account.id,
        request=EditFinancialAccountRequest(
            expected_version=2, nickname="Updated asset", archived=True
        ),
        scope=PERSONAL,
    )
    restored = service.edit(
        user_id=owner,
        account_id=asset.account.id,
        request=EditFinancialAccountRequest(expected_version=3, archived=False),
        scope=PERSONAL,
    )
    assert archived.account.archived and not restored.account.archived
    assert restored.account.nickname == "Updated asset"
    replay = api.details(owner, asset.account.id, request, key)
    assert replay.replayed and replay.change_version == 2
    assert replay.stored.account.version == 4
    assert replay.stored.asset_changes == history
    assert account_response(replay.stored).asset.changes[0].ownership_share_bps == share
    valued, _ = estimate(api, owner, replay.stored, "10000", 1)
    assert account_response(valued.stored).asset.personal_position_minor == personal_minor
    assert valued.stored.asset_changes == history
