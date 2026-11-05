begin;
set local lock_timeout = '5s';
set local statement_timeout = '60s';

alter table public.business_access_invites
    alter column expires_at set default (now() + interval '7 days');

-- Shorten pending windows only. Accepted grants and revoked history are retained.
update public.business_access_invites
set expires_at = least(expires_at, created_at + interval '7 days')
where accepted_at is null and revoked_at is null
  and expires_at > created_at + interval '7 days';

commit;
