# Repository operating reference

This is the complete instruction body moved from root AGENTS.md at integration
`77ddf2c7d33cc4c7273cc4c39354b5152fe01e91`. The [startup index](../../AGENTS.md)
owns entry order and points to this reference. Read the full reference before
implementation or review. Repository paths in commands and code spans are
relative to the repository root. Markdown links are relative to this file.

Later scoped decisions and assignments in the [authority map](../DOCUMENTATION_AUTHORITY.md),
[decision log](../specs/argus-decision-log.md) and [execution manifest](../specs/argus-execution-board.md)
take priority over dated product or assignment statements here. Historical Argus
release references do not authorize Cuadrao promotion to main. The approved
Cuadrao memory foundation is in ARCHITECTURE.md's Cuadrao reuse decisions. The
older Alpha RAG deferral below still protects the unchanged Argus loop.

# Project Agents & Tools: Argus

Argus is evolving from its grounded finance chat into the founder-approved
minimum viable financial ecosystem. Existing chat, calculations, research,
and historical simulations remain valuable product capabilities.

Read [documentation authority](../../docs/DOCUMENTATION_AUTHORITY.md) to distinguish
approved experience from existing technical contracts and assigned work. The
[MVEE](../../docs/specs/argus-minimum-viable-ecosystem-experience.md) owns the pivot's
experience; it is not an implementation or deployment authorization.
The backtesting engine remains critical infrastructure.

This file is the primary orientation guide for AI coding agents working in the repository.

# 🛡️ Read These First (Mandatory)

Before making code changes, agents must review these source-of-truth docs in this order:

1. `docs/PRODUCT.md`
   - Product truth, scope boundaries, user priorities, and the "Golden Path."
2. `docs/DOCUMENTATION_AUTHORITY.md` and `docs/specs/argus-minimum-viable-ecosystem-experience.md`
   - Document ownership, approved experience, unresolved decisions, and package reconciliation.
3. `docs/ARCHITECTURE.md`
   - System boundaries, stateful vs stateless responsibilities, service ownership, and deployment model.
4. `docs/API_CONTRACT.md`
   - Frontend/backend contract, endpoint shapes, request/response truth, and auth/profile behavior.
5. `docs/DATA_MODEL.md`
   - Persistence truth, entities, ownership rules, and RLS expectations.
6. `.agent/designs/argus/DESIGN.md`
   - Visual system, preserved chat interaction details, and ecosystem design boundaries.

> [!IMPORTANT]
> Read each document within its declared scope. The MVEE owns approved product
> experience; technical docs retain existing contracts and technical intent.
> Resolve contradictions before changing the affected contract. Do not infer
> new APIs, migrations, permission models, or shipped capabilities from vision text.

# 🧠 The Split-Brain Rule (Founder-Locked 2026-08-12)

**Ask of every change: who else holds this fact, and what forces them to agree?**

This is the single question that generates most of Argus's defects. Not "is it
tested." A duplicated fact that is tested is still duplicated; the test merely
pins today's agreement, and the copies drift the Tuesday someone touches one.

Ten defects found on 2026-08-12, the day Argus first had real users, were all
one shape: the same fact living in two places with nothing forcing them to
agree.

| Defect | The two brains |
| :--- | :--- |
| #483 | The turn summary knows the asset; the missing-fields check does not |
| #475 | `argus-api` caches market data 12 hours; `argus-backtests` does not cache |
| #455 | `recurring_contribution or starting_capital`, one field standing in for another |
| #480 | Guest identity and permanent identity, so a signup reads as an email change |
| #453 | The interpreter's raw value and the typed projection it should have become |
| #459 | Supabase's dashboard owns 13 email templates; our code owns a 14th |
| #470 | Render declared `arguschat.ai`; the repo declared `onrender.com` |
| #438 | A flag in the release profile that `render.yaml` never declared |
| n/a | The em dash rule in `.agent/rules`, enforced in one prompt out of many |
| n/a | A test asserting a two-service deploy step while three services were live |

None were regressions. Every one had existed for weeks and had simply never
been executed by a person.

## How to satisfy it

**One owner, everything else derives.** Not two implementations kept in sync,
and not a test asserting they match. A single source that others read.

Worked examples in this repo:

- PR #477 clamps the data window inside the shared resolution that both
  preflight and worker call, so they cannot disagree.
- PR #446 **deleted** `user_phrase` rather than giving it a language parameter,
  so the domain layer can no longer format prose at all.
- PR #472 introduced one shared `LOCAL_QA_CAPTCHA_TOKEN` rather than a second
  literal.
- PR #443 needed twelve review rounds because each one moved the guard to a
  better place while the truth it checked stayed split across the route's reads,
  the transcript, and the job tables. Only "one liveness oracle every reader
  derives from" could ever have worked.

## The tells

Reach for this rule the moment you see any of these:

- A fallback like `a or b`, which makes one value silently become another.
- A second cache, a second config file, or a second template store.
- A rule written in prose that some code paths enforce and others do not.
- A test that asserts two things match, rather than a structure that makes a
  mismatch unrepresentable.
- Any fact that lives both in this repo and in a dashboard nobody diffs.

## The related rule

Fix the macro pattern, not the flagged line, and treat recurrence as proof the
previous fix was at the wrong altitude. Two rounds on one theme is the trigger,
not three. **The tell is a fix that enumerates:** adding the fourth field or the
third known-bad string means the next unenumerated case is already waiting.

# 🎯 Product Direction

The [MVEE](../../docs/specs/argus-minimum-viable-ecosystem-experience.md) owns the
approved audience, ecosystem surfaces, ingestion, personal/household experience,
and boundaries. [PRODUCT.md](../../docs/PRODUCT.md) connects that direction to
capabilities already present.

Do not use chat-primary identity, a first-backtest activation requirement, or
PWA-only scope as requirements for the pivot. Preserve existing chat and
simulation behavior while implementing only the explicitly assigned scope.

# ⚙️ Canonical Current Constraints

- **Same-Asset Simulations Only**: Runs must be 100% Equity, 100% Crypto, or
  100% Currency Pair.
- **Default Benchmarks**: Equity -> `SPY`, Crypto -> `BTC`, Currency Pair ->
  the tested pair.
- **Logic**: Long-only, equal-weight multi-symbol runs.
- **Limits**: Max 5 symbols per run.
- **Localization**: Static UI must support English (`en`) and Spanish (`es-419`).
- **Organization**: Legacy Collection rows may contain mixed themes/assets, but no
  current Collection surface creates or manages them; runs may not mix asset classes.

# 🚀 Implementation Decisions

Start from the assigned user outcome, preserve API/data correctness and runtime
trust, and keep the experience simple on phones. The MVEE is not an ordered
engineering backlog. Resolve the relevant open technical contracts before
implementing a new financial-record or household capability.

