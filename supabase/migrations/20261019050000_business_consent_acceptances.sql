-- A person's acceptance of the Business data-use screen ("Antes de empezar"):
-- who accepted, in which Business they were working (their own or a client's
-- through a grant), which wording, and when. One row per person and wording;
-- a new wording asks again. A row is never edited. It goes with the person,
-- or with the Business it names.

create table public.business_consent_acceptances (
    user_id uuid not null references auth.users (id) on delete cascade,
    space_id uuid not null references public.spaces (id) on delete cascade,
    copy_version text not null check (copy_version ~ '^[0-9a-f]{16}$'),
    accepted_at timestamptz not null default now(),
    primary key (user_id, copy_version)
);
create index business_consent_acceptances_space_idx
    on public.business_consent_acceptances (space_id);

alter table public.business_consent_acceptances enable row level security;

revoke all on public.business_consent_acceptances
    from public, anon, authenticated, service_role;
grant select, insert on public.business_consent_acceptances to service_role;
-- The time is the database's: a client names only who, where and which wording.
grant select on public.business_consent_acceptances to authenticated;
grant insert (user_id, space_id, copy_version)
    on public.business_consent_acceptances to authenticated;

create policy business_consent_acceptances_select
    on public.business_consent_acceptances
    for select to authenticated
    using (user_id = (select auth.uid()));

-- Only one's own row, naming a Business one may read: the owner's own grant
-- or a live client grant, the same rule the bank tables use.
create policy business_consent_acceptances_insert
    on public.business_consent_acceptances
    for insert to authenticated
    with check (
        user_id = (select auth.uid())
        and argus_private.business_bank_has_capability(space_id, 'read')
    );
