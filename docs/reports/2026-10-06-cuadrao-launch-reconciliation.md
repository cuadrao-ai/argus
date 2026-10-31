# Cuadrao launch reconciliation, October 6, 2026

This record reconciles the consumer launch tracker
[#817](https://github.com/lagarcess/argus/issues/817) and its in-scope issues
against what is actually on integration. It is a documentation and GitHub
status audit. It changes no application code, test, migration, workflow,
configuration, flag, hosted system or installed build, and it spends no provider
money. #817 stays open: its finish line is a launch candidate that passes its own
gates, not accurate tracking.

## Source identity

| Item | Value |
| --- | --- |
| Integration audited | `codex/private-alpha-next` at `df3882668413e7978d3983adfe1f054cb83595c4` (PR [#873](https://github.com/lagarcess/argus/pull/873) housekeeping merge). Integration CI [37414161228](https://github.com/lagarcess/argus/actions/runs/37414161228) and smoke [37414161226](https://github.com/lagarcess/argus/actions/runs/37414161226) passed at this SHA. |
| Method | Fresh `git fetch origin`; every cited PR's `mergeCommit` read from GitHub and tested with `git merge-base --is-ancestor <mergeCommit> origin/codex/private-alpha-next`. Every checklist item was checked against code or documents at the audited SHA, not only against issue comments. |
| Environment | Repository and GitHub only. No hosted inspection, no simulator, no phone, no local API or database, no provider call. Local, simulator, CI, hosted, provider and phone results are kept separate throughout. |
| Recovery branch | `codex/cuadrao-connected-preview` at `1eca92329c62c012fc789beb3b9c973c49aaaef2`, pushed, not integrated, no PR. |

## Definitions applied

`implemented` means the full issue scope is on integration; a component, a branch
or a reviewed PR alone does not qualify. `verified` means the issue's applicable
acceptance passed with a linked commit, environment and journey evidence.
`enabled` means observed activation for a named environment and audience with
approval; it does not apply to documentation or test-only work. An issue closes
when its own scope and acceptance are complete. No acceptance criterion was
removed, moved or reinterpreted to close an issue. Every SHA below is the real
squash-merge commit, not the reviewed head.

## Result

- Closed issues and their labels are in the [closure table](#closed-by-this-reconciliation).
- No other in-scope issue earns `implemented`, `verified` or `enabled`. Several
  have landed bounded slices (recorded as checked items inside the issue and in
  the table below), but each still has acceptance that no landed evidence
  covers.
- Six product decisions remain open in the Trust ledger. They are the exact
  blockers for #818, #819, #798, #805, #828 and #803. See
  [open decisions](#open-product-decisions).
- #818, the scope matrix, blocks eleven launch issues and has no comment or PR.
  It is the highest-leverage unfinished deliverable.
- Four PRs remain open and each keeps its hold. See [open PRs](#open-pull-requests).

## Closed by this reconciliation

| Issue | Why it closes | Evidence and environment | Labels |
| --- | --- | --- | --- |
| [#676](https://github.com/lagarcess/argus/issues/676) password recovery throttle keyed on a spoofable hop | Its only written criterion is met: recovery throttling uses the trusted client IP header, and a test shows a rotated first `X-Forwarded-For` hop does not reset the limit. | PR [#865](https://github.com/lagarcess/argus/pull/865), merge `ce7c7350af9a75019a622016ce3a65dbd17e1cc8`. `web/lib/recovery-request.ts` reads only the configured trusted header (default `CF-Connecting-IP`). `web/__tests__/recovery-client-ip.test.ts` returns 429 on the new code and 202 on the old, and integration CI [37414161228](https://github.com/lagarcess/argus/actions/runs/37414161228) passed it. Environment is unit tests and CI. Hosted ingress sanitization stays with #686, #694 and #832. A web QA script (`web/e2e/qa-248`) still sets `x-forwarded-for`, which recovery now ignores; this is a note for its owner, not a defect found here. | `implemented`, `verified` |

An independent read-only reviewer tried to refute this closure and a second
proposed one. It confirmed #676 and rejected closing #804, so #804 stays open
below with its remaining criterion.

## Audit table

Merge SHAs are on integration unless marked. "Evidence environment" is the
strongest environment the cited evidence reached.

### Trust, identity and deletion

| Issue | Landed work (merge SHA) | Evidence environment | Exact remaining criterion | Owner or dependency | State and labels |
| --- | --- | --- | --- | --- | --- |
| [#800](https://github.com/lagarcess/argus/issues/800) sign-in ship gates | Gates 2, 3, 4, 5, 9 done: #844 `a6688eea1`, #857 `7018e0ede`, #864 `5d46a73d4`. Server revocation and admission: #858 `f5c83cd88`, #862 `7c2522fb7`. Name: #869 `927740efd`, #874 `a2c65549b`. Deletion core: #875 `8146d16e9`, cleanup #876 `184d2614e`. Manifest: #849 `5861a8f1b`. | Unit, real local Auth/API/Postgres, simulator. No phone, provider or hosted proof. | Gate 1: no app caller reaches `deleteAccount`, so there is no reachable deletion UI and no app re-prompt for a fresh Apple code; no check couples the client Apple flag to server `CUADRAO_APPLE_REVOCATION_CAPTURE_ENABLED`. Gate 6: end to end blocked by gate 1, #805 and #806. Gate 7: web Apple/Google sign-in not built and no recorded exclusion. Gate 8: manifest declares required-reason APIs only; collected-data answers, SDK closure on a signed archive and App Store labels open. Plus real provider and phone proof. | Native identity (the #877 recovery lead wires deletion UI, R3); privacy owner for gate 8; Lucas for the web decision and provider credentials. | Open. No milestone label. |
| [#798](https://github.com/lagarcess/argus/issues/798) first sign-in follow-ups | Item 2 (Apple name): server #869, native #874. | Local tests only. Migration is local-only. | Item 1 allowlist orphans: decision between a pre-sign-up hook (`supabase/config.toml` hook is commented out) and scheduled cleanup (runbook records a no-cron decision). Item 3 Hide My Email linking: decision, nothing built. Item 2: real Apple first-authorization proof and hosted migration. | Lucas decision (gate `identity-policy`); backend auth. | Open. No label. |
| [#803](https://github.com/lagarcess/argus/issues/803) #802 follow-ups | Items 1, 2, 3, 4, 6 landed in #858 and #864; item 5 documented. | Unit and local PostgreSQL. | Item 5: accept-and-document or guard the stalled cleanup-revoke race. `docs/API_CONTRACT.md` says acceptance of that recovery policy "remains open in #803". | Lucas decision (gate `apple-late-cleanup`). Recommendation on file: accept and document the forced sign-out recovery. | Open. Body checkboxes ticked for the five landed items. No label. |
| [#804](https://github.com/lagarcess/argus/issues/804) #794 follow-ups | #871 `c0d44d399b8fbf2edcdd0a8fd3ad4759a0e9c548` landed six of seven items: entropy-floor test, accurate hex comment, PID-scoped lock-wait test, runbook secret ordering, default-off beta flags in `render.yaml` and the release profile. The `WEB_CONCURRENCY` item is satisfied by the documented gate (`docs/PRIVATE_LAUNCH_RUNBOOK.md`), which the issue allows. | Unit tests and local PostgreSQL. CI skips the real-Postgres tests. | The census item is not met: `tests/test_account_deletion_fk_census_postgres.py` lines 711 to 721 assert hard-coded 3 and 0, and never read the census document, so the document's "Held 3 / Catalog only" rows can go stale without a failure. The test must assert the document's probe cells. That is a test change outside this documentation grant. Hosted secret, destructive migration approval and worker-count readback stay with #830 and #832. | Test owner; backend. | Open. Body checkboxes ticked for six items. No label. |
| [#805](https://github.com/lagarcess/argus/issues/805) frozen closed-line balance | Nothing built. #875 and #876 are deletion command and cleanup, not balances. | none | Build the frozen-balance read, the settle command and event, the bilingual copy, and the real-Postgres test. Blocked on the accepted contract: the canonical source of an "open balance with" a member and who may settle it. | Lucas decision (gate `balance-source`); then backend household/planning. | Open. No label. |
| [#806](https://github.com/lagarcess/argus/issues/806) PostHog deletion adapter | #847 `70b0cd389`: default-off adapter, durable request tracking, tests with the `persons_found: 0` shape. | Mocked provider and local PostgreSQL. No PostHog call. | Real PostHog request, completion and event readback with a deletion-scoped key; project parity between capture and deletion; Alpha API availability and approval; hosted configuration. A mock proves code behavior only. | Lucas (PostHog access); backend. | Open. `implemented` not earned because the core need is real deletion. |
| [#807](https://github.com/lagarcess/argus/issues/807) Lane 6 ops follow-ups | #846 `26c0692d6`: re-seal, fingerprint pin, rollback rotation rule. Item 5 per-worker limit is documented as 6N in `docs/API_CONTRACT.md`. #875, #876 partial. | Local PostgreSQL and docs. | Item 3: wire the escalation metric to an alert route or record the daily operator run as the only escalation path. Item 15: name the operator and revisit the no-cron decision. A one-line OpenAPI correction: the 403 text on `src/argus/api/routers/account.py` still says a placeholder, but placeholders get 401. Hosted worker-count readback. | Ops and release; Lucas names the operator. The OpenAPI line is a code change outside this grant. | Open. Body checkboxes ticked for landed items. No label. |
| [#811](https://github.com/lagarcess/argus/issues/811) explicit client grants | #837 `f655d131b` migration `20261005090000_explicit_client_grants.sql`, grant-matrix test, CI on pinned and latest CLI. #851 `49add7b0d` latest-CLI resolution. | Local on both CLI images; CI both legs green at the tip. | The CI pin still reads `2.109.0` (`.github/workflows/ci.yml` line 20) and the weekly latest run is inert until the workflow is on `main`, so the fix list's "then move the pin" is not done. Hosted application after the pending migrations, before/after hosted catalog readback, profile-save and job-follow confirmation, behind the migration gate's maintenance review. | CI owner for the pin; Lucas and ops for hosted. | Open. `implemented` not earned strictly (pin). No `verified`. |
| [#856](https://github.com/lagarcess/argus/issues/856) Google label at accessibility sizes | #857 changed button appearance only. | Simulator matrix. | The stock `GoogleSignInButton` is unchanged and still clips at Accessibility XXXL in Spanish. Acceptance needs readable complete labels on both entry forms, both languages, light and dark, with the official control retained. | Native identity and accessibility (#800 owner). Revalidate on the recovery branch first (#877). | Open. No label. |
| [#832](https://github.com/lagarcess/argus/issues/832) public-launch hardening | #865 `ce7c7350a` (#676); #845 evidence. | See children. | #807 alert and operator; #803 and #804 findings; #671 per-instance limiters (in-process `defaultdict`); #700 chat-turn `Idempotency-Key` replay (syntax check only); #656 raw `months_to_goal` label; #686 and #694 at the promotion that carries #674; #797 census gaps (nothing landed). Each needs its own evidence or an approved applicability decision. | Per child. | Open. No label. |

### Everyday money, home and chat

| Issue | Landed work (merge SHA) | Evidence environment | Exact remaining criterion | Owner or dependency | State and labels |
| --- | --- | --- | --- | --- | --- |
| [#818](https://github.com/lagarcess/argus/issues/818) scope and acceptance matrix | Direction only: #835 `7e0c0b1d9` (reuse decisions, locked stack), #814 `883d289ff`, #813 `4bc4bd4c9`. | Documents. | No finite matrix exists with owner, journey and environment per item. First chat jobs and memory/voice inclusion are not named. Space-model decisions are not recorded as settled. Customer-work baselines and targets are not recorded per journey. Nine unchecked boxes stay unchecked; two are only partly met. Closure needs one reviewed docs PR adding the matrix, after the founder answers the decisions below. | Captain and docs seat, with Lucas for decisions. Blocks #819, #820, #821, #825, #826, #828, #829, #830, #831, #832, #833. | Open. No label (planning). |
| [#819](https://github.com/lagarcess/argus/issues/819) space and ownership migration | Nothing. No `spaces`, memberships or `owner_space_id` in migrations or source. | none | Founder model lock, bounded API and data contract, additive migration, real-Postgres isolation and backfill proof, backup and recovery notes, vector-metadata census. | Lucas decision (gate `space-model`). Recommendation on file: keep personal roots and existing household grants. | Open. No label. |
| [#820](https://github.com/lagarcess/argus/issues/820) no-conversion currency | #853 `2b2d0d9e8` primary-currency persistence; #854 `7d037b07d` exact paired transfer amounts, default off. | Real local Auth/API/Postgres, simulator. No phone. | Home shows currencies alphabetically (`CuadraoHomeOverview.swift` lines 8-9); primary-first Home and Forecast presentation, one-currency charts, onboarding choice placement, native paired-transfer consumers, mixed DOP/USD connected journeys. Candidate bindings are on `codex/cuadrao-primary-home-bindings-20261005` (`87a616ef0`) and `codex/cuadrao-primary-forecast-binding-20261005` (`27dc03711`), not on the recovery branch (#877 R2). | Foundations owner; #877 R2. | Open. No label. |
| [#821](https://github.com/lagarcess/argus/issues/821) onboarding | Building blocks: invite gate and models (#794, #810), auth (#795, #864), Apple name (#869, #874). | Local. | No install-to-first-action flow exists. Needs invite intent preservation, waitlist path, permission recovery and a real-phone run, after #798, #800, #819, #820, #830. | Consumer journey owner. | Open. No label. |
| [#822](https://github.com/lagarcess/argus/issues/822) Accounts, Plans, Household | #838 `ec666c96c` recurring movement to Upcoming to confirmed payment; #836 `7ddb9cdbb` real-API proof; #839 `19f0dc3af` row actions. Household client #810 `ecb062348`. | Simulator iOS 27.0 and 26.5, local connected stack. Not hosted, not phone. | Account/activity breadth and reconciliation, Plan split and repayment journeys, admin invitation to removal journeys, beta quota behavior, deletion across shared records after #805 and #806, customer-work evidence. A bounded slice is implemented; the issue-level label is not earned. | Consumer journey owner; blocked by #819, #820, #805, #806. | Open. No label. |
| [#823](https://github.com/lagarcess/argus/issues/823) receipts | #776 backend draft foundation; native capture and local store. | Local and simulator. | Native has no `/financial/documents` client. Missing: connection to the backend, canonical save and split, private Storage (#778), Render Workflows job (`financial_documents.py` still uses `BackgroundTasks`; `workflows/main.py` has only `workflow_proof` and `run_backtest_job`), shared consent policy (#828), real camera proof, baseline comparison. | Consumer and storage owners; blocked by #778, #828, #822. | Open. No label. |
| [#824](https://github.com/lagarcess/argus/issues/824) Home insights, Search, moves | #838 rolling 30-day Upcoming; #839 Home detail with return and swipes. | Simulator. | Full Home history and insights from canonical records and coverage; known-zero rule; Search-to-detail from Updates and chat; greyed read-only pre-move history; real-data isolation. The observation reader exists only on the recovery branch (`5aa369d9e`), with no production caller. Historical type and ownership attribution contract needs review before any migration. | Foundations owner and Home owner; #877 R2. | Open. No label. |
| [#825](https://github.com/lagarcess/argus/issues/825) Updates, reminders, push | Native states only. The connected shell passes `.unavailable`. | Local. | No inbox router, event table, reminder scheduling or APNs code. Event ownership and durable read-state contract come first. | Events owner; blocked by #818. | Open. No label. |
| [#826](https://github.com/lagarcess/argus/issues/826) first chat jobs and runtime contract | Direction in the MVEE and `docs/ARCHITECTURE.md`; stack and provider locks. | Documents. | No contract spec and no founder bounded assignment. Of 15 boxes, two are met (stack applied, providers named); the rest need a committed spec under `docs/specs/lanes/`. | Runtime lead with Lucas for scope; blocked by #818. | Open. No label (planning). |
| [#827](https://github.com/lagarcess/argus/issues/827) agentic chat slice | Nothing. Connected chat is `ChatSampleView`, a design sample. | none | Everything, after #826, #828 and #822. | Runtime owner. | Open. No label. |
| [#828](https://github.com/lagarcess/argus/issues/828) one AI consent policy | Pre-existing per-draft document guard (`domain/ingestion/documents/service.py`). | Unit tests. | No persisted or versioned provider-transmission consent. Memory embedding (`personalization_memory_index.py`) and sensitivity-assessment (`personalization_memory_assessor.py`) calls have no consent check. Needs the scope and versioning decision first. | Lucas decision (gate `consent-policy`); consent-policy owner. | Open. No label. |
| [#829](https://github.com/lagarcess/argus/issues/829) Profile release boundaries | Code gating (`CuadraoFirstRelease`), lane inventory `lanes/cuadrao-profile-hidden-rows-backend.md`. | Simulator `ReleaseUIJourneyTests` 13/0 at the #838 and #839 heads. | Per-row exclusion statement or child issue, release tests that assert excluded routes are unreachable, the memory decision, and customer-work evidence. | Profile owner; Lucas for memory inclusion. | Open. No label (planning). |
| [#778](https://github.com/lagarcess/argus/issues/778) document source storage | Nothing. `source_bytes` is still `bytea`. | none | Private owner-scoped Storage bucket with an object reference, deletion on disconnect and account deletion, real-Postgres and storage tests, `API_CONTRACT` update, plus the listed low-severity folds. Blocks extraction enablement and #823. | Storage owner. | Open. No label. |

### Service, privacy and release

| Issue | Landed work | Exact remaining criterion | Owner or dependency | State and labels |
| --- | --- | --- | --- | --- |
| [#830](https://github.com/lagarcess/argus/issues/830) signing, domains, activation | Hosted nothing. #837 migration awaits hosted apply. | Every checkbox: entity and Apple team, bundle identifier availability, credentials and redirects, Resend domain, associated domains, APNs, effective release flags and schema identity, invite-code secret and the destructive migration gate, deletion operator, environment manifest, share-pages decision. | Lucas for founder-only access; service preparation. Blocked by #818. | Open. No label. |
| [#831](https://github.com/lagarcess/argus/issues/831) privacy, Terms, Apple disclosure | #849 `5861a8f1b` manifest; #845 `dd04130e8` privacy evidence and bilingual recommendations; #873 packaging evidence (Debug simulator app, 12 manifests). | #781 legal facts and counsel; published Spanish and English pages; App Store answers; a signed archive and the official aggregated Xcode privacy report (one unsigned archive attempt exited 70); consent-dependent claims. | Privacy and legal owner, counsel, Lucas. Blocked by #818. | Open. No label. |
| [#784](https://github.com/lagarcess/argus/issues/784) combined phone acceptance | Historical Mac verification of #809, #790, #810, #812. | The actual combined connected candidate on the phone with pinned identities. Depends on the prerequisite behaviors above. | One Mac and phone scheduler. Blocks #833. | Open. No label. |
| [#833](https://github.com/lagarcess/argus/issues/833) TestFlight | none | Eighteen open prerequisites plus approved external distribution and Beta App Review. | Release owner. | Open. No label. |
| [#834](https://github.com/lagarcess/argus/issues/834) submission package | none | #830, #831, #832, #833, then founder approval before Submit for Review. | Release owner and Lucas. | Open. No label. |

### Follow-ups and narrow fixes

| Issue | Finding | State |
| --- | --- | --- |
| [#840](https://github.com/lagarcess/argus/issues/840) dark-mode text | Not fixed on integration. The issue's suspected cause, `Color(white: 0.08)` at `ConnectedCuadraoShell.swift` line 81, is unchanged. A shared-palette fix for auth fields exists only on the recovery branch. | Open. Revalidate in #877 R4. |
| [#841](https://github.com/lagarcess/argus/issues/841) flaky canary test | Probably the same socket-reuse mechanism as #861, but that is an inference. No change maps an unowned transport failure to a reason code. | Open. Close only with a bounded repro or repeated green runs, or a linked duplicate finding. |
| [#842](https://github.com/lagarcess/argus/issues/842) native test debt | No commit references it and it has not been rerun at head. | Open. #877 R4 revalidates. |
| #861, #867, #872 | Narrow fixes already closed. No contradicting evidence found. | Stay closed. |

## Merge identities checked

All of these are ancestors of integration `df3882668`; the merge commit is
listed, never the reviewed head.

| PR | Merge SHA | PR | Merge SHA |
| --- | --- | --- | --- |
| #743 | `12bccd4d6e17` | #853 | `2b2d0d9e8ed3` |
| #744 | `fcbb70cc2899` | #854 | `7d037b07d4b9` |
| #808 | `915d67446729` | #857 | `7018e0edebbc` |
| #813 | `4bc4bd4c9b00` | #858 | `f5c83cd88a0a` |
| #814 | `883d289ff8f9` | #862 | `7c2522fb7d08` |
| #815 | `518429e47d5e` | #864 | `5d46a73d4d97` |
| #835 | `7e0c0b1d99c7` | #865 | `ce7c7350af9a` |
| #836 | `7ddb9cdbba36` | #869 | `927740efd791` |
| #837 | `f655d131bb10` | #871 | `c0d44d399b8f` |
| #838 | `ec666c96c40b` | #873 | `df3882668413` |
| #839 | `19f0dc3af36f` | #874 | `a2c65549b3ff` |
| #843 | `875de09ac211` | #875 | `8146d16e90633` |
| #844 | `a6688eea1089` | #876 | `184d2614e4d2` |
| #845 | `dd04130e8aa1` | #847 | `70b0cd389193` |
| #846 | `26c0692d634` | #849 | `5861a8f1b11c` |
| #851 | `49add7b0d4fb` | #860 | `13a1a339cbab` |

#803 and #804 cite two eval heads (`c4844525` for #802, `b84f5330` for #794) that
are not ancestors. Both are labeled as eval heads beside the real merge commits
`79831e4d` and `1478957e`; do not use them as ancestry anchors.

## Open product decisions

*October 6 update, after this record was first written:* the founder decided the assistant and memory and voice scope (see the two rows marked partly answered below). The other four gates remain unanswered.

The Trust ledger [gates.md](evidence/cuadrao-trust-20261005/orchestration/gates.md)
records six open gates. A search of the decision log, master plan, execution
board, MVEE, lane documents and every comment on #808, #813, #814, #815 and #744
found no founder answer to any of them. Two other gates in that file are
resolved.

| Gate | Answer on record | What it blocks |
| --- | --- | --- |
| `identity-policy`: #798 allowlist orphans and Hide My Email linking | Absent. The October 5 Apple-session lock states that it does not select this policy. | #798 items 1 and 3, #821 acceptance |
| `balance-source`: #805 canonical source and settlement owner | Partial. Decision 17 locks the outcome and copy. The source and who may settle are not decided. | #805, #822 deletion journey |
| `consent-policy`: #828 consent scope, versioning, memory and voice | Partly answered October 6: memory and voice are in release 1. Consent scope and versioning are still not decided; Option A is a proposal, not a lock. | #828, #827, #823 dispatch, #831 AI disclosure |
| `space-model`: #819 personal roots with household grants versus household-owned roots | Partial. Timing is locked before TestFlight. The model choice is open. | #819, #818, #820 consumers |
| `release-jobs`: #818 and #826 first retained chat jobs and memory/voice | Partly answered October 6: memory and voice are in release 1, and the assistant is the agentic one, with old Argus code kept until removed ([decision](../specs/argus-decision-log.md#october-6-2026-first-release-assistant-and-memory-and-voice-scope)). Which first jobs it does is still not named. | #818, #826, #827, #829 memory rows |
| `apple-late-cleanup`: #803 late provider revocation | Absent. | #803 only |

The recommendations on file are in `foundation-contract-map-proposed.md` and
`gates.md`. This record does not accept them. None of these gates blocks the
#877 recovery of the approved design.

## Open pull requests

Read back October 6, 2026. All four target `codex/private-alpha-next`. Full file
lists were paginated; the first page alone can mislead on a large PR. Skipped
draft checks are not passing evidence. No hold below was lifted and no PR was
merged or closed on its own authority beyond what the disposition states.

| PR | Head | State | Real scope | Linked | Hold | Disposition |
| --- | --- | --- | --- | --- | --- | --- |
| [#781](https://github.com/lagarcess/argus/pull/781) legal draft | `b9a695d747b6` | Draft, 3 docs files, merges clean, 54 commits behind | `docs/legal/` only | #831 | "Do not merge before in-app deletion is live", the draft's own do-not-publish banner, open P4 to P8 | Preserved as held. See below. |
| [#774](https://github.com/lagarcess/argus/pull/774) #773 landing record | `e23f5d3b865b` | Draft, 4 docs files, conflicted in the board and the ledger | docs only | none | none recorded | Superseded by this record. Unique content restored here. |
| [#732](https://github.com/lagarcess/argus/pull/732) web preview | `a63856a305e5` | Open, `triage:hold`, 367 files | 346 docs and evidence, 11 runtime files under `web/app/dev/ecosystem/`, 10 web tests and e2e | none | Founder deferral comment, [5884467031](https://github.com/lagarcess/argus/pull/732#issuecomment-5884467031) | Preserved as held. Not the native Preview. |
| [#646](https://github.com/lagarcess/argus/pull/646) result follow-up | `6ca156eb8504` | Draft, 11 files | 1 doc, 1 prompt and schema file, 1 web test, 8 evaluation tooling files | #606 | Founder go and live measurement; cap $12.50 or 30 minutes; prompt freeze deliberately not refreshed | Preserved as held. Not a consumer launch blocker. |
| [#744](https://github.com/lagarcess/argus/pull/744) iPhone plan | merged `fcbb70cc2899` | Merged | board and ledger | none | none | Historical authority. Not pending. |

**#781.** The hold stands. Landed work does not discharge it. Deletion is behind
`CUADRAO_ACCOUNT_DELETION_ENABLED=false` and Apple and Google are default off, so
the Terms line promising deletion from the app is not yet true. The draft's
deletion text omits decision 17 (placeholder member, frozen balances, plan
handover) and calls deletion final, which the #845 recommendations contradict
because deletion can stay pending until providers confirm. Its provider list
omits Perplexity and OpenRouter memory assessment, and it names Plaid, Gmail,
voice and PostHog without saying "only if enabled". Still open and not
invented here: operating entity and jurisdiction (P4), support address (P5),
publication location (P6), actual backup, log and analytics retention (P7), and
counsel review (P8). Editing the draft needs an assignment under #831.

**#774.** Its landing report, the PR #773 register section, the stale-sentence
corrections (lane header and the sentences still calling that lane unmerged) and
the `DOCUMENTATION_AUTHORITY.md` correction were unique and are restored by this
change. Its header rewrites of the board and the ledger would have regressed
newer status and were dropped. It carried a stale parity sentence naming
`.github/argus-env.sh`, which no longer holds the flag; the restored record says
so. Close #774 as superseded by the pull request that carries this record.

**#732.** Owner is the founder. The comment's whole text is that it needs rework
and a decision from the founder and is deferred. It records no date, assignee or
trigger. No merge, rework, rebase or close is recorded here.

**#646.** It changes model-facing text, so the repository's scorecard rule
applies before any merge. Its measurement baseline now needs recomputing because
integration changed `result_conversation.py` in `c77ff4ba7` after the proposal
was written. No go exists on the PR or on #606.

## Corrections made to tracking text

- #817 body: current status section and checklist annotations; the sentences
  calling PR #835 unmerged are corrected with a dated note; the earlier October 4
  status text is preserved.
- The unticked boxes inside #803, #804 and #807 now match landed work.
- Dated reconciliation comments on each open in-scope issue state what is
  complete, what is missing, what evidence closes it and who owns it.
- The execution board gains an October 6 checkpoint and the restored #773
  landing register. `DOCUMENTATION_AUTHORITY.md` no longer lists shared Plan
  consumers as unsettled.

## What needs Lucas

1. Answer `space-model`, and name the first chat jobs (the rest of `release-jobs`). They gate #818, which blocks eleven issues, and they unlock the matrix, the migration and the first chat jobs.
2. Authorize publication of the recovery pull request and set a phone window for
   the combined Check build, once the recovery lead reports R1 to R4 done.
3. Later and independent: the other four gates, the PostHog deletion access, the
   legal facts for #781, the hosted readbacks, #732 reactivation and the #646 go.
