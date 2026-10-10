# Argus and Cuadrao agent startup

This is the shared startup index for Codex, Claude and Cursor. Read the linked
operating reference before implementation or review. It preserves the complete
repository instructions, examples, workflow catalog and environment guidance.
Keep this index compact. Add detailed rules to their existing owner.

## Read these first

Before code changes, read these documents in order and within their named scope.

1. [PRODUCT](docs/PRODUCT.md) owns current product behavior and availability.
2. [Documentation authority](docs/DOCUMENTATION_AUTHORITY.md) maps scope and
   conflicts. The [MVEE](docs/specs/argus-minimum-viable-ecosystem-experience.md)
   owns approved experience.
3. [ARCHITECTURE](docs/ARCHITECTURE.md) owns runtime and service boundaries.
4. [API_CONTRACT](docs/API_CONTRACT.md) owns endpoints and payloads.
5. [DATA_MODEL](docs/DATA_MODEL.md) owns persistence, ownership and RLS.
6. [Argus DESIGN](.agent/designs/argus/DESIGN.md) owns the existing web guide.
   Use the applicable native or Business design owner named by the authority map.
7. [Operating reference](docs/agents/operating-reference.md) contains the full
   repository rules. Read it in full before implementation or review.
8. [Decision log](docs/specs/argus-decision-log.md) records later founder locks.
   [Execution manifest](docs/specs/argus-execution-board.md) is the single map
   of current work, owners, dependencies, acceptance and action grants.
   Then read your explicitly assigned package and its issue.

Vision, a historical plan, a prior grant or a green test does not assign work.
Resolve conflicting contracts in their affected scope. Continue unrelated work
that is already authorized. Do not invent an API, permission or shipped feature
from experience prose.

## Current Business assignment

Read the [October 10 hosted Business assignment](docs/specs/argus-execution-board.md#business-hosted-invite-only-build-october-10-2026)
and [decision](docs/specs/argus-decision-log.md#october-10-2026-hosted-business-beta-and-build-grant).
The [Business execution spec](docs/specs/lanes/cuadrao-business-agent-execution-spec.md)
owns C0-first order and J1 to J3. The [Business handoff](docs/handoffs/cuadrao-business-lane.md)
records integration and preserved exclusions. Tracker #942 owns the larger flows.

The bounded grant is an invite-only internet Business build on integration and
staging. It does not authorize main or production, public signup, marketing
publication, Apple TestFlight or unrelated Consumer work. The root coordinator
alone owns merge and staging actions. Workers act only within their assigned
files and hand off exact commits. The Render workspace and named runtime model
choices are approved. Grok 4.3 is the first evaluation judge. The 22:32 UTC
continuation authorizes the existing development `OPENROUTER_API_KEY` within
its conservative remaining allowance until expiry. It replaces the $5 run cap
and spending hold. Only the root coordinator controls synthetic live calls,
reservations, concurrency and token bounds. Read the manifest before any call.
First acceptance uses one direct named-accountant grant for one Business.
The manifest preserves the later L11 firm-delegation requirement.

"Pagué 850" is one example. Interpret varied natural-language transactions,
follow-ups, uncertainty and corrections through the existing typed runtime.
Never route intent through phrase or regex gates. Acceptance checks saved state,
source links, revision history and authorized human approval across varied cases.
Laptop or synthetic transport proof does not establish hosted customer readiness.

## Bootstrap and stop conditions

Start with `git status`. Preserve user changes. Work in a sibling worktree with
one named writer. Record the fetched `origin/codex/private-alpha-next` SHA as
the integration base. Ordinary Cuadrao workers do not start from main.
Before READY, fetch integration again, merge it one-way into the worker when
needed, audit semantic overlap and verify the affected result. Do not rebase a
published or evidenced lane. Follow the reference's exact-head evidence rules.

For docs-only work, use offline checks. Skip bootstrap and environment writes.
For runtime work, read [environment doctrine](docs/agents/operating-reference.md#local-environment-doctrine)
and [worktree environment contract](docs/agents/operating-reference.md#worktree-environment-contract)
before setup or tests. Read topology with
`bash .github/setup-worktree-env.sh --check "$PWD"` without exposing values.
Missing or conflicting topology blocks affected runtime work. Shared `.env` and
`web/.env.local` links are not write targets. Do not print secrets, overwrite the
canonical environment, or run paid provider or Render tasks without the scoped
grant. Python uses `.python-version`; frontend work uses Bun.

Stop affected work for duplicate writers, contradictory contracts, denied or
missing action authority, scope expansion, uncertain external outcomes or
repeated unproductive failures. Notify the coordinator with the concrete
blocker. Do not bypass a hold through another agent. Keep unrelated work moving.

## Runtime, review and release rules

Ask who owns each fact and what forces all readers to agree. One canonical owner
must supply durable facts. LangGraph is the only chat brain. Supabase owns
product records. The frontend renders backend state. Tools enforce current
permissions, exact money, revision approval and duplicate-safe effects.

### Agent Quality Pillars

The canonical [four pillars](docs/agents/operating-reference.md#agent-quality-pillars)
remain in the full operating reference. Use them as the same quality lens.

### Never-Violate Standard 12

Model-facing prompts and schema field descriptions require a committed live
scorecard with no regression and an updated fingerprint under
[Standard 12](docs/agents/operating-reference.md#-never-violate-standards).
Do not make a live call before named-model and spend authorization.

Read [tests/evals/README.md](tests/evals/README.md) Test Tiers before eval work.
Use the mocked harness for every change. Reserve live eval for the documented
gates with explicit spending authority. Browser QA is real-API work and spends
tokens. Passing deterministic tests does not replace required live evidence.

Review reachable defects proportionally and fix their shared cause. Follow the
reference's clean-delta review termination and unresolved-thread checks.
Before READY, verify modularity budgets on the would-be merged tree and record
the exact head, integration reconciliation, retained evidence and terminal CI.

[CI/CD discipline](docs/specs/private-alpha-ci-cd-sota.md),
[launch runbook](docs/PRIVATE_LAUNCH_RUNBOOK.md) and
[release manifest template](docs/release-manifests/TEMPLATE.md) own release gates.
Use the branch-deployed staging/private-alpha Render validation surface for
exact-candidate canary evidence. Do not treat merge to `main` as a prerequisite for canary.
In the legacy Argus promotion contract, `main` is the later promotion target
after founder approval. The current Business grant stops at integration and staging.

### Commit and checkpoint discipline

Make atomic changes. Verify each coherent slice before committing it. Report
checks, evidence, caveats and a commit or the reason work remains uncommitted.
Keep scratch material in `temp/`. Do not commit unrelated changes or customer data.
