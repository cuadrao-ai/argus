# Lane07 security retention checkpoint

This is local verification evidence. Independent root review, exact-head CI and
any hosted acceptance remain separate gates. No provider request, Render change,
Supabase write, migration, or production action was performed.

## Approved scope and ownership

The coordinator assigned 7A and 7C on October 16, 2026. The branch started at
`ebc3cbf762b2512156997a074429f8d81be64e54`. Before completion, integration advanced to
`8b8d3dfa8b10e44e54444d4bd4969876a7472e4f`. That change touches Business web controls,
its evidence and a separate ownership entry. There is no provider, startup,
configuration, API, or data-model overlap. The coordinator authorized reconstruction
as three logical commits on this base after preserving the published head remotely.
The backup tag is `lane07-preserved-05a13d378-20261016`; both ownership entries remain.

| Family | Status | Delivery |
| --- | --- | --- |
| 7A provider retention | PENDING root review and CI | Provider policy commit, including transport and consent regressions |
| 7C configuration literals | PENDING root review and CI | Configuration commit and CI credential scanner commit |
| 7B advisor fixes and leaked-password setting | SUPERSEDED | Assigned to Lane08 PR2. No SQL, migration or Supabase configuration edit in this branch. |

## Policy behavior

`openrouter_provider_policy` owns the required provider block. Structured
requests, chat, memory, document extraction, the legacy LangChain adapter and
OpenRouter web search use it. Request guards and SDK invocation reject explicit
attempts to weaken that policy. There is no retention exception or opt-out.

A provider routing 404, an embedded 404 error, or a privacy-related 400/403 raises
`OpenRouterZDRUnavailableError`. It emits `llm_zdr_unavailable` with the model ID
only. No provider body, prompt, receipt, key or exception text enters that event.
The HTTP model loops and both primary and fallback legacy interpretation stop on
this error.
Reasoning retries still require retention and recheck access.

The existing HTTP helpers moved to `openrouter_transport.py`; the entry points
in `openrouter.py` keep their signatures. The existing legacy failure receipt and
log moved to the existing `interpreter/contract_recovery.py` owner. These moves
keep the changed files within the unchanged modularity budgets.

The Business route fixtures now contain the canonical retention block. Their
revocation, drift, final-validator mutation, captured-alias and no-dispatch
assertions remain. Prompt strings, schema descriptions and the prompt fingerprint
are unchanged.

Provider reference checked on October 16, 2026:
[OpenRouter provider routing](https://openrouter.ai/docs/guides/routing/provider-selection).
Endpoint availability was not tested live. Models without an eligible endpoint
will stop instead of routing under weaker retention.

## Configuration and Lucas handoff

The blueprint now uses `sync: false` for `argus-api` / `SUPABASE_ANON_KEY` and
`argus-app` / `NEXT_PUBLIC_SUPABASE_ANON_KEY`. The `cuadrao-web-staging` public key
already used `sync: false`. These are public-class keys; this change does not
rotate a key or alter a project URL. The existing 06E gateway startup fence and
all of its tests are unchanged.

Lucas owns any required Render environment setting. The coordinator can verify
that the existing staging values are present and match the authorized project.
No production readback or environment update was performed by this lane.

The required CI ownership job now runs `scripts/check_config_credentials.py`.
The scanner checks Git-tracked configuration files for JWT-shaped and `sb_`
credentials. Findings contain only the filename and line number. It never echoes
the matched value. Untracked environment files are outside its scan.

## Local verification and environment

The initial retention regression had 16 failures and one pass. All provider task
profiles are now covered. The most important probe sends a 404 through the real
LangChain SDK with a mocked HTTP transport, then checks the typed error and a
single request. Other probes cover sync, async, streaming hooks, embedded errors,
policy overrides, reasoning retries and retained Business consent gates.

Python 3.10.20 uses the existing interpreter with an ignored, lane-owned package
overlay for missing lxml, xlsxwriter and a working locked SciPy 1.15.3 wheel.
Both `import scipy` and `import scipy.linalg` passed with that overlay. Numba cache
writes stay under this lane's `temp/` directory. All provider keys are blanked for
the deterministic and mocked runs.

The shared `.env` link and its target remain intact. Auto-review rejected a
proposal to replace the local link. Render shell fixture tests instead ran in
`/private/tmp/argus-lane07-render-fixture-20261016`, with copies of the tested
scripts and blueprint, a synthetic staging `.env`, and mocked external calls.
All 11 tests passed there. No runtime test was weakened for local configuration.

The full local command covers the provider suites, Business transport gates,
document budget, startup fences, CI scanner and workflow contracts, the ten
required mocked eval modules, and discovery search adapters. Exact counts and
candidate SHA are recorded in the PR and coordinator handoff after reconciliation.

The final combined local run passed 843 tests in 24.92 seconds. The unchanged
budget, repository Ruff check and ownership check passed. The final candidate SHA
and terminal CI state belong to the PR and coordinator handoff.

A final regression reproduced one legacy gap after PR creation. A generic primary
SDK outage followed by ZDR unavailability on the fallback reached repair calls.
The added typed-error catch stops before repairs. The coordinator authorized
folding this regression and fix into the provider policy commit, preserving the
three-commit delivery. The prior remote head remains available through the backup
tag. No independent final review had been completed on that prior head.
