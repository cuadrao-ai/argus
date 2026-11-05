# Apple identity lock observer investigation

The failure is a test observer defect. Under controlled ordering, the existing observer reports zero waiting captures for the full five-second deadline while a fresh connection sees the capture waiting on the expected parent-row lock. The production capture still rejects the conflicting identity after the writer commits and stores no credential.

## Scope and source

Read-only repository investigation. No tracked files, branches, providers, hosted systems, root environment, or production data changed. Temporary reproduction files are under `/private/tmp/cuadrao-apple-lock-observer-proof-20261005/`.

Tested current fetched integration `7018e0edebbc370b999005a857230bf3c3a1ad8b` from `/Users/garces/.codex/worktrees/7086031b-3547-4387-b461-0bf0f7973e17/private-alpha-next` without editing it. `git diff f5c83cd88 origin/codex/private-alpha-next -- tests/test_apple_identity_postgres.py src/argus/domain/apple_sign_in/credentials_postgres.py src/argus/domain/apple_sign_in/identity.py` is empty. The relevant files therefore match the failed merge baseline. The failing test entered integration in `f5c83cd88`, PR #858.

The parent supplied the historical CI observation for run 37355951520, matrix 1: 1 failed, 647 passed, 49 warnings. The failure was `test_identity_insert_committed_while_parent_lock_waits_is_seen`, line 255, `assert count`, with count zero. This investigation did not independently fetch that CI log or rerun the full matrix.

Runtime was `/private/tmp/cuadrao-scipy-env-20261005/bin/python`, PostgreSQL 17.6 on the exclusive disposable local port 60332, `PYTHONPATH=web:src:.`, and `PYTHONDONTWRITEBYTECODE=1`. Only fixture-created synthetic users were written. Fixtures removed them by their generated UUIDs. No reset was used.

## Cause

The capture thread sets `started` before `save(repo, user)`. That event proves only that the thread has started. The observer may execute its first `pg_stat_activity` query before the capture begins waiting on the parent row.

The observer uses psycopg's default transaction mode. Its first statistics query fixes the current-query snapshot for the transaction. Every later poll can therefore keep returning zero even after the capture reaches the lock. A longer timeout would keep reading the same old snapshot.

PostgreSQL documents this behavior in [the statistics documentation](https://www.postgresql.org/docs/current/monitoring-stats.html#MONITORING-STATS-VIEWS). Information about current queries remains fixed throughout a transaction; `pg_stat_clear_snapshot()` discards that snapshot. Ending each polling statement's transaction also gives the next poll a fresh view.

The production repository uses separate statements to lock `auth.users` and then read `auth.identities`, explicitly under READ COMMITTED. The identity read sees the conflicting row committed while the parent lock waited. None of the production path relies on `pg_stat_activity`.

## Controlled reproduction

`build.py` extracts the exact integration test into temporary files. It adds one event after `started.set()` and before `save`. The observer releases that event only after its first real query. This makes the failing scheduler order deterministic without replacing database results, changing production code, or extending the five-second deadline.

Each case checks the same parent query and pool-specific application name from a second, fresh autocommit connection before the writer can commit. That independent observer must see exactly one lock waiter.

For three original-observer cases, the original query remained zero while the fresh connection returned one. Each original `assert count` failed. For three autocommit-observer cases with identical ordering, both observers returned one and all original denied-state assertions passed.

A second diagnostic test keeps that ordering but explicitly expects the stale observer count in the baseline case, allowing the writer to commit. It then retains the original thread-termination, `AppleIdentityUnavailable`, and no-credential assertions. All six diagnostic cases passed. This separates an observation failure from an identity-integrity failure.

Results:

| Run | Result |
| --- | --- |
| Unmodified integration identity test module | 12 passed in 2.79s |
| Controlled original observer, three attempts | 3 failed at `assert count`; fresh observer saw one waiter in every case |
| Controlled autocommit observer, three attempts | 3 passed |
| Denied-outcome diagnostic, both observer modes, three attempts each | 6 passed |
| Combined controlled and diagnostic invocation | 3 failed, 9 passed, 24 deselected in 31.02s |
| Complete temporary identity module with only observer autocommit changed | 12 passed in 1.99s |

The 24 deselections are the original module's tests imported into the two temporary test modules and excluded by `-k`. They are not skipped checks in the controlled cases. An initial sandboxed attempt could not access localhost and ended with 12 setup errors before any database writes. The authorized local-network reruns produced the results above.

Logs and reproduction source:

- `/private/tmp/cuadrao-apple-lock-observer-proof-20261005/build.py`
- `/private/tmp/cuadrao-apple-lock-observer-proof-20261005/test_controlled.py`
- `/private/tmp/cuadrao-apple-lock-observer-proof-20261005/test_outcome.py`
- `/private/tmp/cuadrao-apple-lock-observer-proof-20261005/test_candidate.py`
- `/private/tmp/cuadrao-apple-lock-observer-proof-20261005/baseline.log`
- `/private/tmp/cuadrao-apple-lock-observer-proof-20261005/controlled.log`
- `/private/tmp/cuadrao-apple-lock-observer-proof-20261005/candidate.log`

Reproduce from the integration checkout with the stated environment and disposable DSN:

```sh
python -m pytest -o addopts='' -p no:cacheprovider -qs \
  /private/tmp/cuadrao-apple-lock-observer-proof-20261005/test_controlled.py \
  /private/tmp/cuadrao-apple-lock-observer-proof-20261005/test_outcome.py \
  -k 'controlled_observer or denied_outcome'
```

## Smallest safe fix

Change only the observer context to `with psycopg.connect(DSN, autocommit=True) as observer:`. Keep the writer transaction, five-second deadline, pool-specific parent-lock query, worker join, exception type, and absent-credential assertions unchanged. The existing test can also retain a first-poll event handshake as a deterministic regression guard so it always tests a transition from not-yet-waiting to waiting. That handshake plus autocommit is demonstrated in the temporary controlled test.

Do not increase the timeout, swallow `assert count`, or relax denied-state assertions. No production identity change is indicated by this evidence. The observed impact is a false-red integration gate, not a demonstrated account-binding failure.

The root-cause principle shaped the experiment: force the first-read ordering and compare a fresh observer instead of guessing that the worker merely needs more time. A repository census found the other `pg_stat_activity` lock observers in invite security and memory reconciliation tests already use autocommit; no broader observer rewrite is justified.

## Cleanup and handoff

All pytest processes and capture threads finished. Fixture cleanup completed. Final read-only checks returned zero `siwa-` fixture users and zero `apple-credentials-test-` connections on the assigned database. No worktree was created. The exclusive PostgreSQL slot is released. The root agent owns issue creation and any implementation decision. The report and reproduction are local artifacts; attach them to the owned issue if remote retention is required.
