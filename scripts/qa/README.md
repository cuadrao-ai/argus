# Issue-248 real-auth QA harness

End-to-end account-recovery and session-control QA against real Supabase Auth.
Everything here targets the worktree-local Supabase stack (or one approved QA
branch) and is blocked from production by `assert-nonprod-target.sh`.

## Guest exact-head evidence

Guest Block 4 QA uses the same non-production guard and local Supabase stack.
After a zero-state `supabase db reset --local`, run the guest browser matrix
only against the exact committed candidate SHA with mock Auth disabled. Guest
access defaults on; explicit false remains the emergency kill switch. Public-
account access stays false for staged-mode checks and is enabled only for the
isolated new-account conversion case, then restored false.

Store sanitized evidence under:

```text
temp/qa-evidence-guest/<candidate-sha>/
```

The evidence set may include screenshots, sanitized `/me` and usage shapes,
hashed owner labels, counts, expiry facts, zero-cross-owner results,
chart-interaction network method/path counts, and console status. It must not
include passwords, email addresses, Auth UUIDs, raw conversation/artifact/job/
run ids, cookies, bearer tokens, headers, handoff secrets, query strings, or raw
transcript dumps.

The exact-head matrix is one visible pass with Playwright retries disabled.
Use deterministic database setup for quota, expiry, cleanup, and concurrency;
use only one bounded real interpreter/provider journey. Stop on the first
product failure and preserve the sanitized evidence without silently retrying.
Passing local evidence does not authorize integration, deployment, public
flags, or tester exposure.

### Block 4 guest browser harness

The Block 4 matrix has a dedicated local-only runner. It selects only the
guest harness, rejects hosted targets, disables Playwright retries/traces/
video, launches one headful Chromium worker, and keeps public-account access
off except for the in-process isolated conversion step.

The runner builds once per mode and serves the compiled frontend with
`bun run start`. The provider-free guest-entry fixtures use a dedicated
mock-auth production build because browser API interception cannot satisfy the
server-rendered `/chat` Supabase session guard. The authoritative matrix uses a
separate real-Auth production build from the same exact SHA.

Before committing a harness correction, validate setup and teardown without a
runtime turn:

```bash
bash scripts/qa/run-guest-experience-qa.sh list --list
bash scripts/qa/run-guest-experience-qa.sh preflight
bash scripts/qa/run-guest-experience-qa.sh entry
```

The runner defaults to the repository-local Supabase project and ports
`3000`/`8000`. When another Argus lane is active, select one lane-owned local
stack and unused ports without changing those defaults:

```bash
ARGUS_GUEST_QA_APP_PORT=59900 \
ARGUS_GUEST_QA_API_PORT=59901 \
ARGUS_GUEST_QA_SUPABASE_WORKDIR=/absolute/path/to/isolated-worktree \
ARGUS_GUEST_QA_DB_CONTAINER=supabase_db_isolated-project \
bash scripts/qa/run-guest-experience-qa.sh preflight
```

The selected worktree must contain `supabase/config.toml`; its `project_id`
must match the running database container label. The runner refuses occupied
ports and never stops an existing listener.

After committing, reset the local Supabase stack and prove zero state before
the one authorized live run:

```bash
supabase db reset --local
bash scripts/qa/run-guest-experience-qa.sh authoritative
```

Do not run the authoritative command against an existing server or a hosted
Supabase project. The runner requires a clean worktree and starts fresh local
services itself. It is branch-agnostic so the same committed gate can verify a
merged or reintegrated candidate. Pin the expected commit when handing the run
between release captains:

```bash
ARGUS_EXPECTED_CANDIDATE_SHA="$(git rev-parse HEAD)" \
bash scripts/qa/run-guest-experience-qa.sh authoritative
```

## One-shot run

```bash
supabase start -x vector,edge-runtime,imgproxy   # once per machine boot
supabase db reset --local                        # migrations from zero + seed
bash scripts/qa/write-local-env.sh               # untracked .env + web/.env.local
bash scripts/qa/run-local-auth-qa.sh             # guard -> backend -> identities -> journeys
```

