-- Cuadrao marketing site: Personal early-access signups (#882).
-- Spec: docs/specs/cuadrao-marketing-forms-contract.md.
--
-- One row per normalized address, keyed by its SHA-256 digest. Visitors have no
-- Argus account, so nothing here references auth.users and the account deletion
-- census is unaffected.
--
-- Removing a signup erases the address but keeps the digest and a removed_at
-- timestamp. That row is the suppression record: the page's insert conflicts
-- with it and is ignored, so a removed address is never registered or notified
-- again, and the visitor cannot tell a new address from a removed one.
--
-- Dated after main's latest migration and before the first newer integration
-- migration, so a fresh replay orders it correctly on both branches. A database
-- that already applied the newer integration migrations needs --include-all.
--
-- Only the marketing service writes this table, through service_role. RLS is on
-- with no policy, and anon and authenticated hold no privilege, so the project's
-- public API keys cannot read or write it.

create table public.cuadrao_early_access_signups (
    email_digest text primary key
        check (email_digest ~ '^[0-9a-f]{64}$'),
    email text
        check (
            email = lower(btrim(email))
            and char_length(email) between 3 and 254
            and email !~ '[[:space:]]'
        ),
    language text not null check (language in ('es', 'en')),
    consent_version text not null
        check (char_length(consent_version) between 1 and 64),
    source text not null default 'personal-page'
        check (char_length(source) between 1 and 64),
    created_at timestamptz not null default now(),
    -- Stamped by the operator script after the one availability notice is sent.
    notified_at timestamptz,
    removed_at timestamptz,
    -- An address is stored exactly while the signup is active.
    constraint cuadrao_signups_email_iff_active
        check ((removed_at is null) = (email is not null)),
    -- The digest is derived from the address, never supplied independently.
    constraint cuadrao_signups_digest_matches_email
        check (
            email is null
            or email_digest = encode(sha256(convert_to(email, 'UTF8')), 'hex')
        )
);

comment on table public.cuadrao_early_access_signups is
    'Cuadrao Personal early-access signups from the marketing site. service_role only; email is null once removed, and the row remains as the suppression record.';

alter table public.cuadrao_early_access_signups enable row level security;

-- service_role is revoked too: hosted Supabase grants it every privilege on a
-- new table by default, including delete, which would let suppression rows go.
revoke all on table public.cuadrao_early_access_signups
    from public, anon, authenticated, service_role;
grant select, insert, update on table public.cuadrao_early_access_signups
    to service_role;
