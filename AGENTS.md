# Cuadrao: repository guide for coding agents

Cuadrao is a Spanish-first personal and Business finance app for people in the
Dominican Republic. Code still lives under `src/argus/` and many settings keep an
`ARGUS_` prefix. Those are code names, not the product name.

This file holds codebase facts. Team process lives outside the repo and arrives in
your launch prompt. On process, follow the prompt; on codebase facts, this file wins.

## How to work

- Work in poteto mode: one job per PR, no slop, proven before you call it done.
- Base and PR target: `codex/private-alpha-next`, never `main`. Record its fetched SHA first.
- Edit only the files your brief names. Stop and report if you need a file someone
  else holds, hit contradicting contracts, lack permission, or fail the same way twice.
- Start with `git status`; keep others' changes. Use a sibling worktree, never a nested
  one: it inherits the parent `.env` and turns mocked runs into live calls.
- Scratch goes in `temp/`. Delete what you create. No new Markdown notes outside docs.

## Where truth lives

Product today: `docs/PRODUCT.md`. Which doc owns what: `docs/DOCUMENTATION_AUTHORITY.md`.
Services: `docs/ARCHITECTURE.md`. Endpoints: `docs/API_CONTRACT.md` and
`docs/api/openapi.yaml`. Tables and row security: `docs/DATA_MODEL.md`. Core flows:
`docs/CORE_FLOWS.md`. Design: `.agent/designs/cuadrao/DESIGN.md` (native) and
`.agent/designs/cuadrao-business/DESIGN.md`. Status: `docs/specs/argus-execution-board.md`.
A spec, roadmap or green test does not assign work. Your brief does.

Layout: `src/argus/` API (`api/`, `agent_runtime/` chat runtime, `domain/`, with
`domain/business/` for Business), `web/` web app, `marketing/` marketing site,
`ios/` and `mobile/android/` native apps (see their READMEs), `supabase/migrations/`,
`tests/` (with `tests/evals/`), `scripts/` checks and ops tools, `.github/` CI and setup.

## Setup and run

- Python is pinned by `.python-version` (3.10); run it through `poetry run`. Frontend
  packages use bun, not npm. Docs-only work skips setup and every env write.
- Run `.github/setup.sh` once per runtime worktree; it links missing `.env` files to the
  integration worktree. Check (prints no values): `bash .github/setup-worktree-env.sh --check "$PWD"`.
  `missing` or `conflicting-link` means stop and fix first.
- Fast mode: `.github/dev.sh` (memory store, synthetic fixtures, mock auth), then
  `cd web && bun run dev` with `NEXT_PUBLIC_MOCK_AUTH=true`. Parity: `.github/qa.sh`.
- The `web/` framework breaks older APIs: read `web/node_modules/next/dist/docs/` first.

## Checks (CI runs these)

```bash
poetry run ruff check src tests workflows scripts
poetry run python scripts/check_modularity_budget.py
poetry run pytest tests -q --no-cov
python scripts/check_config_credentials.py
python .agent/scripts/ownership/verify_branch_ownership.py
cd web && bun run lint && bun test && bun run build
cd marketing && bun run lint && bun run typecheck && bun test && bun run build
```

- Hermetic chat sweep (seconds; minutes means a live path leaked, so stop):
  `OPENROUTER_API_KEY= ARGUS_MARKET_DATA_PROVIDER_MODE=synthetic_unit_fixture poetry run pytest tests/agent_runtime tests/test_spine_guardrails.py -q --no-cov`
- Postgres tests need `ARGUS_DISPOSABLE_DATABASE_URL` on a throwaway local DB, never staging/prod.
- Evals: read the Test Tiers in `tests/evals/README.md`. Use the mocked harness for
  every change. A live eval runs only at its documented gates with spend approved in
  your brief. Browser QA is real-API work and spends tokens.
- Modularity budgets (`.agent/modularity_budget.json`) are shared: check the merged tree.

## Codebase rules