New worktrees normally inherit `.env` and `web/.env.local` as symlinks to the
canonical integration worktree. `write-local-env.sh` safely detaches those
links and writes regular lane-local files before local-stack QA. Do not replace
this command with `cat > .env` or similar redirection, which follows symlinks
and can corrupt the shared canonical environment.

The local stack uses the stable `project_id = "argus-qa"` (containers such as
`supabase_db_argus-qa`) and a same-site topology — app on
`http://localhost:3000`, API on `http://localhost:8000` — so the Argus
HttpOnly cookie transport is real in local QA.

The runner executes six Playwright phases from `web/e2e/qa-248/`:

1. `1-recovery.spec.ts` — enumeration safety, Mailpit delivery, single PKCE
   exchange, reset, reuse/malformed/expired links, correct-current-password
   change. The wrong-current-password rejection is enforced by the hosted
   `security_update_password_require_current_password` policy, which the
   local CLI cannot enable, so that journey lives in the hosted live matrix.
2. `2-sessions.spec.ts` — two-context revoke-others/revoke-all, ordinary
   logout scope, revoked-bearer rejection, partial cookie-cleanup honesty.
3. `3-es-mobile.spec.ts` — Spanish + mobile surfaces, cross-user isolation.
4. `5-password-change-session.spec.ts` — session-integrity pins for the
   password-change path (expected-fail tripwire until provider-native
   `current_password` enforcement exists; see the spec header).
5. `6-argus-cookie-path.spec.ts` — the Argus HttpOnly cookie transport:
   cookie-only auth, stale-cookie rejection after revocation, cookie
   clearing on successful logout.
6. `4-verification-outage.spec.ts` — retryable 503 while the verification
   database is down and the auth provider stays healthy (runner-orchestrated).

Evidence (screenshots, HTML report, backend log, current-password state) lands
in `temp/qa-evidence-248/`.

## Product limits the harness must respect

- Argus login limiter: 8 attempts per email and per IP per 10 minutes. The
  runner restarts the backend between spec files; each file stays within one
  identity's budget.
- Argus recovery limiter: 5 requests per email and per client address per 10
  minutes. Specs use run-unique trusted-client-IP addresses
  (`CF-Connecting-IP`; `X-Forwarded-For` is ignored for backend keying);
  sends to the
  recovery identity stay at 3 per run, so leave ~10 minutes between full runs
  against a still-running server (fresh servers reset the in-memory buckets).
- GoTrue `max_frequency` (1s between sends per user): specs call
  `respectSendWindow()` before repeat sends.
- `supabase/config.toml` pins `otp_expiry = 60` so the expired-link journey
  completes in-band. Production keeps its own expiry.

## Identities

`setup-local-identities.sh` creates two disposable users through the real
Argus signup path (allowlist rows come from `supabase/seed.sql`), verifies
login, and writes runtime credentials to untracked `.qa-identities.env`.
It talks only to the stack's HTTP surface (auth admin + PostgREST), so it
needs no Docker access; only the `auth.sessions` row-count assertions in
spec 5 shell into the local db container and skip when Docker is absent.
`--teardown` removes users, profiles, and the credential file. Passwords are
generated per setup run and never committed; recovery journeys persist the
current password in `temp/qa-evidence-248/qa-state.json`.

## Hosted QA branch mode

Export `ARGUS_QA_APPROVED_SUPABASE_REF=<branch project ref>` and point the
generated env files at that branch before running; the guard then admits
exactly that ref and still hard-fails on any production reference.
Mailpit-dependent recovery specs skip in hosted mode — hosted recovery
delivery stays gated on sandbox SMTP.

## Backend tests

The focused backend matrix must run hermetically, per `AGENTS.md`:

```bash
OPENROUTER_API_KEY= ALPACA_API_KEY= ALPACA_SECRET_KEY= \
ARGUS_MARKET_DATA_PROVIDER_MODE=synthetic_unit_fixture \
poetry run pytest tests/test_auth_sessions.py tests/test_alpha_api_supabase.py \
  tests/test_alpha_artifacts.py tests/test_environment_scripts.py -q --no-cov
```
