# Independent server review of PR 869

Reviewed head 175982863f33bc71820242d2827214a68f2a77f3 against integration fc4057c8789d3e3504fcb0e980344d6bf51e66c0. Original base 2b2d0d9e8ed311c11b7585fbd757fb37f915e12f; normal reconciliation 8d5cc0192758138069ef21b83b9b2c5696cb323a. Stable patch ID e4f91d1d390173d45f21dd32e689743a9a546150. Full diff SHA-256 3952f5c10a62bfc49ea5658a6ace4ee7036659524a4d802362c5d6144d14d6e5.

No concrete correctness, security or contract findings in this bounded server slice. The canonical profiles row owns display_name. The marker carries only eligibility. Existing identity parsing and account capability owners are reused. Parent and identity locks fence current Auth facts; the profile row serializes seed and explicit name edits. The triggers close eligibility on explicit same-value/NULL writes and prevent reopening, including privileged ordinary writes. Historical rows remain conservatively closed. Unrelated partial profile writes preserve eligibility. No preferred_name, Auth metadata, email-linking or provider dispatch is added. Default-off middleware returns 404 before body/auth processing.

Independent exact-head execution:

- Memory/API/OpenAPI cohort: 72 passed, 0 failed, 0 skipped, no warnings reported, 4.24 seconds.
- Isolated Postgres/Auth cohort: 46 passed, 0 failed, 0 skipped, no warnings reported, 5.05 seconds. This executes 32 name persistence/migration/privilege tests, the signed local Auth/API reconstructed-client journey, the existing concurrent currency-profile journey and 12 shared identity tests. The name suite includes 12 actual blocked-writer races observed with autocommit pg_blocking_pids before releasing the first transaction.
- Ruff: all changed Python modules/tests passed.
- Combined reconciled-tree modularity: 0 violations. Diff whitespace passed.
- Read-only comment review: clean; 0 edits. Exception docstring and FastAPI B008 suppression are justified.

The first PG attempt could not connect because sandbox TCP was denied with Operation not permitted. It reported 3 failures and 43 setup errors without executing SQL. The same authorized cohort was rerun with the necessary local-network permission and passed as recorded above. This failed setup is retained in /private/tmp/apple-name-independent-postgres.log and is not an application failure or successful proof. Successful logs are /private/tmp/apple-name-independent-memory.log and /private/tmp/apple-name-independent-postgres-authorized.log.

Merge remains gated on #862 landing and normal reconciliation followed by combined deletion-admission/name-lock proof. Current integration deletion admission does not yet hold the same parent lock. This review does not claim that missing race proof passed. Exact-head CI and final reconciliation review belong to the captain.

Native callback capture, durable intent/relaunch retry, device/provider authorization, hosted migration/readback and activation remain separate. No native or physical-device acceptance is established. No hosted data/configuration or feature flag was changed.

Review made no branch edits or pushes. The only child was a read-only comment reviewer and is stopped. All test processes completed and their own fixtures cleaned their synthetic identities/schema. Exclusive PG lease is released; the root stack remains running. No Mac, simulator, API process, paid call or provider request was created.
