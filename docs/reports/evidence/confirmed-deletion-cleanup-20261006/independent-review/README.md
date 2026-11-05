# Atomic confirmed-deletion cleanup QA

Scoped runtime QA passed at `f787ca63af9ba4e6355357ed5e1a8ead5a3dfb21`.
The baseline is fetched integration `8146d16e90633eb543781f8882665482f0d5dca9`.
The candidate stayed clean. No source fix or branch write was made by this
reviewer. Root owns publication, integration, CI and release decisions.

| Check | Actual result | Evidence |
| --- | --- | --- |
| Historical cleanup-before-ack probe on exact 8146 | 1 passed, 0 skips/failures; 0.008 seconds. This reproduces the gap, not baseline correctness | 8146-gap-reproduction.log, BaselineDeletionCleanupGapTests.swift |
| Full current package | 174 executed: 170 passed, 4 existing opt-in local-stack skips, 0 failures; 11.477 seconds | f787-package.log |
| Six new real-filesystem cases | 6 passed, 0 skips/failures; 0.021 seconds | f787-filesystem6.log |
| All affected deletion cases | 20 passed, 0 skips/failures; 0.042 seconds | f787-deletion20.log |
| Migrated actual local SDK/API/Auth/PG harness | 1 passed, 0 skips/failures; 0.770 seconds | f787-live-sdk.log, LiveDeletionTests.swift |

These are separate runs, not one summed suite count. The four existing package
opt-in cases were not re-executed here. The new filesystem cases and migrated
live harness all executed without skips.

## Before and after the boundary

The historical probe deliberately uses 8146's old API: complete A, sign B in,
remove A's unique temporary draft directory, then await acknowledgement. The
actor rejects that stale receipt, but the real A file is already gone. B's file
and session survive. The passing probe confirms this unsafe sequence occurred;
it does not claim that the old boundary was safe. Its temporary directories are
removed by the fixture.

On the corrected API, the six cases prove:

- A stale completed A callback while B owns the session changes neither A nor B
  files, and preserves B's snapshot and the completed obligation.
- A valid callback receives the validated journal UUID, removes only that user's
  temporary directory and preserves an unrelated user's directory. An already
  missing directory is idempotent.
- Callback failure preserves files and the completed record; a reconstructed
  controller retries only cleanup. Deletion POST count remains 1.
- Successful cleanup followed by acknowledgement-storage failure preserves the
  completed record. Idempotent retry finishes without a second deletion POST.
- Active B SDK adoption rejects cleanup before filesystem effects and preserves
  the exact pending proof.
- Accepted 202, uncertain 503 and ordinary sign-out cannot authorize cleanup; real
  temporary files survive those denied states.

All filesystem effects are confined to unique temporary fixture directories.
No Application Support directory, actual app receipt store, UI or user data is
touched. The app adapter is still a separate gate. There is no suspension between
the actor's admission check, synchronous callback and journal removal, and no
callback-free production overload. [Actor diff](actor-change.diff) and
[source hashes](provenance.json) bind that boundary to the tested source.

## Initial fixture failure and correction

Original b77de5f6df62f3a47e138c6a1b88055505b67416 failed compilation before any
tests ran. AccountDeletionTests.swift:415 constructed a ternary [String:Any]
dictionary for actor.configure; Swift 6 rejected the non-Sendable transfer.
[Initial failure](b77-compile-failure.log) is retained.

The source author published f787, replacing that expression with separate fresh
literal constructions in the existing 202/503 branches. Assertions, six cases
and production actor behavior are unchanged. [Fixture correction](fixture-fix.diff)
records the small change; production actor object hashes match b77 exactly.
The full and focused runs then passed. No zero-test or failing run is counted
as acceptance.

## Migrated live boundary

The committed migrated LiveDeletionTests copy runs against the current production
Swift SDK, transport and Keychain, current API on owned 60343, real local Auth60331
and PostgreSQL60332. Only the live fixture's port allow-list changes;
[port diff](port-adaptation.diff) and provenance preserve that adaptation.

Observed result: completed 200, A absent from PostgreSQL, B still present and the
owned run done. While B owns the SDK, A's receipt is suppressed and the migrated
explicit callback acknowledgement returns staleOperation. B survives controller
reconstruction and signs out normally. [Readback/cleanup log](live-readback-cleanup.log)
retains only booleans, run status and nonsecret process metadata.

The API process explicitly uses APP_ENV=test with analytics deletion disabled;
the repository's recording analytics adapter contacts nobody and counts as
complete only in this synthetic local setting. This 200 is not evidence of live
PostHog, Apple or other provider completion. No Apple identity/code was involved.
The private 600-mode fixture, owned users/run and API process are cleaned in the
driver's finally block. No Auth container/configuration was changed.

## Commands, warnings and cleanup

Package and focused checks used explicit owned caches:

```sh
CLANG_MODULE_CACHE_PATH=/private/tmp/cuadrao-combined-clang-cache \
SWIFTPM_MODULECACHE_OVERRIDE=/private/tmp/cuadrao-combined-swift-cache \
swift test --package-path ios/Packages/ArgusSession \
  --scratch-path /private/tmp/cuadrao-apple-session-swift \
  --cache-path /private/tmp/cuadrao-session-spm-cache \
  --disable-sandbox --disable-automatic-resolution
```

The historical probe uses that command with its isolated 8146 package and filter
BaselineDeletionCleanupGapTests. The six-case filter names exactly the six new
cleanup methods; the all-deletion filter is AccountDeletionTests. [Live recipe](live-driver.py)
uses the independently copied current package and filter LiveDeletionTests,
private api-env.json, dotenv disabled and only owned 60343/local stack resources.
No root.env is read or copied.

Package runs report inaccessible sandboxed user-level Swift configuration and
security caches; explicit owned caches are used. Final tests report no failures
or skips in the focused/runtime cases. Raw API logs and credential fixtures are
not published. Actual local credential values were scanned and none appear in
this folder.

[Cleanup](cleanup.json) verifies own 60343 free, owned users absent, credential
fixture removed, root Auth health 200 and PostgreSQL responding, and candidate
clean. The exclusive run-id before/after set verifies own deletion-run cleanup.
No simulator or app was created/launched. Root DB, foreign services, Preview,
phone and actual receipt-store data were preserved. No hosted/provider/paid work,
activation, main change, merge or deployment occurred.

The captain must commit or attach this evidence before a ready claim. Final app
cleanup integration, UI, physical phone, provider and exact-head CI gates remain
separate.
