# Apple deletion admission and recovery

Backend protection for #800, with existing #803/#807 boundaries preserved.

## Lineage and ownership

- Original and fetched current integration: `f5c83cd88a0af56dc8154a89c6ea4f75d9c518ce`.
- Runtime implementation: `ec47f20bd2a205a9be474b11a0af6ed04b27087b`.
- Final runtime fix: `9c7cb53560ca78987dcf7d3784820b74005563b2`.
- No reconciliation merge was needed at this checkpoint; integration had not advanced.
- One implementation writer, one narrow fix writer, and separate read-only reviews. Parent owns documentation and delivery. Native/session/profile changes belong to another lane.

## Behavior and verification

A linked Apple account without a readable, current-subject-bound credential now fails before the first deletion run or protected mutation. Fresh authorization uses the existing Argus JWT. Known pending recovery stays pending; unknown admission returns503 incomplete rather than202 accepted or an account-intact claim.

Confirmed provider revoke and exact credential removal share one local transaction with the existing run receipt. Capture, admission and receipt paths share Auth user, identity, credential, then run ordering. Recovery capture and receipt writes verify the live claim after lock acquisition. Provider HTTP holds no SQL locks.

[Recorded output](verification.txt) includes the behavioral baseline: missing credential still produced `banned=1, deleted=1`. Final runs used the locked Python3.11 environment, synthetic fixtures and mocked Apple/provider adapters:

| Check | Result |
| --- | --- |
| Adjacent real PostgreSQL deletion/Apple suites |92 passed,0 failed,0 skipped |
| Final focused PostgreSQL after pending-marker fencing |27 passed,0 failed,0 skipped |
| Final unit/API/auth/operator suite including unknown-state fix |124 passed,0 failed,0 skipped |
| Generated OpenAPI compatibility and API mapping |53 passed,0 failed,0 skipped |
| Changed-file Ruff, whitespace, modularity |Passed |

The27 focused cases cover missing/unbound/mismatched/unreadable/unavailable admission, identity insert/update races, capture/admission contention, duplicate claims, interrupted receipt transaction, lost/expired claim, replacement preservation, legacy pending recovery, failure classification and unchanged current/foreign money. Existing banned-token expiry/session scope tests remain green. These counts overlap; they must not be summed as unique tests.

Initial fixture constraint errors were corrected before the green runs. One combined API/database invocation inherited mock-auth configuration and failed an existing auth expectation; the final unit/API suite used its ordinary isolated setup. The initial baseline invocation skipped before the synthetic database URL was supplied, and a sandbox connection attempt failed before writes; neither was counted as database evidence.

## Review and cleanup

Independent review found one reachable expiry race: capture used time sampled before waiting for locks. The fix checks fresh time after the run lock; a blocked-lock regression passes. The subsequent fix-delta review was clean. A separate API regression exposed unknown admission returning202; a fresh writer retained a distinct unknown-state exception, and its independent delta review was clean at `9c7cb5356`. Two newly added narration docstrings were removed; the provider-only public contract documentation remains.

The PostgreSQL slot was released after teardown. New fixtures tracked exact run IDs and verified removal even after the journal scrubbed identity. Readback at release showed0 Apple credentials,0 fixture Apple identities and0 pending runs. Two household-pattern users of unknown ownership were left untouched.267 anonymous completed receipts remained globally, including one unidentified baseline receipt and records intentionally retained by existing full-world tests. No broad cleanup was attempted.

## Remaining gates

This evidence makes no real-provider, hosted, physical-phone, native-flow or release-readiness claim. Capture/deletion/provider flags remain unchanged. The native consumer and combined OpenAPI must reconcile through integration before landing. Real Apple reauthorization/revocation and banned-session recovery on a phone remain acceptance gates. #798 orphan/Hide My Email decisions, #803 late cleanup race acceptance, #805 money-policy blockers, #819 permission ownership, and #807 operator/escalation decisions remain with their existing owners. No cron, operator assignment, live alert, migration, provider call or hosted configuration was added.

## Integration reconciliation

Before final delivery, integration advanced to `7018e0edebbc370b999005a857230bf3c3a1ad8b` via #857. One-way merge `bfbe3b0292c97176f3510c69cbfbf53c9cf49001` brought it into this branch. Semantic overlap: none. #857 changes native provider button appearance and its native UI tests/evidence; this branch changes backend deletion/capture owners, API error/request contracts and their Python tests. No shared API/data contract, migration, environment variable or direct test owner changed in the intervening commit. PostgreSQL evidence is retained; no provider, phone or broad database matrix was repeated.

The reconciled tree passed148 combined unit/API/auth/operator/OpenAPI tests with0 skips/failures, and its merged-tree modularity check passed. The subsequent evidence-only commit changes no runtime or test input, so these results remain valid. Terminal CI and unresolved-review-thread status are reported on the PR after its final publication.
