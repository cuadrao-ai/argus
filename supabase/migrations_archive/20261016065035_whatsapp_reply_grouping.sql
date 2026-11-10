begin;

-- One waiting failure group per hashed sender. Samples contain only authenticated ciphertext.
create table public.whatsapp_reply_groups (
    sender_hash bytea primary key check (octet_length(sender_hash) = 32),
    owner_id uuid not null references auth.users(id) on delete cascade,
    link_id uuid not null references public.whatsapp_sender_links(id) on delete cascade,
    failed_count integer not null check (failed_count > 0),
    samples jsonb not null check (jsonb_typeof(samples) = 'array' and jsonb_array_length(samples) between 1 and 3),
    last_sent_at timestamptz not null,
    send_after timestamptz not null,
    retries integer not null default 0 check (retries >= 0)
);
create index whatsapp_reply_groups_due on public.whatsapp_reply_groups(send_after);
create index whatsapp_reply_groups_owner on public.whatsapp_reply_groups(owner_id);
create index whatsapp_reply_groups_link on public.whatsapp_reply_groups(link_id);

-- One counter per hashed sender and UTC day. Reservations cover unresolved send outcomes.
create table public.whatsapp_reply_days (
    sender_hash bytea not null check (octet_length(sender_hash) = 32),
    day date not null,
    owner_id uuid not null references auth.users(id) on delete cascade,
    sent_count integer not null default 0 check (sent_count >= 0),
    reserved_count integer not null default 0 check (reserved_count >= 0),
    primary key (sender_hash, day)
);
create index whatsapp_reply_days_owner on public.whatsapp_reply_days(owner_id);

-- One active send per sender, separate from newly arriving failures.
create table public.whatsapp_reply_attempts (
    sender_hash bytea primary key check (octet_length(sender_hash) = 32),
    token uuid not null unique,
    owner_id uuid not null references auth.users(id) on delete cascade,
    link_id uuid not null references public.whatsapp_sender_links(id) on delete cascade,
    day date not null,
    failed_count integer not null check (failed_count > 0),
    samples jsonb not null check (jsonb_typeof(samples) = 'array' and jsonb_array_length(samples) between 1 and 3),
    last_sent_at timestamptz not null,
    expires_at timestamptz not null,
    retries integer not null check (retries >= 0),
    foreign key (sender_hash, day) references public.whatsapp_reply_days(sender_hash, day)
);
create index whatsapp_reply_attempts_expiry on public.whatsapp_reply_attempts(expires_at);
create index whatsapp_reply_attempts_owner on public.whatsapp_reply_attempts(owner_id);
create index whatsapp_reply_attempts_link on public.whatsapp_reply_attempts(link_id);

alter table public.whatsapp_reply_groups enable row level security;
alter table public.whatsapp_reply_days enable row level security;
alter table public.whatsapp_reply_attempts enable row level security;
revoke all on public.whatsapp_reply_groups, public.whatsapp_reply_days,
    public.whatsapp_reply_attempts from public, anon, authenticated;
grant all on public.whatsapp_reply_groups, public.whatsapp_reply_days,
    public.whatsapp_reply_attempts to service_role;

create index whatsapp_reply_days_day_idx on public.whatsapp_reply_days(day);

commit;
