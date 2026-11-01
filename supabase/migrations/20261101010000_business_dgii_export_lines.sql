-- One row per 606 or 607 line a person downloaded in a DGII TXT. From then on
-- that record's declaration is frozen: a 606 write on it is refused with
-- fiscal_declaration_exported. Append-only evidence with the money rows: the
-- key to spaces restricts, and the closed-Business purge removes these rows
-- itself (argus.domain.business.purge). The activity's own delete takes
-- its lines with it, as it takes its settlement.

begin;
set local lock_timeout = '5s';
set local statement_timeout = '60s';

create table public.business_dgii_export_lines (
    id uuid primary key default gen_random_uuid(),
    space_id uuid not null references public.spaces (id) on delete restrict,
    activity_id uuid not null
        references public.financial_activity_groups (id) on delete cascade,
    form text not null check (form in ('606', '607')),
    period text not null check (period ~ '^[0-9]{6}$'),
    actor_id uuid references auth.users (id) on delete set null,
    exported_at timestamptz not null default clock_timestamp()
);
create index business_dgii_export_lines_activity_idx
    on public.business_dgii_export_lines (space_id, activity_id);

alter table public.business_dgii_export_lines enable row level security;
revoke all on public.business_dgii_export_lines from public, anon, authenticated;
grant select, insert on public.business_dgii_export_lines to service_role;

commit;
