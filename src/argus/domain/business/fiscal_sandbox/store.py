"""Short transactions; the sole contact permit is returned after commit."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from psycopg import Connection
from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from argus.domain.business.authority import ActionError, authorize
from argus.domain.business.contracts.authority import TrustedActor

from .contracts import Case, FiscalOperation, Observation, digest
from .projection import project


class Store:
    def __init__(self, pool: ConnectionPool) -> None:
        self.pool = pool

    @staticmethod
    def _row(
        db: Connection, operation_id: UUID, space_id: UUID | None = None
    ) -> dict[str, Any]:
        row = db.execute(
            "select * from public.business_fiscal_operations where id=%s and (%s::uuid is null or space_id=%s) for update",
            (operation_id, space_id, space_id),
        ).fetchone()
        if not row:
            raise ActionError("not_found", "business_record_not_found")
        return row

    @staticmethod
    def _view(db: Connection, row: dict[str, Any]) -> FiscalOperation:
        events = db.execute(
            "select evidence from public.business_fiscal_observations where operation_id=%s order by id",
            (row["id"],),
        ).fetchall()
        observations = [Observation.model_validate(e["evidence"]) for e in events]
        return FiscalOperation(
            id=row["id"],
            business_id=row["space_id"],
            case_id=row["case_data"]["case_id"],
            kind=row["kind"],
            number=row["number"],
            payload_digest=row["payload_digest"],
            provider_id=row["provider_id"],
            state=project(
                observations,
                contacted=row["contact_token"] is not None,
                identified=row["provider_id"] is not None,
                attempts=row["attempts"],
            ),
        )

    def prepare(
        self, actor: TrustedActor, grant: UUID | None, case: Case
    ) -> FiscalOperation:
        if actor.space_id != case.business_id or actor.actor_kind != "member":
            raise ActionError("permission_denied", "business_permission_denied")
        try:
            with (
                self.pool.connection() as conn,
                conn.transaction(),
                conn.cursor(row_factory=dict_row) as db,
            ):
                auth = authorize(conn, actor, grant)
                auth.require("prepare")
                db.execute(
                    "insert into public.business_fiscal_operations(space_id,document_key,account_key,company_id,issuer,kind,number,case_data,payload_digest,prepared_actor) values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) on conflict do nothing",
                    (
                        case.business_id,
                        case.document_key,
                        case.account_key,
                        case.company_id,
                        case.issuer,
                        case.kind,
                        case.number,
                        Jsonb(case.model_dump(mode="json")),
                        case.payload_digest,
                        Jsonb(auth.provenance.model_dump(mode="json")),
                    ),
                )
                db.execute(
                    "select * from public.business_fiscal_operations where space_id=%s and document_key=%s for update",
                    (case.business_id, case.document_key),
                )
                row = db.fetchone()
                if not row or row["case_data"] != case.model_dump(mode="json"):
                    raise ActionError("idempotency_conflict", "fiscal_identity_conflict")
                return self._view(conn.cursor(row_factory=dict_row), row)
        except UniqueViolation:
            raise ActionError(
                "idempotency_conflict", "fiscal_identity_conflict"
            ) from None

    def get(
        self, actor: TrustedActor, grant: UUID | None, operation_id: UUID
    ) -> FiscalOperation:
        with (
            self.pool.connection() as conn,
            conn.transaction(),
            conn.cursor(row_factory=dict_row) as db,
        ):
            authorize(conn, actor, grant).require("read")
            return self._view(db, self._row(db, operation_id, actor.space_id))

    def claim(
        self,
        actor: TrustedActor,
        grant: UUID | None,
        operation_id: UUID,
        expected_digest: str,
    ) -> tuple[FiscalOperation, Case | None]:
        with (
            self.pool.connection() as conn,
            conn.transaction(),
            conn.cursor(row_factory=dict_row) as db,
        ):
            auth = authorize(conn, actor, grant)
            auth.require("approve")
            if actor.actor_kind != "member" or not auth.context.is_current_owner:
                raise ActionError("permission_denied", "business_permission_denied")
            row = self._row(db, operation_id, actor.space_id)
            if row["payload_digest"] != expected_digest:
                raise ActionError("stale_version", "fiscal_payload_changed")
            case = None
            if row["contact_token"] is None:
                db.execute(
                    "update public.business_fiscal_operations set contact_token=%s,contacted_at=clock_timestamp(),approved_actor=%s,next_check=clock_timestamp()+interval '30 seconds' where id=%s returning *",
                    (
                        uuid4(),
                        Jsonb(auth.provenance.model_dump(mode="json")),
                        operation_id,
                    ),
                )
                row = db.fetchone()
                case = Case.model_validate(row["case_data"])
            view = self._view(db, row)
        # Neither a failed commit nor a losing contender receives a send permit.
        return view, case

    @staticmethod
    def _append(
        db: Any,
        operation_id: UUID | None,
        space_id: UUID | None,
        event: Observation,
        event_key: str,
    ) -> None:
        if db.execute(
            "select 1 from public.business_fiscal_observations where source=%s and event_digest=%s",
            (event.source, event_key),
        ).fetchone():
            return
        if operation_id is not None:
            count = db.execute(
                "select count(*) as n from public.business_fiscal_observations where operation_id=%s",
                (operation_id,),
            ).fetchone()["n"]
            if count >= 256:
                raise RuntimeError("fiscal_evidence_capacity")
        else:
            # Serialize quarantine capacity checks, bounded independently of input.
            db.execute("select pg_advisory_xact_lock(82402410)")
            count = db.execute(
                "select count(*) as n from public.business_fiscal_observations where operation_id is null"
            ).fetchone()["n"]
            if count >= 1000:
                raise RuntimeError("fiscal_quarantine_capacity")
        db.execute(
            "insert into public.business_fiscal_observations(space_id,operation_id,event_digest,source,disposition,evidence) values(%s,%s,%s,%s,%s,%s) on conflict(source,event_digest) do nothing",
            (
                space_id,
                operation_id,
                event_key,
                event.source,
                "applied" if operation_id else "quarantined",
                Jsonb(event.model_dump(mode="json")),
            ),
        )

    @staticmethod
    def _apply(db: Any, row: dict[str, Any], event: Observation, key: str) -> None:
        identity_ok = (
            row["contact_token"] is not None
            and event.issuer == row["issuer"]
            and event.number == row["number"]
            and bool(event.provider_id)
            and row["provider_id"] in (None, event.provider_id)
        )
        if event.source not in ("unknown", "artifact", "conflict") and not identity_ok:
            event = Observation(
                source="conflict",
                provider_id=event.provider_id,
                issuer=event.issuer,
                number=event.number,
                code="identity_mismatch",
                evidence_digest=digest(event.model_dump(mode="json")),
            )
            key = digest([str(row["id"]), key, "identity_conflict"])
        elif identity_ok and row["provider_id"] is None:
            db.execute(
                "select pg_advisory_xact_lock(hashtextextended(%s,82402411))",
                (row["account_key"] + ":" + row["company_id"] + ":" + event.provider_id,),
            )
            duplicate = db.execute(
                "select id from public.business_fiscal_operations where environment='sandbox' and account_key=%s and company_id=%s and provider_id=%s and id<>%s",
                (row["account_key"], row["company_id"], event.provider_id, row["id"]),
            ).fetchone()
            if duplicate:
                event = Observation(
                    source="conflict",
                    provider_id=event.provider_id,
                    issuer=event.issuer,
                    number=event.number,
                    code="provider_identity_conflict",
                )
            else:
                db.execute(
                    "update public.business_fiscal_operations set provider_id=%s where id=%s",
                    (event.provider_id, row["id"]),
                )
        Store._append(db, row["id"], row["space_id"], event, key)

    def record(
        self, operation_id: UUID, event: Observation, *, lease: UUID | None = None
    ) -> None:
        with (
            self.pool.connection() as conn,
            conn.transaction(),
            conn.cursor(row_factory=dict_row) as db,
        ):
            row = self._row(db, operation_id)
            if lease is not None and (
                row["lease_token"] != lease
                or not db.execute(
                    "select lease_until>clock_timestamp() as live from public.business_fiscal_operations where id=%s",
                    (operation_id,),
                ).fetchone()["live"]
            ):
                return
            self._apply(
                db, row, event, digest([str(operation_id), event.model_dump(mode="json")])
            )
            if lease is not None:
                db.execute(
                    "update public.business_fiscal_operations set lease_token=null,lease_until=null where id=%s",
                    (operation_id,),
                )

    def callback(self, case: Case, event: Observation) -> None:
        key = digest(
            [
                case.account_key,
                case.company_id,
                event.model_dump(mode="json", exclude={"evidence_digest"}),
            ]
        )
        with (
            self.pool.connection() as conn,
            conn.transaction(),
            conn.cursor(row_factory=dict_row) as db,
        ):
            if db.execute(
                "select 1 from public.business_fiscal_observations where source='callback' and event_digest=%s",
                (key,),
            ).fetchone():
                return
            db.execute(
                "select * from public.business_fiscal_operations where account_key=%s and company_id=%s and issuer=%s and number=%s and kind=%s for update",
                (
                    case.account_key,
                    case.company_id,
                    event.issuer,
                    event.number,
                    case.kind,
                ),
            )
            row = db.fetchone()
            if row and row["contact_token"] is not None:
                self._apply(db, row, event, key)
            else:
                self._append(db, None, None, event, key)

    def quarantine(self, event: Observation) -> None:
        with (
            self.pool.connection() as conn,
            conn.transaction(),
            conn.cursor(row_factory=dict_row) as db,
        ):
            self._append(db, None, None, event, digest(event.model_dump(mode="json")))

    def recovery(
        self, business_id: UUID, limit: int
    ) -> list[tuple[UUID, Case, str | None, UUID]]:
        with (
            self.pool.connection() as conn,
            conn.transaction(),
            conn.cursor(row_factory=dict_row) as db,
        ):
            db.execute(
                "select * from public.business_fiscal_operations where space_id=%s and contacted_at is not null and next_check<=clock_timestamp() and attempts<20 and (lease_until is null or lease_until<clock_timestamp()) order by next_check limit %s for update skip locked",
                (business_id, limit),
            )
            rows = db.fetchall()
            result = []
            for row in rows:
                token = uuid4()
                db.execute(
                    "update public.business_fiscal_operations set attempts=attempts+1,next_check=clock_timestamp()+interval '60 seconds',lease_token=%s,lease_until=clock_timestamp()+interval '120 seconds' where id=%s",
                    (token, row["id"]),
                )
                result.append(
                    (
                        row["id"],
                        Case.model_validate(row["case_data"]),
                        row["provider_id"],
                        token,
                    )
                )
            return result

    def locator(
        self, actor: TrustedActor, grant: UUID | None, operation_id: UUID, kind: str
    ) -> tuple[Case, str | None, str | None]:
        with (
            self.pool.connection() as conn,
            conn.transaction(),
            conn.cursor(row_factory=dict_row) as db,
        ):
            authorize(conn, actor, grant).require("read")
            row = self._row(db, operation_id, actor.space_id)
            key = kind + "_url"
            events = db.execute(
                "select evidence from public.business_fiscal_observations where operation_id=%s order by id desc",
                (operation_id,),
            ).fetchall()
            url = next(
                (e["evidence"][key] for e in events if e["evidence"].get(key)), None
            )
            return Case.model_validate(row["case_data"]), row["provider_id"], url
