from __future__ import annotations

import json
from datetime import date, datetime, timezone
from types import UnionType
from typing import Annotated, Literal, Union, get_args, get_origin
from uuid import UUID, uuid4

import pytest
from argus.domain.business.access import AccessAction
from argus.domain.business.authority import ActionContext
from argus.domain.business.contracts.actions import (
    ApproveExpense,
    BusinessAction,
    Command,
    PrepareAttachmentCommand,
    RebindAttachmentCommand,
    Refused,
)
from argus.domain.business.contracts.venta import (
    Customer,
    MarkVenta,
    MarkVentaCommand,
    SaleWrite,
    SetVentaCollection,
    SetVentaCollectionCommand,
)
from argus.domain.business.sales import (
    load_sales_period,
    mark_venta,
    set_venta_collection,
)
from argus.domain.business.transactions import transaction
from faker import Faker
from psycopg import Connection
from psycopg.types.json import Jsonb

from tests import test_business_actions_postgres as shared
from tests.test_business_spaces_migration_postgres import connection as source_connection

fake = Faker()
actions = shared.actions
users = shared.users
pytestmark = shared.pytestmark


@pytest.fixture(autouse=True)
def _release_recorded_sales(actions):  # noqa: ANN001
    service, context, _ = actions
    yield
    with service.authority.pool.connection() as connection:
        connection.execute(
            "delete from public.business_sales where space_id = %s",
            (context.actor.space_id,),
        )


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
    changed = MarkVenta.model_validate(
        {**request.model_dump(mode="json"), "invoice_total": "1200.00"}
    )
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
            "select count(*) from public.business_sales" " where space_id=%s and ncf=%s",
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
def test_policy_uses_scalar_uid_and_selects_only_live_members(actions, users) -> None:  # noqa: ANN001
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


def _union_members(annotation: object) -> tuple[object, ...]:
    origin = get_origin(annotation)
    if origin is Annotated:
        return _union_members(get_args(annotation)[0])
    if origin in (Union, UnionType):
        found: list[object] = []
        for arg in get_args(annotation):
            found.extend(_union_members(arg))
        return tuple(found)
    return (annotation,)


def _literal_strings(annotation: object) -> tuple[str, ...]:
    origin = get_origin(annotation)
    if origin is Annotated:
        return _literal_strings(get_args(annotation)[0])
    if origin is Literal:
        return tuple(arg for arg in get_args(annotation) if isinstance(arg, str))
    return ()


def _action_of(model: type) -> str:
    values = _literal_strings(model.model_fields["action"].annotation)
    if len(values) != 1:
        raise AssertionError(model)
    return values[0]


def _domain_receipt_actions() -> dict[str, str]:
    """Every command and access action, classified as turn or turnless."""

    turn_models = set(_union_members(BusinessAction))
    catalog: dict[str, str] = {}
    for model in _union_members(Command):
        catalog[_action_of(model)] = "turn" if model in turn_models else "turnless"
    for action in _literal_strings(AccessAction):
        catalog.setdefault(action, "turnless")
    return catalog


def _actor(context: ActionContext, kind: str) -> dict[str, str]:
    return {
        "actor_id": str(context.actor.actor_id),
        "actor_kind": kind,
        "display_name": "Member",
        "grant_id": str(context.grant_id),
        "issuer_id": str(context.owner_id),
        "issuer_display_name": "Owner",
    }


def _prepare_attachment_command(
    connection: Connection, context: ActionContext, actor: dict[str, str]
) -> dict[str, object]:
    source = source_connection(
        connection, str(context.owner_id), str(context.actor.space_id)
    )
    binding = {
        "schema_version": 1,
        "binding_id": str(uuid4()),
        "space_id": str(context.actor.space_id),
        "owner_id": str(context.owner_id),
        "connection_id": source,
        "source_sha256": "a" * 64,
        "actor": actor,
        "target": None,
        "consent": True,
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }
    connection.execute(
        "insert into public.financial_document_extractions"
        " (connection_id, user_id, draft, source_bytes, preparation_binding, batch)"
        " values (%s, %s, %s, %s, %s, %s)",
        (
            source,
            str(context.owner_id),
            Jsonb({"sha256": "a" * 64, "consent": True, "source_available": True}),
            b"synthetic receipt",
            Jsonb(binding),
            Jsonb({}),
        ),
    )
    return {
        "action": _action_of(PrepareAttachmentCommand),
        "binding": binding,
        "batch_sha256": "b" * 64,
    }


def _insert_allowed_receipt(
    connection: Connection,
    context: ActionContext,
    action: str,
    kind: str,
    index: int,
) -> None:
    prepare = action == _action_of(PrepareAttachmentCommand)
    actor = _actor(context, "extractor" if prepare else "member")
    command: dict[str, object] = {"action": action}
    if action == _action_of(RebindAttachmentCommand):
        command["binding"] = {"space_id": str(context.actor.space_id)}
    if prepare:
        command = _prepare_attachment_command(connection, context, actor)
    turn_key = None
    action_index = None
    if kind == "turn":
        turn_key = f"allow-{index}-{uuid4().hex}"
        action_index = 0
        connection.execute(
            "insert into public.business_turns"
            " (turn_key, space_id, sender_hash, actor_id, model_state, plan, plan_actor)"
            " values (%s, %s, %s, %s, 'completed', %s, %s)",
            (
                turn_key,
                context.actor.space_id,
                uuid4().hex + uuid4().hex,
                context.actor.actor_id,
                Jsonb({"schema_version": 1, "actions": [command]}),
                Jsonb(actor),
            ),
        )
    connection.execute(
        "insert into public.business_action_receipts"
        " (space_id, actor_id, idempotency_key, input_hash, command,"
        " turn_key, action_index, actor)"
        " values (%s, %s, %s, %s, %s, %s, %s, %s)",
        (
            context.actor.space_id,
            actor["actor_id"],
            f"allow-{index}-{action}",
            uuid4().hex + uuid4().hex,
            Jsonb(command),
            turn_key,
            action_index,
            Jsonb(actor),
        ),
    )


class TestReceiptAllowList:
    def test_constraint_accepts_dgii_venta_and_domain_actions(self, actions) -> None:  # noqa: ANN001
        catalog = _domain_receipt_actions()
        turn_models = _union_members(BusinessAction)
        assert turn_models
        assert all(catalog[_action_of(model)] == "turn" for model in turn_models)
        for action in _literal_strings(AccessAction):
            assert catalog[action] == "turnless"
        for model in (MarkVentaCommand, SetVentaCollectionCommand):
            assert catalog[_action_of(model)] == "turnless"
        for action in ("approve_refund", "set_business_rnc"):
            catalog[action] = "turnless"

        service, context, _grant = actions
        with service.authority.pool.connection() as connection:
            for index, (action, kind) in enumerate(catalog.items()):
                try:
                    _insert_allowed_receipt(connection, context, action, kind, index)
                except Exception as error:
                    raise AssertionError(f"{action} ({kind})") from error
