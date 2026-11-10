-- Household lane: invite codes, beta invites, the founder group link, the
-- who-invited-whom record, and beta admission.
-- Spec: docs/specs/lanes/mvee-five-lane-handoff.md#lane-1-household-invitations
-- Decisions: docs/specs/argus-decision-log.md#october-2-2026-cuadrao-lane-locks
--
-- Pattern (same as household_* tables): RLS on, every client privilege
-- revoked, the API service writes, and the API checks the role. The policies
-- below are explicit per command so a later grant cannot silently open writes.
--
-- Deletion: live user ids sit beside the anonymous record and use
-- ON DELETE SET NULL. invite_referrals keeps no name, email or user id once a
-- person is deleted, so counts and the invite chain survive (decision 3).
-- The account-deletion lane clears these ids explicitly as well.

-- 1. A short human-typeable code beside the existing household token.
alter table public.household_invitations
    add column code_hash text;

create unique index household_invitations_code_hash_idx
    on public.household_invitations (code_hash)
    where code_hash is not null;

-- 2. Beta invites (single use) and founder group links (capped, multi use).
create table public.beta_invitations (
    id uuid primary key default gen_random_uuid(),
    kind text not null check (kind in ('beta', 'group_link')),
    token_hash text not null unique,
    code_hash text not null unique,
    created_by uuid references auth.users(id) on delete set null,
    source_label text check (
        source_label is null or char_length(source_label) between 1 and 80
    ),
    max_uses integer not null check (max_uses between 1 and 10000),
    use_count integer not null default 0 check (use_count >= 0),
    overflow_count integer not null default 0 check (overflow_count >= 0),
    created_at timestamptz not null default now(),
    expires_at timestamptz not null,
    revoked_at timestamptz,
    idempotency_key text not null check (char_length(idempotency_key) between 1 and 200),
    request_hash text not null,
    check (expires_at > created_at),
    check (use_count <= max_uses),
    -- A beta invite is the single-use code; the group link is the one
    -- exception and always carries its source label.
    check (
        (kind = 'beta' and max_uses = 1 and source_label is null)
        or (kind = 'group_link' and source_label is not null)
    ),
    unique (created_by, idempotency_key)
);

create index beta_invitations_sender_idx
    on public.beta_invitations (created_by, created_at desc)
    where created_by is not null;

-- 3. A random, per-person sender reference. The mapping row goes with the
-- account, so the reference left on the record identifies nobody, while
-- "invites sent per user" stays countable after a deletion.
create table public.invite_sender_refs (
    user_id uuid primary key references auth.users(id) on delete cascade,
    ref uuid not null unique default gen_random_uuid()
);

-- 4. The who-invited-whom record. One row per beta or household invitation,
-- and one row per group-link redemption (the link is the inviter).
create table public.invite_referrals (
    id uuid primary key default gen_random_uuid(),
    kind text not null check (kind in ('beta', 'household', 'group_link')),
    beta_invitation_id uuid references public.beta_invitations(id) on delete set null,
    household_invitation_id uuid
        references public.household_invitations(id) on delete set null,
    -- The referral that admitted the sender, if any. Survives deletion so the
    -- "invitee invited someone" chain is still countable.
    inviter_origin_id uuid references public.invite_referrals(id) on delete set null,
    sender_ref uuid,
    sender_user_id uuid references auth.users(id) on delete set null,
    acceptor_user_id uuid references auth.users(id) on delete set null,
    sent_at timestamptz not null default now(),
    accepted_at timestamptz,
    check (acceptor_user_id is null or accepted_at is not null),
    -- A group link row is a redemption: no person is the inviter.
    check (
        kind <> 'group_link'
        or (sender_user_id is null and sender_ref is null and accepted_at is not null)
    )
);

create unique index invite_referrals_one_per_invitation_idx
    on public.invite_referrals (beta_invitation_id)
    where kind = 'beta' and beta_invitation_id is not null;

create unique index invite_referrals_one_per_household_invitation_idx
    on public.invite_referrals (household_invitation_id)
    where household_invitation_id is not null;

create unique index invite_referrals_one_redemption_per_person_idx
    on public.invite_referrals (beta_invitation_id, acceptor_user_id)
    where kind = 'group_link' and acceptor_user_id is not null;

create index invite_referrals_sender_idx
    on public.invite_referrals (sender_user_id, sent_at desc)
    where sender_user_id is not null;

create index invite_referrals_origin_idx
    on public.invite_referrals (inviter_origin_id)
    where inviter_origin_id is not null;

