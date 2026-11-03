# CI test sharding

Two backend workers and three database workers per variant collect their complete
existing test selection before
assigning whole files to shards. Files stay together to retain module fixtures and
test order. The counts use measured test costs and the elapsed time of the other
CI jobs to limit repeated setup. The partitioner assigns the longest measured file to the least loaded
shard, with stable tie breaks. New files use the median measured cost per test.

Each database worker starts its own disposable local database on its own runner.
Database variants retain the existing event rules. Pull requests run the pilot
selection on the pinned variant. Pushes and full manual runs use the complete
database glob on both variants. Scheduled and probe runs use the complete glob on
the latest variant. Anonymous-auth tests run once, on pinned shard zero.

The `backend-checks`, `database-checks (pinned)`, `database-checks (latest)` and `ci`
checks retain their public names. A suite gate requires successful workers and
verifies their downloaded inventories before it can pass. It checks exact node
identity union, zero duplicates, complete shard indices and completed execution
reports. Database proofs additionally require every selected test to pass. Worker
artifacts use stable names within a run so failed-job retries can retain evidence
from successful shards.

## Reproduce the evidence

Balancing weights come from the successful test inventories in
[the initial timing run](https://github.com/cuadrao-ai/argus/actions/runs/41575666061)
on PR #1724, head `967da39abac61387af209d9ea239caac92d120ef`.
The generated files contain seconds summed over setup, call and teardown for each
test file. They are balancing inputs, not wall-time measurements.

Ten parametrized cases originally used generated values as node IDs. Their
explicit labels are now stable; the generated values and assertions are unchanged.
[The comparison baseline](https://github.com/cuadrao-ai/argus/actions/runs/41579775450)
uses those labels at head `94d95a4ddd25ee12ca8fbd6388f24546ca7ea15c`. Download that
run's inventories for exact identity comparisons; use the initial run for
regenerating the committed timing weights.

After downloading the initial inventories into `temp/initial/`, regenerate them:

```bash
poetry run python -m scripts.ci.update_shard_timings temp/initial/backend.json scripts/ci/timings/backend.generated.json
poetry run python -m scripts.ci.update_shard_timings temp/initial/postgres.json scripts/ci/timings/postgres.generated.json --require-passed
```

Each aggregate gate uploads a `ci-proof-*` artifact with the full exact node list,
a digest, selected counts, skipped identities and the union result. To compare
backend shard inventories against the baseline as well as the current collection:

```bash
python scripts/ci/test_shards.py temp/after/backend-*.json --baseline temp/baseline/backend.json --allow-added-file tests/test_ci_test_shards.py --allow-added-file tests/test_ci_shard_workflow.py --allow-added-file tests/test_ci_shard_timings.py --output temp/backend-comparison.json
python scripts/ci/test_shards.py temp/after/postgres-*.json --baseline temp/baseline/postgres.json --require-passed --output temp/postgres-comparison.json
python scripts/ci/test_shards.py temp/after/auth.json --baseline temp/baseline/auth.json --require-passed --output temp/auth-comparison.json
```

The comparison rejects removed identities and newly skipped existing tests. Only
the named new sharding-test files may add identities. The PR records the actual
before and after run links, wall times and runner execution minutes. Use job
start/end timestamps for elapsed time and summed job durations for runner minutes;
test phase durations omit collection, dependency installation and database startup.
Keep workflow-wide time separate from the time of the two changed suites.