---

# Agent Quality Pillars

This is the canonical definition of the four pillars. `docs/ARCHITECTURE.md` and
`docs/specs/private-alpha-next-roadmap.md` point here and must not restate them —
one source, so they cannot drift.

Use these pillars as a quality lens for roadmap work, subagent prompts, reviews,
and slice specs. They are not automatic release blockers unless the active
roadmap, runbook, or founder explicitly turns one into a gate. One clause is
already a gate: the Evaluation pillar's "evaluate the full turn path" is enforced
for interpreter-facing changes by the interpreter-facing live gate in the roadmap
under "Standing release discipline".

- **Intelligence**: Keep context anchored to Argus-owned artifacts such as
  conversations, backtest runs, Idea/IdeaVersion records, EvidenceArtifacts,
  DecisionNotes, and future user-confirmed MemoryRecords. LLMs interpret and
  voice responses; canonical records own durable facts.
- **Evaluation**: Judge assistant quality at the session level, not only by
  isolated prose. Important evals should inspect the user-visible response plus
  the hidden structured path: interpretation, tool/fact sources, artifact ids,
  UI state, recovery, cost, and latency when relevant.
- **Platform**: Prefer shared typed contracts, reusable runtime services,
  correlation ids, feature flags, and append-only operational evidence over
  one-off feature plumbing. New platform machinery earns its place only when it
  protects the chat/backtest/evidence loop.
- **User Experience**: Preserve conversational continuity and use the MVEE for
  ecosystem surface ownership. Direct controls should exist where they reduce
  friction. UI must show assumptions, preserve continuity, avoid invented backend facts, and make unsupported behavior clear
  without blaming the user.

Document and execution ownership lives in `docs/DOCUMENTATION_AUTHORITY.md`.
The decision memo is historical rationale, not a competing product authority.

# 🧭 Current Direction and Assigned Work

When working from `codex/private-alpha-next` or a worker branch, read the MVEE
for approved experience and the explicitly assigned package for execution.
Wave 1's existing package/stage/review rules remain applicable to assigned
Wave 1 work; see `docs/specs/wave-1/README.md`. Conflicting experience scope
must be reconciled as described in `docs/DOCUMENTATION_AUTHORITY.md`.

This documentation reconciliation neither creates a replacement execution
schedule nor cancels existing packages. The answers board retains carried
issues and operating history, but no longer owns conflicting product direction.
`docs/specs/private-alpha-next-roadmap.md` remains superseded P2 history and
contract reference. Archived boards retain their landed-work provenance.

Lanes are built production-ready end to end. There are no phases and no
incubation branches: work that is not ready for users ships behind a default-off
flag, not behind a staged branch.

For task onboarding, use `docs/DOCUMENTATION_AUTHORITY.md`, the MVEE, and the
assigned slice. Read relevant decision-memo sections only for historical or
technical rationale; do not treat them as new work assignments.

Use `docs/specs/private-alpha-ci-cd-sota.md`,
`docs/PRIVATE_LAUNCH_RUNBOOK.md`, and
`docs/release-manifests/TEMPLATE.md` as release-discipline references. They
still own smoke/canary/release-manifest expectations, but they no longer own
Private Alpha Next product sequencing.

Use `docs/specs/private-alpha-next-integration.md` as staging and branch-process
context. It records integration-lane guardrails, closed work, and branch-process
boundaries, but it should not override the authority map or assigned package.

Integration guardrails:

- Worker branches start from `codex/private-alpha-next`, not directly from
  `main`, unless the task is an urgent hotfix.
- At lane start, record the fetched `origin/codex/private-alpha-next` SHA as the
  lane's integration base. Before a READY claim, fetch integration again and
  record both the original base and current remote integration SHA.
- Reconciliation is one-way: merge current
  `origin/codex/private-alpha-next` into the worker branch. Never merge a worker
  branch into the canonical integration checkout by hand; worker delivery goes
  through its GitHub PR targeting `codex/private-alpha-next`.
- Once a worker branch is published or has browser, live-eval, or other
  exact-head evidence, do not rebase it. Use a normal integration merge so the
  reviewed/evidenced lineage remains inspectable. Do not merge `main` into an
  ordinary Private Alpha Next worker.
- When integration advanced after the worker's recorded base, compare the
  worker diff with the intervening integration diff and report semantic
  overlap by shared runtime owner, API/data contract, UI state owner, migration,
  environment variable, and directly affected tests—not merely Git conflict
  status. No textual conflict is not proof of behavioral independence.
- If there is no semantic overlap, preserve the lane's accepted evidence and
  rerun the normal exact-head deterministic/CI gates after reconciliation. If
  overlap exists, audit the overlap and rerun only the affected acceptance
  surface. Do not repeat paid evals, provider turns, real backtests, or broad
  browser matrices unless the overlap invalidates that specific evidence.
- Every final READY report must include the original integration base, current
  integration SHA, reconciliation merge SHA if any, overlap disposition,
  evidence retained or invalidated, exact PR head, and terminal CI state.
- Visual and browser acceptance evidence must be durable. Commit the
  artifacts under `docs/reports/evidence/<issue-or-pr>/` in the lane's PR, or
  upload the images as GitHub attachments on the issue/PR comment that cites
  them. Local worktree paths or SHA-256 hashes alone are not durable
  evidence: a claim whose images exist only in a local folder is not closed.
  Evidence must be captured at the exact head it vouches for; if the head
  moves afterward, re-capture or explicitly re-validate.
- Before a READY claim, run `scripts/check_modularity_budget.py` against the
  would-be merged tree (after the one-way reconciliation merge, or via
  `git merge-tree` with current integration), not only against the worker
  branch. Modularity budgets are a shared pool: two individually green
  branches can exceed a watched file's limit when combined, and the violation
  only exists on the merged result.
- Write the terminal audit only after the final Codex review has returned,
  and record that review's outcome in it. An audit that races an in-flight
  review request can be truthful for minutes and stale on arrival; review
  responses may arrive as inline threads without a summary comment, so check
  the PR's unresolved-thread count, not just for a bot comment.
- A review loop terminates when one review pass scoped to the latest fix's
  delta returns clean and the PR's unresolved-thread count is zero. Do not
  re-request review on an unchanged head, and do not let unchanged code
  become a new source of findings to keep a loop alive. Findings that arrive
  after the terminal state are either new scope — spin them out to an owned
  issue — or declined with one line of rationale; neither reopens the loop.
