from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator
from uuid import UUID, uuid4

from psycopg import Cursor
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from argus.domain.business.authority import ActionError, authorize
from argus.domain.business.contracts.authority import TrustedActor
from argus.domain.business.contracts.invoicing import (
    Customer,
    CustomerWrite,
    Invoice,
    InvoiceAmounts,
    InvoiceDraft,
    InvoiceWrite,
)
from argus.domain.business.fiscal_sandbox.contracts import digest
from argus.domain.business.fiscal_sandbox.store import Store as FiscalStore

from .validation import amounts, customer_errors, draft_errors, fiscal_blockers


class InvoiceError(ActionError):
    def __init__(
        self,
        outcome: str,
        code: str,
        *,
        field_errors: dict[str, str] | None = None,
        attempted: dict[str, Any] | None = None,
        current_version: int | None = None,
    ) -> None:
        super().__init__(outcome, code)
        self.field_errors = field_errors or {}
        self.attempted = attempted
        self.current_version = current_version


class Store:
    def __init__(self, pool: ConnectionPool) -> None:
        self.pool = pool

    @contextmanager
    def transaction(
        self,
        actor: TrustedActor,
        grant: UUID | None,
        *,
        write: bool = False,
    ) -> Iterator[Cursor]:
        with (
            self.pool.connection() as conn,
            conn.transaction(),
            conn.cursor(row_factory=dict_row) as db,
        ):
            if not write:
                db.execute("set transaction isolation level repeatable read")
            auth = authorize(conn, actor, grant)
            auth.require("prepare" if write else "read")
            if actor.actor_kind != "member":
                raise ActionError("permission_denied", "business_permission_denied")
            yield db

    @staticmethod
    def replay(db: Cursor, business: UUID, key: str, request: Any) -> dict | None:
        db.execute(
            "select pg_advisory_xact_lock(hashtextextended(%s,82402701))",
            (str(business) + key,),
        )
        row = db.execute(
            "select * from public.business_invoice_commands where space_id=%s and command_key=%s",
            (business, key),
        ).fetchone()
        if row and row["request_digest"] != digest(request):
            raise ActionError("idempotency_conflict", "invoice_idempotency_conflict")
        return row["result"] if row else None

    @staticmethod
    def remember(db: Cursor, business: UUID, key: str, request: Any, result: Any) -> None:
        db.execute(
            "insert into public.business_invoice_commands(space_id,command_key,request_digest,result) values(%s,%s,%s,%s)",
            (business, key, digest(request), Jsonb(result.model_dump(mode="json"))),
        )

    @staticmethod
    def customer_view(row: dict) -> Customer:
        return Customer(
            id=row["id"],
            business_id=row["space_id"],
            version=row["version"],
            data=row["data"],
            archived=row["archived"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def customer_row(
        db: Cursor, business: UUID, customer_id: UUID, *, lock: bool = True
    ) -> dict:
        row = db.execute(
            "select * from public.business_customers where space_id=%s and id=%s"
            + (" for share" if lock else ""),
            (business, customer_id),
        ).fetchone()
        if row is None:
            raise ActionError("not_found", "business_record_not_found")
        return row

    def customer(
        self, actor: TrustedActor, grant: UUID | None, customer_id: UUID
    ) -> Customer:
        with self.transaction(actor, grant) as db:
            return self.customer_view(
                self.customer_row(db, actor.space_id, customer_id, lock=False)
            )

    def save_customer(
        self,
        actor: TrustedActor,
        grant: UUID | None,
        customer_id: UUID | None,
        body: CustomerWrite,
        key: str,
    ) -> Customer:
        request = ["customer", str(customer_id), body.model_dump(mode="json")]
        with self.transaction(actor, grant, write=True) as db:
            replay = self.replay(db, actor.space_id, key, request)
            if replay:
                return Customer.model_validate(replay)
            errors = customer_errors(body.data)
            if errors:
                raise InvoiceError(
                    "invalid_input", "customer_invalid", field_errors=errors
                )
            if customer_id is None:
                if body.expected_version is not None:
                    raise ActionError("invalid_input", "invoice_version_invalid")
                row = db.execute(
                    "insert into public.business_customers(space_id,data,archived) values(%s,%s,%s) returning *",
                    (
                        actor.space_id,
                        Jsonb(body.data.model_dump(mode="json")),
                        body.archived,
                    ),
                ).fetchone()
            else:
                row = db.execute(
                    "select * from public.business_customers where id=%s and space_id=%s for update",
                    (customer_id, actor.space_id),
                ).fetchone()
                if not row:
                    raise ActionError("not_found", "business_record_not_found")
                self.check_version(
                    row, body.expected_version, body.model_dump(mode="json")
                )
                row = db.execute(
                    "update public.business_customers set version=version+1,data=%s,archived=%s,updated_at=clock_timestamp() where id=%s returning *",
                    (
                        Jsonb(body.data.model_dump(mode="json")),
                        body.archived,
                        customer_id,
                    ),
                ).fetchone()
            result = self.customer_view(row)
            self.remember(db, actor.space_id, key, request, result)
            return result

    @staticmethod
    def check_version(row: dict, expected: int | None, attempted: dict) -> None:
        if expected != row["version"]:
            raise InvoiceError(
                "stale_version",
                "invoice_version_conflict",
                attempted=attempted,
                current_version=row["version"],
            )

    @staticmethod
    def invoice_row(
        db: Cursor, business: UUID, invoice_id: UUID, *, lock: bool = True
    ) -> dict:
        row = db.execute(
            "select * from public.business_invoices where id=%s and space_id=%s"
            + (" for update" if lock else ""),
            (invoice_id, business),
        ).fetchone()
        if not row:
            raise ActionError("not_found", "business_record_not_found")
        return row

    @staticmethod
    def invoice_view(db: Cursor, row: dict, *, lock: bool = True) -> Invoice:
        revision = db.execute(
            "select * from public.business_invoice_revisions where invoice_id=%s and version=%s",
            (row["id"], row["version"]),
        ).fetchone()
        data = InvoiceDraft.model_validate(revision["data"])
        operation = None
        if row["operation_id"]:
            operation = FiscalStore._view(
                db, FiscalStore._row(db, row["operation_id"], row["space_id"], lock=lock)
            )
        return Invoice(
            id=row["id"],
            business_id=row["space_id"],
            version=row["version"],
            revision_id=revision["id"],
            data=data,
            field_errors=draft_errors(data),
            fiscal_blockers=fiscal_blockers(data),
            amounts=InvoiceAmounts.model_validate(revision["amounts"])
            if revision["amounts"]
            else None,
            operation=operation,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def invoice(
        self, actor: TrustedActor, grant: UUID | None, invoice_id: UUID
    ) -> Invoice:
        with self.transaction(actor, grant) as db:
            return self.invoice_view(
                db,
                self.invoice_row(db, actor.space_id, invoice_id, lock=False),
                lock=False,
            )

    def save_invoice(
        self,
        actor: TrustedActor,
        grant: UUID | None,
        invoice_id: UUID | None,
        body: InvoiceWrite,
        key: str,
    ) -> Invoice:
        request = ["invoice", str(invoice_id), body.model_dump(mode="json")]
        with self.transaction(actor, grant, write=True) as db:
            replay = self.replay(db, actor.space_id, key, request)
            if replay:
                return Invoice.model_validate(replay)
            if body.data.customer_id:
                self.customer_row(db, actor.space_id, body.data.customer_id)
            if invoice_id is None:
                if body.expected_version is not None:
                    raise ActionError("invalid_input", "invoice_version_invalid")
                row = db.execute(
                    "insert into public.business_invoices(space_id) values(%s) returning *",
                    (actor.space_id,),
                ).fetchone()
            else:
                row = self.invoice_row(db, actor.space_id, invoice_id)
                self.check_version(
                    row, body.expected_version, body.model_dump(mode="json")
                )
                if row["operation_id"]:
                    raise InvoiceError(
                        "stale_version",
                        "invoice_already_prepared",
                        attempted=body.model_dump(mode="json"),
                        current_version=row["version"],
                    )
                row = db.execute(
                    "update public.business_invoices set version=version+1,updated_at=clock_timestamp() where id=%s returning *",
                    (invoice_id,),
                ).fetchone()
            total = amounts(body.data)
            db.execute(
                "insert into public.business_invoice_revisions(id,space_id,invoice_id,version,customer_id,data,amounts) values(%s,%s,%s,%s,%s,%s,%s)",
                (
                    uuid4(),
                    actor.space_id,
                    row["id"],
                    row["version"],
                    body.data.customer_id,
                    Jsonb(body.data.model_dump(mode="json")),
                    Jsonb(total.model_dump(mode="json")) if total else None,
                ),
            )
            result = self.invoice_view(db, row)
            self.remember(db, actor.space_id, key, request, result)
            return result
