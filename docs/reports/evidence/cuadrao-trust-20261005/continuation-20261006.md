# Trust and Shared Foundations continuation

Integration base for this follow-up is `13a1a339cbab1a3896e10779477658af63e062b3`, fetched October 6. The preceding coordinator evidence checkout is preserved. Root owns the single merge queue and the shared contract schedule.

## Landed and integration verified

[Housekeeping PR #860](https://github.com/lagarcess/argus/pull/860) merged as `13a1a339cbab1a3896e10779477658af63e062b3`. Its source head `8506db39d5f253afcbe76cfaf7d54301f10fda15` and integration share tree `23ad2ecc4f5c060ad89770732b7efc7e91dc9b83`. Canonical integration checkout was clean at that SHA.

Integration CI run [37400081928](https://github.com/lagarcess/argus/actions/runs/37400081928) passed on attempt 2 after the original backend operation was canceled. The original failure remains recorded in [#872](https://github.com/lagarcess/argus/issues/872); it was not attributed to an application defect. Smoke run [37400081857](https://github.com/lagarcess/argus/actions/runs/37400081857) passed. [Terminal landing evidence](https://github.com/lagarcess/argus/pull/860#issuecomment-6007881597) records the completed workflow. The 16 implementation slices in the existing landing records remain landed; parent issue scopes remain open.

## Verification before the subsequent session landing

Apple session PR #864 at `257b1c080658c1b578df6c0edfed2cfa873ee578` is not ready to merge. [CI 37403404071](https://github.com/lagarcess/argus/actions/runs/37403404071) reports backend 10,396 passed, two failed, 1,248 skipped; the required PostgreSQL matrix reports 730 passed and one rejected skip. The guest pinned suite reports 134 passed and one failed. The failures concern the changed identity projection, its response schema and an extra local-auth opt-in. The author reproduced both failures on the candidate while the same two tests passed on integration. Fixed head `49215121969c17347bcf2e702199196e23ec4ede` changes tests and evidence only: 85 focused tests and one real local Auth test passed with no skips. [Final independent delta review](https://github.com/lagarcess/argus/pull/864#pullrequestreview-5423144255) is clean, with 85 independently executed unit tests passed and retained native evidence hashes verified. Exact-head CI is running; merge remains blocked until it passes.

Native Apple-name source `a6efe6e3360f1c4e58c97807b91547de527b0b04` passed independent verification: package 150 passed, four optional local-stack skips; focused cases 16 passed; independent boundary cases three passed; signed local API/Auth/PostgreSQL one passed; provider configuration 22 passed; actual model UI one passed with four screenshots. The report preserves an introduced XCTest property compile error and a deletion cleanup regression, their baseline reproductions, author fixes and successful reruns. This is local proof, not physical Apple authorization. Evidence-only publication `0f4b8b59c1006b2c92454403dad4cbc21a57854d` is pushed, preserving unchanged source and all 29 original entries plus publication provenance. Independent publication review is clean, with all 29 raw entries and 401 native provenance hashes checked. Dependency reconciliation remains pending.

Native deletion core `40708a935cc78cbaf30b0e9bacb9f1d59110c005` compiled and its 13 new deletion tests passed, but the complete package failed five existing Apple notification tests (eight failure events), with four local-stack skips. Those five tests passed on the exact name baseline. The deletion author published the shared-actor repair at `cc58b16f7f8ee4f520ffa4658f1396ba7a0cc4d7`; the independent runtime rerun is active. No passing full-package claim is made. The final application deletion adapter and its UI journeys remain unfinished.

## Ownership and external boundaries

Root owns integration landings and contract coordination. `apple_session_currency_reconcile` owns the session CI repair. `apple_name_contract` owns name evidence publication. `native_deletion_command` owns deletion actor changes. `apple_session_combined_native_verification` owns serial Mac and local PostgreSQL verification. Temporary database subleases are explicit and serial. The root database remains running; workers may clean only their own fixtures and resources.

Shared Foundations currency Home and forecast bindings have independent source reviews but no native runtime acceptance. Their recovered UI parent requires the outstanding explicit PR creation authorization following automatic approval rejection. The concrete publication packet is prepared; no alternate route bypasses that rejection.

The six existing product gates remain open in `orchestration/gates.md`: identity orphan policy, frozen former-member balance provenance, transmission consent, space ownership migration, retained release jobs, and late Apple cleanup semantics. The additional Home history meaning choice is now asked and parked: recorded observations versus reconstruction. Its proposed payload and next test unit are recorded in `shared-home-history-contract-audit.md`; no choice is assumed. Independent approved work continues. Phone, actual provider proof, hosted migration/readback, legal approval and feature activation remain separate gates. No hosted changes or activation occurred.

## Subsequent session landing

#864 merged as `5d46a73d4d97b0412dccff517eb43c73e4316977` after the reviewed repair passed all checks. [Landing record](pr864-landing-record.json) records the actual terminal outcome; earlier failure details above remain historical evidence. Canonical checkout parity is clean. Integration CI37405778022 and smoke37405778015 both passed, with housekeeping in #873. Native deletion core subsequently passed 164 package tests with four optional local skips, 19 focused tests, one actual local SDK/API/Auth/PG case and a generic app build; final UI and filesystem work remain open.

Focused landing configuration checks at the reconciled tree passed35, zero failures/skips, 8.95 seconds, using isolated synthetic settings with dotenv disabled. [Exact output](root-config-5d46.txt). No new environment variable names were introduced by #864.

## Subsequent name landing

#874 merged as `a2c65549b3ffcb97ee0be24b971110be8c090b32`, with17successful exact-head checks, three expected skips and no unresolved threads after clean final review. [Record](pr874-landing-record.json) preserves its matching tree and source retention. Canonical parity is clean. Integration smoke37407223674 and CI37407223683 both passed. Phone/provider/hosted/activation gates remain open.

## History authority correction

The observations-versus-reconstruction question was unnecessary. Current Cuadrao DESIGN lines257–267 and390–404 already select recorded-position observations, actual dates, same-scope signed contributions, no comparison from one observation, explicit partial accounts and no fabricated flat history or later data. The gate is resolved from that existing founder authority. The audit now cites those locks; no new founder answer is required. Missing temporal metadata, canonical DTO and complete-period spending coverage remain separate technical work. Six original product gates remain open.

## Subsequent deletion core landing and next scope

#875 merged as `8146d16e90633eb543781f8882665482f0d5dca9` after17successful checks, three expected skips, zero unresolved threads and a clean independent review. [Record](pr875-landing-record.json) preserves matching trees and accepted proof. Canonical checkout parity is clean; integration CI37408905271 and smoke37408905356 both passed.

The subsequent atomic cleanup candidate atf787ca63 passed independent package170/four opt-in skips, six real filesystem cases,20focused deletion cases and one actual synthetic SDK/API/Auth/PG case. The old external cleanup-order gap was reproduced, and a new fixture compile error was corrected before tests. Publication and final independent review of PR #876 at7887546 are complete; exact-head CI remains pending. Actual app receipt-store and UI work remain separate.

The existing observation APIs suffice for the raw personal reader. Counsel owns its bounded implementation and Mac verification; root retains historical attribution, authorization and household/move contracts. The former history-meaning question is resolved by existing design, not a new founder choice.

## Subsequent atomic cleanup landing and privacy proof

#876 merged as `184d2614e4d2beb5ed994bd3cd8f3a5ef211f1dd`, matching its reviewed tree. [Record](pr876-landing-record.json) preserves16successful exact-head checks, three expected skips, zero unresolved threads,170package passes/four optional skips, six filesystem cases,20deletion cases and one local SDK/API/Auth/PG case. Final UI/receipt-store, provider, hosted and phone gates remain open. Canonical parity is clean; integration CI37412482876 is running and smoke37412482873 passed.

Current simulator-bundle privacy verification passed7checks over12manifests with source equivalence; its [evidence](current-privacy-bundle/README.md) keeps the scope explicit. One unsigned archive attempt stopped before compilation on simulator-only platform configuration; no archive/report/signing acceptance is claimed. All local Mac and PG leases are released; owned temporary resources were cleaned and root/foreign resources preserved.