- Behavioral acceptance evidence for strategy-surface changes must span the
  supported strategy-shape space, not one canonical shape. Include at least
  one non-buy-and-hold strategy (for example DCA with an explicit
  `recurring_contribution`, or an indicator-driven template) unless the
  surface is provably strategy-agnostic. This is a macro rule: as new
  strategy shapes ship, acceptance evidence diversifies with them instead of
  standardizing on the oldest, fastest-to-drive shape. Facts most likely to
  be dropped by a defect (contribution cadence, indicator parameters,
  modeled costs) deserve evidence before facts that rarely break (dates,
  capital).
- Test suites must scale by construction, not duplication. Prefer shared
  fixtures, factories, and pytest parametrization over copy-pasted cases
  with hardcoded values; derive expected values from the same canonical
  constants and builders the code under test uses instead of repeating magic
  literals; use Faker for incidental data. Hardcoded fixture values that
  encode convenient fictions — weekend trading days, always-present
  fractional seconds, a single strategy shape — are how green suites hide
  real breakage: fixture realism is part of test correctness. Style details
  live in `.agent/rules/testing.md`; this bullet governs when suites grow.
- After the founder merges a worker PR, the active agent should run
  `.agent/workflows/integration-landing.md` if its checkout and GitHub authority
  permit it. A cloud agent may perform that workflow; the local
  `argus-integration-landing` skill is helpful but not required. If the agent
  cannot complete the landing workflow, it must post the following conspicuous
  handoff once in both its final response and the merged PR when PR commenting
  is available:

  ```text
  🚨🚨🚨 FOUNDER ACTION REQUIRED — INTEGRATION LANDING NOT RUN 🚨🚨🚨
  PR #<number> merged as <sha>, but roadmap/issues/env parity and exact-head
  integration verification are still pending. Run the Argus integration
  landing workflow from the canonical codex/private-alpha-next checkout.
  ```
- `codex/private-alpha-next` is the clean integration gate. Quarantine branches
  such as `codex/private-alpha-next-quarantine-fc231e8` and
  `codex/private-alpha-next-p2.1-quarantine` are read-only reference material
  for product direction, UI salvage, tests, and anti-pattern evidence unless
  the founder explicitly approves a surgical promotion.
- Do not broad cherry-pick or merge runtime code from quarantine into the clean
  integration branch. Reintegrate in small, reviewable, revertable slices.
- Jules work is decommissioned for the near term. Do not create or maintain
  `jules/**` branches, `codex/private-alpha-next-jules-intake`, or Jules intake
  PRs unless the founder explicitly reactivates that workflow.
- External async implementation agents, if reintroduced later, must work from
  a fresh founder-approved delegation model and must not push product code
  directly to `main` or `codex/private-alpha-next`. After a founder-confirmed
  merge, an agent explicitly assigned the repository-owned integration-landing
  workflow may push only its bounded documentation/configuration housekeeping
  directly to `codex/private-alpha-next`.
- Codex reviews worker diffs before merging or cherry-picking them into the
  integration branch.
- Apply review proportionality to local, cloud, subagent, acceptance, and
  pre-merge review. Before changing code, confirm that the finding is real,
  reachable, and relevant to the active lane; weigh its severity, likelihood,
  affected users or artifacts, and risk to correctness, security, privacy,
  evidence integrity, or durable state against the complexity the fix adds.
  Choose the smallest safe fix. After implementation, reassess the actual diff
  and remove or simplify machinery the validated finding does not justify.
  Discard speculative or disproportionate scope, and revisit only risk surfaces
  materially changed by the latest fix; unchanged code must not become a new
  source of requirements merely to continue a review loop. If the smallest safe
  fix for a confirmed correctness, security, privacy, evidence-integrity, or
  durable-state requirement exceeds the lane, escalate instead of weakening or
  waiving the requirement because the fix is difficult.
- For Argus multi-agent work, the main Codex thread is the release captain and
  owns subagent cleanup. Every spawned agent must have a bounded goal, expected
  output, and cleanup expectation. After the run, the parent agent must
  summarize outputs, close/archive completed agents, and leave open only agents
  with an explicit active follow-up.
- For horizon-spec work, follow the AI-native engineering cadence: delegate
  code-aware planning/scoping, first-pass implementation, test generation,
  review, and documentation support to bounded agents, but keep prioritization,
  sequencing, architecture tradeoffs, release readiness, and merge/deploy
  ownership with the main Codex release captain and founder. Before
  implementation, the release captain should write or activate a Goal that names
  the outcome, verification surface, constraints, no-touch areas, and stop
  conditions. Subagent prompts must include lane-specific goals with allowed
  surfaces, forbidden surfaces, expected output, verification evidence, and
  cleanup expectation.
- CI/CD SOTA warmup and canary evidence should be gathered for release
  candidates against the exact candidate SHA. For local reintegration slices,
  pass focused backend/frontend tests and live browser QA before promotion to
  `codex/private-alpha-next`; use Render canary evidence when preparing a
  tester-facing or deploy-facing checkpoint.
- For eval work, read `tests/evals/README.md` "Test Tiers" before running
  checks. Use the mocked harness for every change, reserve live eval for the
  three documented gates, and treat Browser QA as real-API work because every
  turn spends tokens.
- For release checkpoints, CI/CD SOTA warmup and canary evidence must be
  gathered against the branch-deployed staging/private-alpha Render validation surface
  for the exact candidate SHA. Do not treat merge to `main` as a prerequisite for canary evidence; `main` is the later promotion target after founder approval.
- Production deploys remain manual and founder-directed.
- Perplexity Research Lab, generic memory/RAG, public excerpts, voice provider
  integration, and broker/export execution remain design-only until the roadmap
  explicitly starts those slices.
- The old `codex/private-alpha-readiness-clean` coordination note now lives at
  `docs/archive/private-alpha-readiness-orchestration.md` as historical
  branch-specific context. Do not treat it as the active command source for
  `codex/private-alpha-next`.

---

# 🧭 Historical Checkpoint: Private Alpha Conversation Trust

When working on private-alpha conversation trust branches, including
`codex/private-alpha-conversation-trust` and follow-up branches such as
`codex/private-alpha-ux-trust-followups`, use
`docs/archive/private-alpha-conversation-trust.md` as the milestone source of
truth for historical context. This milestone hardened the current private-alpha
chat/backtest loop; it does not implement the Perplexity Research Lab thesis.

This is a completed checkpoint, not the active command document for
`codex/private-alpha-next`. For current document ownership and assigned-work
entry points, use `docs/DOCUMENTATION_AUTHORITY.md` after the canon docs.
For release-gate, canary, and manifest work, use
`docs/specs/private-alpha-ci-cd-sota.md` as the release-discipline reference.

Milestone guardrails:

- Re-enable fast CI and local verification without automatic production deploys.
- Unify confirmation, queued/running job, result, and assistant-turn actions as
  one coherent artifact lifecycle.
