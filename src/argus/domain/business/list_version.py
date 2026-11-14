"""The one owner of a Business's list version.

Bandeja and Registros ask "did anything change?" far more often than anything
changes. The version answers that from one statement over the records' own
change marks, so no writer keeps a counter. Equal versions mean the lists a
person sees are the same; a different version means read them again.
"""

from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from typing import Iterable

from psycopg_pool import ConnectionPool

# Every table the statement reads. A list that starts to depend on another
# table adds it here and to the statement, with a test that its write moves
# the version.
LIST_VERSION_TABLES = (
    "public.financial_source_connections",
    "public.financial_document_extractions",
    "public.financial_import_events",
    "public.business_action_receipts",
    "public.business_email_deliveries",
    "public.business_email_address_events",
    "public.business_receipt_read_states",
    "public.business_receipt_reading_consents",
    "public.business_document_settlements",
    "public.business_dgii_export_lines",
    "argus_private.business_document_purges",
)

# Counts and version sums ride with each newest change time: a purge deletes
# rows, and a few writers change a row without touching its time.
_STATEMENT = """
select md5(concat_ws('|',
  (select row(count(*), max(c.updated_at), sum(c.version))::text
     from public.financial_source_connections c
    where c.owner_space_id = %(space)s),
  (select row(count(*), sum((d.draft->>'version')::bigint),
              max(d.draft->>'updated_at'), count(d.preparation_job))::text
     from public.financial_document_extractions d
     join public.financial_source_connections c
       on c.id = d.connection_id and c.user_id = d.user_id
    where c.owner_space_id = %(space)s),
  (select row(count(*), max(e.updated_at), sum(e.version))::text
     from public.financial_import_events e
    where e.owner_space_id = %(space)s),
  (select row(count(*), max(a.created_at), count(a.outcome))::text
     from public.business_action_receipts a
    where a.space_id = %(space)s),
  (select row(count(*), max(m.updated_at))::text
     from public.business_email_deliveries m
    where m.space_id = %(space)s),
  (select row(count(*), max(s.created_at))::text
     from public.business_email_address_events s
    where s.space_id = %(space)s),
  (select row(count(*), max(r.seen_at))::text
     from public.business_receipt_read_states r
    where r.space_id = %(space)s and r.person_id = %(person)s),
  (select row(count(*), max(greatest(k.consented_at, k.revoked_at)))::text
     from public.business_receipt_reading_consents k
    where k.space_id = %(space)s),
  (select row(count(*), max(t.updated_at))::text
     from public.business_document_settlements t
    where t.space_id = %(space)s),
  (select count(*)::text
     from public.business_dgii_export_lines x
    where x.space_id = %(space)s),
  (select row(count(*), max(p.purged_at))::text
     from argus_private.business_document_purges p
    where p.space_id = %(space)s)
))
"""

# A list also shows states that move with the clock and not with a write (a
# read that timed out, the day in the Business calendar). The window bounds
# how long a "no change" answer can stand for those.
WINDOW_SECONDS = 300


def records_mark(pool: ConnectionPool, *, space_id: str, person_id: str) -> str:
    """The Business's records as one mark, for this person's read states."""

    with pool.connection() as connection:
        row = connection.execute(
            _STATEMENT, {"space": space_id, "person": person_id}
        ).fetchone()
    return str(row[0])


def list_version(
    mark: str,
    *,
    space_id: str,
    person_id: str,
    capabilities: Iterable[str],
    now: datetime | None = None,
) -> str:
    """The version a client holds and sends back. It names who is looking and
    what they may do, since both shape the list, and the current window."""

    window = int((now or datetime.now(timezone.utc)).timestamp()) // WINDOW_SECONDS
    parts = (mark, space_id, person_id, ",".join(sorted(capabilities)), str(window))
    return sha256("|".join(parts).encode()).hexdigest()[:32]
