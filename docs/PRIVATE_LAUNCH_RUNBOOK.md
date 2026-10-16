# Private Launch Runbook

> [!NOTE]
> Current operational gate for Private Alpha candidate validation. Use
> `docs/DOCUMENTATION_AUTHORITY.md` for product ownership and assigned work.
> `docs/specs/private-alpha-next-roadmap.md` and
> `docs/specs/private-alpha-next-decision-memo.md` are historical references,
> not product-sequencing authorities. Use this runbook with
> `docs/specs/private-alpha-ci-cd-sota.md` and
> `docs/release-manifests/TEMPLATE.md` for release gating.
> For CI/CD promotion decisions, the decision memo is a later-context document, not part of this release gate.

> [!NOTE]
> The validated 2026-07-14 private-alpha checkpoint is recorded in
> [`docs/release-manifests/2026-07-14-private-alpha-release-integrity.md`](release-manifests/2026-07-14-private-alpha-release-integrity.md)
> and [#197's closure evidence](https://github.com/lagarcess/argus/issues/197#issuecomment-4965556704).
> It validates the existing branch-deployed private-alpha Render surface; it did
> not merge `main`, deploy production, enable automatic production deployment,
> invite testers, or expose testers.

This runbook is for the first trusted-user internet tests on Render.

## Cuadrao capability acceptance

For an assigned Cuadrao capability, use the selected user journey to define its
acceptance evidence. The [consumer launch boundary](specs/argus-minimum-viable-ecosystem-experience.md#consumer-and-business-launch-boundary)
and existing release gates still apply. The constitution's feature catalog does
not add a fiscal, business or connector prerequisite to every release.

### Customer work removed

Each in-scope customer journey answers these questions in its issue:

1. What job does it finish?
2. What trusted records does it use or create?
3. Who is allowed to do it?
4. What happens when it is wrong or fails?
5. How will we know it worked?

Record the work the customer does today and the work left after the feature.
Use realistic samples to measure completion, active review time, fields corrected,
manual re-entry and successful recovery where applicable. Agree the relevant
thresholds from a baseline; do not invent a universal target or waive correctness
and authorization to reduce taps. Test data is labeled as such.

For receipts, the outcome is a confirmed expense with retrievable source evidence,
not successful OCR alone. Evaluate capture through review, confirmation, relaunch
and correction. Automatic preparation does not replace explicit confirmation of
financial writes under the current policy.

### Journey evidence

Record the following in the assigned issue and release evidence:

- The actor, space, source records, confirmed effect and path back to the evidence.
- The applicable failure and recovery cases, including duplicate submission,
  interruption, missing data, changed permissions and corrections.
- The exact candidate, environment and observations. Distinguish fixture tests,
  connected physical-device journeys and live-provider checks. One does not
  substitute for another.
- Relevant measures of correctness, user correction effort, latency and cost.
  Set numeric thresholds from an agreed baseline and the selected workflow.
  Low latency does not excuse incorrect money or unauthorized access.

Apply fiscal issuance, provider settlement and other specialist checks when that
capability is in scope. Mark an inapplicable check with the reason. This does not
waive an existing mandatory security, privacy or release gate. Regulatory and
vendor claims from research need current evidence before a release relies on them.

## Launch URLs

- App: `https://arguschat.ai`
- API: `https://api.arguschat.ai`, moved 2026-08-13 and live. It must stay on a
  subdomain of the app's registrable domain: the guest handoff cookie is
  `SameSite=Lax`, so on `onrender.com` it was third-party and every iOS browser
  dropped it, which broke guest conversion for every user until the move.
  `test_api_and_app_share_a_registrable_domain` pins the two hosts together.
  Changing the host requires an `argus-app` rebuild, because
  `NEXT_PUBLIC_ARGUS_API_URL` is baked into the web bundle at build time.

## Before Tester Sessions

The promotion target is `main`, but `codex/private-alpha-next` remains the
integration staging branch until the founder approves promotion. Do not merge
to `main` or open a release PR before that approval. Deploys are manual. The
release profile and `render.yaml` declare `autoDeployTrigger: off` for all three
services (founder decision, 2026-09-13), so the release audit expects `off` and
a Blueprint sync cannot turn autodeploy on. Every
candidate still follows the gate below and needs a release manifest before
testers are invited; start from
`docs/release-manifests/TEMPLATE.md` and fill it with the exact candidate SHA,
API/web env fingerprint, workflow-service proof, canary evidence, rollback
target, autodeploy proof for all three services, and approver.

The candidate below must be the exact would-be `main` promotion commit: the
immutable commit produced from current `main` and the approved integration tree
that will actually land and deploy. A worker or integration head is not
sufficient when the landing method creates a different commit. If the landing
method cannot preserve a pre-gated SHA, keep all three live autodeploy triggers
manual through step 4 and gate the landed SHA before any deploy-capable action.

Local preflight doctrine:

- Run `.github/setup.sh` first and confirm `poetry run python --version` reports
  the `.python-version` runtime (`3.10.x`; currently `3.10.20`). Python 3.14
  green runs are non-canonical for deployed-runtime proof.
- Do local candidate work from sibling worktrees only, never nested inside
  another Argus checkout, so dotenv cannot inherit a parent `.env` and turn a
  mocked run into a live-provider run.
- For deterministic agent-runtime sweeps, blank live provider keys and set
  `ARGUS_MARKET_DATA_PROVIDER_MODE=synthetic_unit_fixture`. A clean mocked sweep
  is seconds-scale; minutes means stop and investigate live-call leakage.

1. Confirm the local checkout is the candidate commit you intend to promote:

```bash
git status --short --untracked-files=no
git rev-parse HEAD
```

The status command must show no tracked changes, and the SHA must be the exact
candidate. The migration gate enforces both before it opens a database
connection.

2. Run the local predeploy smoke gate before any internet-facing canary:

```bash
.github/local-smoke.sh --expected-sha "$(git rev-parse HEAD)"
```

3. After selecting production as the target and recording the intended config
   and deploy mode without changing it, run the production migration gate
   before any operation that can deploy a service, including a Blueprint sync
   or a change to autodeploy configuration. Export the production direct or
   session-pooler URL from the operator secret store under the gate-only name
   below. The URL must not contain query parameters or a fragment because libpq
   can use them to override the validated host or user. Do not put it on the
   command line, and the gate deliberately does not discover dotenv files, so
   the values must be exported into the running process. The gate forces
   `sslmode=verify-full`; it cannot fall back to a plaintext connection, which
   is why it needs the production root CA by absolute path.

```bash
export ARGUS_PRODUCTION_DATABASE_URL="$SUPABASE_POSTGRES_SESSION_POOLER_URL"
export ARGUS_PRODUCTION_DATABASE_SSL_ROOT_CERT="$HOME/.argus/prod-ca-2021.crt"
ARGUS_CANDIDATE_SHA="$(git rev-parse HEAD)"
poetry run python scripts/ops/production_migration_gate.py \
  --candidate-sha "$ARGUS_CANDIDATE_SHA" \
  --output temp/release-evidence/production-migration-gate.json
```

Both are aliases to things that already exist, so neither is a new secret to
mint. `SUPABASE_POSTGRES_SESSION_POOLER_URL` is in the root `.env`; source it
read-only and alias it rather than adding a second name for the same value.
Use the session pooler, not the direct URL, which fails on IPv6 here.

**Keep the CA at `~/.argus/prod-ca-2021.crt`, not in `~/Downloads`.** The
certificate is public, the same file Supabase serves at a public URL, so it is
a path and not a credential. But `~/Downloads` is TCC-protected on macOS and a
freshly downloaded copy carries `com.apple.quarantine`, so an agent process is
denied even though the file is world-readable and a normal shell reads it
fine. The gate then reports `must be an absolute readable file`, which reads
like a missing file and is not. One-time setup:

```bash
mkdir -p ~/.argus
cp ~/Downloads/prod-ca-2021.crt ~/.argus/prod-ca-2021.crt
xattr -c ~/.argus/prod-ca-2021.crt
```

The gate reads every migration from the exact candidate Git tree, verifies the
production Supabase project, opens a read-only database session, and compares
the full candidate list with the version, name, and parsed statement arrays in
`supabase_migrations.schema_migrations`. Read the candidate, applied, missing,
unexpected, name-drift, and content-drift lists in the JSON. Candidate and
applied records expose statement counts and statement-array SHA-256 digests.
`status=pass` is required before continuing. A missing migration is a stop even
when its safety classification is additive. An unreadable ledger, unexpected
production migration, duplicate version, name mismatch, missing statement
history, or statement content drift is also a stop.

The gate never applies migrations. If it reports a gap, stop the promotion. A
human reviews the exact pinned SQL and classification. The automated
classification is conservative: ambiguous top-level SQL becomes
`contract-replacing`, and the report does not replace inspection of the live
objects the migration will touch. Use these requirements:

- `additive` may be considered for live application after rollback review;
- `contract-replacing` needs an expand/contract compatibility plan or a
  maintenance window;
- `destructive` needs a maintenance window, backup/readback plan, and explicit
  founder approval.

Apply only approved files out of band, in repository order. Record the file
hash, ledger before and after, and affected-object readback in the release
manifest. Then rerun the same gate. Do not deploy until the rerun reports
`status=pass`, and attach its JSON as durable release evidence.

**Migrations that create functions the shipping code calls must be applied
before the deploy, not after.** A deploy that lands first runs new code against
a schema that lacks the objects it calls, and the failure surfaces as production
behavior rather than a gate result. The first promotion carrying PR #476 is the
live case: `.github/canary-render.sh` and the ops approve route call five
functions created by
`20260816150000_scope_access_welcome_enforcement.sql` and its two predecessors,
including `delete_private_alpha_access_welcome_artifacts`, which is how the
daily canary tears down the allowlist and delivery rows it creates. Deploy
before applying and the canary creates rows it cannot delete, on every run,
in production.

State the intended order explicitly in the manifest for any promotion carrying
a migration, so the operator cannot get it backwards from the checklist alone.

4. Land or read back the candidate on `main` without rewriting the gated
   commit. Keep the checkout on the gated candidate and rerun the same
   executable gate in landed-ref mode:

```bash
poetry run python scripts/ops/production_migration_gate.py \
  --candidate-sha "$ARGUS_CANDIDATE_SHA" \
  --verify-landed-ref origin/main \
  --output temp/release-evidence/production-migration-gate.json
```

The option fetches `origin/main` inside the gate and blocks before database
access if the fetch, ref resolution, or exact-SHA comparison fails. It then
repeats schema parity and records the landing proof in the final JSON. Do not
continue on any nonzero result. A squash, rebase, conflict edit, new merge
commit, or concurrent `main` update invalidates the earlier report. Keep all
three live triggers manual, check out the exact landed commit, rerun steps 1 and
2, then rerun the gate against the landed SHA as described in step 3 and replace
the manifest evidence. When `checksPass` is already live, use only a landing
method that preserves the pre-gated commit SHA; otherwise code can deploy before
the landed tree is verified.

> [!NOTE]
> **The deploy mode lives in the release profile.** The profile and
> `render.yaml` declare `off` for `argus-api`, `argus-app`, and
> `argus-backtests`, so a Blueprint sync and the companion Workflow API sync
> (`.github/render-env-sync.sh workflow-runtime`) keep all three manual. Before
> 2026-09-13 the repository declared `checksPass` while live Render stayed
> manual, so any configuration sync could turn autodeploy on as a side effect
> and every release audit reported drift. Enabling autodeploy is a founder
> decision made by changing the profile and `render.yaml` together for all three
> services, never by a sync.

5. In Render, sync the Blueprint from `render.yaml` only when `argus-api` or
   `argus-app` config drift needs reconciliation. Render Blueprints cannot
   declare the `argus-backtests` Workflow service. Its release contract is held
   in four separate places that must agree:

   - the release profile declares the Workflow runtime and deploy target;
   - `.github/render-env-sync.sh workflow-runtime` applies that target through
     the Render Workflow API;
   - `release-config-audit` reads the live Workflow configuration back;
   - steps 10 and 11 deploy `argus-backtests` and prove its ready version matches
     the same candidate as the API and app.

   If any one of these four controls drifts, `argus-backtests` can stay stale
   even while the API and app advance, which is the failure caught on
   2026-08-11.
6. Confirm Render is updating the existing `argus-app` and `argus-api` services.
   Stop if Render proposes duplicate services.
7. Confirm the live deploy mode matches the deliberate founder decision and is
   uniform across `argus-api`, `argus-app`, and the Git-linked
   `argus-backtests` Workflow: either all three are manual (`off`) or all three
   use `checksPass`. Never enable autodeploy for only a subset of the three.
   The repository target is not proof that live enablement was approved.
8. Export local ops and canary secrets, or keep these in the root `.env` file
   and let the scripts load them:

```bash
export ARGUS_OPS_TOKEN="..."
export ARGUS_CANARY_EMAIL="..."
export ARGUS_CANARY_SUPABASE_URL="https://lgdhvepyrzbnscqssgqq.supabase.co"
export ARGUS_CANARY_SUPABASE_SERVICE_ROLE_KEY="..."
```

For local founder/operator runs, `.github/canary-render.sh` also accepts
`MOCK_USER_EMAIL`, `SUPABASE_URL`, and `SUPABASE_SERVICE_ROLE_KEY` from the root
`.env`. The `ARGUS_CANARY_*` names remain the preferred GitHub Actions names.

9. Confirm the API is in real-workflow private-alpha validation mode. This mode
   keeps the API lean and sends `Run backtest` through the durable Render
   Workflow job path:

```bash
.github/render-env-sync.sh api-real-workflow-on
```

Restart `argus-api` after changing Render env values.

10. Deploy **all three live services** from the candidate commit:
   `argus-api`, then `argus-app`, then **`argus-backtests`**.

   When all three live triggers use `checksPass`, a commit on the configured
   deployment branch deploys after its checks pass. In manual mode, explicitly
   deploy the candidate using the same three-service order.

   **`argus-backtests` is the easiest one to forget and the one that breaks the
   canary.** It is the Render Workflow service that actually runs backtests, it
   is not declared in `render.yaml`, and it was missing from this step until
   2026-08-11. On that promotion the API and web shipped while the workflow
   service stayed a week behind, and the canary stopped at
   `workflow_commit_mismatch` before spending money on a paid journey. Deploy it
   every time, and never let a promotion finish with the three on different
   commits.

11. Confirm the live `argus-api`, `argus-app`, and `argus-backtests` deploy
   commits match the candidate commit you intend to test and that their latest
   versions are ready:

```bash
ARGUS_RELEASE_SHA="$(git rev-parse HEAD)"
.github/render-env-sync.sh api-deploy-status
.github/render-env-sync.sh web-deploy-status
.github/render-env-sync.sh workflow-version-status
```

If any of the three deployed commits is not `ARGUS_RELEASE_SHA`, stop and deploy
that stale service before running the strict canaries. The canary script
enforces the same deployed SHA/status check with `ARGUS_CANARY_SHA`, and its
resolver compares all three, which is what caught the workflow service running
behind on 2026-08-11.

For `argus-backtests`, Render exposes the deployed Git commit as the ready
Workflow version name, currently a seven-character SHA prefix. The status and
canary resolvers require that prefix to match the exact API/web commit. They do
not trust mutable workflow env markers, so checks-passing and manual releases
use the same version-owned proof.

12. Run the product warmup script and verify the API stayed in real workflow
   mode. When Supabase verifier credentials are present, this also runs the
   stale queued/running job scan:

```bash
.github/warmup-render.sh --expect-mode real-workflow
```

Render workflow dispatch is ceremony-gated spend: the hosted product (real
users), the scheduled Private Alpha Canary workflow, and these promotion steps
are the only paths that run paid `workflow_proof` / `run_backtest_job` tasks.
Local and dev-agent work runs backtests in-process on local compute; the mode
scripts pin dispatch off (dev hard-off, QA default-off with explicit
pre-export opt-in).

13. Run both authoritative canary surfaces with privacy-safe evidence. They are
separate fail-red jobs, so one cannot hide or relabel a failure in the other.
The canary is a small fixed check that never follows features (founder
decision, 2026-09-13, #614). The release profile's `canary.required_steps`
names its four checks:

- `services_same_commit`: `argus-api`, `argus-app`, and `argus-backtests` run
  the same commit.
- `signed_in_chat_answer`: the signed-in canary account loads the chat and gets
  one ordinary answer.
- `backtest_completes`: one backtest completes.
- `research_answer_with_sources`: one research question returns an answer with
  sources.

Every failure names the check, release guard, or harness step that failed, as
`ERROR: canary failed at <name>: <reason>` in the log and as `failed` in the
evidence JSON. The evidence also records each check's status.

- **Release coherence** proves `services_same_commit` and keeps three release
  guards: `release_config` (the release-config audit, warmup, and live-provider
  workflow proof), `disabled_signup_denial` (the direct API signup-denial
  probe), and `welcome_email` (the access-approval welcome-email proof).
- **Authenticated browser journey** starts from a private Playwright storage
  state and runs the other three checks against the deployed app. It never
  visits the signup or login page. It rechecks `services_same_commit`
  immediately before minting the session and after the browser checks, so a
  rollout during the checks cannot inherit the earlier release label. Sign-in
  retries once when `GET /api/v1/me` returns 401, 429, or a server error, and
  the evidence records `sign_in_attempts`, so a green run with two attempts is
  still visible. A failed sign-in names the HTTP status and API problem code.

Decision records, receipts, Search reopening, exact result facts, intercepted
recovery, and console checks are not canary checks. The promotion walk covers
features.

The disabled-email denial check belongs only to release coherence. The runner
creates a `user` allowlist row with `disabled_at` set, then
`.github/canary-requested-signup-denial.py` sends that address to the
ops-authenticated route owned by `REQUESTED_SIGNUP_DENIAL_PATH` in
`src/argus/api/ops_contract.py` and requires `200 {"denied": true}`. This proves
the disabled row is blocked with public access on and with the allowlist-only
emergency rollback. The probe never calls the signup provider or CAPTCHA, so it
cannot create an auth identity. `verify_no_signup_auth_identity` asserts that
none exists before the canary stages the same row as an active `requested` row
and calls the protected access-approval operation. That operation sends the real
localized welcome, records the provider-accepted delivery, and promotes the row
to `user` atomically; the canary then reads the delivery row back and requires
a provider receipt stamped inside this run, so a stopped-sending regression
cannot score green. A unique generated address scoped to the run identity
forces every canary attempt through the first-send path instead of delivery
replay. The exit trap deletes any resulting auth identity and allowlist row,
removes the run's claim and delivery rows through the service-reachable
`delete_private_alpha_access_welcome_artifacts` cleanup, then reads back that
no matching auth identity remains. If an approval fails after its claim is
written, the claim blocks that address's SMTP for 24 hours and the daily
maintenance pass releases it after 48; an operator can release immediately with
`release_expired_private_alpha_access_welcome_claims()`. Do not move this probe
into Playwright, enable its temporary identity for browser use, or weaken
Turnstile anywhere deployed.

For a local release-coherence run, generate a fresh non-secret nonce for every
attempt. Local mode is available only when both GitHub run identity variables
are absent. Do not combine the local nonce with GitHub identity variables or
override the generated signup email.

```bash
mkdir -p temp/release-evidence
ARGUS_CANARY_SURFACE=release-coherence \
ARGUS_CANARY_LOCAL_RUN_NONCE="$(poetry run python -c 'import secrets; print(secrets.token_hex(12))')" \
ARGUS_CANARY_SHA="$(git rev-parse HEAD)" \
ARGUS_CANARY_HARNESS_SHA="$(git rev-parse HEAD)" \
ARGUS_CANARY_EVIDENCE_PATH=temp/release-evidence/release-coherence.json \
ARGUS_CANARY_CAPTURE_PATH=temp/release-evidence/release-coherence-capture.json \
.github/canary-render.sh
```

For a local authenticated-browser run, install the pinned browser dependencies
first and use the dedicated canary identity described below:

```bash
cd web && bun install --frozen-lockfile && bunx playwright install chromium
cd ..
ARGUS_CANARY_SURFACE=authenticated-browser-journey \
ARGUS_CANARY_SHA="$(git rev-parse HEAD)" \
ARGUS_CANARY_HARNESS_SHA="$(git rev-parse HEAD)" \
ARGUS_CANARY_EVIDENCE_PATH=temp/release-evidence/authenticated-browser.json \
ARGUS_CANARY_CAPTURE_PATH=temp/release-evidence/authenticated-browser-capture.json \
.github/canary-render.sh
```

### Canary identity, session rotation, and revocation

`ARGUS_CANARY_EMAIL` must identify a dedicated Supabase Auth user. It must never
be an admin, developer, employee account, or real user. Its enabled
`private_alpha_allowlist` row must have exactly `role=user`, and its Auth user
app metadata must contain `source=private-alpha-canary`. Its exact `profiles`
row must also have `is_admin=false`; changing an allowlist role does not prove
that a previously elevated profile lost its privilege. App metadata is
operator-owned; do not use user-editable metadata for this marker. The canary
fails closed if any of those facts are not true.

Provisioning is a one-time manual action for identity rotation. Generate a new
address matching
`private-alpha-canary+<32-lowercase-hex>@get-argus.com`, write it directly to
the GitHub `ARGUS_CANARY_EMAIL` secret without echoing it, and dispatch the
candidate branch with `canary_identity_action=provision`. That action is never
available to the schedule. It accepts only the canary-specific address shape,
refuses to relabel an existing unknown user, creates a confirmed non-anonymous
Auth user with app metadata `source=private-alpha-canary`, records Spanish in
Auth user metadata, and creates the enabled `role=user` allowlist row. For a new
identity, it then mints a one-time session and calls Argus's authenticated
`GET /api/v1/me` endpoint so the normal backend profile owner creates the
profile. The setup session is revoked before the action requires the exact
profile row to have `is_admin=false`. It prints no email, user id, token, or
service-role value. Later manual and scheduled runs use the default
`canary_identity_action=validate` and fail closed on drift.

After the new identity completes a normal browser canary, revoke the prior
identity using the emergency sequence below. Do not leave two active canary
identities as an informal fallback.

No long-lived browser state or password is stored in GitHub. On every browser
run, the service-role step generates and verifies a one-time magic link for the
dedicated identity, serializes the resulting least-privilege session to a mode
`0600` Playwright storage-state file, and passes only that file and the expected
user id into the browser process. The browser process explicitly has the
service-role variables removed. This is the routine rotation: every run gets a
fresh session.

The browser surface revokes that session with local scope before it records
success. The exit trap retries revocation on every earlier failure path, then
deletes both the storage-state file and its private token handoff. Argus also
checks the Supabase session id on authenticated API requests, so a removed
session stops being an active Argus session. A revocation failure is an
`Authenticated browser journey` failure, never a passed artifact with a red
process exit.

For emergency revocation:

1. Disable the canary allowlist row.
2. In Supabase Auth, revoke every session for the dedicated user and confirm no
   `auth.sessions` row remains for its user id.
3. Delete the dedicated Auth user only after session revocation is confirmed.
4. Remove or replace `ARGUS_CANARY_EMAIL` in GitHub Actions.
5. Provision a new dedicated `role=user` identity with
   Auth app metadata `source=private-alpha-canary`, update the GitHub value, and
   run a manual canary before restoring the schedule.

Do not use deletion alone as immediate revocation. A previously issued access
token can remain cryptographically valid until expiry even after its Auth user
is deleted.

If a canary fails after warmup passed, do not redeploy one-off fixes in a loop.
The first authoritative run writes the sanitized capture beside the human-safe
evidence. Do not rerun the charged journey to collect a capture. When that
capture contains a final response, replay it locally before redeploying:

```bash
poetry run python scripts/ops/canary_capture_replay.py \
  temp/release-evidence/canary-es-419-capture.json
```

If the failure happened before any final response existed, keep the capture as
diagnostic evidence and inspect the hashed labels, the failed check, and API
logs instead of forcing a replay or spending a second journey.

Read the job name, the failed check, and its reason before treating a canary red
as a product regression. `Release coherence` owns `services_same_commit` and the
`release_config`, `disabled_signup_denial`, and `welcome_email` guards.
`Authenticated browser journey` owns session creation and the
`signed_in_chat_answer`, `backtest_completes`, and
`research_answer_with_sources` checks. `canary_harness` means the canary itself
could not run, not that the product failed. A browser job must never report a
Turnstile challenge timeout, because it does not cross an auth form.

If the exact candidate reaches the API but returns the normal interpreter
recovery response, keep the failed capture and evidence. Record the safe HTTP
status, route-receipt task/outcome summary, and environment fingerprint first;
do not increase token budgets or switch models as a speculative fix.

Use the replay to identify the macro-pattern and make one coherent fix.
Docker is optional for this step unless the production release path moves to
container images; prefer the local smoke gate plus canary replay first.

Before treating local UI changes as launch-ready, also run the browser recovery
spec against the local app/API environment:

```bash
cd web && bun run test:e2e e2e/chat-action-recovery.spec.ts --project=chromium
```

Only send the app URL to testers after API deploy-status, app deploy-status,
workflow version status, local smoke, warmup, both canary surfaces, and the
release manifest all pass against the intended candidate commit.
If any service reports a different commit, deploy the candidate branch before
continuing. If
warmup fails, do not invite testers yet. Check Render service status and redeploy
only if the service is stuck. If warmup passes but the canary fails, treat it as
an Argus product-path regression and inspect the failed-capture replay, API logs,
Supabase messages, backtest runs, and route receipts using the hashed labels and
internal access controls from the canary evidence.

For the daily automated gate, configure GitHub repository secrets with the same
canary variables above plus `RENDER_API_KEY` and `ARGUS_WORKFLOW_DATABASE_URL`,
then use the scheduled or manually dispatched `Private Alpha Canary` workflow.
Set `ARGUS_WORKFLOW_DATABASE_URL` from the `.env`/`.env.example` mapping to
`SUPABASE_POSTGRES_TRANSACTION_POOLER_URL`; do not use the session pooler for
short-lived workflow tasks. The two jobs report independently. Release
coherence owns warmup and the provider/config proof. The real backtest in the
browser journey runs on `argus-backtests`, while
`release-config-audit --expect-mode real-workflow` proves the workflow env itself
is using `live_provider`. Warmup then runs the deployed `workflow_proof` task and requires
`workflow_runtime_provider_mode=live_provider` and
`workflow_runtime_proof=ready`, proving effective workflow runtime rather than
only saved Render env vars. The jobs upload
`private-alpha-release-coherence-evidence` and
`private-alpha-authenticated-browser-evidence`, each with its own exit file.
Their failure captures are separate. The browser job can also upload
`private-alpha-authenticated-browser-context` after its redaction sentinel is
present.

The canary script masks the email, any legacy password present in an operator
environment, the session access and refresh tokens, serialized auth-cookie
values, and the artifact probe value before it creates
`web/temp/playwright-results/.redacted`. The workflow keeps the sentinel gate:
if redaction did not run or failed, it logs
`browser_context_upload=skipped_unredacted` and does not upload browser context.
The storage state and private handoff are temporary files outside the artifact
paths and are deleted on exit.

To prove this control, manually dispatch from the candidate branch twice. Use
`browser_artifact_probe=redacted` first. The browser job must fail deliberately,
the probe value must be masked in its context, and the sentinel-gated context
upload must occur. Then use `browser_artifact_probe=unredacted`. Redaction fails
deliberately, no sentinel is written, and the context upload must be skipped.
Both are expected red proof runs. Never use a real credential as the probe.

Trigger choice controls which harness is exercised:

- A schedule checks out `main`, resolves the coherent production SHA, and
  detaches to that deployed commit. The harness SHA and deployed SHA must match.
- A `workflow_dispatch` keeps the selected branch checked out while the resolver
  records the exact coherent production SHA separately. Only dispatch may run a
  branch harness against a different deployed target, and both SHAs are written
  to the evidence.

This means a branch dispatch can prove a canary-harness fix before promotion,
while still testing the exact production deployment. Merging the fix only into
`codex/private-alpha-next` does not change scheduled runs. The scheduled canary
uses the fix only after the production promotion reaches `main`; a still-red
schedule before that promotion is the old deployed harness, not evidence that
the branch fix failed.

After the gate passes, copy the relevant command output and canary evidence into
a candidate manifest based on `docs/release-manifests/TEMPLATE.md`. The
`env_fingerprint` emitted by `.github/render-env-sync.sh release-config-audit`
remains the API/web environment fingerprint; record it as
`api_web_env_fingerprint` and keep the raw script output for traceability. The
workflow proof is recorded separately as `workflow_env_fingerprint` and
`workflow_env_status`. The workflow env proof must show
`workflow_env_status=ready`, `ARGUS_MARKET_DATA_PROVIDER_MODE=live_provider`,
redacted-present required workflow secrets,
`workflow_runtime_provider_mode=live_provider`, and
`workflow_runtime_proof=ready` before tester exposure. The manifest must also
name the candidate SHA, deployed API/web SHAs, `workflow_task`,
`real_workflow_task`, backtest service mode, workflow-service proof for
`argus-backtests`, canary evidence, rollback target, and approver.

The stale job scan is an operator-run step. It is not a deployed release
surface, and nothing runs it automatically.

**Destructive ops jobs refuse to guess their target.** `DATABASE_URL`,
`SUPABASE_URL` (or `SUPABASE_PROJECT_URL`), and `SUPABASE_SERVICE_ROLE_KEY`
must be set explicitly in the process environment. Dotenv discovery is disabled,
so a job with none of them set exits 2 rather than resolving whatever `.env`
happens to sit above it. Each job prints the resolved database and Supabase host,
without credentials, before doing anything destructive; read that line and
confirm it is the environment you meant.

```bash
DATABASE_URL=… SUPABASE_URL=… SUPABASE_SERVICE_ROLE_KEY=… \
  .github/stale-backtest-jobs.sh --json
```

For privacy-safe aggregate job health over the existing Supabase
`backtest_jobs.execution_metadata` records:

```bash
poetry run python scripts/ops/alpha_readiness_metrics.py --json
```

This report is operational only. It summarizes job statuses, readout provenance,
and timings without emitting user ids, conversation ids, prompt text, or product
analytics events.

## Backtest Workflow Modes

The permanent Render Workflow service is `argus-backtests`. It owns multiple
tasks:

- `argus-backtests/workflow_proof`: proof/canary task for API -> Render Workflow
  -> Supabase lifecycle validation.
- `argus-backtests/run_backtest_job`: real backtest execution task.

Use explicit API modes instead of editing individual flags by hand:

```bash
.github/render-env-sync.sh api-safe-off
.github/render-env-sync.sh api-proof-shadow-on
.github/render-env-sync.sh api-real-workflow-on
```

`api-real-workflow-on` is the controlled private-alpha validation mode: `Run
backtest` creates a durable real job and the UI reads queued/running/succeeded/
failed state from Supabase. `api-proof-shadow-on` is only for proof dispatch
validation. `api-safe-off` is the emergency rollback mode that disables workflow
dispatch/execution and removes the Render API key from `argus-api`.

### Retrieving workflow task logs

Use the workflow ID as `resource` and the run ID as the separate `taskRun`
filter. A `trn-...` ID is not a log resource: that call returned HTTP 500 in
the [issue #484 production probe](reports/evidence/484/README.md). The same
run returned HTTP 200 with logs using the correct filter. This is a call-pattern
problem, not a current Render limitation; no duplicate log store is needed.

The read-only query below follows Render's [List logs API](https://api-docs.render.com/reference/list-logs).
Set the workspace, workflow, and task-run IDs from Render. Choose explicit UTC
bounds around the run's `startedAt` and `completedAt` from
`GET /v1/task-runs/{taskRunId}`; for a running task use the current time as the
end. The default one-hour window can miss an older run entirely.

```bash
curl --fail-with-body --silent --show-error --get \
  'https://api.render.com/v1/logs' \
  --header "Authorization: Bearer ${RENDER_API_KEY}" \
  --data-urlencode "ownerId=${RENDER_OWNER_ID}" \
  --data-urlencode "resource=${RENDER_WORKFLOW_ID}" \
  --data-urlencode "taskRun=${RENDER_TASK_RUN_ID}" \
  --data-urlencode "startTime=${TASK_LOG_START_UTC}" \
  --data-urlencode "endTime=${TASK_LOG_END_UTC}" \
  --data-urlencode 'direction=forward' \
  --data-urlencode 'limit=100'
```

Read the `logs` array from the response object. When `hasMore` is true, repeat
with `nextStartTime` and `nextEndTime` as the next bounds until it is false.
An HTTP failure or a null response is not an empty log result. For no matching
lines, check the owner, workflow, run, time window, and retention first.
The job's `execution_metadata.workflow_backtest` remains durable execution
evidence when a task crashes or its logs have expired.

## Render Environment Ownership

`render.yaml` is allowed to sync non-secret launch configuration: mode flags,
public service URLs, public Supabase URL/anon key values, feature flags, paper
trading mode, CORS origins, and model routing IDs.

Both `argus-app` and `argus-api` must set the server-only `ARGUS_APP_ORIGIN` to
the exact HTTPS app origin. The web service uses it for password-recovery
redirects; the API uses it for approval signup links. It must never use a
`NEXT_PUBLIC_` name. Local development may use the documented localhost
origins; production must not use HTTP.

### Auth Email Deliverability

Supabase Auth sends transactional email as `noreply@get-argus.com` through
Resend. Cloudflare DNS must keep one SPF record at the root,
`v=spf1 include:_spf.mx.cloudflare.net ~all`, for inbound
`support@get-argus.com` forwarding, while Resend's verified custom MAIL FROM
uses `send.get-argus.com` with `v=spf1 include:amazonses.com ~all` for outbound
SPF; DKIM at `resend._domainkey.get-argus.com` authenticates Resend's signature;
and DMARC at `_dmarc.get-argus.com` monitors strict alignment with aggregate
reports sent to `support@get-argus.com`. Start DMARC at `p=none`; after one week
of clean aggregate reports, moving it to `p=quarantine` is a founder decision.
Supabase Authentication URL Configuration must set Site URL to
`https://arguschat.ai` and allow the exact recovery redirects
`https://arguschat.ai/auth/recovery` and
`https://argus-app-suz5.onrender.com/auth/recovery`; keep the Render origin
during the transition, because an unlisted redirect silently falls back to Site
URL instead of returning an error.

### Requested Access Promotion

Promote an active `requested` row only through the ops route owned by
`ACCESS_REQUEST_APPROVE_PATH` in `src/argus/api/ops_contract.py`,
`POST /internal/access-requests/approve`. Never PATCH
`private_alpha_allowlist.role` to `user` directly. The protected operation sends
the localized access welcome, records the provider-accepted delivery, and then
activates access through the database completion boundary. This is the only
human promotion command:

```bash
(
set -euo pipefail
source .github/argus-env.sh
argus_load_root_env >/dev/null || true
REQUESTED_EMAIL="<requested email>"
OPS_CURL_CONFIG="$(mktemp)"
APPROVAL_REQUEST="$(mktemp)"
APPROVAL_RESPONSE="$(mktemp)"
trap 'rm -f "$OPS_CURL_CONFIG" "$APPROVAL_REQUEST" "$APPROVAL_RESPONSE"' EXIT
chmod 600 "$OPS_CURL_CONFIG" "$APPROVAL_REQUEST" "$APPROVAL_RESPONSE"
printf 'header = "Authorization: Bearer %s"\n' "$ARGUS_OPS_TOKEN" > "$OPS_CURL_CONFIG"
REQUESTED_EMAIL="$REQUESTED_EMAIL" python3 - "$APPROVAL_REQUEST" <<'PY'
import json
import os
import pathlib
import sys

email = os.environ["REQUESTED_EMAIL"].strip().casefold()
pathlib.Path(sys.argv[1]).write_text(
    json.dumps({"email": email}, separators=(",", ":")),
    encoding="utf-8",
)
PY
APPROVE_PATH="$(python3 -c 'import sys; sys.path.insert(0, "src"); from argus.api.ops_contract import ACCESS_REQUEST_APPROVE_PATH; print(ACCESS_REQUEST_APPROVE_PATH)')"
curl -q --fail --silent --show-error \
  --config "$OPS_CURL_CONFIG" \
  -X POST \
  -H "Content-Type: application/json" \
  --data-binary "@$APPROVAL_REQUEST" \
  "${ARGUS_PRIVATE_LAUNCH_API_URL}${APPROVE_PATH}" \
  > "$APPROVAL_RESPONSE"
python3 - "$APPROVAL_RESPONSE" <<'PY'
import json
import pathlib
import sys

try:
    payload = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError) as exc:
    raise SystemExit("access request promotion returned an invalid response") from exc
if (
    not isinstance(payload, dict)
    or set(payload) != {"approved"}
    or payload["approved"] is not True
):
    raise SystemExit("access request promotion was not approved")
PY
)
```

Success is exactly `{"approved":true}`. Missing or invalid ops authorization
remains route-indistinguishable `404`. Missing configuration, ineligible state,
email-provider failure, delivery persistence failure, and completion failure
remain generic errors. Do not expose provider detail or infer approval from an
error response.

Support may read only the private
`private_alpha_access_welcome_deliveries` record through existing privileged
operational access. Its support-readable fields are `recipient_email`,
`language`, `content_version`, `subject`, `provider_receipt`, `sent_at`, and
`created_at`. Browser roles have no access to this table. The record is delivery
evidence; the guarded completion operation remains access truth.

**Consent scope: transactional only.** The requested access grant does not
authorize product updates, tips, re-engagement, follow-up mail, broadcasts,
campaigns, onboarding sequences, or any other marketing email.

Keep true secrets manual in Render:

- `DATABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `SUPABASE_JWT_SECRET`
- `OPENROUTER_API_KEY`
- `ALPACA_API_KEY`
- `ALPACA_SECRET_KEY`
- `ARGUS_OPS_TOKEN`
- `ARGUS_APPROVAL_EMAIL_SMTP_PASSWORD`
- `POSTHOG_PROJECT_TOKEN`
- `PERPLEXITY_API_KEY`
- `ARGUS_VISITOR_KEY_SECRET`

Keep `NEXT_PUBLIC_POSTHOG_KEY` present but empty. Product analytics capture is
server-side only through the sanitized observability envelope.

Set `POSTHOG_REGION="US Cloud"` (or normalized `us`) for US Cloud unless the
founder explicitly changes the analytics data-region posture. US Cloud is a
compliance-posture choice for the current private alpha, not an accidental
default. Do not enable frontend PostHog, autocapture, session replay, or person
profiles.

Set `ARGUS_OPS_TOKEN` manually in Render for `argus-api`; it is intentionally
`sync: false`. Keep `ARGUS_OPS_TOKEN` out of frontend environment variables.

## Operator-Run Maintenance

Maintenance is not a Render service and is not part of the deployed release
topology. An operator runs the retained entry point from a laptop against an
explicit target:

```bash
poetry run python scripts/ops/scheduled_maintenance.py
```

That pass runs guest workspace retention first, then stale and stranded
backtest job reconciliation, expired access-welcome claims, and the account
deletion sweep (`scripts/ops/resume_account_deletions.py`). Every job runs even
when an earlier one fails, so one failure never hides another. The retention
windows in `DATA_MODEL.md` hold only as often as an operator runs this command.

### Account deletion runs (Lane 6)

The account deletion sweep resumes runs still waiting on a third party (Apple,
Plaid, Gmail, PostHog). Those accounts are locked meanwhile (signed out, every
route but `POST /account/delete` refuses them) and their auth delete waits, so
they finish only when the person retries or an operator runs this pass. Nothing
runs it on a schedule: retries stay manual (this operator-run sweep, no cron),
as Lucas decided at 2:04 AM CT on Oct 3, 2026, to be revisited before an
external beta. **Cadence: while any run is in flight, run
`scheduled_maintenance.py` at least daily.** To see whether any is:

```sql
select status, count(*), min(created_at)
  from argus_private.account_deletion_runs
 where status <> 'done'
 group by status;
```

`--deletion-limit` (1-100, default 25) bounds how many runs one pass resumes,
apart from `--guest-limit`. The sweep prints
`resumed`/`done`/`pending`/`failed`/`busy`: `pending` is a step still owed,
`busy` a run another pass or request holds right now (left alone), and `failed`
exits nonzero. To revoke, the operator process also needs
`ARGUS_INGESTION_SECRET_KEY`, the `PLAID_*` keys and the `ARGUS_APPLE_*` keys;
without them those revocations stay pending, never done.

What the logs and run record tell you:

- **The key check.** Every stored token carries the fingerprint of the key
  that sealed it (`secret_key_fingerprint`, non-secret). A token that won't
  open is discarded as `unrecoverable` (or Apple's through
  `discard_unreadable`) only when its fingerprint is this process's
  `ARGUS_INGESTION_SECRET_KEY`'s: that key sealed it and can't open it.
  `key_unproven` in `steps.last_error` means another key sealed it (a rolling
  rotation, a stale environment) or it predates Lane 6 and has no
  fingerprint; `key_unavailable` means this process has no key. Nothing was
  dropped: rerun from a process with the key that sealed it. A token sealed
  under a key no process holds any more stays pending; after 7 days force it
  (below), which tries one more revoke first.
- **Key rotation.** Don't rotate `ARGUS_INGESTION_SECRET_KEY` in the deploy
  that ships the Lane 6 migration (`20261004090000`), or while any pre-Lane 6
  process can still run, including a rollback. Older writers can re-seal a
  token without updating its fingerprint. Keep the key unchanged through that
  deployment and its rollback window. Before a later rotation, verify that
  every running process and every permitted rollback writes the fingerprint
  with the ciphertext. Retain access to the old key for credentials it sealed.
  A newer process holds those credentials pending; it cannot revoke them
  without that key. Rotation does not complete their deletion.
- **Apple.** No stored credential records `apple_revoke: none` (nothing to
  revoke). `apple_unconfigured` means this process has no `ARGUS_APPLE_*`
  config: the step stays pending, never silently done. `already_revoked` means
  Apple says the token was already dead (the person removed the app).
- **The already_revoked spike.** Apple `invalid_grant`, Google
  `invalid_grant`/`invalid_token` and Plaid `ITEM_NOT_FOUND`/
  `INVALID_ACCESS_TOKEN` are recorded `already_revoked` and counted per run,
  with an `account_deletion.already_revoked` metric each. When 5 or more runs
  updated in the last 24 hours have seen one (any provider), the run logs
  `account_deletion.already_revoked_spike` (with the count): worth a look, a
  provider may be revoking grants on its own.
- **PostHog.** Only the API service's configuration decides whether the step
  is `not_applicable`, when the person's request opens the run. A sweep, a
  force run or a later retry never marks the step `not_applicable`, whatever
  its own environment holds. A step left pending stays pending and keeps its
  `analytics_evidence`.
  - `ARGUS_ANALYTICS_DELETION_ENABLED` on: the PostHog deletion adapter (#806)
    runs, whether or not `POSTHOG_PROJECT_TOKEN` is set.
  - Flag off and no `POSTHOG_PROJECT_TOKEN` on the API service: the server
    sends no PostHog events, so the run opens with
    `analytics: not_applicable` and
    `analytics_evidence.reason: posthog_not_configured` and can finish, never
    `deleted`
    ([decision 1B](specs/argus-decision-log.md#october-15-2026-account-deletion-analytics-step-without-posthog-events)).
    On October 15, 2026, a read-only check found no `POSTHOG_PROJECT_TOKEN`
    on the staging API service, no PostHog setting on the staging web
    service, and no client PostHog setup in the web or iOS code.
  - Flag off and the token set: outside tests and local dev the step stays
    pending (`analytics_adapter_unconfigured`) until the adapter deletes the
    events or an operator forces it (`operator_forced`). A no-token environment
    cannot force analytics complete: the step remains pending even with
    `--confirm`, until the adapter confirms deletion.

  A deployment that has ever sent events keeps them at PostHog after its
  token is removed. Turn on the deletion adapter there before removing the
  token. Don't turn on `ARGUS_ACCOUNT_DELETION_ENABLED` before #805
  (decision 17's closed-line balance), nor, on a deployment that sends
  PostHog events, before #806 closes.
- **The 7-day alert.** A step pending for 7 days logs
  `account_deletion.needs_operator` (with the step and its last error, no user
  id). Decide whether it can still finish. If it can't (Apple keeps answering
  `invalid_request` because the person removed the app, a provider is gone for
  good, a token sealed under a key nobody holds any more), force it. Run it
  first without `--confirm`: that is a dry run that prints the step, how many
  days it has waited and its last error, and changes nothing. Then add
  `--confirm`:
- **storage** (`account_deletion.storage_failing`, retained document sources,
  #778): fix Storage; the next resume finishes it; not forceable.

```bash
poetry run python scripts/ops/force_account_deletion_step.py \
  --user-id <uuid> --step apple|plaid|gmail|analytics \
  --reason "Apple invalid_request for 7 days; app removed" --operator <your name> \
  [--confirm]
```

It refuses a step pending for less than 7 days (`step_pending_under_7_days`)
or not pending at all (`step_not_pending`). With `--confirm`, an Apple, Plaid
or Gmail step first gets one more revoke attempt, recorded in the run like any
pass (`revoke_attempt` in the output); if that finishes the step nothing is
forced. A no-token analytics force run also stays pending and returns
`forced: false` until the adapter confirms deletion; missing configuration never
proves deletion. Otherwise it records the step `operator_forced` with the reason
and your name in the run record, which outlives the deletion, then resumes the
run. **The reason must
not contain personal data**: no name, email or account details (the script
refuses an `@`). There is no route for this. Get the user id from the support
request or the person's account, never from logs (they carry none).

The pass exits nonzero if any job fails, and prints a final JSON summary line
with `status`, `failed_count`, and `failed_jobs`. Alert on a nonzero exit or on
`"status": "degraded"`. Keep the per-job output: guest cleanup prints its
`selected`/`auth_deleted`/`auth_delete_failed`/`purge_failed` counts, and the
reconciler prints its scan report.

Provide `DATABASE_URL`, `SUPABASE_URL` or `SUPABASE_PROJECT_URL`,
`SUPABASE_SERVICE_ROLE_KEY`, and `RENDER_API_KEY` only in the operator process.
Do not copy production deletion credentials into CI. Record the command target,
timestamp, final summary line, and selected or purged counts in operator
evidence.

### Applying an approved migration list

`scripts/ops/apply_approved_migrations.py` applies an explicit, ordered list of
migration versions to a named database and records each ledger row the way
`production_migration_gate.py` reads it (the file's own version and name,
statements split by the gate's splitter). Use it where the Supabase CLI cannot:
production's ledger holds history the CLI would try to re-run or rewrite.
Versions at or below the gate's reconciliation threshold are never recorded; a
listed `--unrecorded` version runs without a ledger row.

Each file runs as one transaction. A file wrapped in `begin` and `commit` runs
as one transaction with the wrapper dropped from what runs and kept in the
ledger row. A file that commits inside itself runs as separate transactions only
when its version is passed with `--allow-mid-file-commit`; each committed
transaction is printed, and the ledger row joins the last one. `rollback` and
`savepoint` are refused, and so is a file with no runnable statement. Each
transaction sets `--lock-timeout` (default `5s`, at least 1) so a file that
cannot get its locks fails and rolls back. One run holds an advisory lock,
taken before the ledger is read.

It refuses any hosted Supabase host in any spelling (case, trailing dot, encoded
dots) on the URL, on every `--allow-host` and on the connected host, unless a
hosted approval record names that host (below). The target URL comes from an
environment variable (default `ARGUS_APPLY_DATABASE_URL`), never the command
line. The host and database must be named with `--allow-host` and
`--allow-database`; a DNS name also needs its resolved address on the list. A
name check cannot tell that an IP literal is a hosted database, so never
allow-list one. The default run only prints the plan; `--execute` applies it.
After a stop, everything printed as committed stays applied; recorded files show
in the ledger, but `--unrecorded` steps leave no trace, so take each reported one
out of the retry command.

**Unrecorded versions.** A version at or below the gate's reconciliation threshold
cannot be recorded without breaking the pinned hand-reconciled history, so it runs
with `--unrecorded` and leaves no ledger row. With no row, the ledger cannot stop a
repeat, so each such version has a read-only effect probe in the tool. Today there
is one: `20260505000001` (it widens `strategies_asset_class_check` and
`backtest_runs_asset_class_check` to allow `currency_pair`; its probe reads both
definitions with `pg_get_constraintdef`). The tool refuses an unrecorded version
that has no probe, refuses one whose effect is already present (before anything
runs, including in a dry run), and after the run checks the effect is visible. The
file is also idempotent, so a repeat would end in the same state, but the tool does
not rely on that.

**Hosted targets.** Pass `--hosted-approval <path>` with a JSON record under
`docs/release-manifests/` (the tool refuses any other path), committed on top of
the candidate commit, and `--ssl-root-cert <CA bundle>`. It has exactly these
keys: `id`, `project_ref`, `hosts`, `database`, `candidate_sha`,
`versions_sha256`, `issued_at`, `expires_at`, `approved_by`,
`approval_reference`. The tool refuses unless all of these hold:

- the file is a regular tracked file (not a symlink), unmodified, and committed
  after `--candidate-sha`; it is read from the committed blob;
- `candidate_sha` equals `--candidate-sha`;
- `versions_sha256` equals the digest of this exact run: the recorded versions,
  the `--unrecorded` ones and the `--allow-mid-file-commit` ones, each sorted.
  A different batch, or a retry with a different list after a stop, needs a new
  record;
- the record is valid now and for at most three days (ISO 8601 with a time zone);
- every `hosts` entry is the project's direct host `db.<ref>.supabase.co` or a
  Supabase pooler host; the target is one of them, names port 5432 in the URL
  and the live connection is on 5432 (a transaction pooler breaks the run lock), carries the project ref (direct host,
  or the pooler user `postgres.<ref>` exactly), and the database matches;
- the connection reaches a named host and database, and the server certificate
  is verified against `--ssl-root-cert` (verify-full, as the gate does).

`--execute` also needs `--hosted-confirm <id>` repeating the record's id. The
record is the founder's approval made reviewable. It does not authorize
anything by existing; the founder approves the run before it is committed. A
record never applies to a target that is not hosted. For a hosted target the
resolved address is not on any list; the verified certificate replaces that
check.

```bash
ARGUS_APPLY_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5432/rehearsal \
poetry run python scripts/ops/apply_approved_migrations.py \
  --candidate-sha "$(git rev-parse HEAD)" --approved-file approved.json \
  --allow-host 127.0.0.1 --allow-database rehearsal            # plan only
```

## Runtime Tuning Flags

These are optional runtime knobs (not secrets). Defaults are safe for
private-alpha launch; record any override in the release manifest.

- `ARGUS_ENABLE_EXECUTION_REALISM` — models trading fees + slippage end to end.
  The capability is active by default, but modeled costs remain opt-in per
  idea. Runs without stated fees or slippage stay idealized and retain the "No
  fees/slippage" assumptions footer. Set the flag explicitly to
  `false|0|off|no` only as a kill switch; that restores the pre-realism path
  byte-for-byte. Record any kill-switch override in the release manifest.
- `ARGUS_STRUCTURED_REASONING_EFFORT` / `ARGUS_CAPABILITY_REASONING_EFFORT` —
  per-tier OpenRouter reasoning-effort overrides for the structured
  interpretation and capability-conflict calls
  (`xhigh|high|medium|low|minimal|none`). Unset uses the profile default. Lower
  effort saves cost in dev; run production at full effort. Invalid values are
  ignored with a warning.
- Prompt caching is automatic: structured-artifact calls
  (interpretation/repair/field-fidelity/capability-conflict) send a stable
  prefix so OpenRouter can cache it. No env toggle; it activates for those tasks.
- `ARGUS_RUN_LIVE_EVALS=1` — runs the live eval suite under `tests/evals/` (real
  model spend). Unset/`0` keeps evals mocked. Set it for the pre-merge
  landing-gate run and every `main` promotion candidate.

### Live eval is a comparison, not a scoreboard

**Founder-locked 2026-08-13.** A red live eval does not by itself block a
promotion. The question a promotion asks is *"is this worse than what users
have right now"*, and a suite scored against frozen expectations cannot answer
it. Expectations drift as decisions land, so a failing check may be a
regression, a superseded expectation, or model variance, and the three are
indistinguishable from one run.

**Founder-locked 2026-08-21.** This eval gate is weak evidence regardless of
whether an aggregate count rule exists. It measures structured internals, and
it read green for weeks while all three seeded front-page chips were broken for
real users. Founder-overseen production browser acceptance is the stronger gate.
The release manifest's post-deploy checklist decides whether the promotion
succeeded.

So a red candidate run requires a **baseline run at the deployed production
SHA**, with identical provider modes, and the two are compared:

- **Candidate fails only what production already fails** → not a regression.
  Promote, and record every failure with its owner in the manifest.
- **Candidate fails anything production passes** → that is a regression.
  Do not promote.
- **Candidate passes what production fails** → an improvement, record it.

#### What a measurement stands for

**Enforced by `tests/promotion_evidence_identity.py` ([#608](https://github.com/lagarcess/argus/issues/608)).**
One rule decides whether evidence measured at one commit stands for another, and
every check asks it: the live eval scorecard for the candidate, the baseline for
the deployed build, and each side of a targeted A/B. Evidence measured at commit
A stands for commit B when nothing the measurement can reach differs between
them.

- **Reach fails closed.** Python loads code through imports, strings, plugins,
  warning filters and startup modules, more channels than a reader can list.
  So every Python file the eval process could import counts, tests and scripts
  included. So do the data files beside that code, the pytest configuration on
  the eval's path, and every file at the repository root, where the toolchain
  finds its configuration (`pyproject.toml`, `poetry.lock`, `.python-version`,
  `.coveragerc` and the like). The root exceptions are `render.yaml` and
  `.env.example`, which the release contract owns and the eval never reads (the
  harness refuses an `ARGUS_EVAL_ENV_FILE` that is, or passes through, a tracked
  file or tracked symlink), and documentation. Import roots come from the pytest and Poetry configuration,
  never from a list of product paths.
- **A change outside that keeps the code evidence:** `render.yaml`, `.env.example`,
  the release profile, migrations, frontend code, docs and evidence scripts.
  Release-profile models and on/off flags must also pass the configuration check below.
- **A change inside it needs a new measurement.** The gate names the changed
  files.
- **Measured models and flags must match the build.** Measurement scorecards
  use schema v3 and record `provenance.release_configuration`. Its keys derive
  from the API service in `.github/private-alpha-release-profile.json`: every
  `_MODEL` key and every setting whose contract value is `true` or `false`.
  The eval records runtime-resolved model IDs and flags from its own environment,
  then rechecks them before serialization. Set flags explicitly to `true` or
  `false`; an absent flag stays unknown and aliases are not treated as equivalent.
  The shared evidence-identity check compares those values with the release
  profile read from the build's commit, even when measured and build SHAs match.
  A mismatch names the key, measured value and contract value. Timeouts,
  allowances, other environment settings, and other services stay out of scope.
  Candidate, baseline and targeted A/B evidence all use this check against the
  build each side represents; a configuration-only change cannot skip baseline
  failure comparison. Targeted A/B documents carry the same provenance field.
  The fixed historical manifests listed in `tests/promotion_evidence_configuration.py`
  retain their original scorecards unchanged. New promotions require schema-v3
  measurement scorecards and configuration-bearing baseline/A/B evidence.
  This catches configuration mistakes, not deliberate evidence tampering.
  `tests/evals/README.md` still requires a live run after a model/provider change.
- **The manifest names both commits.** Beside the candidate or rollback SHA,
  name the SHA each piece of evidence measured whenever the two differ.

On 2026-09-13 a promotion turned sharing off after its full run. Between the
measured head `df7aee12` and the candidate `4fd587bf` only `render.yaml`, the
release profile and docs changed, yet the checks disagreed and forced a paid
re-measurement of unchanged eval code. That historical manifest retains its
scorecard under the explicit compatibility rule; new promotions must also pass
model and flag comparison:

```text
- Candidate SHA: `4fd587bf24ce39b794c2228d61f94693826d0da2`
- Live eval scorecard: `docs/reports/evidence/2026-09-12-main-promotion/candidate-eval-scorecard-df7aee12.json`
- Live eval measured SHA: `df7aee12955f667e31057464d62c72287fb12247`
```

#### A candidate-only PROSE failure is not a regression until both sides are measured

**Enforced 2026-09-03 by `tests/release_promotion_evidence_support.py`.** Voiced
prose is stochastic, so a single suite run can hand back a candidate-only prose
failure that no user would meet twice. Naming it in the manifest is not a
disposition, and the gate refuses one.

Measure the rate on both sides with a targeted interleaved A/B:

- one case, **ten rounds minimum**, baseline then candidate inside each round;
- one session, live provider on both sides;
- count occurrences of the specific defect, not the judge's verdict;
- reference both side documents in the manifest and record the two rates.

About ten minutes and **$0.20**, against $1.33 and half an hour for a suite
re-run that cannot answer the question anyway, because re-running gives you one
more sample of the same noise.

**Do not substitute a judge-only replay.** Replaying the recorded text through
the judge measures whether the *grader* is stable on that input. It cannot tell
you whether the candidate voices the defect more often than production, which
is the only thing a regression can mean. On 2026-09-03 the replay split 8 pass
/ 12 fail and a browser turn did not reproduce it; neither settled anything.
The A/B returned 0 of 10 on both sides and the promotion proceeded. On
2026-08-27 a judge-only replay was accepted in place of this measurement; that
manifest is grandfathered in the gate and named there as the reason the rule
exists.

The same method settled the disputed case on 2026-08-21. Reach for it before
building a theory.

Run the baseline from a detached worktree at `origin/main` so the candidate
tree is untouched, and commit both scorecards as durable evidence.

Why this rule exists: on 2026-08-13 a candidate carrying five user-visible
fixes was held by twelve failures that all turned out to live in code already
deployed. The gate was measuring the wrong thing. Twelve failures nobody had
reported were outranking five defects real users had hit.

The corollary is the more important half: **run the eval before merging**
anything that touches the interpreter or the edit spine, not only before
promoting. PR #431 shipped compound editing on 2026-08-11 without one. The
suite already contained the cases that would have caught it, and had scored
them 14/14 eight days earlier. That is [#498](https://github.com/lagarcess/argus/issues/498).

### What the run costs, measured

One full 60-case suite is **$1.33** and **29 minutes** (2026-08-14, `eaf5d52b`).
Confirmation-edit cases are the expensive ones at ~$0.05 each against a $0.022
mean, because they burn the tier-3 interpreter across multiple turns.

That price is low enough to gate on the full suite directly rather than
maintain a cheaper subset, so there are no coverage gaps to reason about.

**Two runs of the same commit produced identical failure sets**, 17 of 60, with
no case differing in either direction. Treat a single flipped case as signal
and re-run to confirm rather than assuming variance.

### Model-facing text is frozen against a scorecard

`tests/test_interpreter_prompt_freeze.py` fingerprints every piece of text the
interpretation model reads: prompt builders and Pydantic
`Field(description=...)` across the eval-reachable tree. It costs nothing and
runs in about a second, so it is the cheap layer that decides when the paid one
has to run.

Changing that text requires a live eval on the branch, its scorecard committed
under `docs/reports/evidence/`, a case-by-case comparison against the scorecard
named in `.agent/interpreter_prompt_fingerprint.json`, and a regenerated
fingerprint. Because the fingerprint is a single file recording one measured
state, **only one lane may hold this surface at a time**; two concurrent prompt
lanes conflict on it and neither measures the combined result.

Why this exists: PR #491 rewrote the shared prompt for a DCA change on
2026-08-14. Its own tests passed, CI went 6/6 green, and it regressed asset
extraction, start-date preservation, and discovery routing in three unrelated
places. No unit test sends a message through a model, so nothing but the paid
eval could have caught it, and that ran after the merge.

## Household and beta invite hosted gate

Before any hosted activation, generate a separate secret for that environment
with `openssl rand -base64 48`, as defined in
[Invite code security](API_CONTRACT.md#invite-code-security). Set
`ARGUS_INVITE_CODE_SECRET` on the API service in Render before the deploy that
applies destructive migration `20261003150100`. Keep the secret out of release
evidence and logs. That migration discards old unkeyed codes; existing links
remain valid. Follow the destructive-migration gate above, including the
maintenance window, backup/readback plan, and explicit founder approval.

Keep `ARGUS_HOUSEHOLDS_ENABLED`, `ARGUS_BETA_INVITES_ENABLED`, and
`ARGUS_BETA_INVITE_GATE_ENABLED` false until the secret is installed and the
approved migration deployment has passed readiness. Enable a flag only through
an explicit, reviewed hosted change.

Before enabling any of these flags, the operator must verify one API instance
and `WEB_CONCURRENCY=1` in the deployed Render configuration and record the
non-secret readback in the release manifest. The invite lookup counters live
in each API process; multiple instances or workers multiply the budgets.
If the worker or instance count cannot be confirmed, keep the flags off.
This local checklist does not authorize hosted configuration or migration work.

## Guest Staged Rollout

The operational security checklist for later internet-facing Guest exposure is
[Guest Public Launch Safety](GUEST_PUBLIC_LAUNCH_SAFETY.md). It is a promotion
and traffic-exposure gate, not a prerequisite for merging the Guest
implementation into the internal integration branch.

Product defaults:

```bash
ARGUS_GUEST_ACCESS_ENABLED=true
ARGUS_PUBLIC_ACCOUNT_ACCESS_ENABLED=true
NEXT_PUBLIC_GUEST_ACCESS_ENABLED=true
ARGUS_VISITOR_KEY_SECRET=<unique high-entropy environment secret>
ARGUS_DISCOVERY_GLOBAL_DAILY_CEILING=500
```

Guest access is part of the normal product shape. The two Guest flags are
default-on emergency kill switches; explicit `false` activates rollback. The
frontend flag controls presentation only and the API remains authoritative.
Public-account access is open as of 2026-08-12: permanent signup and login
admit any email without an explicitly disabled allowlist row, the guest surface
offers account creation, and existing admin/developer behavior is unchanged
because opening the gate grants no role. That third flag is the one that fails
closed when unset, so it must be set explicitly on every service that reads it;
omitting it denies registration rather than opening it.

Staging uses Cloudflare Turnstile test keys: the always-pass site key in
`NEXT_PUBLIC_CUADRAO_TURNSTILE_SITE_KEY` (the Cuadrao name; the Argus name
`NEXT_PUBLIC_ARGUS_TURNSTILE_SITE_KEY` is only a fallback in `web/lib/public-env.ts`)
and Supabase's staging CAPTCHA test secret. Production must refuse them. Before a
production promotion, confirm the site key does not start with `1x0000` and the
CAPTCHA secret does not start with `1x0000` or `2x0000`. Those are Cloudflare's
published test patterns. A search of `web`, `src` and `scripts` found no code that
rejects them, so this is a manual release check, recorded in the release manifest.

Hosted Supabase prerequisites are external operations and must be recorded in
the release manifest: anonymous Auth enabled, approved CAPTCHA configuration,
`NEXT_PUBLIC_CUADRAO_TURNSTILE_SITE_KEY` present in the web build, provider
anonymous-sign-in limits, Argus origin enforcement and per-IP attempt limits,
no direct anonymous-role access to product tables, migrations applied through
`20260727230000_add_visitor_usage_counters.sql`, and a founder-approved
`ARGUS_DISCOVERY_GLOBAL_DAILY_CEILING`. Generate a unique
`ARGUS_VISITOR_KEY_SECRET` for each deployed environment so visitor identifiers
remain opaque and cannot be correlated across environments. Without the public
site key, non-loopback production preserves the auth landing rather than
beginning an unusable Guest bootstrap. Do not mutate hosted Auth configuration
as part of a code promotion.

Guest cleanup is an operator-run step, and nothing runs this deletion
automatically. The at-least-daily floor is an operator's responsibility, and the
retention windows in `DATA_MODEL.md` hold exactly as often as someone runs the
command below.

To inspect what the next scheduled pass would select, without deleting:

```bash
DATABASE_URL=… SUPABASE_URL=… SUPABASE_SERVICE_ROLE_KEY=… \
  poetry run python scripts/ops/cleanup_expired_guest_workspaces.py --dry-run --limit 25
```

Run the deleting form by hand only to drain a backlog faster than the schedule,
and only against an environment you intend to delete rows in:

```bash
DATABASE_URL=… SUPABASE_URL=… SUPABASE_SERVICE_ROLE_KEY=… \
  poetry run python scripts/ops/cleanup_expired_guest_workspaces.py --limit 25
```

Record the selected/deleted/preserved/failed counts and oldest eligible expiry
in the release manifest. A nonzero `auth_delete_failed` result or a failed
cleanup transaction must alert and retry; never compensate by deleting product
rows manually.

The same run is the retention boundary for the visitor-keyed tables, which are
deliberately not foreign-key bound and so have no owner to cascade from. It
reports `visitor_usage_purged`, `funnel_milestones_purged`, and `purge_failed`.
A nonzero `purge_failed` also exits nonzero and must alert: while it persists,
IP-derived visitor digests are being retained past their stated window. A dry
run deletes nothing and always reports zero for all three. Product deletion, anonymous-identity
revalidation, and Auth-row deletion are one database transaction. Claimed
source identities use a fifteen-minute reconciliation grace; incomplete
bootstrap identities use five minutes.

Conversion safety is non-negotiable: new accounts use ordinary signup to create
a different permanent Auth identity, then claim the complete guest graph
through the workspace-lifetime, email-hash-bound handoff. Existing accounts use
the short-lived handoff that login claims before returning a permanent session.
Guest usage never merges into registered hour/day counters. Cleanup
re-verifies anonymous source truth and must not delete a permanent account or
the transferred graph.

Product analytics reach PostHog only through the closed wave 1 event registry
(`docs/DATA_MODEL.md` section 12.1.1); the earlier guest funnel events and the
browser `POST /api/v1/analytics/guest-events` relay were removed in SPEC 0
package 0C-1. PostHog keys, autocapture, session replay, prompts, assistant
prose, amounts, exact capital/dates, email, Auth material, private
titles/previews, provider/model names, and raw transcripts stay out.

Rollback order:

1. set `NEXT_PUBLIC_GUEST_ACCESS_ENABLED=false`;
2. set `ARGUS_GUEST_ACCESS_ENABLED=false`;
3. leave `ARGUS_PUBLIC_ACCOUNT_ACCESS_ENABLED=true` untouched, because rolling
   guest access back does not close public registration;
4. verify the preserved centered auth landing path;
5. stop new guest creation while retaining existing rows for safe expiry,
   conversion, or bounded cleanup.

Step 2 is a drain, not an active-session kill switch: already-verified guests
remain usable until their fixed policy boundary.

Do not roll back by reversing migrations or deleting anonymous users in bulk.
Authentication continues to land both guest and registered identities directly
in ordinary chat. Guest behavior differs through verified identity,
persistence, allowances, and conversion policy, not through onboarding.

### Paid waitlist rollback controls

The live `argus-api` plan is `standard`. The live `argus-app` plan is
`starter`. The requested-role migration and access-request exposure are
complete after the paid-plan readback and maintenance/private-health probes in
`docs/release-evidence/public-alpha-readiness.md`. Public account creation is
open: the founder set `ARGUS_PUBLIC_ACCOUNT_ACCESS_ENABLED=true` live on
2026-08-12, recorded in
`docs/release-manifests/2026-08-12-main-production-promotion-716221f.md`, so
anyone may register and the allowlist blocks only explicitly disabled rows.
The evidence records the paid API instance type plus the maintenance and
private/SSH/local verification controls.

The paid controls must remain available for rollback. If any control becomes
unavailable, rollback below `061ba50e` remains forbidden until the maintenance,
quiescence, and private route-absence proof can be completed.

### Waitlist rollback floor

The durable waitlist rollback procedure is
`docs/release-evidence/public-alpha-readiness.md`. Commit `061ba50e` is the
fail-closed floor while the schema can contain active `requested` rows. Prefer
a forward fix. Before any authorized rollback below that commit:

1. read back `serviceDetails.maintenanceMode.enabled=true` out of band and
   require the exact maintenance status and page fingerprint on every
   configured custom domain and on the `argus-app` onrender URL. After
   `argus-api`'s `renderSubdomainPolicy: disabled` is applied,
   `https://argus-ohr5.onrender.com` must return HTTP `404` and is not a
   maintenance probe surface;
2. complete a same-SHA restart and prove Render's old-instance shutdown/drain
   finished with no pre-maintenance worker left;
3. only then take the `ACCESS EXCLUSIVE` lock, disable active requested rows,
   read back and assert zero, then commit;
4. deploy under maintenance and verify the exact rollback SHA from Render
   metadata;
5. require a private invalid-body route-absence probe to return HTTP `404`;
6. re-verify the maintenance configuration and response signature;
7. disable maintenance last, then require the public invalid-body readback to
   return HTTP `404` on every public API surface.

Never front the API with a Cloudflare Worker in the `arguschat.ai` zone.
Worker subrequests rewrite `CF-Connecting-IP` to a single Cloudflare IPv6
and would collapse every guest into one rate-limit bucket.

The API `renderSubdomainPolicy` takes effect only when Blueprint or
dashboard settings are applied at the next `main` promotion, together with
#674. Autodeploy is off, so merging this field does not change live
routing by itself. The checked-in Blueprint field and its contract test
declare intent only; `release-config-audit` does not read this setting
back. When that promotion applies the policy, require live proof before
calling the hostname hygiene done: either a control-plane readback of
`serviceDetails.renderSubdomainPolicy=disabled` on `argus-api`, or a
public `GET https://argus-ohr5.onrender.com/health` that returns HTTP
`404`. That live proof is promotion-ceremony evidence, not a substitute
for the #694 forged-header test that owns IP-trust verification.

Generic error statuses are not maintenance proof. If control-plane state,
response fingerprint, restart drain, exact SHA, or a private verification
surface cannot be verified, rollback below the floor is forbidden; stop and
forward-fix. Never execute the production cleanup SQL during local repository
verification.

## Smoke Test

Use an allowlisted account and verify:

- Login succeeds.
- A new conversation can be created.
- Cold-start starter chips are visible, feel current, and do not reference 2024
  by default.
- Clicking a cold-start starter chip submits a natural-language prompt into the
  normal chat runtime.
- A Spanish prompt reaches confirmation without coaching or manual translation.
- The confirmation card shows exactly three card-scoped, structured actions:
  - `Run backtest` starts the supported job path.
  - `Change assumptions` is the single editing entry point. Single-field and
    compound edits preserve every explicit assumption the user did not change.
  - `Cancel` marks the draft canceled and removes the executable action.
- `Change dates` and `Change asset` do not render as separate actions.
- With `ARGUS_IN_PLACE_CARD_EDITS_ENABLED=false`, the capital and dates drawers
  do not render. Capital and date changes continue through the conversational
  `Change assumptions` path.
- A supported backtest completes and shows a result card.
- The result includes a readable Quick take.
- Explain result opens a deeper card-scoped explanation without replacing the
  Quick take.
- Retry preserves the failed setup and recovers through a structured action, not
  duplicated user text.
- Reloading the page preserves the conversation, job state, and result.
- Feedback can be submitted.

## Founder-Facing Tester Notes

Before sending the URL, make sure tester instructions say:

- Argus Alpha provides educational historical simulations only, not investment,
  tax, legal, brokerage, or execution advice.
- Alpha backtests are intentionally narrow: same-asset runs only, long-only,
  equal-weight multi-symbol logic, max 5 symbols, and daily bars.
- Market or benchmark data can be unavailable. If that happens, retry the same
  setup, change the dates, or choose a different supported asset/benchmark.
- Feedback buttons and the feedback dialog are the primary first-session
  listening channel. PostHog is limited to the approved server-side product
  events and must not receive raw prompts, credentials, balances, holdings,
  audio, route receipts, provider/model metadata, or frontend session data.
- Terms, Privacy Policy, and explicit alpha consent remain a founder-owned gate
  before inviting users outside the private circle.

## Supabase Persistence Check

Before the smoke test, capture current counts:

```sql
select
  (select count(*) from public.conversations) as conversations_total,
  (select count(*) from public.messages) as messages_total,
  (select count(*) from public.backtest_runs) as backtest_runs_total,
  (select count(*) from public.route_receipts where run_id is not null) as run_receipts_total,
  (select count(*) from public.feedback) as feedback_total;
```

After the smoke test, run the same query. A completed backtest should increase
`backtest_runs_total`, and the related route receipts should include a `run_id`.

## Data Cleanup Boundary

Do not delete Supabase profiles, conversations, messages, runs, or receipts as
part of the launch deploy. Cleanup should be a separate task with a dry-run count
and explicit deletion criteria.