- Keep feedback/retry/more-menu actions structured and turn-scoped; do not use
  prose matching to infer retry behavior.
- Add out-of-focus chat attention state without inventing backend facts in the
  frontend.
- Treat Quick take, Explain result, and Try next as distinct result surfaces:
  the card owns numerical reporting, Quick take tells the first-glance story,
  and Explain result develops the fact-grounded holding experience and
  tradeoffs without repeating it. A supported next historical test may follow
  naturally in the prose; Try next actions remain structured experiments,
  not investment advice or a duplicated readout.
- Do not restore "copy conversation link" or "share conversation id" as a
  pseudo-share action. Until the public excerpt feature exists, the header menu
  should expose only real owner actions such as rename, pin, and delete.
- When public conversation excerpts are implemented, they must be immutable,
  sanitized snapshots behind owner-only create/revoke and an unguessable public
  slug. Do not expose source conversation ids, route receipts, provider/model
  metadata, retry payloads, or direct anon table access.
- Keep Perplexity/Research Lab work as design-only unless a later milestone
  explicitly starts that implementation. The preserved thesis lives in
  `docs/archive/research-lab-thesis.md`.

Never let UI polish violate the runtime principles below: the frontend renders
backend-provided artifacts, LangGraph remains the only chat brain, and
deterministic result prose must not become the normal happy-path Argus voice.

---

# 🧭 Argus Philosophy & Runtime Principles

The MVEE owns the approved ecosystem experience. Preserve the existing
assistant's ability to explain finance and test investing ideas while staying
honest about assumptions, limitations, and supported execution. The runtime
principles below remain safeguards for the existing system, not a technical
design for the new ecosystem.

## Product Philosophy

- **Conversation carries forward**: Preserve chat, its continuity, and progressive disclosure. The MVEE defines its role alongside Home, Accounts, Plan, Search, and Updates; direct input is a supported experience, not a competing chat brain.
- **The backtesting engine is critical infrastructure**: Results must be reproducible, grounded in real engine outputs, and presented with clear assumptions.
- **Simplicity within the ecosystem**: Keep each assigned journey understandable and complete across the relevant surfaces; do not force every user job into a historical test.
- **Trust through clarity**: Never hide defaults, unsupported behavior, missing data, or asset-class constraints. Explain limitations in product language, not provider plumbing.
- **Beginner-friendly by default**: Use plain language, small follow-up choices, and honest educational context. Avoid trading-terminal complexity unless the user explicitly asks for more depth.
- **Conversation continuity**: Confirmation cards, result cards, historical legacy links, and follow-up actions must remain attached to the conversation flow and hydrate correctly after reload.

## Runtime Migration Principles

These principles come from the recent modular monolith / LangGraph migration plans in `docs/superpowers/plans/` and must not regress:

- **LLM-first interpretation**: Normal user language must reach the structured LLM interpreter before routing decisions. Do not add regex, hardcoded language gates, localized stop-word or alias tables, display-label token matching, or legacy NLU shortcuts before the interpreter. Offline fallback choices must use typed action metadata such as button ids or `replacement_values`, not per-language phrasebooks.
- **Deterministic guardrails after interpretation**: Code validates facts the LLM cannot own: asset resolution, provider availability, same-asset constraints, max symbol limits, date/data windows, executable indicator support, benchmark defaults, and required fields.
- **Model-facing text is shared and measured**: The interpreter's system prompt and the response schema's field descriptions steer every interpreted turn, so a change made for one surface moves behavior on all of them. PR #491 rewrote the prompt for a DCA change and regressed asset extraction, start-date preservation, and discovery routing; unit tests and CI stayed green because no unit test sends a message through a model. This text is therefore frozen against a committed scorecard (Never-Violate Standard 12). Prefer deterministic grounding after interpretation whenever code can own the fact; reach for prompt text only when it cannot.
- **Redundancy over an LLM read must be observable**: Where deterministic code compensates for an unreliable model read, such as taking the union of two independent structured reads of the same turn, it must record when it fires. An unmeasured compensation layer hides model decay instead of surfacing it.
- **One active chat brain**: The LangGraph runtime is the only active conversational runtime. Do not restore or recreate a parallel legacy orchestrator, state machine, or second intent taxonomy.
- **LangGraph owns runtime memory**: Runtime thread state belongs in the LangGraph checkpointer using `thread_id == conversation_id`. Supabase owns current product persistence such as messages, conversations, backtest runs, feedback, and usage counters, plus read-compatible legacy Strategy and Collection rows.
- **Supabase product records are durable artifacts**: Messages store assistant/user text and structured metadata. Backtest runs store immutable result truth. Legacy Strategy and Collection records remain readable, but no current writer creates or manages them.
- **Canonical SSE is data-only**: Production chat streaming should emit canonical `data: {"type": ...}` frames: `stage_start`, `token`, `stage_outcome`, `final`, then `[DONE]`. Legacy named `event:` parsing may be tolerated by the frontend during migration, but new backend paths should not depend on it.
- **Thin FastAPI routers**: API routes perform auth, quota checks, request validation, transport, persistence, and error shaping. They must not become a second conversational orchestrator.
- **Frontend renders, it does not invent**: The web app renders backend-provided stages, cards, actions, and persisted metadata. It should not fake progress states, reconstruct strategies from text, or infer hidden run context.
- **Composer mentions are provenance, not shortcuts around validation**: The `@` tool must use provider-backed asset discovery and the supported indicator catalog, not a tiny static menu. Selected mentions help bound ambiguous references for the backend, but normal LLM interpretation and backend validation still own executable meaning. Browser-session discovery caching is acceptable; durable Supabase discovery/market-data caches require explicit schema, freshness, and invalidation design.
- **No Alpha RAG/vector overreach**: Do not add embeddings, pgvector, semantic memory, or agentic RAG for the launch chat/backtest loop. Use provider catalogs, structured state, run metadata, typed idea/evidence records, and text search until a concrete Beta need exists.
- **Provider details stay internal**: Users should hear capability truth ("I can test BTC over that period" or "that data range is not available for this instrument"), not vendor-specific implementation details unless the product explicitly decides otherwise.
- **Research informs, Argus providers execute (truth-boundary lock, same standing as S10)**: quoting research-grounded prices, figures, or valuations to the reader is correct and encouraged, but no `finance_search` value may ever reach a simulation. A test launched from a research answer re-grounds through Argus market-data providers, research turns never write strategy/confirmation/execution state, and the shared research cache is public-market data only, never reusable for anything user-scoped. Guarded by `tests/research/test_research_truth_boundary.py`.

---

## 🛡️ Rules (`.agent/rules/`) — Always-Follow Guidelines

