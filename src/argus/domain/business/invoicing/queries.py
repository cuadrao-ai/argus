from __future__ import annotations

from datetime import date
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BeforeValidator, Field

from argus.domain.business.contracts.authority import TrustedActor
from argus.domain.business.contracts.invoicing import CustomerPage, InvoicePage, Strict

from .store import Store


def _query_integer(value: object) -> object:
    if isinstance(value, str) and value.isascii() and value.isdecimal():
        return int(value)
    return value


class CustomerQuery(Strict):
    page: int = Field(default=1, ge=1, le=1000000)
    page_size: Annotated[Literal[25, 50, 100], BeforeValidator(_query_integer)] = 25
    search: str = Field(default="", max_length=200)


class Query(CustomerQuery):
    currency: Literal["DOP", "USD", "EUR"] | None = None
    stage: Literal["all", "draft", "issued", "processing", "rejected", "uncertain"] = (
        "all"
    )
    date_from: date | None = None
    date_to: date | None = None
    sort: Literal["newest", "oldest"] = "newest"


_BASE = """
with base as (
 select i.*,r.data,r.amounts,o.number,
   case when o.id is null then 'draft'
        when exists(select 1 from public.business_fiscal_observations e where e.operation_id=o.id
          and (e.source='conflict' or (e.evidence->>'legal'<>'unreported' and e.evidence->>'legal'<>legal.value))) then 'uncertain'
        when legal.value in ('ACCEPTED','ACCEPTED_WITH_OBSERVATIONS') then 'issued'
        when legal.value='REJECTED' then 'rejected'
        when o.contact_token is not null and o.provider_id is null then 'uncertain'
        else 'processing' end as stage,
   coalesce((select max(e.id) from public.business_fiscal_observations e where e.operation_id=o.id),0) as evidence_version
 from public.business_invoices i
 join public.business_invoice_revisions r on r.invoice_id=i.id and r.version=i.version
 left join public.business_fiscal_operations o on o.id=i.operation_id
 left join lateral (select e.evidence->>'legal' as value from public.business_fiscal_observations e
   where e.operation_id=o.id and e.evidence->>'legal'<>'unreported' order by e.id limit 1) legal on true
 where i.space_id=%s
 and (%s::text is null or (pg_input_is_valid(r.data->>'issued_on','date') and r.data->>'issued_on'>=%s))
 and (%s::text is null or (pg_input_is_valid(r.data->>'issued_on','date') and r.data->>'issued_on'<=%s))
), filtered as (
 select * from base where (%s='all' or stage=%s)
 and (%s::text is null or data->>'currency'=%s)
 and (%s='' or position(lower(%s) in lower(concat_ws(' ',data->'customer_input'->>'name',data->>'notes',number,id::text)))>0)
)
"""


def invoices(
    store: Store, actor: TrustedActor, grant: UUID | None, query: Query
) -> InvoicePage:
    start = query.date_from.isoformat() if query.date_from else None
    end = query.date_to.isoformat() if query.date_to else None
    args = (
        actor.space_id,
        start,
        start,
        end,
        end,
        query.stage,
        query.stage,
        query.currency,
        query.currency,
        query.search,
        query.search,
    )
    direction = "desc" if query.sort == "newest" else "asc"
    with store.transaction(actor, grant) as db:
        rows = db.execute(
            _BASE
            + f" select * from filtered order by created_at {direction},id {direction} limit %s offset %s",
            (*args, query.page_size, (query.page - 1) * query.page_size),
        ).fetchall()
        metadata = db.execute(
            _BASE
            + """
 select (select count(*) from filtered) as total,
 coalesce((select jsonb_object_agg(stage,n) from (select stage,count(*) n from base group by stage) c),'{}'::jsonb) as stage_counts,
 coalesce((select jsonb_agg(s) from (
  select data->>'currency' as currency,to_char(sum((amounts->>'total')::numeric),'FM999999999999999999990.00') as billed
  from filtered where stage='issued' group by data->>'currency' order by data->>'currency'
 ) s),'[]'::jsonb) as summaries,
 coalesce((select md5(string_agg(id::text||':'||version::text||':'||coalesce(operation_id::text,'')||':'||evidence_version::text,',' order by id)) from base),md5('')) as query_version
 """,
            args,
        ).fetchone()
        return InvoicePage(
            items=tuple(store.invoice_view(db, row, lock=False) for row in rows),
            page=query.page,
            page_size=query.page_size,
            **metadata,
        )


def customers(
    store: Store,
    actor: TrustedActor,
    grant: UUID | None,
    query: Query,
    archived: bool = False,
) -> CustomerPage:
    with store.transaction(actor, grant) as db:
        where = " from public.business_customers where space_id=%s and archived=%s and (%s='' or position(lower(%s) in lower(data->>'name'))>0)"
        args = (actor.space_id, archived, query.search, query.search)
        total = db.execute("select count(*) as n" + where, args).fetchone()["n"]
        rows = db.execute(
            "select *" + where + " order by lower(data->>'name'),id limit %s offset %s",
            (*args, query.page_size, (query.page - 1) * query.page_size),
        ).fetchall()
        return CustomerPage(
            items=tuple(store.customer_view(row) for row in rows),
            total=total,
            page=query.page,
            page_size=query.page_size,
        )
