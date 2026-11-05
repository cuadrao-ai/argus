# Real Postgres CI sender assertion repair

PR #1228 head before this repair was
`abce9d8898a0c488c327c8b0c37b18d6e3f88eaf`. CI run `39099474824`
failed the protected approval replay test in both Postgres matrices, jobs
`117592854133` and `117592854172`. Integration was freshly fetched at
`651870a54be4e5506dbb38f3902fef1a97eef8df` and required no reconciliation.

## Cause and bounded change

The real gateway test's fake SMTP server still expected
`noreply@get-argus.com`. The approved shared transport supplies
`no-responder@mail.cuadrao.ai`. The assertion raised inside `smtp.mail`, and
the unchanged protected approval handler correctly returned 503.
`before.log` records this exact failure through the actual SupabaseGateway,
Supabase client, PostgREST and Postgres.

Change only the fake SMTP envelope expectation and add this test's exact path
to this branch's ownership allowlist. Every replay, exactly-once delivery,
language, content-version, subject and persisted promotion assertion is kept.
No production code, legacy welcome template, ops approval path, database
guard, migration, admission rule or ownership checker changes.

## Local verification

The reproducer created only `invite_pg_ci_repair_20261018` from `template0`
inside the assigned local Postgres 17.6 container. It applied the existing
`set_updated_at` function and these committed migrations without edits:

- `20260530000001_private_alpha_allowlist.sql`
- `20260530000002_simplify_private_alpha_allowlist.sql`
- `20260731080154_add_requested_private_alpha_access.sql`
- `20260812142717_add_access_welcome_deliveries.sql`
- `20260812173805_claim_access_welcome_delivery.sql`
- `20260816150000_scope_access_welcome_enforcement.sql`

A separately named cached PostgREST v16.3 container connected to this
database. A local HTTP adapter stripped `/rest/v1` before forwarding to
PostgREST. The actual Supabase client and gateway used a synthetic local
service-role JWT. SMTP remained the existing test recorder. No hosted
database, shared database contents, real provider or environment file was
changed. The baseline database was only read for schema inspection.

Python was 3.10.20 from the shared read-only dependency environment. All
commands used `env -i`, `PYTHONPATH=src:.`, `PYTHON_DOTENV_DISABLED=1`,
synthetic market data, memory persistence/checkpointer and no provider keys.
Database URL and local gateway configuration existed only in the test process.

At the original head, the exact failing test produced `1 failed in 2.32s`.
After the assertion repair, the following existing suites produced
`104 passed in 0.61s`, including all 22 actual Postgres access tests and the
real gateway replay test. See `after.log`.

```sh
python -m pytest tests/test_access_request_postgres.py \
  tests/test_access_approval_email.py tests/test_feedback_notification.py \
  tests/business/test_invite_email.py tests/business/test_invite_email_api.py \
  tests/business/test_invite_expiry.py -q --no-cov --tb=short
```

The branch ownership gate, modularity budget and repair-delta whitespace check
passed. Deslop review confirmed the repair is one changed assertion plus its
exact ownership entry and evidence.

This was a minimal access-schema reproduction, not a full Supabase reset.
Both full migration-reset Postgres CI matrices and all required exact-head
checks remain required on the new commit. Independent delta Eval remains a
root-owned gate. Receipt, merge, staging, activation and actual recipient
receipt remain held. Legacy welcome, admission and template remain KEPT under
issue #1230. Reviewer model for this repair: GPT-6.1-sol, high reasoning.