| Rule                  | Scope                                 | Purpose                                                                       |
| :-------------------- | :------------------------------------ | :---------------------------------------------------------------------------- |
| `coding-standards.md` | `src/**/*.py`, `web/**/*.ts`          | Python loguru/types, TypeScript zod/react-hook-form, API contract sync        |
| `testing.md`          | `tests/**/*.py`, `web/__tests__/**/*` | TDD-first, 63% coverage, Faker mock data, frontend integration                |
| `git-workflow.md`     | All                                   | Conventional commits, monorepo branch naming, feature flags, API contract PRs |
| `performance.md`      | `src/argus/analysis/**`, `web/**`     | Numba <50ms/analytic, <3s backtest, <30s build, Bun hot-reload                |
| `workspace.md`        | All                                   | Monorepo layout, Poetry + Bun, env separation, mock data toggle               |

---

## 🧠 Skills (`.agent/skills/`) — Domain Knowledge

| Skill                                | When to Use                                                                 |
| :----------------------------------- | :-------------------------------------------------------------------------- |
| `coding-standards/`                  | Python/TypeScript style, logging, validation patterns                       |
| `numba-patterns/`                    | JIT compilation, warmup, pure-math constraints                              |
| `backend-patterns/`                  | API-first design, sync execution, error responses, caching                  |
| `testing-patterns/`                  | pytest, TDD workflow, coverage strategy, rate-limit tests                   |
| `frontend-patterns/`                 | React/Next.js, Argus design system, component patterns, form validation    |
| `security-review/`                   | RLS policies, JWT handling, Supabase auth, Alpaca secrets                   |
| `supabase/`                          | Supabase CLI, Auth, Edge Functions, and migration workflows                 |
| `supabase-postgres-best-practices/`  | Performance optimization, GIN indexing, and RLS bottlenecks                 |
| `mock-data-patterns/`                | Faker generators, mock API endpoints, toggle mechanism                      |
| `database-patterns/`                 | Supabase migrations, RLS immutability, quota management                     |
| `monorepo-patterns/`                 | API contract sync, Bun + Poetry coordination                                |
| `design-taste-frontend/`             | High-end UI/UX, CSS hardware acceleration, metric-based design              |
| `emil-design-eng/`                   | UI polish, animation physics, and micro-interaction details                 |
| `react-components/`                  | Stitch-to-React conversion, modular component architecture                  |
| `redesign-existing-projects/`        | Upgrading legacy UI to premium, anti-generic standards                      |
| `shadcn-ui/`                         | Shadcn component integration, customization, and best practices             |
| `stitch-design/`                     | Stitch MCP orchestration, prompt enhancement, screen generation             |
| `stitch-design-taste/`               | Semantic design system enforcement, premium aesthetics                      |
| `stitch-loop/`                       | Iterative Baton-Passing loop for rapid UI development                       |
| `rag-architect/`                    | RAG/LLM agent architecture, DeepSeek R1/Qwen integration                    |
| `database-schema-designer/`         | Precision SQL migrations, RLS policies, and Phase C accounting              |
| `apple-hig-expert/`                  | Premium UI/UX aesthetics, Argus/Apple-grade physics                         |
| `skill-security-auditor/`           | Automated security gating for agent skills and external plugins               |
| `playwright-pro/`                   | Advanced E2E testing framework, target 63% coverage                          |
| `argus-experience-audit/`           | Guest/signed-in checkpoint audits, cloud QA, and locked evidence packs       |
| `senior-architect/`                 | Principal-level system guidance and Institutional-grade reliability         |
| `saas-metrics-coach/`               | Fintech quota throughput and monetization logic                              |

---

## ⚙️ Workflows (`.agent/workflows/`) — Command Reference

### Core Development

| Command      | Description                                             |
| :----------- | :------------------------------------------------------ |
| `/plan`      | Generate implementation plan before changes (API-first) |
| `/implement` | TDD: write test → implement → verify (mock data ready)  |
| `/fix`       | Fix a failing test (max 3 iterations, verify mock API)  |

### Quality & Release

| Command   | Description                                                                  |
| :-------- | :--------------------------------------------------------------------------- |
| `/review` | Code review: standards, security, design audits                              |
| `/verify` | Full suite: pytest + Bun lint + coverage check (63%+) + backtest perf (<3s)  |
| `/pr`     | Create PR: include API contract link if schema changed, mark scope (api/web) |
| `/perf`   | Benchmark: Numba analysis, backtest latency, Bun build time                  |
| `/integration-landing` | Reconcile a confirmed integration merge, docs, issues, env templates, and exact-head CI |

### Discovery & Ops

| Command  | Description                                                               |
| :------- | :------------------------------------------------------------------------ |
| `/issue` | Diagnose: trace backend/frontend, check with mock API first               |
| `/learn` | Extract lessons: what patterns worked, metrics improved, blockers removed |

---

## 🔧 Scripts (`.agent/scripts/github/`) — GitHub Context

| Script                 | Purpose                                       |
| :--------------------- | :-------------------------------------------- |
| `batch_get_issues.sh`  | Fetch multiple issues in one go               |
| `get_issue_details.sh` | Fetch + format a single issue                 |
| `parse_issues.py`      | Parse issue JSON → readable agent context     |
| `parse_pr_comments.py` | Parse PR review comments → prioritized report |

Usage:

```bash
& "C:\Program Files\Git\bin\bash.exe" ./.agent/scripts/github/batch_get_issues.sh 42 43 44
```

---

## 🚀 Quick Start (Local Development)

Argus supports two primary local scenarios. Choose the script first; do not
manually juggle backend mode flags for normal work.

### Local Environment Doctrine

- Python is pinned by `.python-version` (`3.10.x`; currently `3.10.20`).
  `.github/setup.sh` enforces the pinned runtime. A green run on Python 3.14 is
  not deployed-runtime evidence.
- Create Argus worktrees as siblings of the repo, never nested inside another
  Argus checkout. Nested worktrees can inherit a parent `.env` through dotenv
  upward search, silently turning mocked runs into live LLM/provider calls.
- Deterministic agent-runtime sweeps use
  `ARGUS_MARKET_DATA_PROVIDER_MODE=synthetic_unit_fixture` and no live provider
  keys. A clean mocked sweep should be seconds-scale; a run stretching into
  minutes means stop and check for leaked credentials or live provider paths.
- Local compute rule: local and dev-agent backtests run in-process on the
  developer machine. Never set `ARGUS_BACKTEST_WORKFLOW_EXECUTION_ENABLED=true`
  or dispatch paid Render workflow tasks (`workflow_proof`,
  `run_backtest_job`) from local work without explicit founder authorization.
  Paid Render dispatch belongs to the hosted product, the scheduled canary,
  and promotion ceremonies; the mode scripts pin it off (dev hard-off, QA
  default-off with explicit pre-export opt-in).

