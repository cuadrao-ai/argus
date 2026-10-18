from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from psycopg.errors import UniqueViolation

from argus.domain.business.actions import plans
from argus.domain.business.authority import (
    ActionContext,
    ActionError,
    BusinessAuthority,
)
from argus.domain.business.contracts.actions import Applied, Refused
from argus.domain.business.contracts.venta import (
    Customer,
    Form607Row,
    MarkVenta,
    MarkVentaCommand,
    Sale,
    SalesPeriod,
    SaleWrite,
    SetVentaCollection,
    SetVentaCollectionCommand,
)
from argus.domain.business.transactions import ActionTransaction, transaction

_ZERO = Decimal("0.00")


def _form_row(sale: Sale) -> Form607Row:
    return Form607Row(
        buyer_id=sale.customer.id_number,
        buyer_id_type=1 if sale.customer.id_type == "rnc" else 2,
        ncf=sale.ncf,
        issued_on=sale.issued_on,
        invoiced_amount=sale.invoice_total - sale.itbis_charged,
        itbis_invoiced=sale.itbis_charged,
    )


def _sale(row: Mapping[str, Any]) -> Sale:
    return Sale(
        id=row["id"],
        space_id=row["space_id"],
        draft_id=row["draft_id"],
        invoice_total=row["invoice_total"],
        itbis_charged=row["itbis_charged"],
        customer=Customer(
            id_type=row["customer_id_type"],
            id_number=row["customer_id_number"],
        ),
        ncf=row["ncf"],
        issued_on=row["issued_on"],
        collection_status=row["collection_status"],
        currency=row["currency"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def load_sale(tx: ActionTransaction, *, space_id: UUID, sale_id: UUID) -> Sale:
    if space_id != tx.context.actor.space_id:
        raise ActionError("not_found", "business_venta_not_found")
    rows = tx.rows(
        "select * from public.business_sales where space_id=%s and id=%s",
        (space_id, sale_id),
    )
    if not rows:
        raise ActionError("not_found", "business_venta_not_found")
    return _sale(rows[0])


def sales_for_period(
    rows: Sequence[Sale], *, start: date, end: date
) -> SalesPeriod:
    if start > end:
        raise ValueError("period_reversed")
    sales = tuple(
        sorted(
            (sale for sale in rows if start <= sale.issued_on <= end),
            key=lambda sale: (sale.issued_on, sale.id),
        )
    )
    income = sum(
        (sale.invoice_total - sale.itbis_charged for sale in sales), _ZERO
    )
    charged = sum((sale.itbis_charged for sale in sales), _ZERO)
    collected = sum(
        (
            sale.itbis_charged
            for sale in sales
            if sale.collection_status == "cobrado"
        ),
        _ZERO,
    )
    outstanding = sum(
        (
            sale.invoice_total
            for sale in sales
            if sale.collection_status == "por_cobrar"
        ),
        _ZERO,
    )
    return SalesPeriod(
        start=start,
        end=end,
        sales=sales,
        income=income,
        itbis_charged=charged,
        itbis_cobrado=collected,
        por_cobrar=outstanding,
        rows=tuple(_form_row(sale) for sale in sales),
    )


def load_sales_period(
    tx: ActionTransaction, *, space_id: UUID, start: date, end: date
) -> SalesPeriod:
    if space_id != tx.context.actor.space_id:
        raise ActionError("not_found", "business_record_not_found")
    rows = tx.rows(
        "select * from public.business_sales"
        " where space_id=%s and issued_on between %s and %s"
        " order by issued_on,id",
        (space_id, start, end),
    )
    return sales_for_period([_sale(row) for row in rows], start=start, end=end)


def _duplicate_sale(error: UniqueViolation) -> Refused:
    name = error.diag.constraint_name or ""
    if name == "business_sales_space_draft_key":
        code = "business_venta_draft_already_recorded"
    elif name == "business_sales_space_ncf_key":
        code = "business_venta_ncf_conflict"
    else:
        raise error
    return Refused(outcome="idempotency_conflict", code=code)


def _owner(tx: ActionTransaction) -> None:
    if (
        tx.context.actor.actor_kind != "member"
        or str(tx.context.actor.actor_id) != tx.context.owner_id
    ):
        raise ActionError("permission_denied", "business_permission_denied")


def _replayed_sale(
    tx: ActionTransaction, *, space_id: UUID, outcome: object
) -> Sale:
    if not isinstance(outcome, Applied) or outcome.sale_id is None:
        raise ActionError("invalid_input", "business_venta_receipt_invalid")
    return load_sale(tx, space_id=space_id, sale_id=outcome.sale_id)


def mark_venta(
    authority: BusinessAuthority,
    context: ActionContext,
    request: MarkVenta,
    key: str,
) -> SaleWrite | Refused:
    command = MarkVentaCommand(request=request)
    try:
        with transaction(authority, context, "approve") as tx:
            _owner(tx)
            old = plans.receipt(tx, key, command)
            if old is not None:
                outcome = plans.replay(old)
                if isinstance(outcome, Refused):
                    return outcome
                return SaleWrite(
                    sale=_replayed_sale(
                        tx, space_id=context.actor.space_id, outcome=outcome
                    ),
                    created=False,
                )
            plans.start_receipt(tx, key, command)
            draft = tx.rows(
                "select state from public.financial_import_events"
                " where id=%s and owner_space_id=%s for update",
                (request.draft_id, context.actor.space_id),
            )
            if not draft:
                return plans.finish_receipt(
                    tx,
                    key,
                    Refused(outcome="not_found", code="business_record_not_found"),
                )
            if draft[0]["state"] != "open":
                return plans.finish_receipt(
                    tx,
                    key,
                    Refused(
                        outcome="invalid_input", code="business_venta_draft_closed"
                    ),
                )
            conflict = tx.rows(
                "select draft_id,ncf from public.business_sales"
                " where space_id=%s and (draft_id=%s or ncf=%s) for update",
                (context.actor.space_id, request.draft_id, request.ncf),
            )
            if conflict:
                code = (
                    "business_venta_draft_already_recorded"
                    if any(row["draft_id"] == request.draft_id for row in conflict)
                    else "business_venta_ncf_conflict"
                )
                return plans.finish_receipt(
                    tx,
                    key,
                    Refused(outcome="idempotency_conflict", code=code),
                )
            [row] = tx.rows(
                "insert into public.business_sales"
                " (space_id,draft_id,invoice_total,itbis_charged,"
                " customer_id_type,customer_id_number,ncf,issued_on,"
                " collection_status,currency)"
                " values (%s,%s,%s,%s,%s,%s,%s,%s,%s,'DOP') returning *",
                (
                    context.actor.space_id,
                    request.draft_id,
                    request.invoice_total,
                    request.itbis_charged,
                    request.customer.id_type,
                    request.customer.id_number,
                    request.ncf,
                    request.issued_on,
                    request.collection_status,
                ),
            )
            sale = _sale(row)
            plans.finish_receipt(
                tx, key, Applied(outcome="applied", sale_id=sale.id)
            )
            return SaleWrite(sale=sale, created=True)
    except UniqueViolation as error:
        return _duplicate_sale(error)
    except ActionError as error:
        return error.result


def set_venta_collection(
    authority: BusinessAuthority,
    context: ActionContext,
    sale_id: UUID,
    request: SetVentaCollection,
    key: str,
) -> Sale | Refused:
    command = SetVentaCollectionCommand(sale_id=sale_id, request=request)
    try:
        with transaction(authority, context, "approve") as tx:
            _owner(tx)
            old = plans.receipt(tx, key, command)
            if old is not None:
                outcome = plans.replay(old)
                if isinstance(outcome, Refused):
                    return outcome
                return _replayed_sale(
                    tx, space_id=context.actor.space_id, outcome=outcome
                )
            plans.start_receipt(tx, key, command)
            sale = tx.rows(
                "select id from public.business_sales"
                " where space_id=%s and id=%s for update",
                (context.actor.space_id, sale_id),
            )
            if not sale:
                return plans.finish_receipt(
                    tx,
                    key,
                    Refused(
                        outcome="not_found", code="business_venta_not_found"
                    ),
                )
            [row] = tx.rows(
                "update public.business_sales"
                " set collection_status=%s,updated_at=clock_timestamp()"
                " where space_id=%s and id=%s returning *",
                (request.collection_status, context.actor.space_id, sale_id),
            )
            updated = _sale(row)
            plans.finish_receipt(
                tx, key, Applied(outcome="applied", sale_id=updated.id)
            )
            return updated
    except ActionError as error:
        return error.result
