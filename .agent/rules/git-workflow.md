---
trigger: always_on
description: Conventional commits, branch naming, monorepo coordination, feature flags, PR process.
---

# Git Workflow Rule

## Current integration workflow

Read root `AGENTS.md`, `docs/DOCUMENTATION_AUTHORITY.md` and the explicitly
assigned package before branch or PR actions. Ordinary Cuadrao work starts from
a freshly fetched `origin/codex/private-alpha-next`, with its SHA recorded.
Target worker PRs at `codex/private-alpha-next`. Merge newer integration one-way
into the worker before READY and audit semantic overlap. Do not rebase a
published or evidenced lane. The named coordinator owns the serialized merge
slot and acts only under the scoped grant. No production deployment follows
from an integration merge.

## Legacy Argus trunk policy

The following main policy remains for separately authorized legacy Argus
promotion. It does not select main as the current Cuadrao base or merge target.

1. **Short-Lived Branches**: Branches should ideally live for less than 48 hours.
2. **Protected Main**: The `main` branch is protected. Direct commits are forbidden.
3. **PR Requirements**: Merging to `main` requires passing all CI checks (run `/verify`) and getting PR approval.
4. **Always Deployable**: `main` must always be in a stable, deployable state.

## Branch Naming

Use the following prefixes to categorize your work:

- `feat/*` – New features or capabilities
- `fix/*` – Bug fixes and security patches
- `chore/*` – Maintenance or build changes
- `docs/*` – Documentation-only updates
- `perf/*` – Performance improvements
- `refactor/*` – Code restructuring
- `test/*` – Testing updates

**Optional scope prefix for monorepo clarity:**
- `web/feat/...` (Frontend focus)
- `core/fix/...` (Backend/Engine focus)

**Examples:**
- `feat/strategy-builder-ui`
- `web/fix/chart-tooltip`
- `core/chore/numba-jit-warmup`
- `docs/api-contract-v[x.x.x]`

## GitHub Labels

Categorize PRs using these labels for better organization:

- **Type**: `feature`, `bug`, `chore`, `docs`, `perf`, `refactor`, `test`
- **Scope**: `core`, `web`, `api`, `db`
- **Priority**: `high-priority`, `med-priority`, `low-priority`

## Commit Messages

```
<type>(<scope>): <concise description> (#<issue>)

- Detail 1
- Detail 2
```

**Scope examples:** `api`, `web`, `analysis`, `auth`, `db`, `migrations`

### Types

| Type       | When                                   |
| ---------- | -------------------------------------- |
| `feat`     | New feature                            |
| `fix`      | Bug fix                                |
| `refactor` | Code restructure (no behavior change)  |
| `chore`    | Build, CI, tooling, dependency updates |
| `docs`     | Documentation, API contract updates    |
| `perf`     | Performance improvement                |
| `test`     | Adding/fixing tests                    |

## Monorepo Guidelines

1. **API Contract Changes First**: If updating API schema (Pydantic), commit that separately with scope `docs(api-contract)` before backend/frontend implementation PRs.
2. **Parallel PRs OK**: Backend (`feat/api-...`) and frontend (`feat/web-...`) can have open PRs simultaneously against same issue. Merge API contract PR first, then both can merge together.
3. **Feature Flags**: Frontend public flags use `NEXT_PUBLIC_<FLAG_NAME>` (e.g., `NEXT_PUBLIC_FEATURE_MULTI_ASSET`). Document them in `web/.env.local.example`. Backend flags belong in root `.env.example`. Hosted configuration follows the release contract.
4. **Environment Consistency**: Backend + frontend must be able to run together after `setup.sh`. Commit `.env.example` files (never actual secrets).

## PR Process

1. Pass `/verify` before opening PR.
2. Reference issue number in PR title and body.
3. One logical change per PR — avoid mega-PRs (but related backend + frontend changes can be in one PR if they touch the API contract).
4. If PR touches API schema, include the `docs/API_CONTRACT.md` update.
5. Land only into the assigned target with the coordinator's recorded authority.
   Main promotion and production deployment require their separate founder grants.

See: `.agent/workflows/pr.md` for full PR workflow, `.agent/skills/monorepo-patterns/SKILL.md` for coordination details.
