from datetime import timedelta
from uuid import uuid4

import pytest
from argus.domain.financial_search import InvalidCursor, StaleCursor, search
from argus.domain.owner_scope import PERSONAL
from argus.domain.planning.schemas import ExpectationCreate, ExpectationEdit, Schedule
from argus.domain.planning.service import PlanService
from argus.domain.recording.money_schemas import MoneyRequest
from argus.domain.recording.money_service import MoneyService
from argus.domain.recording.schemas import EditFinancialAccountRequest
from faker import Faker

from tests.financial_accounts import test_loop_commands as shared
from tests.financial_accounts.test_loop_commands import NOW
from tests.financial_accounts.test_personal_money import account, save

scene = shared.scene
fake = Faker()


def test_logical_transfer_and_current_correction_only(scene):
    service, owner, first = scene
    second = account(scene)
    original = save(
        scene,
        kind="transfer",
        source_account_id=first,
        destination_account_id=second,
        amount="25",
        note="Old transfer",
    )["activity"]
    found = search(service, owner, q="Old transfer", kind="activity").items
    assert len(found) == 1 and found[0].activity.activity_id == original["activity_id"]
    money = MoneyService(service)
    request = MoneyRequest(
        kind="transfer",
        source_account_id=first,
        destination_account_id=second,
        amount="30",
        note="Nueva transferencia",
        occurred_at=NOW - timedelta(days=2),
        expected_revision=original["revision"],
        reason=fake.sentence(),
    )
    preview = money.preview(
        user_id=owner,
        request=request,
        activity_id=original["activity_id"],
        scope=PERSONAL,
    )
    request = MoneyRequest.model_validate(preview["reviewed_request"]).model_copy(
        update={"preview_token": preview["preview_token"]}
    )
    money.write(
        user_id=owner,
        request=request,
        activity_id=original["activity_id"],
        idempotency_key=str(uuid4()),
        scope=PERSONAL,
    )
    assert not search(service, owner, q="Old transfer").items
    current = search(service, owner, q="Nueva", kind="activity").items
    assert len(current) == 1 and current[0].activity.amount == "30.00"
    assert len(current[0].activity.legs) == 2
    assert not search(service, str(uuid4()), q="Nueva").items


@pytest.mark.parametrize("query", ["cafe", "CAFÉ", "%", "_", "'", "\\"])
def test_accent_and_literal_search_queries(scene, query):
    service, owner, aid = scene
    service.edit(
        user_id=owner,
        account_id=aid,
        request=EditFinancialAccountRequest(
            expected_version=1, nickname="Café 100%_ ' " + chr(92), archived=True
        ),
        scope=PERSONAL,
    )
    found = search(service, owner, q=query).items
    assert len(found) == 1 and found[0].account.id == aid
    assert found[0].account.archived
    assert not search(service, owner, q="%%%").items


def test_snapshot_cursor_scope_staleness_and_stable_pages(scene):
    service, owner, aid = scene
    for _ in range(5):
        account(scene)
    page = search(service, owner, limit=2)
    ids = [hit.account.id for hit in page.items]
    cursor = page.next_cursor
    assert cursor
    for options in ({"q": "cash"}, {"kind": "account"}, {"currency": "USD"}):
        with pytest.raises(InvalidCursor):
            search(service, owner, cursor=cursor, **options)
    with pytest.raises(InvalidCursor):
        search(service, str(uuid4()), cursor=cursor)
    while page.next_cursor:
        page = search(service, owner, limit=2, cursor=page.next_cursor)
        ids.extend(hit.account.id for hit in page.items)
    assert len(ids) == len(set(ids)) == 6
    service.edit(
        user_id=owner,
        account_id=aid,
        request=EditFinancialAccountRequest(expected_version=1, nickname=fake.word()),
        scope=PERSONAL,
    )
    with pytest.raises(StaleCursor):
        search(service, owner, cursor=cursor)
    for invalid in ("not a cursor", "e30=", "W10=", "bnVsbA=="):
        with pytest.raises(InvalidCursor):
            search(service, owner, cursor=invalid)


def test_archived_outside_forecast_expectation_is_findable_and_opens_exact_id(scene):
    service, owner, aid = scene
    planner = PlanService(service)
    item = planner.create(
        owner,
        ExpectationCreate(
            kind="bill",
            title=fake.sentence(),
            currency="DOP",
            amount="40",
            account_id=aid,
            schedule=Schedule(
                cadence="once", start_date=NOW.date() + timedelta(days=500)
            ),
        ),
        str(uuid4()),
    )["expectation"]
    planner.edit(
        owner,
        item["id"],
        ExpectationEdit(expected_version=1, archived=True),
        str(uuid4()),
    )
    page = search(service, owner, kind="expectation", currency="DOP")
    assert len(page.items) == 1 and page.items[0].expectation.archived
    assert planner.get(owner, item["id"])["id"] == item["id"]
    assert not search(service, owner, kind="expectation", currency="USD").items
