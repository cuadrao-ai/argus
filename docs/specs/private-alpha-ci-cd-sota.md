# Private Alpha CI/CD SOTA Plan

Status: Completed release-discipline reference
Date: 2026-06-17
Branch: `codex/private-alpha-next`
Audience: Founder, Codex, reviewers, release-captains

This document is the release-discipline reference for
`codex/private-alpha-next`. It owns smoke/canary/release-manifest expectations,
Render validation posture, and deployment discipline. It no longer owns the
Private Alpha Next product roadmap.

For current product ownership, use
[documentation authority](../DOCUMENTATION_AUTHORITY.md). Build only the
explicitly assigned package; historical roadmap and memo references do not
assign work or override the approved MVEE experience.

Implementation note: the release gate now centers on local smoke, exact-candidate
production migration parity before deploy, Render release-config audit, live
API/web deploy SHA checks, workflow version and env parity proof, an
authoritative Spanish release canary, and a per-candidate release manifest.
The Spanish journey proves the real workflow, finalized evidence/result metadata,
decision-note hydration, Omnisearch provenance, and deployed signup/login UI.
Keep this document as the release gate contract whenever a candidate is
validated on the private-alpha surface or later considered for tester-facing
deployment.

## 2026-07-14 Validated Private-Alpha Checkpoint