- One owner per fact. Ask of every change who else holds this fact and what forces
  them to agree. Derive from one source; never keep two copies in sync.
- One chat runtime. User language reaches the structured interpreter before any
  routing: no regex, phrase lists or language gates in front of it. Code checks facts
  after interpretation, and any layer that patches a weak model read logs when it fires.
- Model-facing text is measured. Prompt builders and `Field(description=...)` are
  fingerprinted by `tests/test_interpreter_prompt_freeze.py`. Changing them needs a
  live scorecard under `docs/reports/evidence/`, no regression against the one named
  in `.agent/interpreter_prompt_fingerprint.json`, and a regenerated fingerprint.
- The backend owns truth; the frontend renders its state and never invents progress,
  totals, statuses or options. Money is exact. Business approval is the owner's alone.
- A schema change updates `docs/API_CONTRACT.md` and `docs/api/openapi.yaml` in the
  same PR. Data changes update `docs/DATA_MODEL.md`.
- Shared hot files (locales, `docs/api/openapi.yaml`, `docs/API_CONTRACT.md`, `docs/DATA_MODEL.md`,
  ownership manifest): add your block where its key sorts. Never reorder or reformat.
- Python: `loguru` not `print()`, `pydantic-settings` not `os.environ`, typed signatures.
- Tests: failing test first for a bug. Shared fixtures and parametrize, Faker data.
- Unfinished features ship behind a default-off switch (`web/lib/private-alpha-flags.ts`,
  `web/lib/language-features.ts`, backend settings), never on a parked branch.

## Migrations, security and data

- New migration: `supabase/migrations/<UTC timestamp>_<name>.sql`, unique version
  (`tests/test_migration_versions_unique.py`). Never edit an applied migration; fix forward.
- Every new table gets row-level security (own rows only), proven by disposable Postgres tests.
- Hosted databases change only via `scripts/ops/apply_approved_migrations.py` with a
  committed approval record, and staging gets a migration only from a merged PR.
- Staging only. Never touch production databases, services or keys. Keep paid hosted
  jobs off locally (`ARGUS_BACKTEST_WORKFLOW_EXECUTION_ENABLED` unset).
- Never commit secrets or env files (`.example` files hold placeholders). Never print
  secret values or write through a linked `.env`. The web gets only `NEXT_PUBLIC_*`.
- New settings use `CUADRAO_*` names (`ARGUS_*` is a read-only fallback). Declare hosted
  ones in `.env.example`, `render.yaml`, `.github/private-alpha-release-profile.json`
  and `scripts/ops/staging_env_manifest.json`.
- Synthetic data only (Faker, the seed script). No real customer data anywhere.

## Copy

- Spanish first (`es-419`), in natural Dominican wording. Every user-facing string lives
  in `web/public/locales/es-419/common.json` and its `en` twin. No hardcoded strings.
- Spanish copy comes through your brief; until then, ship marked placeholder keys.
- No em dash in user-facing copy, in any language (`src/argus/domain/visible_reply.py`).
- No "Argus", provider or vendor names in user-facing copy. Never name outside
  companies or competitors in code, comments, docs, PRs, issues or commit messages.

## Commits, PRs and review

- Conventional commits: `type(scope): summary (#issue)`. One job per PR, no stacks.
- Every pull request description opens with the Merge Danger block in `.github/pull_request_template.md`.
- Hotspot files need the lead's `landing-next` label, and a pull request over about 800 non-test lines needs `size-approved`.
- Merge `codex/private-alpha-next` in before the last push. Never rebase a published branch.
- Attach visual evidence on the pull request, or upload it with actions/upload-artifact. Do not commit it. Capture it at the exact head.
- Never merge your own PR. Report the PR link, head SHA, tests added and the proof.
- Review against the named parent branch; never assume `main` is the comparison base.
- Findings give file and line, severity, impact and the smallest safe fix.
- No broad rewrites, future-slice work or new product surfaces unless they block the job.
