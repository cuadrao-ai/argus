"""Close/reopen one Business without replacing its grants or records."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

from psycopg import Connection
from psycopg_pool import ConnectionPool

from argus.domain.business.space_name import typed_name

REOPEN_WINDOW = timedelta(days=30)
LifecycleAction = Literal["close", "reopen"]


class BusinessLifecycleError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def require_ownership_admission(connection: Connection, person_id: str) -> None:
    """Recheck deletion admission after acquiring this person's Auth row lock."""
    if connection.execute(
        "select 1 from argus_private.account_deletion_runs where user_id=%s",
        (person_id,),
    ).fetchone():
        raise BusinessLifecycleError("business_record_not_found")


@dataclass(frozen=True)
class LifecycleResult:
    space_id: str
    name: str
    closed_at: datetime | None

    @property
    def reopen_until(self) -> datetime | None:
        return self.closed_at + REOPEN_WINDOW if self.closed_at is not None else None


def export_windows(
    activities: Sequence[Mapping[str, Any]],
    drafts: Sequence[Mapping[str, Any]],
    links: Sequence[tuple[Any, Any]],
) -> list[dict[str, Any]]:
    """Consecutive periods the existing export accepts that, downloaded in
    order, cover every recorded day through today; none without a record.
    Each carries the counts of what its download lists, chosen by the
    export's own selection: the records dated in it and their originals."""
    from argus.domain.business.contracts.facts import BusinessResolution, Known
    from argus.domain.business.export import ExportPeriod, select_window
    from argus.domain.business.ledger import occurred_on, today

    days = {occurred_on(activity) for activity in activities}
    for draft in drafts:
        if draft["activity_id"] or draft["state"] not in {"open", "accepting"}:
            continue
        typed = (draft["resolution"] or {}).get("business")
        facts = BusinessResolution.model_validate(typed).facts if typed else None
        if facts is not None and isinstance(facts.occurred_on, Known):
            days.add(facts.occurred_on.value)
    if not days:
        return []
    start, last, windows = min(days), max(max(days), today()), []
    while start <= last:
        # The export's own period type refuses a window it would not serve.
        period = ExportPeriod(start, min(start + timedelta(days=365), last))
        chosen = select_window(activities, drafts, period)
        windows.append(
            {
                "start": period.start,
                "end": period.end,
                "record_count": len(chosen.activity_ids),
                "original_count": len(
                    {source for draft, source in links if draft in chosen.draft_ids}
                ),
            }
        )
        start = period.end + timedelta(days=1)
    return windows


