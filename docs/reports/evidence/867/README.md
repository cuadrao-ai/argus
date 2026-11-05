# Apple parent-lock observer verification

Issue #867 under #832. This test-only change prevents a false failure when the observer queries PostgreSQL activity before capture reaches its parent-row lock.

Original and freshly fetched integration base are both `7018e0edebbc370b999005a857230bf3c3a1ad8b`. No reconciliation merge or intervening integration diff was needed. The tested file SHA-256 is `182f69b76e7df68a0b938be9b06e3e9447110b60a1a17a30cdb0cab85e3ab333`.

The capture waits on `first_poll` before calling `save`. The observer sets that event after its first real statistics query. This forces the formerly intermittent order. Autocommit ends each observer statement's transaction so the next poll can see the new lock waiter. The writer transaction, five-second deadline, exact parent query and pool filter, identity rejection, and absent-credential assertions remain unchanged. Final cleanup releases the event even if observation fails.

## Evidence

- [Red](red.txt). The actual changed test with only observer autocommit removed failed at `assert count`, with count zero. 1 failed in 5.91 seconds.
- [Green](green.txt). The actual fixed module passed all 12 cases in 3.10 seconds.
- [Focused](focused.txt). Identity unit and PostgreSQL credential modules passed 25 cases in 1.68 seconds.
- [Mocked](mocked.txt). The documented ten-module mocked eval command passed 272 cases in 13.81 seconds.
- [Budget](budget.txt). No modularity violations. Integration was unchanged, so this worktree is the would-be merged tree.

Successful runs had zero skipped tests and zero failures. Runtime was Python 3.11.15 in the supplied temporary environment, PostgreSQL 17.6, `PYTHONPATH=web:src:.`, and `PYTHONDONTWRITEBYTECODE=1`. The only database was the assigned disposable local instance. No provider calls or hosted writes occurred.

Commands used `python -m pytest -o addopts='' -p no:cacheprovider -q`. Green selected `tests/test_apple_identity_postgres.py`. Focused selected `tests/test_apple_identity.py tests/test_apple_sign_in_credentials_postgres.py`. Mocked selected the ten files listed in `tests/evals/README.md` under Mocked Run. Red selected `tests/test_apple_identity_postgres.py::test_identity_insert_committed_while_parent_lock_waits_is_seen`, with the deterministic handshake present and the observer using default transaction mode.

Independent read-only code and no-comments review returned clean after inspecting the final test diff. It confirmed first-read ordering, fresh observer transactions, failure cleanup, and preserved lock and outcome assertions. Comment review found zero comments in scope, zero deletions, and zero flags. The deslop pass and `git diff --check` were clean.

Fixture cleanup left zero synthetic `siwa-` users and zero `apple-credentials-test-` connections. The exclusive database slot was released. Exact published-head CI and the release captain's final review remain publication follow-up gates; this report does not claim those are complete.