-- 5. Beta admission: the in-app code gate's record. One row per person.
create table public.beta_admissions (
    user_id uuid primary key references auth.users(id) on delete cascade,
    via text not null check (
        via in (
            'beta_invitation',
            'group_link',
            'household_invitation',
            'existing_account'
        )
    ),
    referral_id uuid references public.invite_referrals(id) on delete set null,
    admitted_at timestamptz not null default now()
);

-- 6. Founder quota grants on top of the 10 beta invites.
create table public.beta_invite_quota_grants (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    granted_by uuid references auth.users(id) on delete set null,
    extra integer not null check (extra between 1 and 1000),
    created_at timestamptz not null default now(),
    idempotency_key text not null check (char_length(idempotency_key) between 1 and 200),
    request_hash text not null,
    unique (granted_by, idempotency_key)
);

create index beta_invite_quota_grants_user_idx
    on public.beta_invite_quota_grants (user_id);

-- Backfill: every existing household invitation joins the record, and every
-- existing registered account is admitted so turning the gate on later does
-- not lock out people who are already in.
insert into public.invite_sender_refs (user_id)
select distinct i.created_by
from public.household_invitations i
where i.created_by is not null
on conflict (user_id) do nothing;

insert into public.invite_referrals (
    kind, household_invitation_id, sender_ref, sender_user_id,
    acceptor_user_id, sent_at, accepted_at
)
select 'household', i.id, r.ref, i.created_by, i.accepted_by, i.created_at, i.accepted_at
from public.household_invitations i
left join public.invite_sender_refs r on r.user_id = i.created_by;

insert into public.beta_admissions (user_id, via, admitted_at)
select u.id, 'existing_account', now()
from auth.users u
where coalesce(u.is_anonymous, false) = false
on conflict (user_id) do nothing;

-- Access rules.
alter table public.beta_invitations enable row level security;
alter table public.invite_sender_refs enable row level security;
alter table public.invite_referrals enable row level security;
alter table public.beta_admissions enable row level security;
alter table public.beta_invite_quota_grants enable row level security;

create policy beta_invitations_sender_select on public.beta_invitations
    for select to authenticated
    using (created_by = (select auth.uid()));
create policy beta_invitations_no_client_insert on public.beta_invitations
    for insert to anon, authenticated with check (false);
create policy beta_invitations_no_client_update on public.beta_invitations
    for update to anon, authenticated using (false) with check (false);
create policy beta_invitations_no_client_delete on public.beta_invitations
    for delete to anon, authenticated using (false);

create policy invite_sender_refs_no_client_select on public.invite_sender_refs
    for select to anon, authenticated using (false);
create policy invite_sender_refs_no_client_insert on public.invite_sender_refs
    for insert to anon, authenticated with check (false);
create policy invite_sender_refs_no_client_update on public.invite_sender_refs
    for update to anon, authenticated using (false) with check (false);
create policy invite_sender_refs_no_client_delete on public.invite_sender_refs
    for delete to anon, authenticated using (false);

create policy invite_referrals_party_select on public.invite_referrals
    for select to authenticated
    using (
        sender_user_id = (select auth.uid())
        or acceptor_user_id = (select auth.uid())
    );
create policy invite_referrals_no_client_insert on public.invite_referrals
    for insert to anon, authenticated with check (false);
create policy invite_referrals_no_client_update on public.invite_referrals
    for update to anon, authenticated using (false) with check (false);
create policy invite_referrals_no_client_delete on public.invite_referrals
    for delete to anon, authenticated using (false);

create policy beta_admissions_self_select on public.beta_admissions
    for select to authenticated
    using (user_id = (select auth.uid()));
create policy beta_admissions_no_client_insert on public.beta_admissions
    for insert to anon, authenticated with check (false);
create policy beta_admissions_no_client_update on public.beta_admissions
    for update to anon, authenticated using (false) with check (false);
create policy beta_admissions_no_client_delete on public.beta_admissions
    for delete to anon, authenticated using (false);

create policy beta_invite_quota_grants_self_select on public.beta_invite_quota_grants
    for select to authenticated
    using (user_id = (select auth.uid()));
create policy beta_invite_quota_grants_no_client_insert on public.beta_invite_quota_grants
    for insert to anon, authenticated with check (false);
create policy beta_invite_quota_grants_no_client_update on public.beta_invite_quota_grants
    for update to anon, authenticated using (false) with check (false);
create policy beta_invite_quota_grants_no_client_delete on public.beta_invite_quota_grants
    for delete to anon, authenticated using (false);

-- Token and code hashes are projected only by the service.
revoke all on public.beta_invitations from anon, authenticated;
revoke all on public.invite_referrals from anon, authenticated;
revoke all on public.invite_sender_refs from anon, authenticated;
revoke all on public.beta_admissions from anon, authenticated;
revoke all on public.beta_invite_quota_grants from anon, authenticated;
