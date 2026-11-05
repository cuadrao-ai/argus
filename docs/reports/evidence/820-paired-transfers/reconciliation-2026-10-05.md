# Integration reconciliation

Original lane base is `875de09ac2115acec42e09060b92878aa5f18eff`.
The prior verified patch is `b482f575a4d0561c7426517348dc9522adcb0673`.
Its integration base was `26c0692d634953bd542a6cca6504138e6e420e6c`.
Current integration `7018e0edebbc370b999005a857230bf3c3a1ad8b` was merged
normally as `60a54988b3a309b4c57ca3332a390b8e5899d98f`, without conflicts.
This evidence commit changes no executable files. The merge commit is the
measured executable head. The final handoff records the evidence commit SHA.

## Overlap assessment

Integration adds Apple credential subject binding and native provider-button
appearance. Recording, Planning and Household runtime owners are unchanged
from the prior verified patch. Incoming API and data changes concern Apple
capture, identity and credential metadata. The shared contract documents and
OpenAPI file merge cleanly in those unrelated sections. Paired-transfer schema,
per-leg amounts, precision, projection and Plan denomination predicates remain
unchanged. The native auth appearance state owner is separate from paired
transfer recording. The incoming migration adds nullable Apple subject metadata
only; this lane has no financial migration. Integration changes none of this
lane's environment files or directly affected financial tests.

The profile still owns `CUADRAO_CROSS_CURRENCY_TRANSFERS_ENABLED=false`.
The environment template and Blueprint retain that default. The shell API key
list still derives from the profile CLI and rejects profile-load failure.
No rate, Plan credit or shared-space semantics were added during reconciliation.

## Revalidated checks

The supplied Python 3.11.15 runtime ran with an empty inherited environment,
explicit synthetic test settings and `PYTHONPATH=web:src:.`. No root environment
file or disposable database DSN was loaded.

- [Focused checks](reconciliation-checks.txt) pass 179 tests with three expected
  no-DSN skips. This includes 74 release configuration and shell checks,
  81 Apple identity/client/API tests and 24 OpenAPI compatibility tests.
  The skipped tests are the three PostgreSQL paired-transfer cases.
- [Mocked and pair checks](reconciliation-mocked.txt) pass 305 tests with
  26 expected no-DSN skips. All 272 required mocked eval tests pass.
  The paired-transfer file adds 33 passing pure checks; its 26 database cases
  skip because this run deliberately has no database configuration.
- [Combined-tree modularity](reconciliation-modularity.txt) passes with no
  budget violations. Shell syntax and whitespace checks pass.

The commands use `python -m pytest --no-cov -q --tb=short` and the exact test
modules named in each log. The mocked modules are the canonical mocked command
in `tests/evals/README.md`. Modularity uses `scripts/check_modularity_budget.py`.
The host emitted one temporary-directory fallback warning in each pytest log.
There were no pytest warnings or failing tests in these runs.

## Retained evidence and handoff

The committed prior proof remains applicable because financial code and its
fixtures are byte-identical to the prior verified patch. This retains the
232-test affected suite with zero skips and 57 existing pool warnings, the
explicit three-case PostgreSQL proof, and the shared-denomination privacy and
correction proof linked by the main README. The current no-DSN skips do not
replace those database results or claim a new database execution.

This is a reconciliation record, not a terminal release audit. Independent final
review, exact-head CI judgment, merge and integration landing remain with the
root coordinator. Native transfer acceptance and hosted activation remain open.
No provider, hosted configuration, Mac setting or customer record was changed.
The worker's test processes have exited; no database or server was started.
