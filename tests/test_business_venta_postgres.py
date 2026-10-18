from __future__ import annotations

import json
from datetime import date
from uuid import UUID

import pytest
from argus.domain.business.contracts.actions import ApproveExpense, Refused
from argus.domain.business.contracts.venta import (
    Customer,
    MarkVenta,
    SaleWrite,
    SetVentaCollection,
)
from argus.domain.business.sales import (
    load_sales_period,
    mark_venta,
    set_venta_collection,
)
from argus.domain.business.transactions import transaction
from faker import Faker

from tests import test_business_actions_postgres as shared

fake = Faker()
actions = shared.actions
users = shared.users
pytestmark = shared.pytestmark


def _request(draft_id: UUID, *, ncf: str | None = None) -> MarkVenta:
    return MarkVenta(
        draft_id=draft_id,
        invoice_total="1180.00",
        itbis_charged="180.00",
        customer=Customer(
            id_type="rnc",
            id_number="1" + fake.numerify("########"),
        ),
        ncf=ncf or f"B{fake.numerify('##########')}",
        issued_on=date(2026, 10, 15),
        collection_status="por_cobrar",
    )


def _count(service, statement: str, params: tuple = ()) -> int:  # noqa: ANN001
    with service.authority.pool.connection() as connection:
        return connection.execute(statement, params).fetchone()[0]


@pytest.mark.owner_acts
def test_mark_replay_and_changed_body_keep_one_sale(actions) -> None:  # noqa: ANN001
    service, context, _ = actions
    draft = shared.ready(service, context)
    request = _request(draft)

    first = mark_venta(service.authority, context, request, "mark")
    assert isinstance(first, SaleWrite) and first.created is True
    replay = mark_venta(service.authority, context, request, "mark")
    assert isinstance(replay, SaleWrite)
    assert replay.created is False and replay.sale == first.sale
    changed = request.model_copy(update={"invoice_total": "1200.00"})
    conflict = mark_venta(service.authority, context, changed, "mark")
    assert isinstance(conflict, Refused)
    assert (conflict.outcome, conflict.code) == (
        "idempotency_conflict",
        "business_action_conflict",
    )
    assert (
        _count(
            service,
            "select count(*) from public.business_sales where space_id=%s",
            (context.actor.space_id,),
        )
        == 1
    )


@pytest.mark.owner_acts
def test_a_second_draft_cannot_reuse_the_ncf(actions) -> None:  # noqa: ANN001
    service, context, _ = actions
    ncf = f"E{fake.numerify('############')}"
    first = mark_venta(
        service.authority,
        context,
        _request(shared.ready(service, context), ncf=ncf),
        "first",
    )
    assert isinstance(first, SaleWrite)
    second = mark_venta(
        service.authority,
        context,
        _request(shared.ready(service, context), ncf=ncf),
        "second",
    )
    assert isinstance(second, Refused)
    assert second.code == "business_venta_ncf_conflict"
    assert (
        _count(
            service,
            "select count(*) from public.business_sales"
            " where space_id=%s and ncf=%s",
            (context.actor.space_id, ncf),
        )
        == 1
    )


@pytest.mark.owner_acts
def test_collection_change_updates_period_itbis(actions) -> None:  # noqa: ANN001
    service, context, _ = actions
    marked = mark_venta(
        service.authority,
        context,
        _request(shared.ready(service, context)),
        "mark",
    )
    assert isinstance(marked, SaleWrite)
    with transaction(service.authority, context) as tx:
        before = load_sales_period(
            tx,
            space_id=context.actor.space_id,
            start=date(2026, 10, 1),
            end=date(2026, 10, 31),
        )
    assert str(before.itbis_cobrado) == "0.00"

    updated = set_venta_collection(
        service.authority,
        context,
        marked.sale.id,
        SetVentaCollection(collection_status="cobrado"),
        "collect",
    )
    assert not isinstance(updated, Refused)
    with transaction(service.authority, context) as tx:
        after = load_sales_period(
            tx,
            space_id=context.actor.space_id,
            start=date(2026, 10, 1),
            end=date(2026, 10, 31),
        )
    assert str(after.itbis_cobrado) == "180.00"


@pytest.mark.owner_acts
def test_recorded_venta_refuses_expense_approval(actions) -> None:  # noqa: ANN001
    service, context, _ = actions
    draft = shared.ready(service, context)
    marked = mark_venta(service.authority, context, _request(draft), "mark")
    assert isinstance(marked, SaleWrite)

    result = service.approve(
        context,
        draft,
        ApproveExpense(version=1, action="record_expense"),
        "approve",
    )

    assert isinstance(result, Refused)
    assert result.code == "business_venta_recorded"


@pytest.mark.owner_acts
def test_policy_uses_scalar_uid_and_selects_only_live_members(
    actions, users
) -> None:  # noqa: ANN001
    service, context, _ = actions
    marked = mark_venta(
        service.authority,
        context,
        _request(shared.ready(service, context)),
        "mark",
    )
    assert isinstance(marked, SaleWrite)
    with service.authority.pool.connection() as connection:
        policy = connection.execute(
            "select pg_get_expr(polqual,polrelid)"
            " from pg_policy where polrelid='public.business_sales'::regclass"
            " and polname='business_sales_authenticated_select'"
        ).fetchone()[0]
    assert "select auth.uid()" in " ".join(policy.lower().split())

    def visible_as(user_id: str) -> int:
        with (
            service.authority.pool.connection() as connection,
            connection.transaction(),
        ):
            connection.execute("set local role authenticated")
            connection.execute(
                "select set_config('request.jwt.claims', %s, true)",
                (
                    json.dumps(
                        {
                            "sub": user_id,
                            "role": "authenticated",
                            "is_anonymous": False,
                        }
                    ),
                ),
            )
            return connection.execute(
                "select count(*) from public.business_sales where id=%s",
                (marked.sale.id,),
            ).fetchone()[0]

    assert visible_as(users["owner"]) == 1
    assert visible_as(users["other"]) == 0