### Release Acceptance Environment Parity

- Release-candidate acceptance runs on the local candidate stack: local
  Supabase (Docker) reset to the candidate schema, env overlay layered over
  untouched canonical files, real provider keys, captcha off. Never run
  `scripts/qa/write-local-env.sh` in the canonical checkout; it overwrites
  `.env` and `web/.env.local`.
- Acceptance includes an environment-parity pass: `.env.example` must be at
  par with every variable the code reads, and cross-checked against the
  integration `.env`. Any variable intended live on hosted services must be
  declared in the release contract (release profile, `render.yaml`, and the
  `argus-env.sh` contract arrays) before promotion. The promotion agent
  derives "what needs setting on hosted" from that contract; discovering
  undeclared live variables at a promotion red gate means acceptance missed
  this step.

### Worktree Environment Contract

The worktree checked out on `codex/private-alpha-next` owns the canonical local
`.env` and `web/.env.local`. Codex worktree setup automatically runs
`.github/setup.sh`, which delegates to `.github/setup-worktree-env.sh` and links
missing worker environment files to that canonical source. Existing regular
files and links to another source are preserved because they may be intentional
lane-local configuration.

For a runtime worktree Phase 0, run the idempotent setup and read-only topology
check below. For a docs-only assignment, skip setup and shared environment
mutations. Read topology only if the assigned check needs it. Do not repair a
shared environment without its owner:

```bash
bash .github/setup-worktree-env.sh "$PWD"
bash .github/setup-worktree-env.sh --check "$PWD"
```

The check reports topology only and never prints values:

- `canonical-linked`: the worker uses the shared integration file.
- `canonical-source`: this is the integration worktree's regular source file.
- `worktree-local`: the lane intentionally owns a regular local file.
- `missing` or `conflicting-link`: stop and correct the environment topology
  before running services, tests, or provider-backed QA.

Shared links are not safe write targets. Never rewrite a linked `.env` or
`web/.env.local` with `cat >`, shell redirection, `sed -i`, or similar in-place
writes. If every lane needs a new value, update the canonical integration file
once. If only one launched process needs an override, inject it at runtime. If
a disposable local-Supabase lane needs generated files, use
`scripts/qa/write-local-env.sh`; it atomically detaches that lane's links before
writing regular worktree-local files. Never print, inspect, or persist secret
values in task output. See [`.github/WORKTREE_CLEANUP.md`](../../.github/WORKTREE_CLEANUP.md)
for the detailed lifecycle and recovery rules.

### Fast Iteration (Dev Mode)
**Use this for:** Building features, debugging, UI work, isolated testing — no persistence needed.

1. **Initialize workspace** (one time):
   ```bash
   .github/setup.sh
   ```

2. **Activate Dev Mode** (Terminal 1: Backend):
   ```bash
   .github/dev.sh
   ```
   This sources `.env` if present, then overrides backend runtime flags for fast
   synthetic-data development.

3. **Start frontend** (Terminal 2):
   ```bash
   cd web && bun run dev
   ```

4. **Frontend env**: for fast mock-auth dev, set in `web/.env.local`:
   ```bash
   NEXT_PUBLIC_MOCK_AUTH=true
   NEXT_PUBLIC_ARGUS_API_URL=http://127.0.0.1:8000/api/v1
   ```

5. **Access**: Open `http://localhost:3000` → Auto-logs in as "Mock Developer"

6. **Build + test**:
   ```bash
   poetry run pytest tests/
   cd web && bun test
   ```

For the private-alpha agent-runtime regression gate, run the hermetic sweep with
provider keys blanked:

```bash
OPENROUTER_API_KEY= ALPACA_API_KEY= ALPACA_SECRET_KEY= \
ARGUS_MARKET_DATA_PROVIDER_MODE=synthetic_unit_fixture \
poetry run pytest tests/agent_runtime tests/test_spine_guardrails.py -q --no-cov
```

### Production Parity (QA Mode)
**Use this for:** End-to-end testing, launch validation, browser QA matrix, release verification.

1. **Initialize workspace** (one time):
   ```bash
   .github/setup.sh
   ```
   Your `.env` should already contain real Supabase credentials and API keys.

2. **Activate QA Mode** (Terminal 1: Backend):
   ```bash
   .github/qa.sh
   ```
   This requires real Supabase, OpenRouter, Alpaca, and `DATABASE_URL` values in
   `.env`, then overrides backend runtime flags for strict production-parity QA.

3. **Start frontend** (Terminal 2):
   ```bash
   cd web && bun run dev
   ```

   For real auth QA, set in `web/.env.local`:
   ```bash
   NEXT_PUBLIC_MOCK_AUTH=false
   NEXT_PUBLIC_ARGUS_API_URL=http://127.0.0.1:8000/api/v1
   ```

4. **Run full QA suite**:
   ```bash
   # Backend contract & runtime tests
   poetry run pytest tests/agent_runtime/ -q

   # Frontend integration
   cd web && bun test __tests__/

   # Browser QA (if Playwright is set up)
   bun run test:e2e
   ```

### What Each Mode Script Does