Candidate `373d1a12dd5f538a81150b20903f4f43db27c639` passed the full release
gate on the branch-deployed private-alpha Render validation surface. Its durable
record is
[`2026-07-14-private-alpha-release-integrity.md`](../release-manifests/2026-07-14-private-alpha-release-integrity.md)
and the live closure evidence is [issue #197](https://github.com/lagarcess/argus/issues/197#issuecomment-4965556704).
This checkpoint validates the existing private-alpha surface only: it is not a
`main` merge, production deployment, automatic production deployment, founder
approval, tester invitation, or tester exposure.

Local runtime proof doctrine:

- Python is pinned by `.python-version` (`3.10.x`; currently `3.10.20`), and
  `.github/setup.sh` enforces that runtime. A green run on Python 3.14 is not
  evidence for the deployed runtime.
- Create worktrees as siblings of the repo, never nested inside another Argus
  checkout. Nested worktrees can inherit the parent `.env` through dotenv upward
  search and silently convert mocked runs into live calls.
- Deterministic agent-runtime sweeps use
  `ARGUS_MARKET_DATA_PROVIDER_MODE=synthetic_unit_fixture` with live provider
  keys absent or blank. A mocked sweep should finish in seconds; minutes means
  stop and investigate credential leakage or live provider paths.

Issue #124 tightened the gate after `argus-api` and `argus-app` were aligned to
a candidate SHA while `argus-backtests` could still run with an effective dev
provider mode. For tester-facing releases, deploy status alone is insufficient:
the release captain must also prove the `argus-backtests` workflow env reports
`ARGUS_MARKET_DATA_PROVIDER_MODE=live_provider`, all required workflow secrets
are present only as redacted proof, `workflow_proof` confirms the effective
runtime with `workflow_runtime_provider_mode=live_provider` and
`workflow_runtime_proof=ready`, and the authoritative Spanish release journey
executes a real live-provider backtest before promotion.

## Purpose

This spec defines the long-term release and validation system Argus needs to
avoid the failure modes surfaced during the private-alpha branch deploy and
issue #117.

The goal is not merely to fix one bug. The goal is to establish a release
system where:

- branch state, deploy state, runtime env state, and feature-flag state are
  visible and checked together;
- private-alpha testing can happen on an internet-reachable surface without
  exposing users to unverified behavior;
- language support, runtime mode, and workflow mode are part of the release
  contract, not informal knowledge;
- a reload cannot resurrect contradictory chat state after a stream failure;
- the path from `codex/private-alpha-next` to `main` is explicit and safe.

## What Broke

Issue #117 exposed a multi-layer drift, not a single bug:

1. A supported user prompt was treated as slow/unstable enough to exceed the
   visible stream contract.
2. The UI rendered a generic failure state, which encouraged a retry.
3. The backend later completed interpretation/confirmation and persisted a
   successful artifact for the same logical request.
4. On refresh, the transcript hydrated into a contradictory state: the failure
   text remained, the duplicate retry remained, and the completed artifact
   appeared below it.
5. The live private-alpha deploy was internet-reachable before the work was in
   `main`, which made the branch act like a public staging surface without a
   disciplined promotion boundary.
6. The current runtime/env management relies on a mix of `render.yaml`,
   `render-env-sync.sh`, manual Render changes, and repo defaults, which makes
   it hard to prove what the service is actually running.

## Root Cause Summary

### Issue #117

The proximate root cause is an ownership gap between stream failure handling,
runtime completion, and hydration.

- The API stream can time out or fall back slowly while still allowing the
  runtime to complete later.
- The frontend can decide the stream has failed and show a generic retry state
  before the backend has finished reconciling the turn.
- On reload, persisted conversation/messages/artifact state can hydrate from a
  later successful path without reconciling the earlier failure surface.

That creates a broken user story:

- failure message
- duplicate user retry
- late completed artifact

This is not PR-ready behavior because it violates conversation trust.

### Release-Process Drift

The branch/deploy process also drifted from a SOTA approach:

- `render.yaml` still points at `main`, but private-alpha validation was being
  performed on manually deployed branch commits.
- Render environment state is partially documented in repo scripts and partially
  synchronized manually.
- The current release path checks deploy commit and warmup, but not all effective
  env/feature/runtime modes as a single contract.
- Spanish support was enabled/assumed inconsistently, revealing that locale is a
  product behavior dimension, not just a translation file concern.

## Target State

The long-term target is a promotion-based system with explicit release
contracts.

### Current Service Topology

The stable target topology is three live services:

- `argus-app`: web surface
- `argus-api`: chat/runtime/orchestration surface
- `argus-backtests`: workflow execution surface

Render Blueprints declare the API and web services, but do not support Workflow
services. `argus-backtests` is therefore guaranteed by the explicit workflow
runtime sync, release, and version-status checks in
`docs/PRIVATE_LAUNCH_RUNBOOK.md`. All three Git-linked services share one
autodeploy trigger, `off`, because deploys are manual. Enabling autodeploy for
only API and web would increase workflow skew.
Workflow deploy proof comes from the ready Render version id and its Git commit
prefix, not from mutable env markers that an automatic release cannot refresh.

Guest retention and stale-job reconciliation remain operator-run jobs through
`scripts/ops/scheduled_maintenance.py`. They are not a fourth deployed release
surface.

The workflow surface has two explicit tasks, not two separate services:

- `argus-backtests/workflow_proof`
- `argus-backtests/run_backtest_job`

Use the proof task when:

- validating the dispatch path end to end
- warming or smoke-testing workflow wiring
- proving queue/job persistence without exposing real execution

Use the real task when:

- a tester intentionally presses `Run backtest`
- the release manifest says the deploy is in real workflow mode
- the warmup/canary gate has already verified the proof path and live env

Do not introduce a new workflow service unless a future decision proves that the
proof and real paths need separate isolation boundaries, queues, or
permissions.

### Environment Topology

- `main`: the clean release checkpoint and the normal production promotion
  source.
- `codex/private-alpha-next`: integration staging branch only.
- `staging`: the internet-reachable validation surface, with controlled config
  and no automatic promotion to production.
- `private-alpha validation`: the branch-deployed private-alpha Render
  validation surface. It uses production-grade release discipline, but it is
  not production and does not imply tester exposure or automatic promotion.
- production: only receives promoted `main` releases or equivalent tagged
  release artifacts.

### Contract Layers

Release readiness should be checked at five layers together:

1. Commit layer: what SHA is deployed?
2. Schema layer: does production's migration ledger match that exact candidate?
3. Runtime layer: what mode is the service actually running in?
4. Locale/feature layer: what user-visible surfaces are enabled?
5. Behavior layer: do canaries and reloads preserve the right artifact lifecycle?

### Ownership Rules

- Render/CI/CD config is owned by Codex release-captains, not left to ad hoc
  manual toggles.
- Locale enablement is part of release scope, not hidden UI debt.
- Runtime mode flags are part of the release contract, not optional tuning.
- Frontend hydration must not invent or merge backend facts; it only renders
  canonical state.
- Every promoted release should have a release manifest containing commit SHA,
  expected env fingerprint, flag state, canary matrix, rollback target, and a
  go/no-go decision record.
- The backtest workflow task choice is part of the release manifest and must be
  explicit for each environment.

### Promotion Path

Use the following progression when moving from integration to `main`.
The ordered Cuadrao staging-to-production checklist, including the current
migration inventory and production env gates, is the launch runbook section
[Cuadrao production promotion](../PRIVATE_LAUNCH_RUNBOOK.md#cuadrao-production-promotion).
This progression is the commit, schema, and deploy discipline that checklist follows.

1. Develop on a focused `codex/private-alpha-next` slice.
2. Validate on the staging/private-alpha surface with the proof workflow task.
3. Select and record the target environment, intended config contract, and
   landing method without syncing or changing the live environment. If the
   landing method cannot preserve one pre-gated commit SHA, keep all three live
   autodeploy triggers manual until the landed commit is gated.
4. Create or resolve the exact would-be `main` promotion commit from current
   `main` and the approved integration tree without publishing it. This must be
   the immutable commit that will land and deploy, not merely the worker or
   integration head. Record its SHA and parents. Any rebase, squash, conflict
   edit, new merge, or concurrent target-branch change invalidates it.
5. Check out that exact promotion commit and run the read-only production
   migration gate before any service deploy. Supply the production Postgres URL
   explicitly from the operator secret store; the gate does not discover dotenv
   files. Use a query- and fragment-free URI; the gate rejects libpq connection
   parameters that could override the validated host or user. Supply the
   current production Supabase root CA by absolute path. The gate forces
   `sslmode=verify-full`, disables alternate GSS transport selection, and never
   falls back to plaintext.

   ```bash
   export ARGUS_PRODUCTION_DATABASE_URL="<production direct or session-pooler URL>"
   export ARGUS_PRODUCTION_DATABASE_SSL_ROOT_CERT="<absolute path to production Supabase CA>"
   ARGUS_CANDIDATE_SHA="$(git rev-parse HEAD)"
   poetry run python scripts/ops/production_migration_gate.py \
     --candidate-sha "$ARGUS_CANDIDATE_SHA" \
     --output temp/release-evidence/production-migration-gate.json
   ```

   Inspect the report's full candidate, applied, missing, unexpected,
   name-drift, and content-drift lists. Candidate and applied records include
   statement counts and statement-array SHA-256 digests derived from Supabase's
   ledger format. `status=pass` requires exact version, name, and statement
   content parity. Missing statement history or any content drift is a stop,
   as is any missing migration or other mismatch, including an additive
   migration. The gate never applies migrations. A human reviews pending SQL
   and its additive,
   contract-replacing, or destructive classification against the live objects;
   ambiguous automated classifications fail toward `contract-replacing`. The
   human applies only the approved files out of band and in repository order,
   reads back the ledger and affected objects, then reruns this same gate.
   Attach the final report to the release manifest as durable evidence.
6. Record the release manifest, including the migration-gate report, workflow
   task selection, and env fingerprint.
7. Land only the gated candidate on `main`, without rewriting it, then fetch
   and prove `origin/main` resolves to the recorded gate candidate SHA by
   rerunning the executable gate in landed-ref mode:

   ```bash
   poetry run python scripts/ops/production_migration_gate.py \
     --candidate-sha "$ARGUS_CANDIDATE_SHA" \
     --verify-landed-ref origin/main \
     --output temp/release-evidence/production-migration-gate.json
   ```

   This mode fetches the remote branch itself and fails before database access
   if the fetch or exact-SHA comparison fails. It then repeats schema parity, so
   the final report binds both proofs. If the landed `origin/main` SHA differs,
   the report is invalid: stop every deploy-capable action, keep autodeploy
   manual, check out the landed commit, and rerun the gate against that landed
   SHA. Replace the manifest evidence before continuing. When `checksPass` is
   already live, only a landing method that preserves the pre-gated SHA is
   allowed.
8. Update the release/config contract for the target environment.
9. Promote the live environment so `argus-backtests` runs the intended task
   (`workflow_proof` for proof validation or `run_backtest_job` for real
   execution).
10. Re-run warmup and canaries against the exact deployed SHA and env
   fingerprint.

When the backtest service moves between proof and real workflow modes, the
change must be documented in the release manifest and verified by warmup before
tester access is allowed.

## Implementation Phases

This plan is intentionally split so the highest-risk work can be done in
parallel where possible.

### Phase 1: Reproduce And Freeze The Failure Shape

Objective:
- Encode issue #117 as a durable regression test before changing behavior.

Scope:
- Use the exact prompt and the exact contradictory lifecycle observed in Render.
- Capture both the live-stream failure and the reload/hydration contradiction.

Likely files:
- `tests/test_chat_stream_contract.py`
- `tests/test_chat_runtime_reload_guardrails.py`
- `web/e2e/chat-action-recovery.spec.ts`
- `web/__tests__/chat-artifact-history.test.ts`

Parallel sub-slices:
- backend stream contract test
- frontend hydration/reload test
- E2E browser reproduction

Verification:
- The test suite fails until the stream/reload contradiction is fixed.
- The tests assert that one logical turn cannot both fail visibly and later
  hydrate as a completed success without reconciliation.

### Phase 2: Fix Runtime Finalization Ownership

Objective:
- Ensure a chat turn has one authoritative terminal path.

Scope:
- The backend stream must not let a late runtime success reappear as a
  contradictory artifact after a visible failure.
- Cancellation, final-state fetch, and runtime completion need to agree on a
  single terminal outcome.
- Preserve LangGraph as the only chat brain.

Likely files:
- `src/argus/api/routers/agent.py`
- `src/argus/api/chat/runtime_worker.py`
- `src/argus/agent_runtime/runtime.py`
- `tests/test_chat_stream_contract.py`

Parallel sub-slices:
- stream timeout / cancellation boundary
- request / turn correlation and logging
- final-state reconciliation

Verification:
- A slow or fallback-heavy turn either resolves within the visible contract or
  fails cleanly without later contradictory artifact mutation.
- Late runtime completion cannot create a second truth for the same request.

### Phase 3: Fix Reload And Hydration Reconciliation

Objective:
- Make refresh load one coherent state, not a failure plus a later success for
  the same request.

Scope:
- The UI should hydrate from canonical backend state and suppress stale retry
  affordances when a later authoritative artifact exists.
- It must not infer strategy facts from prose.

Likely files:
- `web/components/chat/ChatInterface.tsx`
- `web/components/chat/ArtifactHistory.tsx`
- `web/lib/chat-backtest-jobs.ts`
- `web/e2e/chat-action-recovery.spec.ts`

Parallel sub-slices:
- transcript normalization
- visible action derivation
- reload persistence coverage

Verification:
- Refresh shows one consistent artifact lifecycle.
- No duplicate user turn remains paired with a stale generic failure if a later
  authoritative result exists.

### Phase 4: Harden Slow Interpretation Recovery

Objective:
- Supported prompts that hit model fallback churn still produce a valid,
  bounded outcome.

Scope:
- Keep the LLM interpreter first for normal user language.
- Validate facts after interpretation, not before.
- Make slow interpretation/fallback paths explicit in logs and tests.

Likely files:
- `src/argus/agent_runtime/llm_interpreter.py`
- `src/argus/llm/openrouter.py`
- `tests/agent_runtime/test_llm_interpreter.py`
- `tests/test_openrouter_policy.py`

Parallel sub-slices:
- timeout/fallback policy
- structured interpreter repair path
- request receipts and traceability

Verification:
- The issue prompt no longer degrades into a misleading
  `unsupported_or_out_of_scope` path because of fallback churn.
- Route receipts make it clear what happened and why.

### Phase 5: Close The SNDK Data-Window Gap

Objective:
- Handle the market-data edge honestly instead of collapsing it into a generic
  stream failure.

Scope:
- `SNDK` should either produce a supported confirmation or a clear data-window
  explanation.
- No regex phrase gates, no special-case ticker hacks, no strategy-name routing.

Likely files:
- `src/argus/domain/market_data/assets.py`
- engine launch/provider tests
- interpreter tests involving explicit asset/date windows

Verification:
- The exact `SNDK` prompt produces a supported, transparent response path.

### Phase 6: Build A Release-Config Drift Gate

Objective:
- Compare live Render config against the repo contract before tester invites.

Scope:
- Check effective env values, not just deploy SHA.
- Surface missing baseline runtime keys and mismatched locale/feature settings.
- Keep secrets redacted.

Likely files:
- `.github/argus-env.sh`
- `.github/render-env-sync.sh`
- `.github/warmup-render.sh`
- `tests/test_environment_scripts.py`
- `tests/test_render_runtime_compatibility.py`

Parallel sub-slices:
- env contract extraction
- redacted live env audit
- CI assertion for required runtime flags

Verification:
- The gate fails if the live deploy is missing baseline runtime vars or is in
  the wrong mode.
- The gate reports drift in a way a release captain can act on quickly.
- The gate should emit an env fingerprint that can be attached to the release
  manifest and canary record.
- The gate should explicitly report the backtest workflow task currently active
  in the live environment.

### Phase 7: Add A Local Ephemeral Smoke Gate

Objective:
- Run a cheap, disposable pre-deploy validation before any Render deploy or
  tester invite.

Scope:
- Stand up a local ephemeral smoke path that mirrors the release-critical
  surfaces needed for smoke testing: API, web, and the workflow/backtest
  integration path.
- Keep Docker optional unless production deploys move to container images too;
  use Docker Compose only when it is the smallest faithful way to mirror the
  release path.
- Use it to validate the candidate SHA, the current feature-flag set, and the
  intended workflow mode before the internet-reachable deploy is touched.
- Treat any local stack as disposable: create it, run the smoke checks, tear it
  down.
- Keep the smoke gate fast enough that it can run on every candidate push
  without consuming the live canary budget.

Likely files:
- `.github/local-smoke.sh`
- `.github/dev.sh`
- `.github/qa.sh`
- `.github/workflows/private-alpha-smoke.yml`
- `tests/test_local_smoke_contract.py`

Parallel sub-slices:
- local stack bootstrap
- mode/flag fingerprint check
- pre-deploy happy-path smoke run

Verification:
- The smoke gate fails before deploy if the candidate SHA, feature flags, or
  workflow mode do not match the release contract.
- The smoke gate confirms the environment is suitable enough to justify the
  expensive internet-reachable canary.
- The smoke gate does not mutate production or private-alpha release state.

### Recommended Agent Lanes

Use the standing roster with crisp lane ownership:

- `argus-slice-planner`: phase ordering, promotion criteria, and rollback
  shape for Phases 1 through 9.
- `argus-code-scout`: repo impact map for the smoke gate, drift gate, and
  canary files.
- `argus-runtime-guardian`: runtime-finalization and reload contradiction
  review for Phases 1 to 4.
- `argus-evidence-engine-critic`: backtest evidence and result-card truth for
  Phase 5.
- `argus-security-release-reviewer`: release manifest, env drift exposure, and
  live-config risk for Phases 6 through 9.
- `argus-verification-qa`: local smoke proof, browser canary proof, and release
  confidence for Phases 7 and 8.
- `argus-product-architect` and `argus-domain-modeler`: memo-to-product object
  translation only, before implementation begins.

When a phase needs a narrower one-off agent than the standing roster, spawn a
custom bounded agent with this blueprint:

- Goal: one sentence naming the exact phase and proof target.
- Allowed surfaces: a short file list or subsystem list only.
- Forbidden surfaces: anything outside the phase, plus release/config mutation
  unless explicitly requested.
- Expected output: a single artifact type, such as impact map, object model,
  phase plan, or verification matrix.
- Verification evidence: exact commands, files, or browser observations needed.
- Cleanup: close the agent when the artifact is delivered.

Custom-agent examples:

- Local smoke-path agent:
  - Goal: design the disposable local smoke path for Phase 7 and list the exact
    commands needed to prove the release contract, using Docker only if it
    removes more complexity than it adds.
  - Allowed surfaces: `docs/specs/private-alpha-ci-cd-sota.md`, `.github/dev.sh`,
    `.github/qa.sh`, `.github/local-smoke.sh`, `docker-compose.yml` or the
    equivalent local orchestration files.
  - Forbidden surfaces: runtime interpreter behavior, backtest math, release
    config mutation, and frontend state changes.
  - Expected output: container topology, startup/shutdown flow, and smoke
    verification checklist.

- Canary-proof agent:
  - Goal: define the minimal evidence needed to prove the live canary catches
    timeout/reload contradictions.
  - Allowed surfaces: `.github/canary-render.sh`, `.github/workflows`,
    `tests/test_render_canary_script.py`, browser QA notes.
  - Forbidden surfaces: product scope, data model changes, and deploy topology.
  - Expected output: canary proof matrix and failure-evidence requirements.

### Phase 8: Expand Canary Coverage

Objective:
- Make the canary cover the real failure class, not just happy-path completion.

Scope (narrowed by founder decision, 2026-09-13, #614: the canary keeps its
purpose and never follows features):
- Check exactly the four checks the release profile names in
  `canary.required_steps`: the three services run the same commit
  (`services_same_commit`), a signed-in canary account loads the chat and gets
  one ordinary answer (`signed_in_chat_answer`), one backtest completes
  (`backtest_completes`), and one research question returns an answer with
  sources (`research_answer_with_sources`). Every failure names its check.
- Keep the release-coherence guards: workflow env parity
  (`workflow_env_fingerprint`, `workflow_env_status=ready`), effective workflow
  runtime proof (`workflow_runtime_provider_mode=live_provider`,
  `workflow_runtime_proof=ready`), the disabled-signup denial, and the welcome
  email proof.
- Feature postconditions (decision records, receipts, Search reopening, exact
  result facts, intercepted recovery, console checks) belong to the promotion
  walk, not the canary.
- Keep canary output privacy-safe.
- When a canary fails after warmup passes, write a sanitized failed-capture
  artifact and replay it locally before redeploying. The replay should exercise
  canonical result rendering, not LLM prose matching or locale-specific phrase
  heuristics.

Likely files:
- `.github/canary-render.sh`
- `.github/workflows/private-alpha-canary.yml`
- `tests/test_render_canary_script.py`

Verification:
- Canary fails when the environment contract drifts or when one of the four
  checks fails, and the failure names the check.
- Canary passes only when commit, env, and the four checks all agree.
- Canary evidence should be stored with the release manifest so the same SHA
  and env fingerprint can be audited later.
- Canary evidence should note whether the backtest service is in proof or real
  workflow mode.
- Failed-capture artifacts should be kept with release evidence only for failed
  candidates and must not contain raw conversation, user, run, job, cookie, or
  service-role values.

### Phase 9: Update Runbooks And Source-Of-Truth Docs

Objective:
- Make the promotion path understandable and repeatable.

Scope:
- Document branch promotion rules.
- Document environment ownership.
- Document the release gate sequence.
- Document the Spanish readiness requirement as a release criterion, not a
  one-off test.

Likely files:
- `docs/PRIVATE_LAUNCH_RUNBOOK.md`
- `docs/specs/private-alpha-next-integration.md`
- `docs/specs/private-alpha-ci-cd-sota.md` if this becomes the active roadmap

Verification:
- A new release captain can follow the gate without tribal knowledge.

## Serialization And Parallelism

Recommended order:

1. Phase 1 first, because it freezes the actual bug shape.
2. Phase 2 and Phase 3 can then proceed in parallel, since backend finalization
   and frontend hydration are separate ownership areas once the contract is
   pinned.
3. Phase 4 and Phase 5 can run in parallel with Phase 2/3 if they do not touch
   the same files.
4. Phase 6 should land before any new tester invite, because it governs the
   promotion gate itself.
5. Phase 7 introduces the cheap local smoke gate so expensive internet-facing
   canaries only run on candidates that already match the release contract.
6. Phase 8 follows the smoke gate so the canary reflects the final release
   contract.
7. Phase 9 is last, but it should be drafted during implementation so the gate
   instructions stay in sync with the code.

## Acceptance Criteria

The system is ready only when all of the following are true:

- Issue #117 no longer reproduces a generic error followed by a late completed
  artifact for the same logical request.
- Reload/hydration cannot preserve contradictory state.
- Spanish support is validated as a release dimension, not assumed.
- The live deploy’s effective runtime env matches the documented contract.
- The candidate passes a local ephemeral smoke stack before any internet-
  reachable canary or deploy.
- The read-only production migration gate reports exact parity before any
  config sync, merge, or service action that can deploy the candidate.
- The canary asserts both commit and runtime mode.
- `main` is the promotion target, not a surprise prerequisite.
- Public tester exposure only happens after the release gate passes.
- A release manifest exists for each promoted candidate and includes SHA,
  env fingerprint, canary evidence, rollback target, and approver.
- The backtest service task currently active in each environment is explicitly
  documented and verified before testers are invited.

## Guest Candidate Canary Addendum

A guest candidate adds gates; it does not bypass the release sequence above.
Before any guest traffic:

- the exact candidate SHA must pass the local real-Auth/Postgres browser matrix
  in an isolated process;
- checked-in server/frontend Guest defaults must remain true and explicit false
  must preserve rollback. Public-account access is no longer held closed here:
  the founder opened it on 2026-08-12;
- the branch-deployed canary must prove `/` opens guest chat only in the
  approved staged mode, and that permanent signup/login admits an ordinary
  unlisted email while a disabled row stays blocked;
- hosted Supabase must explicitly enable anonymous Auth, configure an approved
  CAPTCHA posture, and retain provider plus Argus rate limits;
- conversion must prove distinct-UUID ordinary signup and atomic claim, plus
  atomic existing-account login claim, without duplicate artifacts, usage,
  jobs, or pending actions;
- the cleanup dry run and bounded real run must be scheduled with an owner,
  alert on failures/lag, and preserve converted or permanent accounts;
- guest analytics must stay personless and metadata-only; browser facts cross
  the authenticated server endpoint and never include financial prose, Auth
  material, exact capital/dates, private titles, or provider/model names;
- calibration evidence must record local synthetic p50/p95 where supported,
  queue/backpressure decisions, anonymous-identity volume, cleanup lag, and the
  single canary's provider-reported latency/cost. Unsupported production
  projections must remain explicitly unmeasured.

Canary failure rolls back presentation first, then server guest bootstrap. It
does not touch `ARGUS_PUBLIC_ACCOUNT_ACCESS_ENABLED=true`, which the founder
authorized separately on 2026-08-12; closing public registration again is its
own founder decision. A local Block 4 pass is not “public ready.”

## CI triggers and tooling (October 13, 2026)

- **Trigger rules (#1040).** In `.github/workflows/ci.yml`, the `push` trigger runs
  only for `main`, `codex/private-alpha-next` and
  `codex/private-alpha-next-jules-intake`. A feature branch with a PR runs CI once
  per push, through `pull_request` against those three base branches. A push to a
  feature branch without a PR runs no CI.
- **PDF tools (#1042).** The `docs-checks` job installs `poppler-utils`, so the
  docs-reading backend tests have `pdftotext`. The `backend-checks` job installs
  it too.

## Non-Goals

- Do not add new product surfaces unrelated to release hygiene.
- Do not implement the Perplexity Research Lab thesis here.
- Do not widen the backtesting feature set beyond private-alpha scope.
- Do not invent frontend truth to paper over backend drift.
- Do not change Supabase schema or RLS as part of the CI/CD spec.

## Notes From Investigation

The current checkout and private-alpha deploy evidence show:

- `codex/private-alpha-next` is the active integration lane.
- Render services are configured with branch `main` and manual deploys
  (`autoDeployTrigger: off`). The workflow is not Blueprint-managed, so its
  matching trigger is
  enforced by the release profile, runtime sync, and live audit. Its ready
  version name supplies the deployed Git prefix used by the three-service SHA
  resolver for both automatic and manual releases.
- The live API is in `real-workflow` mode now, but the effective env contract
  should still be audited before each invite.
- The intended pre-deploy check is a local ephemeral stack, not a second live
  environment.
- The web feature flags are intentionally off for private alpha.
- Spanish support exists in the codebase and tests, but the release process
  must treat it as a contract, not a memory.