class PostgresBusinessLifecycle:
    def __init__(self, pool: ConnectionPool) -> None:
        self._pool = pool

    def close(
        self, *, owner_id: str, space_id: str, confirmation: str, idempotency_key: str
    ) -> LifecycleResult:
        result = self._command(
            owner_id=owner_id,
            space_id=space_id,
            action="close",
            confirmation=confirmation,
            idempotency_key=idempotency_key,
        )
        from argus.domain.business.close_mail import deliver_close_mail

        deliver_close_mail(self._pool, space_id)
        return result

    def reopen(
        self, *, owner_id: str, space_id: str, idempotency_key: str
    ) -> LifecycleResult:
        result = self._command(
            owner_id=owner_id,
            space_id=space_id,
            action="reopen",
            confirmation=None,
            idempotency_key=idempotency_key,
        )
        from argus.domain.business.close_mail import deliver_close_mail

        deliver_close_mail(self._pool, space_id)
        return result

    def owned_spaces(self, owner_id: str) -> tuple[dict, ...]:
        """Each open Business this person owns, with what closing it would do:
        every live member, who loses access and whether they may take
        ownership, the reopen deadline a close now would set, and the export
        periods that download its whole history first."""
        from argus.domain.business.access import PostgresAccessStore
        from argus.domain.business.transfer import PostgresBusinessTransfer

        access = PostgresAccessStore(self._pool)
        result = []
        for space in access.spaces_for(owner_id):
            if space.role != "owner":
                continue
            grants = access.list(space.space_id, owner_id).grants
            with self._pool.connection() as db, db.transaction():
                self._owned_space(db, owner_id, space.space_id)
                members = []
                for member in grants:
                    found = (
                        None
                        if member.owner
                        else PostgresBusinessTransfer.eligibility(
                            db, space.space_id, member.id, owner_id
                        )
                    )
                    if found is None:
                        continue
                    members.append(
                        {
                            "grant_id": member.id,
                            "name": member.display_name,
                            "eligible": found[1] is None,
                            "reason": found[1],
                        }
                    )
                now = db.execute("select clock_timestamp()").fetchone()[0]
            # History loads outside the owner and Business locks above.
            with self._pool.connection() as db:
                history = self._export_history(db, space.space_id)
            result.append(
                {
                    "space_id": space.space_id,
                    "name": space.name,
                    "grant_id": space.grant_id,
                    "member_count": len(members),
                    "reopen_until": now + REOPEN_WINDOW,
                    "export_windows": export_windows(*history),
                    "members": members,
                }
            )
        return tuple(result)

    def _export_history(
        self, db: Connection, space_id: str
    ) -> tuple[list[dict], list[dict], list[tuple[Any, Any]]]:
        """What the Business export selects from, read as it reads it: the
        current activities, every draft, and each draft's linked sources."""
        from psycopg.rows import dict_row

        from argus.domain.owner_scope import BusinessSpace
        from argus.domain.recording.canonical_groups import VisibleAccounts, load
        from argus.domain.recording.money_reads import current_activities
        from argus.domain.recording.postgres_repository import (
            PostgresFinancialAccountRepository,
        )

        custodian = db.execute(
            "select created_by::text from public.spaces where id=%s", (space_id,)
        ).fetchone()[0]
        canonical = load(
            PostgresFinancialAccountRepository(self._pool),
            db,
            {custodian},
            scope=BusinessSpace(space_id),
        )
        visible = [s for s in canonical.records if s.account.user_id == custodian]
        activities = list(current_activities(VisibleAccounts(visible, canonical)))
        with db.cursor(row_factory=dict_row) as cursor:
            drafts = cursor.execute(
                "select id,version,state,activity_id,resolution"
                " from public.financial_import_events"
                " where user_id=%s and owner_space_id=%s order by created_at,id",
                (custodian, space_id),
            ).fetchall()
        links = db.execute(
            "select l.draft_id,s.id from public.business_sources s"
            " join public.business_draft_sources l"
            " on l.source_id=s.id and l.space_id=s.space_id"
            " join public.financial_import_events e"
            " on e.id=l.draft_id and e.owner_space_id=l.space_id"
            " where s.space_id=%s and e.user_id=%s",
            (space_id, custodian),
        ).fetchall()
        return activities, drafts, links

    def closed_spaces(self, owner_id: str) -> tuple[LifecycleResult, ...]:
        with self._pool.connection() as connection:
            rows = connection.execute(
                "select s.id::text,s.name,s.closed_at from public.spaces s"
                " join public.business_client_grants g on g.space_id=s.id"
                " join auth.users u on u.id=g.grantee_id"
                " where g.grantee_id=%s and g.business_role='owner' and g.revoked_at is null and s.kind='business'"
                " and s.closed_at>clock_timestamp()-%s"
                " and coalesce(u.is_anonymous,false)=false"
                " order by s.closed_at desc,s.id",
                (owner_id, REOPEN_WINDOW),
            ).fetchall()
        return tuple(LifecycleResult(*row) for row in rows)

    def _command(
        self,
        *,
        owner_id: str,
        space_id: str,
        action: LifecycleAction,
        confirmation: str | None,
        idempotency_key: str,
    ) -> LifecycleResult:
        if not 1 <= len(idempotency_key) <= 200 or not idempotency_key.strip():
            raise BusinessLifecycleError("invalid_idempotency_key")
        with self._pool.connection() as connection, connection.transaction():
            name, closed_at = self._owned_space(connection, owner_id, space_id)
            confirmation = typed_name(name, confirmation)
            if action == "reopen":
                require_ownership_admission(connection, owner_id)
            previous = connection.execute(
                "select action,confirmation,result_closed_at,result_name,owner_id::text"
                " from public.business_lifecycle_commands"
                " where space_id=%s and idempotency_key=%s",
                (space_id, idempotency_key),
            ).fetchone()
            if previous is not None:
                if previous[:2] != (action, confirmation) or previous[4] != owner_id:
                    raise BusinessLifecycleError("idempotency_conflict")
                return LifecycleResult(space_id, previous[3], previous[2])
            now = connection.execute("select clock_timestamp()").fetchone()[0]
            if action == "close":
                if confirmation != name:
                    raise BusinessLifecycleError("business_name_mismatch")
                newly_closed = closed_at is None
                closed_at = closed_at or now
            else:
                reopened_from = closed_at
                if closed_at is not None and now >= closed_at + REOPEN_WINDOW:
                    raise BusinessLifecycleError("business_reopen_expired")
                if connection.execute(
                    "select 1 from public.spaces where current_owner_id=%s and id<>%s"
                    " and kind='business' and closed_at is null and business_legacy_default"
                    " and (select business_legacy_default from public.spaces where id=%s)",
                    (
                        connection.execute(
                            "select current_owner_id from public.spaces where id=%s",
                            (space_id,),
                        ).fetchone()[0],
                        space_id,
                        space_id,
                    ),
                ).fetchone():
                    raise BusinessLifecycleError("business_already_open")
                closed_at = None
            if action == "close":
                connection.execute(
                    "update public.business_ownership_transfers set status='cancelled',resolved_at=clock_timestamp()"
                    " where space_id=%s and status='pending'",
                    (space_id,),
                )
            connection.execute(
                "update public.spaces set closed_at=%s where id=%s",
                (closed_at, space_id),
            )
            connection.execute(
                "insert into public.business_lifecycle_commands"
                " (space_id,owner_id,idempotency_key,action,confirmation,result_closed_at,result_name)"
                " values(%s,%s,%s,%s,%s,%s,%s)",
                (
                    space_id,
                    owner_id,
                    idempotency_key,
                    action,
                    confirmation,
                    closed_at,
                    name,
                ),
            )
            if action == "close" and newly_closed:
                from argus.domain.business.close_mail import enqueue_close_mail

                enqueue_close_mail(connection, space_id, owner_id, name, closed_at)
            if action == "reopen" and reopened_from is not None:
                from argus.domain.business.close_mail import enqueue_reopen_mail

                enqueue_reopen_mail(connection, space_id, owner_id, name, reopened_from)
            return LifecycleResult(space_id, name, closed_at)

    @staticmethod
    def _owned_space(connection: Connection, owner_id: str, space_id: str) -> tuple:
        user = connection.execute(
            "select id from auth.users where id=%s and coalesce(is_anonymous,false)=false for no key update",
            (owner_id,),
        ).fetchone()
        if user is None:
            raise BusinessLifecycleError("business_record_not_found")
        row = connection.execute(
            "select name,closed_at from public.spaces"
            " where id=%s and kind='business' for update",
            (space_id,),
        ).fetchone()
        if (
            row is None
            or not connection.execute(
                "select 1 from public.business_client_grants where space_id=%s"
                " and grantee_id=%s and business_role='owner' and revoked_at is null"
                " and (expires_at is null or expires_at>clock_timestamp())"
                " and 'read'=any(capabilities)",
                (space_id, owner_id),
            ).fetchone()
        ):
            raise BusinessLifecycleError("business_record_not_found")
        return row