**`.github/dev.sh`** sets:
- `ARGUS_PERSISTENCE_MODE=memory` — Ephemeral, no database writes
- `ARGUS_DEV_MEMORY_FALLBACK=true` — Tolerant (failures don't block the chat)
- `ARGUS_MARKET_DATA_PROVIDER_MODE=synthetic_unit_fixture` — Hardcoded test assets (no API calls)
- `ARGUS_CHECKPOINTER_MODE=memory` — No checkpoint persistence
- `ARGUS_MOCK_AUTH=true` — Backend mock auth for local development

**`.github/qa.sh`** sets:
- `ARGUS_PERSISTENCE_MODE=supabase` — Durable, all writes go to Supabase
- `ARGUS_DEV_MEMORY_FALLBACK=false` — Strict (errors propagate for debugging)
- `ARGUS_MARKET_DATA_PROVIDER_MODE=live_provider` — Real provider-backed asset resolution
- `ARGUS_CHECKPOINTER_MODE=postgres` — Runtime recovery/reload through Supabase Postgres
- `ARGUS_MOCK_AUTH=false` — Real backend auth validation

**Your `.env` stays mostly constant** — It stores credentials and safe defaults.
The scripts are authoritative for backend mode flags, so you should not need to
remember the right `ARGUS_*` combination for dev vs QA.

**Recorded provider fixtures** are not the default manual QA path. They are for
deterministic provider tests or CI when `ARGUS_ASSET_FIXTURE_PATH` points to a
provider-shaped asset catalog snapshot. Until such a snapshot is generated and
versioned, manual QA should use `live_provider` so symbol recognition exercises
the same provider-backed resolution path production will use.

### Feature Flags (All Private-Alpha)
Omnisearch is enabled by default and should only be disabled for a targeted
regression check:

- Once the founder accepts and merges a feature as part of the normal Argus
  product shape, its runtime default is **on**. Retain its flag as an emergency
  kill switch, not as an opt-in gate.
- Local/runtime defaults and Render activation are separate concerns. A merged
  default-on feature still requires its documented Render configuration and
  exact-SHA canary before tester exposure.

```bash
NEXT_PUBLIC_OMNISEARCH_ENABLED=true
NEXT_PUBLIC_RESEARCH_RAIL_ENABLED=false
```

### Frontend Environment (web/.env.local)
Create `web/.env.local` with frontend-specific settings:
```bash
cp web/.env.local.example web/.env.local
```

For fast Dev Mode:
```bash
NEXT_PUBLIC_MOCK_AUTH=true
NEXT_PUBLIC_ARGUS_API_URL=http://127.0.0.1:8000/api/v1
NEXT_PUBLIC_RESEARCH_RAIL_ENABLED=false
```

For QA Mode with real Supabase auth:
```bash
NEXT_PUBLIC_MOCK_AUTH=false
NEXT_PUBLIC_ARGUS_API_URL=http://127.0.0.1:8000/api/v1
NEXT_PUBLIC_RESEARCH_RAIL_ENABLED=false
```

---

## 📖 Documentation

- **Product Truth**: [`docs/PRODUCT.md`](../../docs/PRODUCT.md)
- **Architecture**: [`docs/ARCHITECTURE.md`](../../docs/ARCHITECTURE.md)
- **API Contract**: [`docs/API_CONTRACT.md`](../../docs/API_CONTRACT.md)
- **Data Model**: [`docs/DATA_MODEL.md`](../../docs/DATA_MODEL.md)
- **Design System**: [`.agent/designs/argus/DESIGN.md`](../../.agent/designs/argus/DESIGN.md)
- **OpenAPI Spec**: [`docs/api/openapi.yaml`](../../docs/api/openapi.yaml)
- **Archived Jules Framework**: [`.agent/.jules/README.md`](../../.agent/.jules/README.md)

### Documentation Classes

- **Authority map**: `docs/DOCUMENTATION_AUTHORITY.md` owns document status,
  reading order, and conflict resolution. The MVEE owns approved experience;
  the canon technical docs retain their respective contract scope.
- **Assigned execution**: use the explicitly assigned package and its gates.
  Wave 1 packages remain scoped specifications, subject to MVEE reconciliation;
  this docs-only change does not create a new implementation queue.
- **Historical rationale**: the answers board, pivot draft, and decision memo
  retain useful research, carried issues, and technical history. Their earlier
  product framing does not supersede the MVEE.
- **Release-discipline references**: `docs/specs/private-alpha-ci-cd-sota.md`,
  `docs/PRIVATE_LAUNCH_RUNBOOK.md`, and
  `docs/release-manifests/TEMPLATE.md` own release gates, canaries, manifests,
  and deployment discipline. They do not own the current product roadmap.
- **Staging/process context**: `docs/specs/private-alpha-next-integration.md`
  explains the integration branch, closed work, and branch process. Use it for
  context, not as the active product roadmap.
- **Future/design-only docs**: Research Lab, voice, public excerpt, broker,
  memory-control, and evidence-aware idea-loop specs remain design/reference
  material until an explicit assignment starts a bounded slice under the authority map.
- **Active milestone/spec docs**: files under `docs/specs/` that explicitly
  name the current branch or milestone. Use them for scoped execution details
  after reading canon docs.
- **Historical plans**: older closure plans and `docs/superpowers/plans/*`
  files are evidence and context, not current source of truth unless an active
  milestone doc points back to them.

### 🛡️ Developer Identity: Mock Auth Mode
To bypass the Supabase auth wall in fast Dev Mode, set the following frontend
environment variable:

`NEXT_PUBLIC_MOCK_AUTH=true`

Keep `NEXT_PUBLIC_MOCK_AUTH=false` for QA Mode when validating signup, login,
logout, persistence, reload, and private-alpha allowlist behavior.

**Benefits for Agents:**
- **Auth Bypass**: Instantly logs in as "Mock Developer" (mock user).
- **Sticky Sessions**: Automatically hydrated session across all refreshes.
- **Access Control**: Grants access to current routes such as `/chat` and `/settings` without OAuth.


---

## ⚙️ Architectural Patterns

### 1. Fail-Open Deterministic Fallback
Used for: LLM-backed features that must never block the chat

Pattern:
- Try LLM with bounded timeout (ThreadPoolExecutor)
- On timeout/failure → deterministic fallback
- Log failure but don't expose to user
- Route receipt captures outcome for ops

Example: `result_breakdown_message()` in src/argus/api/chat/breakdown.py

### 2. Task-Scoped Execution Budget
Used for: All OpenRouter calls

Pattern:
- Each task (interpretation, breakdown, naming) has own profile
- Profile controls: temperature, max_tokens, timeout_seconds, max_retries
- Same code path; different budgets based on task importance
- Route receipt captures latency, model, tier, token usage

Example: OPENROUTER_PROFILES in src/argus/llm/openrouter.py

### 3. Stage Result Contract
Used for: Runtime decision-making stages

Pattern:
- Stage returns StageResult(outcome: str, stage_patch: dict)
- Outcome drives routing (ready_to_confirm, needs_clarification, etc.)
- Patch contains only state mutations
- Stage is pure function of (state, contract)

Example: confirm_stage() in src/argus/agent_runtime/stages/confirm.py

### 4. Response Voice Contract
Used for: All assistant-facing prose

Pattern:
- Explicit tone contract defined in response_style.py
- Anti-patterns: dense PDF tone, metric dumps, generic lists, jargon
- Deterministic facts ground LLM language
- No raw enums or internal field names in user-facing text
- Result readouts interpret the card instead of restating its figures. A figure
  belongs in prose only when needed to explain a point, with its fact reference
  and the card's rounding. Accuracy rules guide writing silently; describe the
  experience in everyday language without explaining calculation safeguards.
  A supported next historical test may appear in the story without a "Try next"
  heading or experiment checklist. Quick take stays first-glance; Explain
  result adds depth without repeating it or reusing frame headings.
- Run facts alone own backtest figures. Quick take uses no search. Breakdown may
  add searched historical context with the sources Perplexity returns, including
  their dates when provided; it must not substitute web figures for run facts or
  imply unsupported causality. Its short, plain request receives labeled headline
  facts, never chart series, markers or internal field paths. Forecasts and
  investing advice remain outside both readouts.
- Readout acceptance keeps one light factual guard: declared run figure keys and
  values must match stored facts within display rounding. Missing references,
  repeated figures and optional source dates do not reject prose. Language,
  schema, empty-draft and provider failures still select the complete template;
  writing requirements are not enforced through per-occurrence or prose regex
  bookkeeping. The pending Breakdown frame shows localized working text.

Example: ARGUS_RESPONSE_STYLE_CONTRACT in src/argus/agent_runtime/response_style.py

### 5. Provider Mode Abstraction
Used for: Making asset/market data deterministic without HTTP mocking

Pattern:
- `ARGUS_MARKET_DATA_PROVIDER_MODE` controls data source.
- Modes:
  - `live_provider`: real provider catalog/data; default for manual QA and production-like validation.
  - `recorded_provider_fixture`: provider-shaped catalog snapshot; deterministic tests/CI only and requires `ARGUS_ASSET_FIXTURE_PATH`.
  - `synthetic_unit_fixture`: small hardcoded unit fixture; fast Dev Mode only.
- Code path unchanged; only data source changes.
- Enables deterministic testing with real code paths without making synthetic fixtures look like production truth.

Example: _asset_provider_mode() in src/argus/domain/market_data/assets.py

### 6. Capability Contract Pattern
Used for: Validating what's executable vs draft-only

Pattern:
- CapabilityContract class centralizes "can I execute this?"
- Returns ranked candidates, not binary yes/no
- Used by interpret → confirm → execute → capability Q&A
- Single source of truth across all surfaces

### 7. Semantic Integrity Rules
Used for: Preserving user intent across edits and defaults

Pattern:
- User-explicit constraints (dates, assets, cadence) are immutable
- Defaults only fill gaps, never overwrite user intent
- If constraint cannot be preserved → clarify, don't override
- For DCA: recurring_contribution is sacred once set

Example: conserve_semantic_constraints() in src/argus/agent_runtime/semantic_integrity.py

### 8. Anti-Pattern Checklist
Never do this:
- ❌ Regex/phrase gates before LLM interpretation
- ❌ Strategy name routing (use intent + capability contract)
- ❌ Parallel chat orchestrators (LangGraph is the only brain)
- ❌ Frontend prose inventing strategy state
- ❌ Raw enum/field names in assistant voice
- ❌ Unsupported causality from context packets
- ❌ Silent defaults overwriting user constraints
- ❌ Duplicate action surfaces (one button per action, owned by one component)
---

## 🛑 Never-Violate Standards

1. **API Contract First**: Update `docs/API_CONTRACT.md` before implementation PRs.
2. **Structured Logging**: Use `loguru` (backend) + React Query logs (frontend). No `print()`.
3. **TDD First**: Write failing test before fixing any bug.
4. **JIT Warmup**: Changes to `src/argus/analysis/` require `warmup_jit()` in tests.
5. **<3 Second Backtest**: Single-symbol backtest must execute in <3s.
6. **No Backend Secrets in Frontend**: Root `.env` (backend), `web/.env.local` (frontend).
7. **Use `temp/`**: Never dump scratch files in project root.
8. **Monorepo Coordination**: Backend + frontend must run together after `setup.sh`.
9. **Critical Findings Only**: Only PR/Journal critical improvements (security bugs, >20% perf gain).
10. **Postgres Performance**: All SQL/RLS must be audited against `postgres-best-practices`.
11. **Branch Sync & Goal Realignment**: Private Alpha Next workers must fetch
    `origin/codex/private-alpha-next`, reconcile it one-way into the worker, and
    re-verify the mission and affected evidence before completion. Do not rebase
    a published or evidenced lane, and do not use `main` as the ordinary worker
    base.
12. **Model-Facing Text Is Measured**: Prompt builders and Pydantic
    `Field(description=...)` in the eval-reachable tree are fingerprinted by
    `tests/test_interpreter_prompt_freeze.py`. Changing any of it requires a
    live measurement eval on the branch, its scorecard committed under
    `docs/reports/evidence/`, a case-by-case comparison against the scorecard
    named in `.agent/interpreter_prompt_fingerprint.json` showing no
    regression, and a regenerated fingerprint. One lane owns this surface at a
    time. See "Model-Facing Text" under Runtime Migration Principles.

---

# 🧠 Agent Decision Rules

Before implementing any feature, ask:
1. Is this aligned with `PRODUCT.md`?
2. Is this compatible with `API_CONTRACT.md`?
3. Does `DATA_MODEL.md` already define the source of truth?
4. Does this preserve `ARCHITECTURE.md` boundaries?
5. Does this fit `DESIGN.md` and the applicable MVEE experience?
6. Is this simpler than the alternative?

*If the answer to any of these is "No," pause and redesign.*

# 🎨 Frontend Guidance
- Prioritize mobile-friendly responsive chat UX.
- Use progressive disclosure to handle complexity.
- Avoid cluttered dashboards and dense data tables by default.
- Ensure all static UI strings are translatable (i18next).

# 🛠️ Backend Guidance
- Keep request handling stateless and reproducible.
- Treat Supabase as the canonical persistence layer.
- Enforce contract-first changes and strict rate limits.
- Provide graceful, RFC 9457-compliant error responses.

# ⚖️ If Docs Conflict
Use [documentation authority](../DOCUMENTATION_AUTHORITY.md) for scoped ownership.
The MVEE owns approved experience. PRODUCT owns current product availability.
API_CONTRACT, DATA_MODEL, ARCHITECTURE and the applicable DESIGN each own their
technical or platform contract. The decision log records later founder locks.
The execution manifest and explicit assignment own current work and action grants.
Existing code and release evidence prove implementation, not permission to expand scope.
Resolve a contradiction within its affected scope before changing that contract.

*Argus should feel modern, intelligent, simple, trustworthy, and fast — never intimidating.*

---

## Commit / Checkpoint Discipline

For multi-step or high-risk work, do not accumulate large uncommitted diffs.

Before starting:
- Check `git status`.
- Identify any user-owned changes and do not overwrite them.
- Use a branch/worktree for substantial work.

During implementation:
- Prefer atomic, single-purpose changes.
- After each coherent slice, run focused verification.
- If the slice is working, create a conventional commit checkpoint before moving to the next slice.
- Do not let runtime/UI work grow into 50-file uncommitted diffs unless explicitly approved.

For long plans:
- Each worker/slice should end with: tests run, browser smoke note if applicable, known caveats, and either a commit or a clear reason it remains uncommitted.

Never:
- Commit unrelated user changes.
- Hide broken work in a broad checkpoint.
- Use vague commit messages.
- Leave large exploratory diffs without explaining rollback risk.
