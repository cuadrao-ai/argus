# Personalization Memory Development Lane Contract

## Verdict

- Mode: incubation_lane
- Confidence: high
- Readiness: ready_for_implementation
- Execution authority: none

The contract did not create execution authority. The founder's later
2026-07-29 instruction separately authorizes cumulative, fresh-port incubation
branches for persistence, API, Data Controls, and runtime; independently green
commits; non-force backup pushes; and Draft pull requests as review stopping
points. This checkpoint opens only local persistence, its data-model contract,
and disposable local Supabase proof. It does not authorize a merge, integration
mutation, hosted database write, live provider call, deployment, tester
exposure, or work in the later API, runtime, UI, or analytics slices.

## Current status (2026-09-25)

This contract described incubation. Memory has since shipped. Current
production availability and the approved widening transition are owned by
[PRODUCT.md Current production availability and planned changes](../../PRODUCT.md#current-production-availability-and-planned-changes).
When `ARGUS_ENABLE_MEMORY_SEMANTIC_RECALL` is off, the API keeps canonical
token-match recall (`semantic_recall_enabled()` in
`src/argus/api/personalization_memory.py`).

## Goal

Build cumulative production-intent personalization memory for registered
accounts from the exact current integration head, using the published donor only
as evidence. This checkpoint ports the verified domain tranche, repairs consent
and zero-state gaps discovered during persistence review, and adds complete
local Postgres persistence. Typed backend account eligibility and
database-canonical Auth/workspace truth remain the first boundaries: a verified
Guest must be denied before candidate creation, consent state, storage,
retrieval, provider metadata, memory-specific events, or conversion carryover.

## Evidence Audit

- Base ref: origin/codex/private-alpha-next
- Base SHA: 88ab906dae8e329a526d4ada57318b6b7adcbc5d
- Comparison ref: origin/claude/argus-personalization-memory-2a6257
- Comparison SHA: 8b7ef339325b763c6396d7ed66e5f85835fcbbbc
- Merge base: 390d57294cf9911becdb14ced126770d0124e4cb
- Divergence: base-only 90 commits; donor-only 13 commits
- Changed paths: 16 donor-added files and 3,270 inserted lines: one 640-line program proposal at `docs/specs/personalization-memory-program.md`, six files under `src/argus/memory/`, and nine files under `tests/memory/`
- Remote freshness: On 2026-07-29, the persistence preflight refreshed both remote-tracking refs and confirmed `88ab906dae8e329a526d4ada57318b6b7adcbc5d` for integration and `8b7ef339325b763c6396d7ed66e5f85835fcbbbc` for the donor. The selected base adds PR #305's curated, note-aware decision recall after `4ff3344d`; both earlier approved SHAs remain ancestors
- Shared surfaces: The donor has no direct path collision because all 16 files are additions, but current integration owns authenticated Guest account truth, capability denial, conversion and handoff, Supabase ownership, LangGraph, API/OpenAPI, Data Controls, Omnisearch, observability, and release gates
- Semantic overlap: API and auth overlap is high because current `AccountContext.kind` distinguishes `guest` from `registered`; persistence overlap is high because a Guest is an authenticated owner and owner-only RLS is insufficient; runtime overlap is high because memory must not alter interpretation, routing, or simulation truth; conversion overlap is high because link preserves an Auth UUID and handoff transfers a bounded product graph; PR #304 adds owned interpreter, Try next, message-store, product-event, API, and web seams where memory may later integrate; PR #305 makes DecisionNote-aware Omnisearch the current decision-recall owner, so MemoryRecord must remain a personalization sidecar and never become alternate decision/search truth
- Authority read method: git_show_from_base_ref
- Implementation surfaces: The persistence checkpoint may own `src/argus/memory/**`, `tests/memory/**`, one forward `supabase/migrations/*_add_personalization_memory_persistence.sql`, `docs/DATA_MODEL.md`, this contract, the persistence plan, and its untracked SDD evidence ledger. API, runtime, UI, analytics, live providers, hosted persistence, and deployment remain closed
- Acceptance anchor: Deterministic and real local-Postgres matrices prove that a Guest is rejected before any settings, cooldown, candidate, consent, record, provenance, retrieval, provider metadata, reconciliation, or memory event effect; direct enable and confirmation have exact immutable consent evidence; every conversion zero-state count is database-computed; and no memory operation accepts a bare `user_id`

The complete current decision memo and current canon, roadmap, code, and tests
were read from the exact selected base with SHA-pinned `git show` before the
persistence branch was created. Donor evidence was read with SHA-pinned
`git show` and three-dot diff commands. The authorized persistence branch
`codex/personalization-memory-incubation-persistence-v1` was created directly
from the selected base before production code changes.

The donor is materially stale even though its paths are additive. Its service
authorizes every operation with a bare `user_id`, its store scopes data only by
that id, and neither its memory package nor its memory tests mention Guest,
anonymous Auth, `AccountContext`, or account kind. On current integration, a
Guest has a real `profiles.id`, so donor owner scoping does not enforce the
required account-class boundary.

## Mode Decision

- Why this mode: The founder supplies explicit eventual ship intent and authorizes complete, bounded, no-consumer production-intent work; the donor provides a coherent lifecycle that can be reimplemented from current truth; and the active roadmap keeps integration and activation closed, so mature work must remain isolated and independently verifiable
- Why not the others: `normal_feature_branch` is rejected because current roadmap truth does not permit near-term integration; `dark_integration` is rejected because no accepted current-base flag or owner exists and a default-off flag cannot secure Guest authorization, migrations, RLS, conversion, or durable data; `wait` is rejected because the registered-only outcome, Guest prohibition, donor posture, isolation boundary, and fresh-port strategy are decided well enough to plan reversible slices
- Safe preparatory work: Maintain the current-head donor port map, memo traceability matrix, typed `MemorySubject` and eligibility contract, Guest-negative effect matrix, anonymous Auth and conversion threat model, exact consent-action evidence, complete zero-state digest, canonical provenance validation, and deterministic acceptance
- Eventual ship intent: Ship earned-opt-in, user-confirmed personalization memory only for registered accounts after the founder opens the roadmap milestone and the privacy, control, persistence, evaluation, and release gates pass
- Isolation boundary: Incubation now includes the verified domain package plus
  private local Postgres product records, an injected direct-database adapter,
  a forward migration, and disposable full-stack proof. It still has no
  production consumer, network provider, API, runtime, UI, analytics, hosted
  database, deployment, or user exposure
- Fresh-port strategy: Preserve the donor unchanged; create
  `codex/personalization-memory-incubation-persistence-v1` from
  `88ab906dae8e329a526d4ada57318b6b7adcbc5d`; port the independently accepted
  Codex domain commits; add reviewed repairs and persistence as new green
  commits; and later port only accepted cumulative commits onto a fresh branch
  from the then-current integration head

The founder's latest instruction opens this cumulative incubation workflow. It
does not rewrite the roadmap's post-PMF integration and exposure gates.

## Scope

### Allowed

- Write and validate this contract.
- Plan a first slice that defines a typed memory subject carrying
  `registered` or `guest`, with no constructor from profile fields, email,
  frontend state, or a bare owner id.
- Under the founder's 2026-07-29 implementation authority, fresh-port the donor's typed
  candidate and record contracts, consent and suppression policy, in-memory
  store, provider protocol, lifecycle service, and deterministic tests into new
  `src/argus/memory/` and `tests/memory/` files.
- Repair the reviewed domain prerequisites before schema work: count consent
  receipts, provenance rows, and reconciliation work in zero-state; create
  exact immutable consent-action receipts for direct enable and confirmation;
  bind sensitivity to policy version and content digest; use a literal category
  allowlist; and add record revision/update truth.
- Require the service boundary to receive the typed subject for every operation:
  propose from an explicit request or saved decision, confirm, decline, enable,
  retrieve, explain, edit, delete, disable, and reset.
- Preserve this production ordering for every future entry point: verify the
  session, derive Guest truth from `auth.users.is_anonymous` plus the active
  `guest_workspaces` row, materialize request-scoped `AccountContext`, deny
  `kind == "guest"`, and only then enter the memory subsystem. Eligibility is
  outside the memory pipeline, so Guest denial creates no memory suppression
  record or event.
- Make `guest` fail closed at the first memory instruction, before reading or
  changing settings, marking cooldowns, creating candidates, granting consent,
  storing records, retrieving records, invoking a memory extraction, embedding,
  retrieval, or projection provider, or emitting a memory-specific product,
  cost, or provider event.
- Preserve registered-user earned opt-in, closed category allowlists,
  sensitivity suppression, explicit confirmation, bounded retrieval,
  provenance, inspect/edit/delete/disable/reset semantics, canonical Argus
  ownership, and provider fail-open behavior.
- Create one forward personalization-memory migration with private
  owner-keyed settings, candidate, consent-action, record, provenance,
  prompt-history, reconciliation, and cleanup state; a psycopg-backed
  `CanonicalMemoryStore`; and real disposable local-Supabase tests.
- Recheck canonical registered truth from `auth.users.is_anonymous` and the
  same-identity `guest_workspaces` state before every store read or mutation.
  `MemorySubject` remains an early domain guard, not database authorization.
- Revoke all direct memory-table access from `public`, `anon`,
  `authenticated`, and `service_role`; use the injected backend database pool
  only. Future API wiring must derive `RegisteredMemoryOwner` from a verified
  session before calling the adapter.
- Persist canonical DecisionNote/Evidence provenance as a sidecar pointer and
  atomically revalidate owner and recorded source revision at confirmation.
  Never update or replace canonical decision/evidence/search truth.
- Specify conversion zero-state for both same-identity link and existing-account
  handoff: no Guest candidate, consent, record, provider projection, event, or
  queued extraction may transfer or replay; no Guest transcript or transferred
  artifact is retrospectively mined after conversion; the now-registered user
  must complete a new explicit scoped opt-in before any memory can be proposed
  or stored.
- Preserve ordinary Guest chat, LLM-first interpretation, and the canonical
  Guest product-graph transfer. The memory subsystem is absent; normal chat is
  not replaced with phrase matching or a second interpreter.

### Forbidden

- No wholesale merge, rebase, or cherry-pick of
  `origin/claude/argus-personalization-memory-2a6257`.
- No public or internal API wiring, `AccountCapabilities` change, OpenAPI field,
  LangGraph or interpreter hook, Supabase gateway method, Data Controls UI,
  Omnisearch projection, result-card action, analytics hook, live conversion
  route edit, or release configuration in the persistence checkpoint.
- No Guest memory state, prompt cooldown, decline history, suppression record,
  retrieval timestamp, provider projection, provider call, memory-specific
  event, or conversion carryover, including state that is hidden or default
  off.
- No real user data, live memory provider, live LLM extraction, embeddings,
  pgvector, Mem0 selection, network call, hosted service, hosted database
  write, or shared Docker stack. Only a lane-unique disposable local Supabase
  stack may be created and removed for evidence.
- No frontend-inferred account kind, nullable-email heuristic, profile-metadata
  heuristic, owner-id-only check, or feature flag as the Guest safety boundary.
- No regex, localized phrase table, or pre-interpreter text gate for natural
  language such as "remember this." Ordinary text still reaches the canonical
  LLM interpreter; backend account truth prevents only the personalization
  subsystem and all of its side effects.
- No memory influence on interpretation, routing, simulation inputs,
  confirmation truth, execution, metrics, or canonical evidence.

### No-touch surfaces

- `src/argus/api/**`, especially `guest_access.py`, `dependencies.py`,
  `schemas.py`, auth conversion/handoff, evidence routes, and agent routing.
- `src/argus/agent_runtime/**`, including interpreter, stages, graph state,
  result follow-ups, and current observability seams.
- `src/argus/domain/supabase_gateway.py`, `src/argus/api/**`, `web/**`,
  `docs/api/openapi.yaml`, canon docs other than `docs/DATA_MODEL.md`, active
  roadmap and decision-memo files, existing migration history, release
  manifests, Render configuration, and Guest cleanup, allowance, conversion,
  and handoff application code. The single new forward migration may add
  database triggers that guard existing link/handoff transactions but may not
  add memory tables to their ownership-transfer list.

## Environment and Evidence Tier

- Evidence tier: deterministic domain tests plus a disposable local Supabase
  CLI full stack on repository-pinned Python 3.10.20 and PostgreSQL 17
- Proof provided: typed first-instruction Guest denial; exact consent and
  zero-state contracts; database-canonical registered-owner checks; direct
  Data API role denial; cross-owner isolation; durable controls; conversion
  corruption rejection; provider-reconciliation persistence; no-consumer
  isolation; and unchanged hermetic runtime/spine tests
- Proof ceiling: This tier cannot prove future API `403
  account_conversion_required`, verified-session-to-owner wiring, browser/Data
  Controls behavior, hosted configuration, live provider processing, canary
  behavior, PMF readiness, or production exposure
- Unrelated Docker policy: inspect ownership first; leave unrelated containers,
  networks, volumes, images, and caches untouched
- Docker inventory: record read-only before the stack starts; Docker Desktop may
  be started only for this authorized local evidence tier
- Lane project ID: `argus-memory-persistence-2174`
- Port block: choose and record a confirmed-unused block separate from the
  canonical `argus-qa` 54330–54339 block
- Cleanup target: only resources derived from
  `argus-memory-persistence-2174`; stop them with the Supabase CLI and never run
  a global prune

The stack runs from a scratch copy of `supabase/` whose project id and ports are
lane-specific. Tracked configuration, canonical linked environment files, and
the `argus-qa` stack remain untouched.

## Verification

- Run the lane-contract validator and repair every failure before treating this
  artifact as complete.
- Before migration work, add red/green domain tests for receipt-inclusive
  zero-state and exact immutable consent-action evidence.
- For the authorized implementation tranche, add one table-driven Guest matrix covering
  propose-from-decision, propose-explicit, confirm, decline, enable, retrieve,
  explain, edit, delete, disable, and reset.
- For every Guest case, assert the eligibility result occurs first and that
  settings, cooldown, candidate, consent, record, retrieval, provider, and
  memory-event spies remain untouched. A hidden denial record is still a memory
  effect and fails the contract.
- Prove no public service method accepts only `user_id`; owner scoping remains
  inside the registered path after eligibility.
- Prove registered subjects retain explicit request and saved-decision
  lifecycles, category-scoped consent, confirmation-before-record, sensitivity
  suppression, bounded retrieval, provenance, control operations, and provider
  fail-open behavior.
- Add same-UUID link and existing-account handoff fixtures showing zero memory
  state before and after conversion, no replay or retrospective extraction, and
  a fresh registered scoped opt-in before any later candidate.
- In real Postgres, compute zero-state from every memory table inside the
  conversion transaction. Reject receipt-only, provenance-only, and
  reconciliation-only Guest corruption; never transfer a memory table.
- Prove direct table access is denied to `anon`, `authenticated`, and
  `service_role`, a forged anonymous JWT cannot override `auth.users`, and a
  linked user remains ineligible while its Guest workspace is active or
  claiming.
- Prove direct enable/settings mutation has one immutable exact-scope receipt;
  repeated enable is idempotent; confirmation atomically creates one receipt
  and one record; and any failure leaves candidate/settings unchanged.
- Prove confirmation atomically revalidates owner and revision for current
  DecisionNote plus linked EvidenceArtifact provenance, while Omnisearch,
  Recents, canonical decisions, evidence, conversations, backtests, and
  LangGraph state remain unchanged.
- Prove the package imports neither `argus.api` nor `argus.agent_runtime`, has no
  consumer from current code, and leaves the hermetic agent-runtime/spine sweep
  unchanged.
- Re-run formatting, Ruff, mypy, focused memory tests, the hermetic
  agent-runtime/spine sweep, and `git diff --check` on the exact fresh-port
  candidate. Historical donor greens are reference evidence only.
- Use local Supabase Auth/Data API/RLS tests to prove anonymous-JWT denial,
  cross-user isolation, service-role denial, durable delete/reset, and zero
  conversion carryover. Handoff must reject a corrupt source graph containing
  any Guest-owned memory row; memory tables must never enter its transfer list.

## Reconciliation

- Preserve the published donor tip
  `8b7ef339325b763c6396d7ed66e5f85835fcbbbc` and its 13 commits as read-only
  evidence. Do not rewrite, merge forward, rebase, or cherry-pick it.
- Resolve every conflict in favor of the exact current-base canon, roadmap,
  current `AccountContext.kind`, Guest capability and conversion truth,
  LangGraph ownership, and Supabase product model.
- Under the recorded tranche authority, fresh-port only the coherent donor
  domain concepts needed by the accepted tranche onto the exact selected base.
  Reimplement the eligibility contract from current truth; do not preserve
  donor call signatures merely to reduce diff size.
- Before each later slice or promotion, refresh the base ref, record new exact
  SHAs, merge base, divergence, changed paths, migrations, shared owners, and
  semantic overlap. Re-run affected verification after every material
  reconciliation.
- If a future migration has been applied anywhere, preserve history and use a
  forward fix. Never rewrite durable schema history to resemble the donor.

## Promotion

- Incubation code does not earn integration by being additive or green. When the
  founder explicitly opens the personalization-memory milestone, create a fresh
  branch from the then-current integration head and port only independently
  accepted incubation slices.
- Code promotion requires the roadmap's post-PMF boundary to be explicitly
  reconciled, an accountable owner and accepted backend exposure control to be
  named, canon/API/data-model/design docs to land contract-first, Data Controls
  and delete-all ownership to exist, and Guest unavailability to be proven at
  the request, service, database, provider, event, cleanup, link, and handoff
  boundaries.
- The donor's `[removed obsolete setting]` and related proposed flags are not accepted
  current-base control points. A future control separates registered-user code
  integration from exposure, tests neutral-off and enabled states, has an owner
  and retirement condition, and never substitutes for authorization or RLS.
- User exposure is a separate founder gate requiring earned opt-in, English and
  Spanish browser journeys, reload and cross-conversation controls, provider
  and data-processing approval, exact-SHA branch-deployed canary evidence,
  release manifest, rollback evidence, and explicit confirmation that Guest
  behavior and ordinary chat are unchanged.

## Rollback

- The persistence checkpoint is additive and has no consumer. Code rolls back
  by reverting independently green use-case commits in reverse dependency
  order before integration.
- Once a migration is applied anywhere, repair or removal uses an approved
  forward migration or explicit data-preserving procedure; disabling a flag
  does not remove stored data or repair authorization.
- If any future path classifies a Guest as memory-eligible, keep registered
  exposure disabled, stop memory writes, retrieval, provider work, and
  memory-specific events, preserve privacy-safe request/security evidence, and
  repair the backend and database boundaries before another attempt.

## Caveats

- The current roadmap and founder-resolution addendum still place
  personalization `MemoryRecord` work post-PMF. This request supplies
  production-intent incubation direction, not evidence that the PMF gate passed
  and not permission to integrate or expose memory.
- The prior draft's original `ready_for_implementation` verdict was too broad.
  Readiness is now limited to the exact no-consumer persistence checkpoint
  because the outcome, owned paths, branch, database authorization shape,
  acceptance matrix, environment tier, stop conditions, and release-captain
  authority are explicit. API, integration, exposure, and PMF proof remain
  closed.
- The donor has useful consent, lifecycle, provider-fallback, and control
  concepts, but zero Guest/account-kind coverage. Historical donor greens do
  not prove compatibility with the 90 integration-only commits.
- Persistence review found two repairable prerequisites in the accepted domain
  checkpoint: `MemoryStateDigest` omitted consent receipts, and direct enable
  expanded scope without immutable exact-scope evidence. Both must be fixed
  before the migration is written. A third persistence-only requirement is
  atomic ownership/revision validation for DecisionNote/Evidence provenance.
- "Before provider calls" means before every memory-specific extraction,
  embedding, retrieval, projection, or reconciliation provider call. It does not
  authorize a pre-LLM phrase gate or disable the normal LLM-first Guest chat
  path.
- A standard auth denial may still produce ordinary privacy-safe request or
  security telemetry. It must not create a memory candidate, suppression or
  decline record, memory product event, memory cost entry, or any payload
  containing proposed memory content.
- Current `AccountCapabilities` has no personalization-memory field. Adding one
  is a contract-first integration decision outside the first incubation slice,
  not a field to infer in the frontend or smuggle in through the donor.

## Stop Conditions

- Stop if a Guest can reach policy, settings, cooldown, candidate, consent,
  storage, retrieval, memory provider, or memory event code before typed
  eligibility denies the operation.
- Stop if any memory operation accepts a bare `user_id` or derives eligibility
  from frontend state, email nullability, editable profile metadata, owner id,
  or a feature flag.
- Stop if same-identity link, handoff, cleanup, retry, replay, buffered work, or
  retrospective extraction can create or transfer Guest memory state.
- Stop if Guest denial requires natural-language phrase matching before the
  interpreter or changes ordinary Guest chat provider behavior.
- Stop if memory can influence interpretation, routing, simulation truth,
  canonical artifacts, confirmation, execution, or metrics.
- Stop on any edit outside the persistence plan's owned paths. Shared API,
  runtime, Supabase gateway, UI, observability, application conversion, hosted
  database, and release surfaces require their later slice plans and authority.
- Stop if consent receipts are omitted from zero-state, direct scope expansion
  lacks immutable exact evidence, source ownership/revision is not revalidated
  atomically, or unresolved derivative cleanup can be lost on delete/reset.
- Stop if `anon`, `authenticated`, or `service_role` can directly access a
  personalization-memory table, or if any database write can create Guest
  memory despite canonical Auth/workspace truth.
- Stop if a default-off flag is presented as proof that a migration,
  authorization rule, durable write, provider disclosure, or conversion path
  is safe.
- Stop if promotion is proposed by wholesale donor merge, rebase, or
  cherry-pick, or without a fresh then-current-head port and full
  re-verification.

## Sources

### Argus authority

- `origin/codex/private-alpha-next` at
  `88ab906dae8e329a526d4ada57318b6b7adcbc5d`:
  `docs/PRODUCT.md:271-279,539-561`,
  `docs/ARCHITECTURE.md:660-668,746-777`,
  `docs/API_CONTRACT.md:1560-1705`,
  `docs/DATA_MODEL.md:155-245,1203-1208`,
  `.agent/designs/argus/DESIGN.md:356-369`,
  `docs/specs/private-alpha-next-roadmap.md:490-524,717-723,1103-1130`, and
  `docs/specs/private-alpha-next-decision-memo.md:3260-3347,3669-3705`.
- Current implementation and tests at that SHA:
  `src/argus/api/guest_access.py:55-129`,
  `src/argus/api/dependencies.py:287-322,479-502`,
  `src/argus/api/routers/evidence.py:16-34`,
  `supabase/migrations/20260724211312_guest_workspace_handoffs.sql:180-385`,
  `tests/test_guest_access_policy.py`, `tests/test_guest_conversion.py`, and
  `tests/test_guest_handoff_postgres.py`.
- Current note-aware decision recall at that SHA:
  `src/argus/api/search_assembly.py`,
  `src/argus/domain/postgres_search_reader.py`, and
  `tests/test_search_postgres.py`.
- Donor evidence at
  `8b7ef339325b763c6396d7ed66e5f85835fcbbbc`:
  `docs/specs/personalization-memory-program.md`,
  `src/argus/memory/{contracts,policy,provider,service,store}.py`, and
  `tests/memory/**`.

### External guidance

- https://martinfowler.com/articles/feature-toggles.html supports separating
  code deployment from exposure while recognizing that a flag adds complexity
  and is not an authorization or durable-data safety boundary.
- https://docs.github.com/en/pull-requests supports using a fresh branch and
  pull request for isolated review; a published donor branch is evidence, not
  proof of current integration readiness.
- https://supabase.com/docs/guides/local-development and
  https://supabase.com/docs/guides/local-development/testing/overview support
  the local full-stack Auth/Data API/RLS and negative database tests required by
  a future persistence slice.

### Inference

- `incubation_lane` is the safe mode because the current request explicitly
  names production intent, the domain tranche can remain isolated, and
  current integration and user exposure are still closed.
- `ready_for_implementation` is supported only for the authorized isolated
  persistence checkpoint, with the reviewed domain repairs first, because its
  account boundary, owned surfaces, database authorization shape, acceptance
  matrix, release-captain owner, branch, and verification tier are exact. The
  missing API control point, PMF gate, and promotion timing still block
  exposure.
- A Guest's valid owner id makes the donor's `user_id`-only API semantically
  unsafe. Eligibility must be derived from verified request-scoped account
  truth before memory logic, then reinforced by anonymous-JWT and service-role
  database denial when persistence is introduced.
- Fresh-porting reviewed concepts from the then-current integration head is
  safer than preserving donor history because the donor is published,
  materially stale, and predates the canonical Guest boundary.

### Non-authoritative input

- `/Users/garces/.codex/skills/.validation/argus-development-lane-planner/green-memory-contract.md`
  supplied the earlier incubation hypothesis and negative-test outline. Its
  unverified-freshness caveat is now resolved, while its implementation
  readiness claim is rejected in favor of current roadmap and Guest truth.

## Addendum: 2026-08-05 founder lock — retrieval provider and next stage

- **Retrieval provider decision (locked):** the semantic-recall/retrieval layer
  behind the existing `MemoryProvider` protocol (`src/argus/memory/provider.py`)
  will be **Mem0** (OSS/self-hosted), not a hand-built Supabase pgvector +
  Perplexity embeddings pipeline. Whether semantic recall is on in production
  is owned by
  [PRODUCT.md availability](../../PRODUCT.md#current-production-availability-and-planned-changes).
  Mem0 owns fact extraction, deduplication,
  conflict resolution, embedding generation (default OpenAI, swappable), and
  user/agent/session-scoped retrieval internally; Argus is only responsible for
  calling `.add()` on new confirmed content and `.search()`/`.get()` at
  retrieval time. This matches `docs/specs/private-alpha-next-decision-memo.md`
  §5.6's recommended architecture (Supabase product tables as canonical truth
  -> Mem0/retrieval layer for semantic recall -> LangGraph runtime consuming
  memories as context, never as source-of-truth) and requires no change to the
  domain/service layer built in this persistence checkpoint — only a future
  provider implementation behind the existing protocol seam.
- **Next authorized stage:** `codex/personalization-memory-incubation-api-v1`,
  fresh-ported from the then-current integration head at pickup time (per the
  sequential incubation pattern above — not built on top of this branch).
  Scope: auth-gated API endpoints deriving `RegisteredMemoryOwner` from a
  verified session, wired to the existing `MemoryService`. Still closed at
  that stage: live provider call (Mem0 wiring), runtime/UI hooks, Data
  Controls surface, deployment, tester exposure.
- This PR (#307) remains Draft and unmerged. Execution authority is still
  none; this addendum records a design decision and the next pickup point,
  not a merge or scope authorization.
