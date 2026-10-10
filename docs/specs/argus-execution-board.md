# Argus private iPhone execution manifest

**Updated:** October 10, 2026. Bounded hosted Business assignment added.
**Execution state:** Consumer PR #937 is merged with accepted simulator evidence and green pre-merge CI. Build 3455 is installed; hosted manual-money acceptance remains open. The current Consumer assignment below supersedes the older sequencing only for this lane. The [October 4 code checkpoint](../reports/2026-10-04-cuadrao-code-integration-landing.md) retains its historical evidence.
**Product owner:** [MVEE](argus-minimum-viable-ecosystem-experience.md).
**Authority and onboarding:** [DOCUMENTATION_AUTHORITY](../DOCUMENTATION_AUTHORITY.md).

## Business hosted invite-only build October 10, 2026

The [22:13 UTC founder grant](argus-decision-log.md#october-10-2026-hosted-business-beta-and-build-grant)
authorizes the bounded hosted Business build, clean integration merges and
staging only. The root coordinator owns the sole merge slot and staging
actions. Tracker [#942](https://github.com/lagarcess/argus/issues/942) retains the
larger flows. Related first-flow issues are #943, #944, #946, #947 and #948.
C0 is a build step under that tracker, not another name for issue #943.

The fetched starting integration is `77ddf2c7d33cc4c7273cc4c39354b5152fe01e91`,
the landed [#953](https://github.com/lagarcess/argus/pull/953) documentation
checkpoint. The [Business execution spec](lanes/cuadrao-business-agent-execution-spec.md)
owns C0-first order and J1 to J3. The [lane handoff](../handoffs/cuadrao-business-lane.md)
records retained implementation and exclusions. No runtime slice or customer
journey is claimed delivered by this assignment record.

These are collaboration roles in the root task. They are not new UI-visible
Codex lane threads. All listed worktrees start from the recorded integration.

| Owner | Exclusive worktree or evidence role | Current assignment and dependency |
| --- | --- | --- |
| `/root/shared_context` | `/tmp/cuadrao-hosted-context-20261010`, branch `codex/cuadrao-hosted-context-20261010` | Repair the shared startup index, preserve full instructions, correct stale pointers, and record current decisions and assignments. Documentation only. |
| `/root/runtime_shape_astra` and `/root/runtime_shape_sol` | Read-only design grounding | Inspect the integrated runtime and sandbox dependency candidates. Propose the smallest C0-first contract. They publish no code or shared contract edits. |
| `/root/design_grounding` | Read-only existing UI and Mobbin grounding | Identify the current accountant flow and bounded interaction needs. No UI or product copy edits. |
| Runtime writer, not yet assigned | `/tmp/cuadrao-hosted-runtime-20261010` | Await the chosen C0 contract and an exclusive file assignment. No implied dispatch from this row. |
| Web writer, not yet assigned | `/tmp/cuadrao-hosted-web-20261010` | Await the chosen API/data contract and exclusive UI assignment. No implied dispatch from this row. |
| `/root` | `/tmp/cuadrao-hosted-verification-20261010` | Assemble and independently verify the exact candidate. Own merge and staging actions under the grant. Record semantic overlap, CI and compatibility before each landing. |
| Existing Business lane, thread `01a0de75-29ee-71f0-8f58-0d2bb3934a33` | Existing P0 inventory and private handoff | Retain read-only sandbox dependency inventory and decision reconciliation. Identify missing dependencies and their owners. Do not publish the sandbox wholesale. |

The first hosted acceptance joins a permitted owner's WhatsApp transaction and
its follow-up facts to one traceable record in the authorized accountant web
view. Cover varied natural-language transactions, explicit unknowns, correction,
source preservation, revision history, duplicate delivery and human approval
through the current grant. "Pagué 850" is one example. Do not use phrase or
regex intent gates. A synthetic or laptop test supports engineering verification,
but cannot close hosted customer acceptance. Do not close all seven flows or
claim all J1 to J3 shipped from the first proof.

The deployment candidate must identify the actual staging service revision,
Business web API binding, permitted sender, verified callback and WABA
subscription, current sender-to-Business linking and authorized readback.
The coordinator confirmed `cuadrao-api-staging` at
`cad1cbe1ec27ff89c08eadbec31718a0e627383c`, on the integration branch with
`autoDeploy` off. The selected workspace contains that staging API and the
main API/web. It has no separate staging web. These observations do not prove
the new Business flow or authorize main exposure. #941 remains the real WhatsApp activation prerequisite. Its controlled test
connectivity must be distinguished from general public onboarding.

The [22:22 UTC continuation](argus-decision-log.md#october-10-2026-hosted-business-beta-and-build-grant)
approves workspace `tea-d5rdkfk9c44c73e7a1ig` and names the runtime model
choices. The later continuation selects Grok 4.3 as the first evaluation
judge and prohibits Astra development runtime or judge API calls. Calibrate
known-good and known-bad cases and retain deterministic state assertions.
The [22:32 UTC development-key grant](argus-decision-log.md#october-10-2026-hosted-business-beta-and-build-grant)
supersedes the $5 test cap and pending-development-limit call hold. Use only the
existing development `OPENROUTER_API_KEY`, until its conservative allowance is
exhausted or its expiry at `2026-10-12T02:21:00Z`. Do not swap to a registered
or guest key or rotate credentials. The coordinator's safe read gives
$72.567644643 before concurrent usage, from $300 less total usage
$227.432355357. The larger provider monthly-remaining figure is not all
spending authority. Refresh usage before calls and subtract outstanding work.
Only the root coordinator controls live calls, reservations, concurrency and
token bounds. Judges, fallbacks and retries share this allowance. Synthetic
data only. No live call has occurred; C0, runtime and evaluations are not ready.
Sonnet 5.5 is a potential stretch choice that needs a demonstrated need and
fresh confirmation. It is not an automatic judge or runtime fallback.

First acceptance uses one owner, one authorized accountant and one Business
at a time. The coordinator sequences a direct named-accountant per-business
grant within that existing milestone. Full firm-to-human delegation remains an
L11 roadmap requirement, not a blocker for the first bounded flow or a completed
capability. Do not invent a firm identity. Isolated synthetic test grants are
authorized. Real persistent grants and named live testers still require actual
business authorization and concrete scoped setup confirmation.
New paid services, credentials, expanded grants and security settings also need
that confirmation. The root coordinator owns the hosted
web delivery choice because no separate staging web exists. Tonight's target
is online verification, contingent on the build, staging web setup and candidate
acceptance. The existing staging-only deployment grant remains; new costs and
access expansion still need concrete scoped confirmation.
Retain #925 at `1426404d82ade9ac1eaed255b0e68ed7db9d4a1a` and the sandbox at
`df208f7ec2379cd84efd55eea0deb685d67c5360` as exclusions. T1 defines any needed
tool filter through the canonical catalog, without depending on #925's wording
or eval guard. Model-facing changes still need their committed scorecards.

Stop affected work for missing dependency contracts, duplicate writers,
unauthorized live or hosted actions, uncertain external outcomes, or scope
expansion. Continue independent authorized work. Consumer native acceptance and
Apple TestFlight holds remain. Consumer compatibility must pass. No main or
production promotion, public signup, marketing or legal launch is in scope.

## Consumer assignment: October 9 founder direction

[PR #937](https://github.com/lagarcess/argus/pull/937) landed as `43fac94de2`.
Lucas accepted simulator evidence plus green CI and stopped VoiceOver/Switch
Control testing. The [landing record](../reports/2026-10-09-pr-937-integration-landing.md)
owns the exact source, evidence and verification limits.

Next is the signed-in free account's manual-money journey against
`https://cuadrao-api-staging.onrender.com` only: accounts, transactions, budgets,
goals, search/find later, per-currency totals, corrections and correct balances
after relaunch; Spanish, English and large text. [#877](https://github.com/lagarcess/argus/issues/877)
remains open until the assigned connected journeys are accepted.

Guest mode, saved receipts and shared plans remain locked. The transaction-sheet
redesign stays parked. RevenueCat is outside scope. No more accessibility tooling,
TestFlight upload, new phone install, newer-code deployment or schema changes are authorized.
Lucas subsequently approved the staging owner enabling only the money gate on
the pinned `cad1cbe1e` backend, restarting it and arranging a synthetic test login.
That setup is complete; the [staging evidence](../reports/evidence/consumer-staging-preflight-20261009/README.md)
records authenticated HTTP 200 and one passed native account correction/relaunch
test. Broader acceptance remains incomplete. No further hosted change is granted.
Consumer must coordinate shared ingestion, auth, API, schema and runtime changes
with their existing owners. Business and Marketing retain their own assignments.

## Cuadrao website integration checkpoint

[PR #884](https://github.com/lagarcess/argus/pull/884) delivers the bilingual Business and Personal marketing preview under its default-off flag. The [delivery record](../reports/2026-10-07-cuadrao-website-integration.md) owns its evidence and merge verification. Public launch, Business inquiry delivery and Supabase early-access capture remain open in #880, #881 and #882. This website assignment does not change the mobile roadmap, enable a Business app or authorize deployment.

[PR #929](https://github.com/lagarcess/argus/pull/929) landed the historical Marketing evidence and rollback corrections as `4cb85949b4dea6855971c8268aac1bd1a0cacb01`. The [reconciliation and landing record](../reports/2026-10-10-pr-929-reconciliation.md) preserves source identity and verification. The accepted #939 design remains pending its own integration landing. #927 stays held against main; deployment and public forms remain on hold.

## Business connected-flow and E0 design checkpoint

Lucas approved the [connected Business flow](cuadrao-business-connected-flow-spec.md)
and [offline E0 implementation plan](cuadrao-business-e0-implementation-plan.md),
with task-by-task independent review. The [decision record](argus-decision-log.md#october-7-2026-business-connected-flow-and-offline-e0-plan)
records the documentation-only publication grant and verified source hashes.
This checkpoint publishes design; it claims no E0 implementation or proof.
Lucas will coordinate the existing Business agent for execution.

Business retains the isolated capture-to-expense work and connected period pilot.
Its space contract remains with [#819](https://github.com/lagarcess/argus/issues/819)
and the reviewed [#910 proposal](https://github.com/lagarcess/argus/pull/910).
Consumer coordinates shared migration order and its release candidate through
[#833](https://github.com/lagarcess/argus/issues/833). Marketing retains its separate
launch through [#880](https://github.com/lagarcess/argus/issues/880).
Offline E0 needs no shared migration or hosted service. Its P0 official-source
and profile verification gate remains open. No lane priority or live fiscal
route changes through this publication.

## Current mobile roadmap: October 4 founder lock

The founder approved this execution update on October 4 after reviewing build
3423 and the mobile roadmap. The immediate work is to connect and verify the
product, complete onboarding, discuss Cuadrao's agentic runtime, and reconcile
privacy and release requirements. Broader Liquid Glass polish is deferred;
measured responsiveness fixes preserve the approved artwork and interactions.

The October 9 Consumer assignment above takes priority for that lane. The six-lane contract and
the release UI table below retain their detailed requirements. This lock does
not authorize a merge, deployment, hosted flag, migration, paid provider run,
new runtime implementation, or automatic restart of a parked lane. Claude's
existing scoped assignments are preserved. The founder transferred mobile
ownership to Codex on October 4 after Claude exhausted usage. The runtime
discussion must produce a
separate bounded assignment before architecture or model instructions change.

### Completed checkpoints, with limits

A checked item means only the named checkpoint is complete. Implementation,
merge, simulator verification, phone installation, and connected acceptance
are separate states.

- [x] Core design graft landed on integration: foundation, Plans, receipts,
  contextual chat, Home, Search, Updates, Profile, Settings, and preview tests
  through [#783](https://github.com/lagarcess/argus/pull/783),
  [#785](https://github.com/lagarcess/argus/pull/785),
  [#786](https://github.com/lagarcess/argus/pull/786), and
  [#792](https://github.com/lagarcess/argus/pull/792). Preview availability does
  not establish connected service behavior.
- [x] Backend and native foundations landed for invitations, sign-in, and
  deletion through #788, #794, #793, #795, #802, #791, #799, and #801. The
  [Grok handoff](https://github.com/lagarcess/argus/pull/790#issuecomment-5975107437)
  pins their merges and enablement limits. This does not mark live features done.
- [x] Local verification checkpoint recorded. The
  [round-two candidate ledger](https://github.com/lagarcess/argus/blob/2bde54e48/docs/reports/evidence/cuadrao-iphone-candidate/LEDGER.md)
  records the uncontended `03a33ef2` UI run: 119 passed, 48 skipped, zero
  failures. Both earlier failing tests pass in that full run. Mac builds,
  backend/database/web results and local connected walks retain their named
  tested commits. Codex checked the original UI log during recovery.
- [x] Interrupted visual classification completed: all 92 differing pairs and
  six new-only captures inspected. No new layout or money-format regression
  established. Scroll, slider-input, persisted-hint and transition differences
  retain explicit limits in the [recovery evidence](../reports/evidence/cuadrao-mobile-recovery-2026-10-04/README.md).
  This is not pixel equality or connected-device acceptance.
- [x] Signed preview build 3423 from candidate
  `0408469282a4fe3c5c7857fa668544f7cff7624c` installed and launched on the iPhone
  15 on October 4. Codex observed successful `devicectl` install and launch
  results for `local.cuadrao.design.47R3855RTJ` after reading build 3423 from
  the app's Info.plist. This updates the earlier ledger's unavailable-phone
  statement; it does not prove physical journeys, live auth, or reduced lag.
- [x] Invite-hardening issue [#789](https://github.com/lagarcess/argus/issues/789)
  closed on October 4 after #794. Related follow-ups remain separately owned.
- [x] Default-grants finding recorded as
  [#811](https://github.com/lagarcess/argus/issues/811), including affected
  environments and reachable writes. Filing and assessment are complete;
  its fix and acceptance checks remain open.

- [x] Independent code review and fresh Mac verification completed for #809,
  #790, #810 and #812. Debug/Release builds, focused host checks, 24 release UI
  journeys and ten combined journeys passed. The [code landing record](../reports/2026-10-04-cuadrao-code-integration-landing.md)
  preserves exact source identities, durable captures and the remaining gates.

### Later foundation alignment

The founder identified docs-only [#814](https://github.com/lagarcess/argus/pull/814)
and [#815](https://github.com/lagarcess/argus/pull/815) as the foundation for later
builds. #814 retains this board as the delivery checkpoint. Its currency rule,
pre-TestFlight space-model timing and provider direction inform future assigned
mobile slices; they are not implemented by candidate `03a33ef2`. The new model
still has its stated design/engineering decisions open. #815 archives three
historical specs with compatibility pointers. Neither PR expands this mobile
verification recovery into business, runtime, migration or archive work.

### Remaining work and acceptance

| Work | Current state | Next deliverable and completion check |
| --- | --- | --- |
| Candidate review and landing | The source in this tree includes #809, #790, #810 and #812; independent reviews and affected Mac verification passed | See the [code landing record](../reports/2026-10-04-cuadrao-code-integration-landing.md) and final #812 landing comment for exact heads, merge commits and terminal CI. Preserve remaining device, service and enablement gates. Later design tweaks are separate work. |
| Device responsiveness and connectivity | Phone profiling and app computation fixes recorded in #812; physical connected acceptance remains open | Retain the measured traces and remaining performance limits. The phone is disconnected; resume physical interaction and persistence checks when it returns. Candidate 3428 is not installed. Simulator never-idle counts are not frame-hitch proof. |
| Onboarding | Sign-in and invitation building blocks exist; complete first-use acceptance is open | Install, preserve invite intent, enter code, sign in, complete verification, select or join the permitted context, and perform the first useful action. Cover cancellation, invalid/expired codes, denied permissions, interruption, and relaunch. Request permissions when the feature needs them. |
| Accounts, Plans, Household | Services, native paths and default-off invitation client included | Verify the connected financial and shared journeys on the phone, including relaunch, revoked access, recovery, and correct personal/household boundaries. Preserve existing contract owners. |
| Receipts and imports | Capture/review UI and durable draft foundations exist | Connect capture, save for later, reopen, prepare, correct, split, approve, and save through the same financial services. Prove persistence and sharing boundaries. Keep source/extraction enablement gates open until satisfied. |
| Home, Search, Updates, moves | Designs and partial connected foundations exist | Complete the assigned history/projection, search-to-detail, account-move history, inbox, reminder, and private push paths. Show known zero only with confirmed coverage. Verify authorization, origin navigation, and event-driven data rather than fixtures. |
| Cuadrao chat identity | Small presentation task remains | Discuss and settle the chat/menu-bar logo within the design system; implement and check accessibility when assigned. Do not make it a dependency of runtime architecture. |
| Agentic Cuadrao | Continuous-conversation direction and reuse baseline recorded; runtime lane remains unimplemented | [#826](https://github.com/lagarcess/argus/issues/826) defines the first jobs, space/context transitions, permitted memory, confirmations, durable-job recovery and evaluation under the [experience owner](argus-minimum-viable-ecosystem-experience.md#continuous-cuadrao-conversation) and [reuse decisions](../ARCHITECTURE.md#cuadrao-reuse-decisions). [#827](https://github.com/lagarcess/argus/issues/827) delivers only the approved contract. |
| Privacy, Terms, and Apple readiness | Draft #781, consent/deletion presentation, and backend foundations exist | Reconcile actual data flows, permissions, retention, deletion, provider handling, manifests, published policies, and review access. Complete the release audit and connected acceptance before claiming external TestFlight readiness. |
| Profile backend features | Full design retained in development; unfinished release entries gated | Keep the complete development experience. Persist avatar selections before restoring the connected release editor. Track other unfinished Profile backends after chat; the removal of email notifications remains permanent. |

The assistant must use the same financial actions, permissions, and confirmation
rules as manual controls. The
[agentic direction](argus-minimum-viable-ecosystem-experience.md#agentic-ecosystem-direction-and-sequence)
already says the research/backtest-oriented chat alone does not satisfy Cuadrao.
Preserve useful Argus services and the existing single runtime until its separate
assignment explicitly changes the architecture. No financial write follows from
a hypothetical question or unapproved model output.

All customer-journey issues use the [customer work removed](../PRIVATE_LAUNCH_RUNBOOK.md#customer-work-removed)
acceptance questions. The [scope matrix issue](https://github.com/lagarcess/argus/issues/818)
records each owner, baseline and completion evidence. Use the existing
[consumer tracker](https://github.com/lagarcess/argus/issues/817); no second queue
is created. Tool retirement must follow the architecture's reuse boundary.

### Parallel execution and priority

The [consumer launch tracker #817](https://github.com/lagarcess/argus/issues/817)
owns the linked issue checklist. This table groups that same work, not a second
queue. Leverage reflects dependencies and customer value, not an estimated date.
Landed foundations above remain complete; none of these rows claims connected
release acceptance. Scope selection does not silently remove approved journeys.

| Pillar | Customer outcome and issues | Parallel work and true handoff | Launch leverage |
| --- | --- | --- | --- |
| Scope, spaces and money rules | A finite release; consistent ownership, permissions and currency. #818, #819, #820. | Scope and contract work first. Auth/security and service preparation can run alongside it. Serialize shared ownership, money and migration changes. | Highest dependency leverage: every connected reader and writer relies on these rules. |
| Connected everyday money | Install, sign in, create accounts/plans, invite household members, correct records and split a receipt. #821, #822, #823, with #778 storage. | Prepare onboarding/capture UI in parallel. Connect and verify each journey as its shared contracts stabilize; receipts reuse the confirmed financial-write owner. | Highest customer leverage: one complete receipt-to-reviewed-expense journey proves the central loop. |
| Continuous agentic chat | Resume work with scoped context and approved actions. #826, #827, with #828 consent. | Define the bounded contract alongside manual workflows. Implement against accepted financial actions and the shared consent owner; serialize runtime changes. | High, after shared actions exist. Reuse the [locked stack](../ARCHITECTURE.md#cuadrao-reuse-decisions); do not restart framework selection. |
| Home, Search, Updates and Profile | See accurate summaries, find records, receive notices and reach honest account controls. #824, #825, #829. | Separate read/presentation owners can work in parallel after read/event contracts settle. Native navigation and shared state still have one writer. | High integration value; reuse canonical records and events instead of duplicating calculations. |
| Trust, privacy and operations | Safe sign-in/deletion, permissions, consent, recovery and accurate policies. #800, #798, #805, #806, #811, #828, #831, #832. | Start applicability audits, policy evidence and existing fixes now. Coordinate auth/deletion/RLS edits with space migration. Final signoff follows actual included behavior. | High release leverage: early work avoids discovering launch blockers at the end. |
| Service and distribution setup | Working credentials, app links, push, signing and reviewer access. #830; prepare #833/#834 materials. | Prepare alongside engineering; feature activation waits for its own verified gates and approval. Ask for founder-only account access early, in one batch. | High schedule leverage: external setup must not wait for the UI to finish. |
| Combined acceptance and release | One working phone build, short TestFlight, then submission readiness. #784, #833, #834. | Test completed slices early. Serialize final candidate/device acceptance, beta exit and submission approval. One Mac scheduler owns tests and profiling. | Final sequence; preparation and focused checks run earlier. |

Recommended first allocation: scope/space/money owner, identity/security owner,
service/privacy preparation owner, and consumer-journey owner preparing the
first complete loop. Chat-contract work can progress alongside that loop; it
does not require all Home/Profile polish to finish. Split additional UI work
only after its shared contracts and file ownership are clear.

The main completion chain is scope and shared contracts -> connected money
and receipt/chat journeys -> one accepted device candidate -> TestFlight exit
-> submission approval. Trust and service work must join that chain before the
relevant feature or distribution gate. Existing native GitHub prerequisites
remain authoritative for specific issue closure; scheduling priority is not a
new blocked-by relationship.

Do not defer performance and accessibility to the last candidate. Check real
journeys as they become available, preserve the artwork and gestures, and
measure reported lag rather than removing interaction. Final acceptance still
needs the actual connected phone build. Broader Liquid Glass adoption remains
off the launch critical path.

### Release gates still open

October 5 Trust and Foundations checkpoint through integration `c0d44d399b8fbf2edcdd0a8fd3ad4759a0e9c548` includes [#851](https://github.com/lagarcess/argus/pull/851), [#844](https://github.com/lagarcess/argus/pull/844), [#846](https://github.com/lagarcess/argus/pull/846), [#858](https://github.com/lagarcess/argus/pull/858), [#857](https://github.com/lagarcess/argus/pull/857), [#863](https://github.com/lagarcess/argus/pull/863) and [#853](https://github.com/lagarcess/argus/pull/853) and [#868](https://github.com/lagarcess/argus/pull/868) and [#862](https://github.com/lagarcess/argus/pull/862), [#849](https://github.com/lagarcess/argus/pull/849), [#869](https://github.com/lagarcess/argus/pull/869) and [#847](https://github.com/lagarcess/argus/pull/847), and [#854](https://github.com/lagarcess/argus/pull/854), and [#845](https://github.com/lagarcess/argus/pull/845), and [#865](https://github.com/lagarcess/argus/pull/865), and [#871](https://github.com/lagarcess/argus/pull/871). These slices add release sign-in safeguards, local deletion recovery proof, Apple credential subject binding, official button appearance, a synthetic canary fixture repair and authoritative primary-currency persistence with partial profile updates. Narrow defects #861, #848 and #867 are resolved. Parent launch issues remain open; social sign-in/deletion remain disabled. [The run record](../reports/evidence/cuadrao-trust-20261005/active-queue-20261005.md) owns exact lineage, independent proof, integration checks and the remaining queue.

October 6 session checkpoint: [#864](https://github.com/lagarcess/argus/pull/864) landed as `5d46a73d4d97b0412dccff517eb43c73e4316977`. Existing session provenance, Apple validation and authoritative profile identity passed independent native/local and exact-head CI checks. [Landing record](../reports/evidence/cuadrao-trust-20261005/pr864-landing-record.json) owns counts and remaining gates. Native name/deletion adapters, phone/provider/hosted proof and activation remain separate; #800/#803 remain open. Housekeeping proceeds through #873.

October 6 name checkpoint: [#874](https://github.com/lagarcess/argus/pull/874) landed as `a2c65549b3ffcb97ee0be24b971110be8c090b32`. The native Apple name journal preserves first-grant input and derives retry from the existing session owner and canonical server initializer. [Landing record](../reports/evidence/cuadrao-trust-20261005/pr874-landing-record.json) owns the separate local proof, retained source hashes and phone/provider/hosted gates. Deletion UI and cleanup remain separate.

October 6 deletion core checkpoint: [#875](https://github.com/lagarcess/argus/pull/875) landed as `8146d16e90633eb543781f8882665482f0d5dca9`. Journaled native deletion handles interruption, uncertainty, pending retirement and validated completion through the existing session owner. [Landing record](../reports/evidence/cuadrao-trust-20261005/pr875-landing-record.json) preserves local proof and limits. Final UI, atomic receipt cleanup, provider/hosted/phone acceptance and activation remain open; no frozen-balance semantics are invented.

October 6 cleanup checkpoint: [#876](https://github.com/lagarcess/argus/pull/876) landed as `184d2614e4d2beb5ed994bd3cd8f3a5ef211f1dd`. Confirmed local cleanup admission is atomic with session validation and acknowledgment; failed cleanup retains the existing completed journal for local-only retry. [Record](../reports/evidence/cuadrao-trust-20261005/pr876-landing-record.json) preserves filesystem and SDK proof. Actual receipt-store/UI integration and external acceptance remain separate.

October 6 reconciliation checkpoint (integration `df3882668413e7978d3983adfe1f054cb83595c4`): the [launch reconciliation](../reports/2026-10-06-cuadrao-launch-reconciliation.md) matches every #817 child to its landed merge commit and acceptance evidence. It records that #835 merged as `7e0c0b1d99c71bf121f3891beab56e74087668c2` and that this board is on integration, correcting #817's October 4 text. Apart from #676 (closed `implemented` and `verified`), no in-scope issue earns `implemented`, `verified` or `enabled` at issue level. Six product decisions (#798 policy, #805 balance source, #828 consent scope, #819 space model, #818/#826 first chat jobs and memory/voice, #803 late revocation) remain open in the Trust gates record and are the exact blockers for #818, #819, #798, #805, #828 and #803. The finite scope matrix in #818 does not exist yet and blocks eleven issues. Open PRs #781 (legal draft), #732 (web preview) and #646 (result follow-up) keep their holds; #774 is superseded by the restored [PR #773 landing register](#pr-773-integration-landing); #744 is merged history. October 6 founder decision: the consumer assistant is the agentic assistant, memory and voice are in release 1, and the old Argus chat code stays until the founder removes it ([decision log](argus-decision-log.md#october-6-2026-first-release-assistant-and-memory-and-voice-scope)). The first chat jobs and the consent scope and versioning remain open. The restored-UI recovery is handed to #877 in the [recovery handoff](../reports/2026-10-06-cuadrao-877-recovery-handoff.md). Final phone acceptance precedes any authorized runtime landing. This checkpoint changes no issue scope and authorizes no merge, flag, migration, provider run, deployment or submission.

The founder selected the existing approved Preview3427 interface for mobile recovery. Counsel owns that presentation work on `codex/cuadrao-connected-preview`; Trust preserves the session, consent and deletion action owners. Money or auth tests alone do not prove full UI acceptance. GitHub runner-allocation mitigation restored executing checks; every remaining slice still requires its terminal exact-head CI. Phone, hosted/provider proof and legal approval remain open.

- [x] October 5 overnight landing: #835, #837, #838, #836 and #839 merged with
  independent reviews; integration `19f0dc3af`. Bounded slices of #822 and #824
  (recurring movement to Home Upcoming to confirmed payment; Home movement detail
  and row gestures) are implemented and simulator-verified, not enabled or
  device-accepted. The [overnight landing record](../reports/2026-10-05-cuadrao-overnight-integration-landing.md)
  holds exact SHAs, evidence and limitations.

- [ ] Complete the sign-in gates in
  [#800](https://github.com/lagarcess/argus/issues/800), required credentials,
  provider configuration, and device checks. Apple, Google, and email remain
  the selected choices.
- [ ] Complete native connected deletion and its enablement dependencies
  [#805](https://github.com/lagarcess/argus/issues/805) and
  [#806](https://github.com/lagarcess/argus/issues/806). Retain truthful
  pending/retry handling and the agreed flag-off support fallback. The operator
  retry process remains manual; no schedule is authorized here.
- [ ] Close [#811](https://github.com/lagarcess/argus/issues/811) against its
  acceptance and environment gates. A safer existing hosted configuration does
  not certify a newly built database. The implementation landed on October 5
  through #837 (`f655d131b`) and passed on both local CLI images and in CI;
  hosted application, readback and the migration gate's maintenance review
  remain.
- [ ] Finish [#784](https://github.com/lagarcess/argus/issues/784) for the actual
  combined candidate and the relevant physical journeys. Keep
  [#778](https://github.com/lagarcess/argus/issues/778) before document extraction
  enablement. Setup for universal links and push remains separate from UI completion.
- [ ] Enforce explicit AI consent before personal data reaches an external
  model through chat, voice, or documents. Decline must preserve local capture
  and drafts. Disclosure fixtures do not prove dispatch enforcement.
- [ ] Complete [#781](https://github.com/lagarcess/argus/pull/781): legal entity,
  contact details, permitted source use, actual retention/backups, deletion,
  provider sharing, and approved reachable Privacy/Terms pages. Do not substitute
  vendor maximums or promises for the actual configured behavior.
- [ ] Reconcile App Store privacy answers, app/SDK privacy manifests and required
  API reasons with actual collection. Check permission purpose strings and
  denied-access recovery. Finish VoiceOver, large text, contrast, reduced motion,
  localization, and supported-device acceptance.
- [ ] Prepare reviewer access through the invite gate, available review services,
  accurate screenshots/metadata, support details, age rating, export-compliance
  answers, and evidence of rights to shipped assets. Check applicable purchasing
  and user-content rules against the features actually included.
- [ ] Obtain the existing migration, backup, hosted-flag, share-pages, and
  promotion approvals. Neither candidate verification nor this roadmap opens
  those gates.

Apple audit references checked October 4, 2026:
[review guidelines](https://developer.apple.com/app-store/review/guidelines/),
[account deletion](https://developer.apple.com/support/offering-account-deletion-in-your-app),
[privacy details](https://developer.apple.com/app-store/app-privacy-details/),
[required API reasons](https://developer.apple.com/documentation/bundleresources/describing-use-of-required-reason-api),
and [permission design](https://developer.apple.com/design/human-interface-guidelines/privacy/).
These define an audit to finish, not a completed compliance assessment.

**Checkpoint boundary:** The October 4 foundation documents and the reviewed
mobile code are reconciled in this tree. The [code landing record](../reports/2026-10-04-cuadrao-code-integration-landing.md)
identifies the per-PR heads, accepted tests and final landing evidence. Combined
candidate `25ce9a4d` has the same iOS source tree as accepted candidate `03a33ef2`.
Neither local candidate is a replacement integration branch. The
[earlier candidate evidence](https://github.com/lagarcess/argus/blob/2bde54e48/docs/reports/evidence/cuadrao-iphone-candidate/LEDGER.md)
and [recovery report](../reports/evidence/cuadrao-mobile-recovery-2026-10-04/README.md)
retain their named tested heads and limits. Revalidate only evidence affected by
subsequent changes. This section replaces conflicting current-queue or phone-status
wording below; it does not erase dated evidence or change the lane contracts.

**Original preservation authorization (historical):** The founder accepted this expanded plan for
commit and push on September 29, 2026. That grant authorized documentation preservation
only, not implementation, worker dispatch, merge, deployment or hosted changes.
Recovery branch: `codex/mvee-iphone-delivery-plan`.

## Six-lane delivery handoff

Lane contract, 2 October 2026. Integration tip `d9a7acfc` includes landed
PR #773 `f28b5642` and PR #776. The
[six-lane handoff](lanes/mvee-five-lane-handoff.md) writes the founder's
2 October locks into contract and acceptance for Household invitations, account
deletion, the space list and account moves, Search, Home series, and Updates. The decisions
themselves live in the
[decision log](argus-decision-log.md#october-2-2026-cuadrao-lane-locks).
Landing order is Household, account deletion, the space list, Search, Home
series, account moves, then Updates, one at a time. Account deletion is its own
lane and lands before external TestFlight. Outside services land as fakes behind default-off
flags. iOS pieces land in their own PRs as unverified, with a Mac pass by
Lucas's local agent. The handoff does not dispatch a worker, authorize a merge,
or rewrite the historical landing records below. Sentences in the #773 section
that still say that lane is unmerged predate the squash on this tip.

## Cuadrao release UI landing order

**Founder pivot, October 2, 2026. Retained UI requirements; current completion and order are in the [October 4 roadmap](#current-mobile-roadmap-october-4-founder-lock).**
Ported from design commit
[`fc7650ea`](https://github.com/lagarcess/argus/commit/fc7650eab4eac9298a09eea37eddc3964a709fba)
on `codex/cuadrao-design-scan-recents` and reconciled with the
[October 2 lane locks](argus-decision-log.md#october-2-2026-cuadrao-lane-locks) and
the [six-lane handoff](lanes/mvee-five-lane-handoff.md). Where they differ, the locks
and the handoff win. This table retains the detailed design scope. It refines the
[design dispositions](#cuadrao-design-dispositions) C01 to C10, carried by #790
from the design branch. Earlier preview screenshots and build
3419 acceptance remain valid historical evidence; they do not prove the release
behaviors below.
[Cuadrao's guide](../../.agent/designs/cuadrao/DESIGN.md#13-release-readiness-interaction-rules)
owns interaction rules and inspected Mobbin references. The
[MVEE amendment](argus-minimum-viable-ecosystem-experience.md#native-release-access-and-account-lifecycle-october-2)
owns the native product changes. No backend implementation, deployment or hosted
change is assigned by this documentation checkpoint.

**Starting point.** The design commit verified integration `2185aefe` against design
`2558f866`, with merge base `7c29b2a9`. Since then, #783 adopted the shared design
foundation from checkpoint `2558f866` (1 of 4), #782 landed the six-lane handoff,
#785 adopted plans, groups, receipts and contextual Cuadrao (2 of 4), and #786
adopted Home, Search, Updates, Profile and Settings (3 of 4). Integration is now
`0ea81a20`, which also includes the Lane 1 backend from #788. Integration keeps the four
`ios/ArgusFoundation/Connected/` files and ten `Household/` files that the design
checkpoint lacks. Start each implementation checkpoint from current integration,
recheck its head, and adapt approved design components to those owners. Do not
replace them with `CuadraoHouseholdSheet`, fictional invite acceptance,
`CanvasProfileDraft` or preview sign-out. Do not wholesale merge the divergent
preview branch to obtain the style.

Existing `ConnectedCuadraoAuthFlow` handles email auth. Native Apple and Google
sign-in exist on iOS behind the default-off `ARGUS_APPLE_SIGN_IN_ENABLED` and
`ARGUS_GOOGLE_SIGN_IN_ENABLED` switches (#795; later Mac verification is recorded in the current mobile roadmap above), and the
backend's Apple token capture and revocation sits behind
`ARGUS_APPLE_REVOCATION_CAPTURE_ENABLED` (#793, #802). None is enabled: the keys
are still owed by the founder and the [#800](https://github.com/lagarcess/argus/issues/800)
gates stand. Sign-in for TestFlight is **Apple, Google and
email** ([October 2 founder
decision](argus-decision-log.md#sign-in-for-testflight)). Apple and Google are
built behind default-off flags until the founder supplies the keys, and connected
buttons stay hidden while a flag is off. Email has an in-app confirmation step,
which does not exist yet: today's sign-up ends on an emailed confirmation link. `HouseholdManagement`
owns member/invitation management and explicit account consent;
`HouseholdPlanPeople` owns shared-plan permissions. In-app deletion,
[Lane 6](lanes/mvee-five-lane-handoff.md#lane-6-account-deletion), is built
behind the default-off `ARGUS_ACCOUNT_DELETION_ENABLED` (#799, #801); while it is
off, login deletion stays a support request. Account archive is not an account
move. The team
connecting each checkpoint owns the remaining contract gaps; simulated UI acceptance
must stay distinguished from connected acceptance.

| Landing checkpoint | User items | UI deliverable | Closure evidence and existing responsibility |
| --- | --- | --- | --- |
| 1. Trust and profile | 1 | Delete-account consequences, verification, pending/retry and confirmed signed-out finish, Spanish and English, with Iris's founder-locked copy | Ordinary member, admin and financial-owner variants; "Exmiembro" / "Former member" in other people's plans and plan handover per decision 17; a shared debt plan archived read-only with Iris's banner instead (decision 19, Head of Engineering); no false success or deletion of another owner's data. C07/C10, identity and Household owners, Lane 6. Backend and web landed default-off: census #791, command #799, route and web flow #801, behind `ARGUS_ACCOUNT_DELETION_ENABLED`, which #805 and #806 block. No native flow is on integration. The [API contract](../API_CONTRACT.md#post-accountdelete) and the [launch runbook](../PRIVATE_LAUNCH_RUNBOOK.md#account-deletion-runs-lane-6) own the deletion model. The resume sweep is operator-run with no cron, by founder decision (October 3), and none is to be created |
| 1. Trust and profile | 2 | Signed-in Privacy and Terms destinations | Actual approved links, return to Settings, both languages. C07, native identity/support |
| 1. Trust and profile | 3 | Apple and Google auth alongside email | Founder decision, October 2: Apple, Google and email, Apple and Google behind default-off flags until the keys arrive; email with an in-app confirmation step. Loading, cancellation, error, missing-name recovery and return to invitation; connected credentials/session owned by auth; Apple token revocation, and revoking every Google token Argus holds, at deletion is Lane 6. C07/C10 |
| 1. Trust and profile | 13–14 | Remove email-notification toggle; hide unsupported rows (including Memory, Usage, More options and conversation bulk actions) and the avatar-editing entry, which release builds hide and development builds keep in full ([decision of October 3, 2026](argus-decision-log.md#october-3-2026-avatar-editing-in-release)) | `fc7650ea`, from Yelena's UI checklist, hides Personalization, Security and sessions, Shared conversations, Removed activity and photos; `26055a28` hides the avatar-editing entry; #786 (`a20362d3`) hides Usage, More options and conversation bulk actions as a Head of Engineering judgment call; Memory (`.memory`) waits for native memory. They are designed rows whose backend is owed, hidden only in release builds: `CuadraoFirstRelease` shows every row, including the avatar editor, in development builds (#790). The [hidden-rows backend list](lanes/cuadrao-profile-hidden-rows-backend.md) names what each needs, ordered after chat. Audit all entry paths for hidden destinations and preserve supported preferences/sign-out. C07/C08 |
| 2. Access and Household | 4 | Invitation gate after install and cuadrao.ai waitlist | Valid, invalid, expired, already-used, cancelled auth and admitted-user return. Preserve link intent/manual code recovery. C02/C08 plus auth, Lane 1. The connected iPhone invitation client for items 4 to 8 is built default-off behind `ARGUS_BETA_INVITES_ENABLED` and `ARGUS_INVITE_UNIVERSAL_LINK_ENABLED` (#810), verified with host model and simulator checks ([evidence](../reports/evidence/cuadrao-household-invites/README.md)) and enabled nowhere; universal links wait on AASA and Associated Domains. |
| 2. Access and Household | 5–6 | Personal invitation link/code/QR, remaining quota out of ten and accepted notice | Sharing is not acceptance; counter and notice derive from canonical status; QR scans; the QR card names its purpose. C02/C08, Lane 1 |
| 2. Access and Household | 7 | Administrator-only household invitation without personal quota charge, which also admits a new person to the beta | Existing integration invitation preview/accept and account-sharing boundaries preserved. C02/C05, Household, Lane 1 |
| 2. Access and Household | 8 | Founder-only group access link: creation, cap, expiry, usage and full/waitlist states | Beta only, never household membership. Capacity race/expiry recovery; confirmed enrollment before joined-waitlist wording. Redemptions do not use a personal quota, per Lane 1. C02/C08, Lane 1 |
| 2. Access and Household | 9 | Admin handoff, owner-history removal and household-closed notices | Authorized target or clear terminal explanation, including stale notice after deletion. With no remaining member the household closes (decision 15). The lane that causes the event writes the entry: Household for closure when the last member leaves, Lane 6 for admin handoff and closure caused by deletion. Updates owns display and push opt-in. C05/C07, Household, Lane 6 and Updates |
| 3. Home and Updates | 10 | Monetary difference from a zero baseline, and Sin datos only for missing coverage | A month with confirmed complete coverage and no spending shows the known zero (founder clarification, 10:18 PM CT). Known zero, missing history and covered comparison specimens in both languages. C05, financial history, Lane 4 |
| 3. Home and Updates | 11 | Bill reminders three days before/on due date; contextual push opt-in | Paid/cancelled occurrence suppressed; denied permission preserves inbox; no amounts in push. C07, planning/Updates/native delivery, Lane 5 |
| 3. Home and Updates | 12 | Read-only pre-move household history | Existing owner and cutoff supplied by move contract; lock/read-only text and readable muted style; no hidden edit gestures. C05, financial core/Household, Lane 2 |
| With first external model processing | 15 | AI disclosure and explicit consent across chat/voice/document entry, before sharing personal data with an external model | No personal data sent before consent; decline preserves draft and local capture. May be a first-TestFlight dependency if live AI is enabled. C01/C04/C07, intake/conversation |
| With source activation | 16 | Connected sources and Disconnect | Actual connections, errors/retry and distinction between future access and retained imports. Existing intake/source owner |
| With native memory | 17 | Memory off and reset | Distinct pause vs deletion consequences, permission and recovery. C06/C07, existing memory owner |

Each checkpoint includes shared typography/components, light/dark, Spanish/English,
large text, accessible controls and actual navigation/return checks. Carry over
working state owners and tests. The phone is disconnected; continue simulator
acceptance and record physical checks when available. A UI handoff includes its
state variants, integration base, screenshots and the exact service facts still
needed. External TestFlight readiness requires connected acceptance, not UI-only
success screens. Provide reviewer access to the invitation-gated build.

The design commit's C06, C07 and C08 rows arrived with #790 under
[design dispositions](#cuadrao-design-dispositions). Its historical Profile
checkpoint paragraph stays on the design branch.

## Shared document draft foundation, PR #776

**Founder clarification, October 2, 2026; backend checkpoint under review.**
Worker `codex/document-extraction`, original integration base
`5d403d7bf97d8154b89d88613bdb706c3a35fbb1`. Preserve existing design checkouts and
demos. The [MVEE ingestion flow](argus-minimum-viable-ecosystem-experience.md#4-information-ingestion-one-destination-several-entry-methods)
owns CAPTURE → SAVE → PREPARE → REVIEW → APPROVE. The
[API contract](../API_CONTRACT.md#document-capture-preparation-and-review) and
[data model](../DATA_MODEL.md#import-reconciliation) own the shared backend.

This assignment replaces transient document storage with durable private source
and draft retention on the existing checkpoint. Preparation runs after capture,
keeps recoverable failure state and preserves incompatible observations alongside
valid transactions. Receipt itemization and destination/equal-split/shared-item
proposals remain draft data. Confirmation stays with reconciliation and MoneyService.
No upload or preparation creates an expense, balance change, amount owed or share.

Offline acceptance covers the captured Luna failure without another paid call:
all five observations retained, two exact transactions projected, unknown balance
scope preserved with a review issue. The existing $6 cumulative ceiling and
$2.9205875136 consumed reservations remain unchanged. `ARGUS_VISION_MODEL` stays
`openai/gpt-6-luna`; no paid retries are authorized by this assignment.

Remaining integration: native and Chat entry/reopen actions, authorized Plan
resolution and fixed-currency mismatch review, group split approval and separate
sharing. The expanded preparation schema has not had a new live measurement.
Durable PostgreSQL acceptance must pass the disposable-database CI gate; local
memory checks do not establish persistence across process restart. See the
[PR evidence](../reports/evidence/document-extraction/README.md) for current tests,
review, exact head and CI status. No merge, deployment, hosted changes, privacy
relaxation or feature enablement is authorized.

## Connected shared Household planning lane

**Landed 2026-10-02 via [PR #773](https://github.com/lagarcess/argus/pull/773)** (Exact head
`dee829f8a3a7f83fb25cd81aaf3fa6deac8bfe45`; product squash
`f28b56421caf71d6610caf1cce891e1848e0ace1` onto tip `15e579315…`). See
[PR #773 integration landing](#pr-773-integration-landing).

**Assigned 2026-10-01; connected local acceptance complete; independent review clean; merge complete.** Full original integration base:
`15e57931584b21dd7f9e453dbeb9127fc4b8cff3`, freshly fetched and verified to
include #763/#764, #760/#765 and #766/#767. Worker:
`codex/shared-household-planning`, isolated managed worktree. Preserve the landed
Household demo, personal financial demos, design simulator/cache and phone stack.

**Explicit fixed design assignment:** founder chose
`7f72dfd73d0c137a1118dffebe5219985577548a` in this lane's checkpoint question.
`b32b0705359f02aab9c3091ab59d7067ab7ddf46` remains an older reference.
Neither the moving design branch nor preview stores/fixtures establish connected
functionality. Selective presentation only; no wholesale design merge.

### Approved restart and policy, October 1

Resume from published `6296b8840b6e4f07f0b3475ed50cc8c601db9ced`. Fresh
integration remains `15e57931584b21dd7f9e453dbeb9127fc4b8cff3`; no merge or
semantic overlap is present at restart. The fixed design remains `7f72dfd7`.
No other open integration backend lane was found.

- View-only participants may record/link and correct their own contributions.
  They cannot edit the plan, other participants' contributions or private
  funding accounts. Original account/activity authorization remains separate.
- Owner departure archives their shared plans as read-only for remaining
  authorized members, retains previously shared history/linked transactions,
  and removes future projections. Explain this before departure. No financial
  activity deletion, private funding disclosure or ownership transfer.
- Required allocation/schema/RLS source, migration and complete backfill are
  approved in this worker. Test only in a new isolated disposable local
  database. Remove JSON only after completeness is proved and all readers and
  writers use the canonical owner. Existing demo/hosted databases are forbidden
  targets; incomplete cutover must fail visibly rather than use a fallback.

The prior product questions and automatic-review authorization blocker are
resolved by this explicit grant. Full budgets, bills, goals and debt delivery
remains required through native acceptance and merge-ready review. The new local
resource assignment is `ios-accounts-59750`: API 59750 reserved, local Auth
59751 / disposable Postgres 59752, CAPTCHA 59755 reserved, helper ports
59753–59754 and 59757–59761. Configuration/state stays in this worker's ignored
`ios/.build/accounts-local-59750`. Configure verifies every assigned port is
unused and project ownership matches before starting. Old 59700 stays stopped
and is never migrated. Response-loss proxy 59762 and optional mirror 59763 were
verified unused before assignment. The explicitly assigned simulator is
`C93072E7-D29A-4B0A-BE76-E6418E4E9F88`, this thread's retained Household device;
no active native build was found. Use only the new bundle
`local.argus.shared-household-planning-demo` and cache
`/private/tmp/argus-shared-household-planning-native-build`. Preserve its existing
`local.argus.household-current-demo` installation and
`/private/tmp/argus-household-current-build`. Design device `8AFB6084…`, compact
financial demos and the phone environment remain untouched.

Canonical residual storage is implemented at
`f32e301198c39a1bcafd24e698466b9fc6441439`. Migration
`20261001190000_goal_residual_allocations.sql` was applied only to NEW Postgres
59752. It validates every legacy allocation, backfills ordered owner-qualified
rows, proves bidirectional multiset completeness, then removes the JSON field
and rejects old writers in one explicit transaction. The Personal adapter reads
and writes only this relation; no JSON fallback remains. Captain verification
at that source passed **170 tests, zero skips/failures**, including zero/Int64
bounds, malformed/foreign/duplicate rejection, rollback, RLS and existing
Personal Goal/Budget/Debt/Plan regressions. Durable
[cutover proof](../reports/evidence/shared-household-planning/allocation-cutover-check.json)
links the command, JUnit and log. Extending shared claims/pools and all four
connected native journeys remains required. This is storage progress, not
shared-planning delivery. Code-only rollback is unsafe after cutover; restore
validated ordered JSON from canonical rows in a coordinated transaction before
using the legacy adapter. No existing or hosted environment was migrated.

### Connected implementation checkpoint, October 1

Five subsequent additive migrations were reviewed and applied **only** to NEW
Postgres 59752: `20261002000000` shared-plan consent/revision/claim storage,
`20261002010000` true original Money leg owners, and `20261002020000` retained
consent revision bounds, `20261002030000` consent/claim lifecycle uniqueness,
and `20261002040000` responsibility carry-forward for every canonical writer.
All five ran in explicit transactions. Seven synthetic
accounts and the one prepared Household remain intact. Raw shared claims,
allocations and retained activity references stay service-only under RLS; history
foreign keys retain restrictive deletion. No existing demo or hosted database was
migrated. These schema checks do not establish the complete shared journey.

The four-kind native forms compile against the fixed checkpoint presentation.
The Session package executes 79 checks with four existing opt-in skips and zero
failures (75 passed); production presentation models pass 24 checks. Scheduled
forms use the canonical server cutoff and preserve recorded occurrences when
changing intentions. Real connected acceptance is still in progress.
Initial real-Postgres shared-budget proof keeps 70/30 planned amounts
separate from 20/10 actual contributions, allows a view-only member's own link,
redacts the other's private source and rejects the third identity. Full bills,
goals, debt, corrections/recovery, cross-owner privacy and departure acceptance
remain required before publication/readiness. The captain-owned UI launcher
`--shared-plan-scene` selects only the assigned C930 simulator, new app/cache,
59750 allocation and retained synthetic fixture; it refuses other devices/ports.
Its bounded resource/recovery helper checks pass. Existing demos stay available.

Backend checkpoint `82383423e23947adb156059b89d664695d7a97f9` implements
all four kinds. The focused real-Postgres matrix passed 458 cases with zero
skips; the final canonical adapter/currentness/Search delta passed 68. Native
checkpoint `05d6c2e0dc820dbc9495fba1d076ea178f3c35fc` passed 77 Session checks
(four existing opt-in skips), 24 Household presentation checks and five affected
Personal recovery/original checks. The repaired broader Personal harness has
six assertion failures in four cases, matching the exact integration baseline;
it is not counted as a green full suite. Its baseline comparison will accompany
the evidence. Assembled native acceptance and independent review were pending at
that component checkpoint; the completed local results are recorded below.

Fresh integration on October 1 remains `15e57931584b21dd7f9e453dbeb9127fc4b8cff3`.
Open ingestion lanes #768–#772 consume Recording and keep their own branches;
they do not modify its canonical services. Versions `20261002120000` through
`20261002120300` are reserved for ingestion. The earlier `20261001190000`
collision is resolved: #772 head `5608a83ef7a28c3359195e947acc12c428cbe4f0`
uses all four reserved versions. Its owner renumbered ingestion on its own
branch; this lane did not edit ingestion or its infrastructure. The consumer handoff lives in
the existing [API contract](../API_CONTRACT.md#recording-consumer-handoff-for-ingestion-october-1).

### Published review and assembled acceptance, October 1

[PR #773](https://github.com/lagarcess/argus/pull/773) targets
`codex/private-alpha-next`. Reviewed and natively tested implementation head:
`41cd27ac93a0e00f39f8190aea0838aa1b59104f`; its financial source remains
`942f1f009a5927816176d166f6c1357577e0ce51`. Final follow-up adds only documentation, durable evidence and the bounded
Goal concurrency-test repair at `d290207646956a60ad1b1eb62b4a49a20e91901a`. Source fingerprints explicitly revalidate
the retained screenshots/recording at that publication; the terminal PR comment
records its exact head and CI state. Original/current integration remains
`15e57931584b21dd7f9e453dbeb9127fc4b8cff3`; no reconciliation merge or
intervening semantic overlap is present. Modularity is checked against the
would-be merged tree.

The fresh independent reviewer `shared_plan_independent_review` completed one
whole-diff pass at `5bd9417a671b6dbdabe2c558794c55d289410352`, then only affected
fixes. Five confirmed findings were fixed: budget-only People fields,
self-advancing exact retries, supported savings credit, unchanged recurrence
anchors and consented originals in Personal projections. The final affected
review is clean at `41cd27ac…`, including distinct native contribution actions,
the bounded menu wait and **Can edit plan / View only** copy. This is the
founder-permitted independent substitution, not a claim of a new Codex review.

A subsequent confirmed GitHub privacy finding is fixed at the shared lifecycle
owner: leaving/removal pins a non-owner contributor's exact original,
refund/reversal and allocation revisions in the same transaction as access
removal. Later private activity or balance changes cannot alter already-shared
history. Remaining contributors stay live. Ended savings backing is unknown
with **Needs review**; fresh rejoining/consent preserves older authorized
revisions. The finding has a written rationale, accepted reaction and resolved
thread. Final unresolved-thread verification belongs to the terminal PR audit.

The affected financial/Household matrix passed **481 tests, zero skips** against
NEW local Postgres on port 59752. The focused departure matrix passed **185**, including
13 new departure cases. Session checks passed **79** with four existing opt-in
skips; Household/Plan presentation checks passed **33**; OpenAPI compatibility
checks passed **23**. The broader Personal harness retains the same six
assertions in four cases as its integration baseline; it is not described as a
green full Personal suite. Logs, JUnit, migration completeness and source
provenance live in the existing
[evidence packet](../reports/evidence/shared-household-planning/).

Four assembled native cases passed at `41cd27ac…`, each with zero skips:

| Observable journey | Saved result and independent proof |
| --- | --- |
| Create all four shared kinds, contribute, correct, archive/restore, Home, Search/back and Spanish relaunch | Budget actual25 + 15 = 40 remains separate from 70/30 planned responsibilities. Bill agreed60/paid20, backed goal 20 with its separate planned definition, and debt paid20 persist. One savings transfer/card payment changes canonical balances without extra spending. |
| View-only own activity and named plan editor | B inspects/corrects only B's original; A's private source and notes stay hidden. B may edit the explicitly granted bill, preserving its recorded payment. |
| Committed response lost, app closed, explicit Retry | Temporary proxy59762 drops one response after upstream commit. Relaunch retains the exact journal command; retry leaves one 700-minor contribution and one 700-minor debit. Proxy stops and the direct API build is restored. |
| Three registered identities and disabled feature | A/B see their own Personal accounts and authorized shared plans; C has neither shared access nor others' private accounts. English/Spanish relaunch preserves scope. With Household disabled only on this lane API, Personal Home/Accounts/Search remain usable and shared controls stay hidden. |

The independent authorized API readback proves the native totals and account
deltas, unknown balance and separate currency preservation, shared/private
history boundaries, and third-user 404s. Departure/removal/rejoining, stale CAS,
parallel retries, allocation conflicts, reversals and recurrence are additionally
covered by real Postgres acceptance and native presentation/journal checks;
the short video is not represented as proof of every case.

Earlier failed verification attempts remain in ignored results. One exposed a
real parent accessibility identifier overriding three contribution actions;
the shared presentation fix preserves each action's identifier. Driver fixes
use actual hittability and a bounded initial menu wait. An extra identity run
after repeated readbacks could not sign in; its normal-cooldown repeat passed
without resetting the authentication limiter. Partial test plans were archived
through their canonical API. Their activity/history remain; no balances,
accounts or datasets were reset.

Source-head CI is green. At documentation head `d140f3a1…`, PR CI passed but
its parallel push guest matrix exposed a valid stale-account rejection omitted
by the existing Goal allocation/recording concurrency test. The repair retains
runtime CAS and adds strict allocation-first/expense-first expectations,
coherent assigned/support pairs, cash80000 and exactly one expense20000.
Seven affected real-Postgres cases passed with zero skips. A P2 ordered-case
assertion gap from the affected reviewer was corrected; final delta review is
clean at `d2902076…`. No production/native code, schema or demo data changed;
all captured runtime fingerprints remain identical. The next publication runs
its normal exact-head CI; no unchanged-head retry is used to hide the race.

Supabase's existing automation **ignored #773 at the
concurrent preview limit** and created no preview. No settings or existing
previews changed. The local demo does not depend on hosted previews. Final
publication CI and review-thread checks are recorded on the PR before READY.

The retained native plans are named **Native household <kind> C6E10C**. Open the
new shared-planning app on assigned C930, choose the prepared Household, then
Plan or Home. The 85-second
[recording](../reports/evidence/shared-household-planning/shared-plan-demo.mp4)
shows own correction, authorized bill edit, Search return and Spanish reopen.
[Restart and click-through instructions](../../ios/HOUSEHOLD_SETUP.md#shared-planning-worker-separate-retained-demonstration)
use only 59750–59755, the new bundle/cache and retained synthetic users/data.

**Remaining limits:** no physical-iPhone/internet verification, deployment,
hosted migration/enablement or external invitation delivery. The product squash
is landed on integration; additive migrations are not production-applied. One
non-blocking invalid-frame runtime warning is retained in the native result; the
established root/design is unchanged. Other MVEE journeys, including imports,
Updates and conversation/voice, keep their existing owners and scope in this
manifest. Completed writers/reviewer are stopped. The demo API, Auth/Postgres
and CAPTCHA bridge remain available; temporary fault/recording helpers are
stopped. Existing demos, design simulator/cache and phone services are
preserved.

### Outcome, owners and execution

The captain owns this one lane through a merge-ready PR: two signed-in members
create, share, inspect, edit and manage budgets, bills, savings goals and debt
commitments, with unequal responsibilities, actual versus planned progress,
private funding, attributable corrections and durable recovery. An unauthorized
third identity cannot discover or access these records. Personal plans remain
private unless explicitly shared. [MVEE Household][mvee-household] and
[MVEE Plan][mvee-plan] retain product authority.

The backend writer `shared_plan_implementation` owns financial rules, canonical
services, schemas, routers, migrations and domain tests. The native writer
`shared_plan_native_scout` owns transport/models/screens/localization against
the fixed typed wire; it cannot change financial rules. Each shared surface has one writer.
The captain owns local fixture/runner helpers, UI acceptance tests, runtime
resources, documentation, integration, durable evidence and release claims.
Read-only scouts/reviewer own no source or runtime resources. No second
allocation owner or financial ledger.

| Surface owned by this lane | Existing owner to retain | Bounded change |
| --- | --- | --- |
| `src/argus/domain/household/` | Membership, grant incarnations and live authorization | Explicit plan consent and safe authorized projections/adapters |
| `src/argus/domain/recording/canonical_groups.py`, bounded Money persistence/read changes | Recording owns exact logical groups, revisions and actual legs | Complete current-group resolution before authorized projection; only then a safe canonical cross-owner extension |
| `src/argus/domain/planning/` | Budgets, recurrence, goal pools, debt intentions and canonical activity claims | Shared responsibilities and authorized participant activity linking without duplicate facts |
| `src/argus/domain/financial_search.py` | Financial search and origin continuity | Authorized shared plan retrieval; no private funding disclosure |
| `src/argus/api/routers/household*`, bounded new shared-plan router, router registration | Thin authenticated transport | Additive documented shared Plan routes using canonical services |
| Bounded additive `supabase/migrations/` and `tests/household/`, `tests/planning/` | Owner-qualified integrity, RLS, transaction locks and receipts | Plan consent/claims; concurrency, privacy and Personal regression evidence |
| `ios/Packages/ArgusSession/` Household/Plan types and transport | Auth, actor partitioning and durable exact-byte journal | Typed scoped commands/reads; preserve session and recovery ownership |
| `ios/ArgusFoundation/Household/` and bounded new shared-plan module | Connected Household model and existing domain details | Shared lifecycle, participant rights and private contribution controls |
| Shared native root, Connected shell, Home/Plan/Search mounting and localization | Landed #760/#766 composition | Native writer alone serializes minimal root/session changes; no redesign |
| `ios/ArgusFoundationUITests/` and `ios/FinancialModelTests/` | Native assembled proof and production model checks | Captain owns UI acceptance; native writer owns model checks; no duplicate edits |
| Existing API/data contracts, this board and lane evidence packet | Respective canonical document owners | Contract first; durable exact-head evidence and restart recipe |

Open PR inventory at start found #762 (design-only), #732 (frozen web preview)
and #646 (unrelated chat); no open integration backend delivery PR. The design
owner reports a clean checkpoint and a proposed, not started, typography/input
pass. Its private checkout, physical-device signing and simulator remain untouched.
Root/session/model/API/migration overlap is reserved above; recheck before READY.

### Required journeys and proof

| User outcome | Inherit | Remaining work | Actual dependency | Assembled acceptance |
| --- | --- | --- | --- | --- |
| Share/create/manage each of budget, bill, goal and debt commitment | Personal domain services and original identities | Explicit consent/participants, view/edit and archive/restore | Accepted plan permission interaction; canonical domain contract | A and B manage authorized definitions; C and unshared Personal IDs denied |
| Agree unequal planned contributions | Canonical schedules, exact currency money | Named responsibilities, planned amounts separate from actual | Shared definition/participant contract | 70/30 intention remains distinct from 20/10 actually recorded, without forced equal split |
| Record/link using private funding | Recording preview/confirm, original revisions, Plan claims | Explicit minimal contribution disclosure and atomic linking | Canonical account-owner boundary and one activity claim owner | Shared amount/date/person/status only; private source IDs/names/balances/notes/history absent through details, Home, Search, totals and receipts |
| Correct and recover without duplicate money | CAS, owner locks, exact-byte journals, original activity screens | Scoped attribution, concurrent edit and live replay authorization | Current original permissions and membership incarnation | Correction recomputes progress; double-tap/lost response retries commit once; stale competing edit explicitly rejected |
| Leave/remove/revoke safely | Landed membership and account grants | Shared-plan access/claim visibility invalidation | Existing approved departure policy; explicit plan consent | Access stops immediately and after relaunch, owner records and legitimate activity remain; rejoin does not revive old grants |
| Refresh authorized Home/Plan/Search | Existing projections and navigation origin | One shared projection owner and context-preserving readers | All four canonical domain adapters | Both users refresh/reopen to consistent authorized progress; unknown/currency rules and Personal regressions hold |
| Safe unavailable state | Server Household default-off and native availability owner | Shared-plan disabled-surface coverage | Existing server exposure gate | No protected read/write/UI or stale protected replay while disabled; no false departure or data loss |

### Decisions and verification disposition

The following is preserved **pre-restart investigation history**. The active
implementation, assigned resources, publication and verification state are in
the checkpoints above; historical pending states below are not current blockers.

Pre-change deterministic baseline: **81 passed, 74 skipped, zero failures**
(15.47s), recorded in [baseline.json](../reports/evidence/shared-household-planning/baseline.json).
Skipped cases require the not-yet-assigned disposable Postgres DSN; they establish
no database acceptance. Existing Household Plan is still explicitly unavailable.
No new demo or shared-planning behavior is claimed at this checkpoint.
Existing native transport/session baseline also compiles: **64 passed, one
opt-in local-service test skipped, zero failures**, at `150a9b10`. Live session
tests were excluded and no Auth fixture was supplied. The command and durable
log are in the same baseline packet. This is not shared-planning native proof.

Two code-grounded shapes were inspected: consent/responsibility references around
canonical definitions, versus explicit Household scope embedded in definitions.
Prefer the additive reference shape if it closes canonical global claims and
private allocation without a second store of money. The backend implementation
writer is `shared_plan_implementation`; the typed wire is its first integration
checkpoint. The founder restart above settles permissions and departure; dependent work
now follows those rules.

The proposed technical shape is preserved in the existing
[API contract](../API_CONTRACT.md#shared-household-planning-contract-sketch) and
[data model](../DATA_MODEL.md#shared-household-planning-storage-sketch). It is
not implemented or enabled. The architecture check identified a required
complete-transaction/current-revision resolver, actual leg owners, safe read
projections, global claim uniqueness, one normalized savings allocation owner,
and ordered cross-owner locks. Raw owner-readable claims and cascade deletion
must not expose or erase another person's private financial records. These
requirements remain implementation and database verification work, not proof
of delivery. Initial contract preparation created no runtime resources. The
isolated local database assigned for the subsequent read checks is recorded
below; no simulator or connected API is running. Bounded read-only scouts and
contract preparation are complete. Independent complete-group reads are
implemented at `2499e3c5a602c4b50b03bc9be8d7fb631feeae3f` in
`canonical_groups.py` and Household `financial.py`/`projection.py`. The writer
reported **45 passed / 65 skipped** focused regressions and clean scoped Ruff.
The captain verified the affected subset at that exact commit: **10 passed /
30 skipped**, zero failures. Missing exact references and incomplete paired
groups fail closed; current revision controls visibility before existing
redaction. Account positions load separately.
[Commands and evidence](../reports/evidence/shared-household-planning/canonical-read-check.json)
explicitly mark SQL-backed load/snapshot/history unverified without the local
DSN. This step retains current write permissions and cross-owner rejection.
No shared plan, contribution or native delivery is claimed.

Independent follow-up verification at `d3147db88e8b7efe01af0f23256b929b575b48a1`
ran the same focused regression set against the new lane-owned local Postgres
59702: **110 passed, zero skipped, zero failures**. This includes the SQL-backed
resolver, Household visibility/history, correction, receipt and Personal debt
regressions. The assigned local allocation is `ios-accounts-59700`, isolated
Auth 59701 / Postgres 59702; API 59700 and CAPTCHA 59705 are reserved for later
assembled work. Its configuration and state live only in this worker's ignored
`ios/.build/accounts-local-59700`. Other allocations remain untouched.
[CI at this head](https://github.com/lagarcess/argus/actions/runs/36901975308) is
SUCCESS, including backend, frontend and required guest database/Auth gates.
Durable [Postgres proof](../reports/evidence/shared-household-planning/canonical-read-postgres-check.json)
records the exact source and 110 executed tests. These checks do not prove shared
planning or native acceptance. A fresh fetch still reports integration
`15e57931584b21dd7f9e453dbeb9127fc4b8cff3`; no reconciliation is needed at this
component checkpoint. The open PR inventory has no other backend delivery lane.

The sole writer's next independent prerequisite owns
`src/argus/domain/planning/goal_allocations.py`, bounded `planning/storage.py`,
one additive local-only allocation migration and focused PG tests. It replaces
owner-readable goal-body residuals with one canonical owner-qualified allocation
relation, retaining Personal API shape and the existing pool reducer. No shared
rows, foreign-authority writers, plan permissions, custody or native UI are
activated by this prerequisite alone. The approved restart now authorizes the
required source/cutover and settles dependent rights/custody. Historically,
automatic approval review rejected the
combined storage/migration patch and then the strictly source-only proposal.
Its stated reason was missing direct founder authorization for the allocation
backfill, JSON-field removal and storage/RLS change. No source patch or database
migration was applied before restart. The founder subsequently approved the
exact change and requires a new disposable local test database; 59702 is not a
migration target. Production migrations
and hosted changes remain prohibited. The test-first
[draft](../reports/evidence/shared-household-planning/goal-allocation-tests-pending.py.txt)
is preserved outside test discovery: its initial case failed on the intended
existing JSON authority, and the expanded cases have not been executed against
the nonexistent new schema. That red test is not passing acceptance evidence. A schema/code cutover would need coordination; reverting the
adapter alone after a future durable cutover is unsafe.

The checkpoint's temporary groups, splitting and guest proposals do not define
Household permissions. Guest finance remains registered-only. A narrow proposed
People & permissions / private-contribution review interaction is approved by
the restart above; implementation and acceptance are still required.
Existing account edit grants never grant plan editing. Shared plan editing never
authorizes private activity correction, ownership change or resharing.

Grounding identified real owner-qualified Money/Plan boundaries and protected
personal receipt payloads. Reuse must preserve those constraints and live
Household checks before replay; do not pretend a foreign-owner transfer is
already supported. Contract and smallest safe canonical extension are settled
within this implementation before dependent writes, never as a parallel ledger.

Execution checklist: (1) ground/record ownership and missing interaction;
(2) choose the smallest canonical contract and privacy shape; (3) implement and
verify one connected shared journey at a time across all four plan types;
(4) assembled real Auth/API/Postgres/native proof and durable recording;
(5) fresh independent review and only affected fixes; (6) fresh one-way
integration reconciliation, merged-tree modularity and exact-head CI; (7) PR and
restart handoff. Component checks do not establish assembled or phone delivery.

The active resource assignment and implementation checkpoint above supersede
these historical prerequisite states. Native assembled acceptance remains
pending; all prior demos and the physical-phone environment stay preserved. No merge, deployment, hosted changes,
production data, paid providers or physical-phone internet readiness is granted.
The entire assigned shared-planning outcome remains required through resumed implementation; it is not narrowed or newly deferred.

### Historical stopped prerequisite stack

Only the new `ios-accounts-59700` services were stopped; their local data is
retained. Existing demos, design/phone environments and source remain intact.
No native simulator was created and no connected API was started by this lane.
From this worker worktree, restart the component test database with:

```sh
python3 ios/scripts/auth/local_stack.py start --accounts --port-base 59700
```

The 110-test reproduction command and exact checked source are in the linked
Postgres proof. Use only its synthetic loopback Postgres 59702, never a hosted
DSN. The pending allocation test draft is deliberately outside discovery until
its prerequisite is authorized and implemented. Stop only this allocation with:

```sh
python3 ios/scripts/auth/local_stack.py stop --accounts --port-base 59700
```

This is a runnable database-check checkpoint, not a shared-planning app demo.
The existing #766 native Household demo remains the connected demonstration;
this lane's four shared-plan journeys, recording and assembled acceptance remain
undelivered and required. The next writer resumes the existing branch and fixed
design snapshot, not a new roadmap or a replacement environment.

## PR #773 integration landing

Founder-confirmed squash merge of the verified shared Household planning head;
integration landing completes the register under standing Project authority.
This grant does not authorize deployment, hosted configuration changes, paid
providers, phone-environment actions, design-checkpoint adoption, Preview
repair, ingestion edits (#768–#772), chat/voice stack work or another delivery
lane.

- [PR #773](https://github.com/lagarcess/argus/pull/773) squash-merged at
  **October 2, 2026, 00:47:28 UTC** as
  `f28b56421caf71d6610caf1cce891e1848e0ace1`, from verified Exact head
  `dee829f8a3a7f83fb25cd81aaf3fa6deac8bfe45` onto tip
  `15e57931584b21dd7f9e453dbeb9127fc4b8cff3`. Integration was already the
  worker merge-base; no reconciliation merge and no intervening semantic
  overlap. Squash tree matches worker tree `2f55d72b…`.
- Pre-merge Exact head: PR CI / push CI / local smoke SUCCESS; Supabase Preview
  SKIPPED at concurrent-branch limit (not a sole gate); Codex P1 contributor
  freeze fixed and resolved; **0** unresolved review threads; modularity budget
  clean.
- `ARGUS_HOUSEHOLDS_ENABLED` remains default-off in `.env.example`,
  `render.yaml`, and the release profile (October 6 readback; the original
  record also named `.github/argus-env.sh`, which no longer carries it). Additive migrations
  `20261001190000` and `20261002000000`–`20261002050000` are not applied to
  production and do not claim ingestion reserved
  `20261002120000`–`20261002120300`.
- Accepted proof retains the assembled native/API/Postgres packet under
  [shared-household-planning evidence](../reports/evidence/shared-household-planning/),
  including four-kind journey, response-loss recovery, three-user isolation and
  disabled-Household Personal surfaces. Retained demo ports `59750`–`59755`
  preserved.
- Remaining outside this land: physical iPhone/internet delivery; external
  invitation delivery; hosted enablement; Preview repair; design checkpoint
  `aba489b0…` adoption. Detail:
  [landing report](../reports/2026-10-02-pr-773-integration-landing.md).

## PR #766 integration landing

Founder-confirmed squash merge of the verified Household native head;
integration landing completes the register under standing Project authority.
This grant does not authorize deployment, hosted configuration changes, paid
providers, phone-environment actions, design-checkpoint adoption, chat/voice
stack work or another delivery lane.

- [PR #766](https://github.com/lagarcess/argus/pull/766) squash-merged at
  **October 1, 2026, 15:10:45 UTC** as
  `079ec8d819f8e2513cc624bfa7a4eb9ca60c7627`, from verified Exact head
  `04831ccb12a46b89a3cd5f5391139d3589321815` onto tip
  `09ce4e0af3b6df7a41e2d21c52c67b4fe7c82c0a`. Integration was already an
  ancestor of the worker; no additional reconcile merge was required at
  promote. Prior one-way reconcile `4fed9efb…` had absorbed #763/#760/#765
  landing docs only (no intervening runtime/API/data/UI/migration/env/test
  overlap).
- Pre-merge Exact head: PR CI / push CI / local smoke / Supabase Preview
  SUCCESS; Codex follow-up clean; **0** unresolved review threads; modularity
  budget clean.
- `ARGUS_HOUSEHOLDS_ENABLED` remains default-off in `.env.example`,
  `render.yaml`, and `.github/argus-env.sh`. Additive consent/grant migrations
  are not applied to production by this landing.
- Accepted proof retains the assembled native/API/Postgres packet under
  [connected-household-native evidence](../reports/evidence/connected-household-native/README.md),
  including default-off Personal surfaces, enabled 980 DOP / one 20 DOP
  correction demo, and response-loss recovery. Full native setup hit the local
  sign-in rate limit and is **not** claimed passing; same-fixture continuation
  and focused gates are.
- Remaining outside this land: physical iPhone/internet delivery; external
  invitation delivery; Business/Custom; hosted enablement; design-checkpoint
  adoption; Accounts tab; Apple on the connected path. Shared
  Plan/budgets/goals/debt later landed via [PR #773](#pr-773-integration-landing).
  Detail:
  [landing report](../reports/2026-10-01-pr-766-integration-landing.md).

## PR #763 integration landing

Standing promote authority merged the verified head and completes this
integration landing. This grant does not authorize deployment, hosted
configuration changes, paid providers, phone-environment actions, #760 edits,
design-branch work or another delivery lane.

- [PR #763](https://github.com/lagarcess/argus/pull/763) squash-merged at
  **October 1, 2026, 05:29:24 UTC** as
  `fbcc399bdb888d89af594422cfa319a4c26c60e5`, from verified head
  `7b80190d057c89b5f92b03845f374a810253dda1` onto unchanged integration
  `9b5e8643f0493145bd672c2af6e7508371d4cfa0` (also the original lane base).
  No intervening semantic overlap or reconciliation merge exists.
- Pre-merge Exact head recorded all 17 CI checks SUCCESS, Codex P1/P2 findings
  fixed (non-recursive `is_active_household_member`, deletion-safe
  `ON DELETE SET NULL` + active-admin CHECK, household-then-invitation lock
  order), and **0** unresolved review threads.
- No linked closing issues. `ARGUS_HOUSEHOLDS_ENABLED` remains default-off in
  `.env.example`, `render.yaml`, `.github/argus-env.sh` and the private-alpha
  release profile. Migration `20261001090000_household_membership.sql` is not
  applied to production by this landing.
- Accepted proof for this land is hermetic only: `tests/household/` runs in
  `PERSISTENCE_MODE=memory` with mocked Supabase gateway and auth-session checks
  (`tests/household/conftest.py`). No durable real Auth/Postgres/RLS evidence is
  cited here.
- Remaining MVEE Household work after this membership land was completed for the
  bounded native consent/activity package by [PR #766](#pr-766-integration-landing)
  and for shared Plan consumers by [PR #773](#pr-773-integration-landing).
  External invitation delivery, physical-phone proof, and hosted enablement
  remain outside. Detail:
  [landing report](../reports/2026-10-01-pr-763-integration-landing.md).

## Connected Spaces and Household lane

**Landed via [PR #766](https://github.com/lagarcess/argus/pull/766)** (Exact head
`04831ccb12a46b89a3cd5f5391139d3589321815`; product squash
`079ec8d819f8e2513cc624bfa7a4eb9ca60c7627` onto tip `09ce4e0a…`). See
[PR #766 integration landing](#pr-766-integration-landing).

This lane connected Household consent and canonical financial projections to
landed #763 membership and #760's connected shell under the approved permission
policy. `ARGUS_HOUSEHOLDS_ENABLED` stays server-default-off. Durable evidence:
[connected-household-native](../reports/evidence/connected-household-native/README.md).
Restart recipe: [ios/HOUSEHOLD_SETUP.md](../../ios/HOUSEHOLD_SETUP.md).

**Remaining outside the landed package:** physical iPhone/internet delivery;
external invitation delivery; Business/Custom lifecycle; hosted
migration/enablement; Accounts tab; Apple on the connected path;
design-checkpoint adoption (`1dcd12a5` / `1b2005fd9` parked). Shared
Plan/budgets/goals/debt consumers landed via
[PR #773](#pr-773-integration-landing). Existing #760 shared-shell / Personal
Search dark contrast polish remains recorded, not claimed fixed here.

Worker branch `codex/connected-household-native` and its isolated checkout are
closed for active delivery after this landing. Earlier competing membership
store at `240854cd…` / `connected-spaces-household` remains recovery/reference
only.

### Recovered decisions and approved permission policy

[MVEE household][mvee-household] owns consent and financial meaning. Creation,
invitation acceptance and account sharing are three separate operations.
Acceptance grants membership only, plus admission to the beta since the
[October 2 lane locks](argus-decision-log.md#october-2-2026-cuadrao-lane-locks):
no automatic joint account, financial-record
ownership transfer, private account sharing, chat/document access or banking
execution. Account ownership percentage remains a financial fact, never access.
Keep one canonical account/history and count its permitted projection once.
Sharing neither moves the account's private-space assignment nor posts money.

Use the fixed [design handoff #762](https://github.com/lagarcess/argus/pull/762)
source `a509cebde8990728693b09add7738856bc682a07`, specifically its
`docs/specs/cuadrao-accounts-design-lock.md` household decisions and existing native
household controls. Home retains the quiet Personal / Household / + selector;
People owns invitations and member status. Sharing uses the native share sheet;
dismissing it never asserts delivery or acceptance. The recipient can accept or
choose Not now. Do not wait for the design PR to merge or import its unfinished
Profile/chat proposals or wholesale runtime ancestry. Use the explicitly assigned C930 simulator above for native proof. Never use
Compact `1A90F684…` or design `8AFB6084…` for this lane.

**Founder approved permission policy, 2026-10-01 (locked — implement this):**

- Creator administers invitations and membership; can transfer administration
  or close the household before departure.
- Members see the member list and can leave.
- Shared accounts start **view-only**; editing only with an **explicit** grant.
- Editing does **not** grant ownership, membership administration, or resharing
  rights. Owners retain ownership, sharing and account-removal powers.
- Leave/removal revokes the departing person's access and withdraws their
  shared accounts. Preserve original owners' records and legitimate transactions;
  do not delete history, reverse spending or change ownership. Rejoining creates
  a fresh membership that requires fresh sharing approval.
- Closing the household preserves all owners' records and history.
- Invitations: revocable, single-use, seven-day links; safe same-recipient
  acceptance retries. Local invitations are synthetic (no email/WhatsApp/
  external delivery in this lane).
- Create household ≠ invite ≠ share account. Acceptance = membership only, plus
  admission to the beta since the October 2 lane locks.

### Ownership, reuse and overlap

The captain owns the coupled membership/authorization contract, implementation,
manifest, integration and final delivery claim. One writer owns all shared backend
and native transport surfaces; independent review/acceptance is read-only. The
completed `household_authorization_scout` mapped existing owners without edits or
runtime artifacts. Assign any further bounded writer only after the policy is
settled; avoid competing permission implementations.

Reuse `current_user` and the registered financial gate, the existing account
repository and canonical Recording services, Plan snapshot reads used by Home and
Search, and native session/journal recovery. Current financial repository access
is strict owner equality; database transport bypasses caller RLS, so authorization
must be checked server-side, including inside mutation transactions. Preserve
owner-qualified money FKs, owner/account locking, actor attribution and replay
identity. Never rewrite record ownership to make sharing work.

Grant-filtered projections must not disclose hidden transfer/refund counterpart
accounts, asset/debt links, history, private plans or source records indirectly.
Separate durable record owner from authenticated actor before permitting editing;
revocation must also prevent receipt replay from returning protected data.
Current paired money activity requires one durable owner across its legs; do not
silently invent cross-owner transfer accounting. Define the bounded adapter in the
existing API/data contracts during implementation rather than duplicate money rules.

[PR #760](https://github.com/lagarcess/argus/pull/760), inspected at
`a2eaca12a937f18e640c803d09d234d7f132cf0c`, owns connected Cuadrao auth/Home/shell
and selective Search presentation. It explicitly excludes household production.
Household owns its new feature modules, authorization adapters and scoped tests.
Shared overlap is the app/root mounting point, Home composition, Search context,
native account responses and localization. Keep adapters separate, record the
composition handoff, and reconcile against freshly fetched integration through
one-way merges; do not edit #760's checkout or overwrite its connected owners.

### Delivery and observable proof

| User outcome | Existing capability | Remaining work and owner | Actual dependency | Assembled proof |
| --- | --- | --- | --- | --- |
| Create and reopen Household | Registered identities; fixed create/open design | Household membership storage/API/native controls; captain's single writer | Settled membership lifecycle | User A creates; relaunch returns to the same household with no auto-shared accounts |
| Invite, defer and accept | Native share-sheet/recipient reference; existing auth return/recovery | Durable invitation lifecycle and authenticated acceptance | Membership contract; local link handoff | A creates link; B defers then accepts; repeat/lost-response acceptance creates one membership |
| Choose exactly which accounts are shared | Canonical accounts/history; MVEE explicit consent | One account-grant owner plus permission preview/edit controls | Approved view/edit policy | B sees A's chosen account, never A's private account; unauthorized IDs and direct database access rejected |
| Inspect shared Home/Accounts/Search | Financial projections and existing detail/Search continuity | Context-aware authorized projections and native adapters | Accepted membership and explicit account grants | Both users agree on canonical values; unknown/currency boundaries survive; hidden linked records do not leak |
| Edit only where permitted | Existing money posting, correction and write journals | Actor-aware authorization adapter to existing writer | Explicit editing grant; existing canonical account/leg contract | View-only writes fail; permitted update retains actual author/history and refreshes both authorized views without duplicate money |
| Revoke, remove or leave safely | Preserved original financial records | Membership/grant revocation and retained-record explanation | Approved departure/custody | Access stops on API, Search, Home and relaunch; original owner retains unchanged identity/history |
| Recover failures and stale views | Session epochs, exact-byte journals, CAS, idempotent writes | Household scope invalidation and confirmed-write retry integration | Above contracts | Interrupted/repeated writes create no duplicates; revoked access cannot replay protected data; en/es/native recording and Postgres readbacks |

Verification uses a real isolated local Auth/API/Postgres stack and the assigned
C930 simulator, not a sample-only canvas. #760 currently owns
Compact `1A90F684-345F-465C-AA50-6A5298F34156`; Cuadrao exclusively owns
`8AFB6084-8918-416E-9164-E21061306BEC` and
`/private/tmp/cuadrao-native-design-build`. Neither is assigned to this lane.
The assigned C930 simulator was checked for ownership and reused; use the separate
current-demo bundle and disposable build cache recorded above. Preserve all demos and synthetic data;
ports 58700–58749 and the physical-phone setup remain untouched.

Keep local invitations synthetic. No email, WhatsApp, external delivery,
shortener deployment or provider call is authorized here. The selected future
do-blitz/Resend adapters depend on this invitation lifecycle and their separate
service/deployment authority; do not substitute sending for acceptance proof.

This bounded assignment connects Personal/Household contexts and account grants.
Private Business/Custom lifecycle/account moves remain D04 work; shared budgets,
goals, debt plans and private-source contributions remain D07/domain-adapter work.
Imports, chat/voice context, Updates, notifications, rebrand and Profile proposals
are excluded here, not newly deferred from the MVEE. Their readers must inherit
this authorization owner when separately assigned.

Default-off membership API/code and hermetic in-memory lifecycle proof landed at
Exact head `7b80190d` through the merge grant above. Real Auth/API/Postgres and
RLS verification (migration, locking, policies) remains explicitly pending; do
not treat this land as Auth/Postgres READY. Native Home/Accounts/Search adapters
and physical-phone proof also remain future assigned work.

## PR #760 integration landing

Standing founder promote authority merged the Compact-verified Connected
Cuadrao head and completes this integration landing. This grant does not
authorize deployment, hosted configuration changes, paid providers,
phone-environment actions, design-checkpoint adoption, chat/voice stack work
or another delivery lane.

- [PR #760](https://github.com/lagarcess/argus/pull/760) product
  squash-merged at **October 1, 2026** as
  `819870e6fcfd28d469b12691fe2471e00e2000db`, from verified Exact head
  `0462f3ade6d347bd13644eda5636264c007034c0` onto integration including
  Household #763 (`fbcc399bdb888d89af594422cfa319a4c26c60e5`).
- Exact merge integration CI/smoke, this landing-docs housekeeping merge
  SHA, and final clean local/remote tip parity are recorded in the merged
  PR landing comment after terminal checks (do not treat the product squash
  as the lasting tip).
- Compact exclusivity during verify: `1A90F684-345F-465C-AA50-6A5298F34156`
  only. Design sim `8AFB6084…` off-limits. Design checkpoint `1dcd12a5`
  adopt-into-#760 = none. Physical iPhone pending (`Device.local`) allowed.
- Accepted Compact matrix at Exact-head lineage: Auth bilingual, account
  entry, archive restore, Spanish check review, complete financial loop,
  Connected Search editors, AuthJourney relaunch; post-#763-reconcile
  complete-loop smoke PASS. Path overlap with #763 none; recording change
  additive `get_any_account` only; iOS household/spaces remain design
  preview; personal-loop Compact evidence retained.
- Modularity clean on merged worker; review threads none; applicable CI
  path-filtered skips (iOS-heavy). No new production configuration from
  #760; financial/household flags remain default-off.
- Remaining outside this land: chat/voice stack, design-checkpoint
  adoption (founder-named only), physical-phone proof, Household native
  adapters / real-stack proof (owned with #763). Detail:
  [landing report](../reports/2026-10-01-pr-760-integration-landing.md).

## PR #759 integration landing

The founder authorized merging the verified head and completing integration
landing. This grant does not authorize deployment, hosted configuration changes,
paid providers, phone-environment actions or another delivery lane.

- [PR #759](https://github.com/lagarcess/argus/pull/759) squash-merged at
  **September 30, 2026, 8:44:43 p.m. America/Chicago** as
  `0cd8d1658c8a58d0a8e29e3307f948aed11ecbc3`, from verified head
  `12a48f598da40fdad16c96caf80a92324f2eb1a4` onto unchanged integration
  `9d6ed94491be9d904da881901a6d7a2dc8cf635b` (also the original base).
  No intervening semantic overlap or reconciliation merge exists. Approved-head
  and squash-merge trees are identical; canonical integration fast-forwarded
  cleanly. The accepted lane evidence is preserved across that identical tree.
- The [terminal readiness audit](https://github.com/lagarcess/argus/pull/759#issuecomment-5922943880)
  records green applicable PR/push CI and smoke, clean fresh independent review
  through the exact final head, a clean scoped Codex follow-up and zero unresolved
  findings. Both assembled native journeys and real API readback revalidated the
  retained evidence at that head. 394 financial/API/OpenAPI/Postgres/recovery
  checks passed without skips; native package tests had 64 passes and four
  inherited opt-in live-auth skips. Real local authentication was exercised by
  the assembled journeys. Ten screenshots and the 60-second recording remain
  durable. Landing does not repeat the accepted journey.
- Exact merge [integration CI](https://github.com/lagarcess/argus/actions/runs/36802549319)
  and [local smoke](https://github.com/lagarcess/argus/actions/runs/36802549379),
  checked landing housekeeping and final clean local/remote parity are recorded
  in the merged PR's final landing comment after terminal checks.
- No linked closing issues or obsolete documents need closure or archiving.
  Only this manifest and the existing integration ledger need landing updates;
  API/data/OpenAPI contracts already landed with the feature.
- No new production environment variable or tracked-template update is needed.
  Existing financial exposure remains default-off. Synthetic native test/proxy
  inputs are local-only. The additive
  `20260930230000_connected_personal_assets.sql` migration was locally and
  ordinary-preview verified; landing applies no hosted migration or activation.
- The [asset demo, evidence and restart guide](../reports/evidence/connected-personal-assets/README.md)
  remain preserved. The runnable demo checkout is detached at the approved head,
  with the same application tree as the feature merge, using the retained
  financial simulator, direct API59300, Auth59201/Postgres59202 and CAPTCHA59305.
  The owned response-loss helper is stopped. Older demos, synthetic records,
  Cuadrao and the physical-phone environment (58700–58749) remain untouched.
  Personal manual assets are locally delivered; physical-iPhone internet proof,
  shared variants and the remaining MVEE outcomes are not completed or assigned
  by this landing.

## Connected personal assets and net worth lane

**Original implementation assignment, September 30, 2026 (historical authority; subsequent merge grant above).** Add a property, vehicle or other
asset, record its estimated whole value and personal ownership share, optionally
link an existing debt, inspect Accounts/Home, correct the estimate, archive and
restore, find it through Search and reopen with preserved state. This lane is
closed and retained only as delivery history. The full MVEE coverage below keeps
its existing owners and deferrals; this landing assigns no further implementation.

**Original and freshly fetched pre-merge integration:**
`9d6ed94491be9d904da881901a6d7a2dc8cf635b`, including #757/#758.
**Recovery branch:** `codex/connected-personal-assets`.
**Delivery checkout:**
`/Users/garces/.codex/worktrees/connected-personal-assets/private-alpha-next`.
**Current state:** the complete assigned journey is locally verified in the native
simulator against real Auth/API/Postgres and landed through [PR #759](https://github.com/lagarcess/argus/pull/759); the integration landing above owns the subsequent merge grant.
Two assembled native cases pass, including partial ownership, linked original
debt, old-estimate correction, archive/restore, Search return, English/Spanish,
reopening and recovery of a lost accepted create response with exactly one asset.
The financial/API/OpenAPI/Postgres and recovery gate passes 394 checks; native
package tests have 64 passes and four inherited opt-in live-auth skips.
The fresh independent reviewer is clean through
`12a48f598da40fdad16c96caf80a92324f2eb1a4`. The confirmed GitHub type-history
finding is fixed at the shared guard and verified in memory and Postgres.
The [durable evidence and restart guide](../reports/evidence/connected-personal-assets/README.md)
record exact source/review SHAs, ten screenshots and the 60-second recording.
Original and pre-merge integration were `9d6ed94491be9d904da881901a6d7a2dc8cf635b`;
no reconciliation or intervening semantic overlap exists. Evidence was retained
across the last test-selector and documentation/evidence deltas and revalidated
at the final head. The [terminal audit](https://github.com/lagarcess/argus/pull/759#issuecomment-5922943880)
records green applicable CI, clean scoped follow-up review and zero unresolved
findings. The integration landing above records the subsequent authorized merge.
The direct API59300 demo remains runnable; the disposable response-loss helper is
stopped. Other demonstrations, Cuadrao and the physical-phone environment remain
preserved. This closes local personal-asset delivery, not physical-phone internet
acceptance or the full MVEE. No financial product choice remains unresolved.

### Locked behavior and contract gates

The [MVEE optional-asset rules][mvee-accounts] own financial meaning. Store the
whole estimate and explicit ownership share, applying the existing personal-share
rounding once. Unknown and zero remain distinct. Display estimate date and basis.
Estimates affect recorded net worth, never cash, income, spending, savings backing
or expected cash movements. A debt link organizes two existing records and grants
no permissions. The existing debt balance and its ownership rules remain canonical;
linking never adds a liability or subtracts it again. Unknown asset value never
prevents recording or linking a loan. Each currency remains separate.

Reuse Accounts identity/types, Recording records/revisions, existing debt plans,
Home position projection, native controls, write recovery and account Search.
Extend the relevant API and data contracts alongside implementation. Do not
introduce another ledger, valuation service or editable derived total. Preserve
history, legacy account readers and all budget/savings/debt behavior. Account
archive remains organizational and retains money totals, with restoration of the
same identity. This lane adds neither disposal accounting nor new sharing rights.

### Accepted implementation shape and decision trail

`assets_financial_design` and `assets_native_design` recovered the canonical
Recording, account projection, native detail/journal and Search contracts.
`assets_architecture_judge`, using a fresh gpt-6-luna context, compared their
complete alternatives against current integration. The captain selected the
native reader's smaller shape, scored 23/25 against 20/25 for the broader shape.
All readers completed and relinquished ownership without repository/runtime edits.

Keep one typed asset projection on the existing account ID. Whole value and
date remain the canonical opening or value-update observation; optional basis
binds to that exact revision. Current ownership remains the account fact. Add
one optional owner-qualified reference to an existing liability account, with no
stored amount, equity or financial allocation. Share and link edits retain their
accepted history and replay identity atomically. This is non-money history,
not another value ledger or generic event-sourcing system. Reuse the current
owner/account locks and replay-before-CAS discipline.

Graft the financial reader's correction safeguard. Correct the selected
observation revision, preserve previous revisions and its observation order,
and hydrate one current observation per identity. A correction recorded today
must not promote an older estimate over a later observation. New dated estimates
and correction of erroneous estimates remain distinct. Add durable pending
account-create recovery using the existing owner-scoped write journal, rather
than preserving create requests only in memory.

Reject a separate Asset identity, multiple debt links, creation of a new debt
from this flow, debt allocation, sale/disposal and generic audit machinery.
Existing 1–10,000 basis-point shares remain supported. Initially unknown assets
can later receive a value; explicit zero remains known. Omitted values never
withdraw a previous known estimate. Withdrawing a known estimate is not an
assigned disposal/withdrawal contract and must not be faked by zero or deletion.
Keep the dated last estimate visible.

Model the Domain selected revision-bound estimate provenance and the existing
account identity. Separate Before Serializing Shared State selected one coupled
implementation writer. Prove It Works requires the actual native/API/database
journey before readiness. Ordinary endpoint, schema and receipt details belong
to that writer and must be documented before their code is committed.

### Ownership, dependencies and acceptance

The captain owns scope, contract selection, acceptance, evidence, environment,
publication, integration reconciliation and this manifest. Read-only financial
and native design readers return bounded alternatives. One exclusive writer
then owns the coupled Recording, API, additive persistence, native and tests.
The writer relinquishes its checkout before captain verification. One fresh
independent reviewer checks the finished diff and only affected fixes afterward.

The following is the original delivery mapping; its personal local outcomes
are verified and landed as recorded above. Physical-phone proof remains pending.

| User outcome | Existing capability | Remaining work | Owner | Dependency | Assembled acceptance |
| --- | --- | --- | --- | --- | --- |
| Add property, vehicle or other asset with whole estimate and share | Nine account types, exact money, account identity and share | Compact native asset entry and canonical estimate facts | Implementation owner | Accepted account/estimate contract | Known, zero and unknown values; half and custom shares; API readback |
| Understand personal net worth without treating estimates as cash | Home position and personal-share reducer | Estimate labels, provenance and connected detail | Same owner | Canonical asset read | Independent currency totals; no cash/spending/forecast change |
| Link and inspect an existing debt | Canonical debt account and payment plans | Owner-scoped relation and original-debt destination | Same owner | Account identity and link contract | Debt update changes Home once; unknown asset still links; no duplicated balance |
| Correct estimate or ownership and inspect history | Append-only revisions, CAS and journals | Estimate/history controls and durable correction provenance | Same owner | Atomic revision/receipt contract | Lost response, exact retry, stale rejection, previous basis retained |
| Archive, restore, Search and reopen | Account lifecycle, Search origin and secure session | Asset detail reuse and refreshed return | Same owner | Existing account/navigation owners | Totals retained when archived; same query/filter/scroll; relaunch preserved |
| Protect existing financial journeys and isolation | Budgets, goals, debts, ownership gates | Focused regression and English/Spanish proof | Captain and reviewer | Finished connected implementation | Real API/Postgres and native acceptance, no cross-owner disclosure |

### Throughput and execution contract

- **Blocking first steps.** Fetch integration, recover financial policy and
  select the canonical shape before code or new environment setup.
- **Independent workstreams.** Read-only backend/native recovery can run together.
  Acceptance preparation uses separate temporary artifacts and no shared writes.
- **Shared mutable state.** Recording truth, account snapshots and native
  contracts have one writer in an exclusive checkout. Simulator use, builds and
  test database changes remain serialized and owned by the captain.
- **Smallest safe decomposition.** One implementation owner prevents competing
  asset totals and revisions. Verify backend units, then the assembled native
  journey and finally one fresh review. Extra feature workers do not earn a place.

The poteto Feature checklist records the delivery sequence.

- [x] `how` over the affected subsystem.
- [x] `architect` for parallel design exploration.
- [x] Write the throughput checkpoint as four todo items.
- [x] Delegate code-writing to a subagent using the configured feature model.
- [x] Verify on the matching surface.
- [ ] Rebase into small, ordered commits. Stack follow-ups.
  Skip rebasing after evidence/publication under the repository one-way rules.
- [ ] If the design is contested, `interrogate` before shipping.
  Skip unless the bounded design comparison identifies an unresolved conflict.
- [x] Run Opening a PR.

Reuse retained financial simulator `1A90F684-345F-465C-AA50-6A5298F34156` and a
suitable lane-owned build cache. Preserve the installed debt demo, synthetic
records, videos and restart guides. Cuadrao simulator
`8AFB6084-8918-416E-9164-E21061306BEC`, cache
`/private/tmp/cuadrao-native-design-build`, its checkouts and previews are forbidden.
Phone ports 58700–58749, signing, certificates, services and data are forbidden.
No new simulator is necessary. Keep temporary services limited and remove only
owned disposable helpers after acceptance.

Acceptance uses synthetic records on real isolated local Auth/API/Postgres and
the native simulator. Independently expected totals cover partial ownership,
unknown/zero, linked-debt updates, corrections, archive/restore, separate
currencies, owner isolation, retries, interrupted writes and reopening. Include
Search/detail/back continuity, English/Spanish and focused financial regressions.
Commit durable screenshots, a short recording and concise restart instructions.

Publication and the existing isolated automatic PR preview are authorized.
Keep all infrastructure settings unchanged. Before readiness, fetch integration,
reconcile one-way if advanced, audit semantic overlap, run affected checks and
merged-tree modularity, and record exact source/evidence/review SHAs and terminal
CI. Stop with a scoped PR targeting `codex/private-alpha-next`, clean fresh
independent review and zero unresolved findings. No merge, deployment, hosted
configuration, paid providers, production data, phone actions or subsequent lane.
Pause only for a genuine unresolved financial product choice or an action outside
this grant, while continuing independent authorized work.

## PR #757 integration landing

The founder authorized merging #757 at the verified head, completing integration
landing and a bounded documentation PR if required. No deployment, hosted
configuration change, next slice or phone-environment action is authorized.

- [PR #757](https://github.com/lagarcess/argus/pull/757) squash-merged at
  **September 30, 2026, 5:16:18 p.m. America/Chicago** as
  `63b73ea80df9af2a61aa99f83afb9595408d0370`, from verified head
  `563c7011c8e37905d148d027665f4449971014d7` onto unchanged integration
  `7c29b2a9b3f4680f6804a2abc8378df45b05540c` (also the original base).
  No intervening semantic overlap or reconciliation merge exists. Approved-head
  and squash-merge trees are identical; canonical integration fast-forwarded
  cleanly and merged-tree modularity passes.
- The [terminal readiness audit](https://github.com/lagarcess/argus/pull/757#issuecomment-5920292387)
  retains green applicable PR/push CI and smoke, clean fresh independent review
  through source `70e34fe94641806ca3e80ac9ac6fff9ad73603f3`, and zero unresolved
  findings. The final preservation delta changed only documentation/evidence;
  runtime equivalence was verified. Three assembled native journeys, 343 real
  financial/API/OpenAPI/Postgres passes, sixteen screenshots and the 90-second
  recording remain valid across the identical merge tree. Landing does not
  repeat the accepted journey.
- Exact merge [integration CI](https://github.com/lagarcess/argus/actions/runs/36784593250)
  and [local smoke](https://github.com/lagarcess/argus/actions/runs/36784593078),
  the checked documentation PR and final clean local/remote parity are recorded
  in the merged PR's landing comment after terminal checks.
- No linked closing issues or obsolete documents require closure or archiving.
  Only this manifest and the integration ledger need landing updates; API/data/
  OpenAPI contracts already landed with the implementation.
- No new production environment variable or tracked-template update is needed.
  `ARGUS_FINANCIAL_ACCOUNTS_ENABLED` stays default-off in `.env.example` and
  `render.yaml`. Synthetic native assertion/proxy inputs are test-only. The
  additive `20260930210000_connected_debt_plans.sql` migration was locally and
  ordinary-preview verified; landing applies no hosted migration or activation.
- The [debt demonstration and restart guide](../reports/evidence/connected-debt-plans/README.md)
  remain on `codex/connected-debt-plans` in its unchanged delivery checkout,
  using the dedicated simulator and 592xx services. All earlier demos, synthetic
  records and the physical-phone environment (58700–58749) remain preserved.
  Personal Plan debt lifecycles are locally delivered; physical-iPhone internet
  proof, shared variants and the other MVEE outcomes remain incomplete. No
  additional implementation is assigned.

## Connected personal debt-payment plans lane

**Original implementation assignment and policy approval, September 30, 2026 (historical authority; subsequent merge grant above).** Deliver the
complete personal debt-plan journey through a runnable native iPhone simulator
against isolated real local Auth/API/Postgres, a short recording, durable
screenshots, restart instructions, applicable green CI and a clean fresh
independent review. Publication and existing isolated automatic PR previews are
authorized. Stop at merge-ready. No merge, deployment, hosted settings,
production data, paid providers, signing changes or phone installation.

**Fresh integration base:** `7c29b2a9b3f4680f6804a2abc8378df45b05540c`,
including savings #755/#756. **Recovery branch:** `codex/connected-debt-plans`.
**Delivery checkout:**
`/Users/garces/.codex/worktrees/connected-debt-plans/private-alpha-next`.
**Current state:** locally verified and landed through [PR #757](https://github.com/lagarcess/argus/pull/757); the integration landing above owns subsequent merge authority.
Assembled source `70e34fe94641806ca3e80ac9ac6fff9ad73603f3` passed three
native journeys, 343 real-Postgres/financial/API/OpenAPI checks with zero skips,
three production native command tests, retained registered-auth acceptance and
fresh scoped independent review with zero unresolved confirmed findings.
Loan create/payment/response-loss/retry/correction/actual return/edit/archive/
restore/Search/reopen, existing card-payment linking/return, and Spanish
Home/Search/back/relaunch passed. The canonical-ID preview bug found by the
simulator is fixed at the shared payment boundary and regression-covered.

A 90-second recording, sixteen financial screenshots, exact native/review/API
proof and retained restart instructions live in
[connected-debt-plans](../reports/evidence/connected-debt-plans/README.md).
The signed-in English/dark app remains runnable against direct API59200. Its
temporary fault proxy and recording helpers are stopped. Existing demos and the
phone-testing environment are preserved. Fresh integration remains the original
base, so no reconciliation merge or intervening semantic overlap exists. Later
preservation commits affect docs/evidence only; source evidence is retained after
runtime-equivalence verification. Final PR head, terminal applicable CI and local/
remote parity are recorded in the PR terminal audit. The subsequent authorized merge is recorded above.

**Remaining limits and visual polish:** optional payoff supports stated monthly
constant-rate terms, not guessed breakdowns, variable rates, lender billing or
automatic actual accrual. Missing/unsupported terms show no invented estimate.
Existing full-owner snapshots retain their scale limit. Passing loan/card native
cases emit the invalid-frame warning also present in retained savings acceptance;
no visible failure was observed, and shared layout polish stays tracked here.
Physical-iPhone internet delivery, shared Plan variants and the other MVEE
outcomes remain unfinished. No additional slice is started. GitHub CLI remains
the publication fallback because Origin CLI is unavailable.

### Approved money rule and shared owners

Other-debt balances mean remaining principal. An actual loan payment uses the
person's explicit principal, interest and fee breakdown. Cash falls by the total,
debt falls by principal, and interest and fees count as spending once. Missing
amounts are never guessed. Cards retain the landed card-payment contract.

Recording owns actual activity, signed account movements, corrections and
spending. Planning owns payment intentions, recurrence, fulfillment and
conditional projections. Native clients render canonical results. Creating or
editing a plan changes no recorded balance. Unknown debt remains unknown, and
currencies never convert. Existing savings pools remain the allocation owner.
Payoff assumptions stay visible and cannot establish an actual cleared balance.

The release captain owns integration, the existing manifest, independent
acceptance and publication. One implementation writer owns the coupled financial,
API, persistence and native surfaces. Temporary architecture readers and the
fresh reviewer do not write implementation. No competing board is introduced.

| User outcome | Inherited capability | Delivered work and owner | Dependencies | Assembled proof |
| --- | --- | --- | --- | --- |
| Create and edit a debt plan | Debt accounts, native Plan controls, Schedule | Implementation owner: canonical definition, funding and schedule connected | Canonical account and recurrence contracts | Create for card and loan; intentions change no balances |
| Understand debt and payoff | Recording position, local TVM calculators | Same owner: recorded debt, optional conditional payoff and explicit missing terms connected | Known balance and stated supported terms for an estimate | Unknown stays unknown; assumptions and actual remain distinct |
| Record or link a payment | Card payments, preview/confirm, atomic Plan receipts | Same owner: explicit loan split, eligible linking and occurrence progress connected | One Recording command and shared owner transaction | Cash, principal, costs and forecast update once |
| Inspect, correct and recover | Original activity editor, revisions, balance checks | Same owner: original split corrections, dated returns, partial and extra payments connected | Current original revision and account versions | Independent totals; correction/reversal re-evaluates links |
| Archive, restore and reopen | Plan lifecycle, native journals and origins | Same owner: debt lifecycle and durable context connected | Stable definition and occurrence identities | Relaunch, lost response, exact retry and stale edit |
| Find and return through Search | Typed financial Search and existing detail navigation | Same owner: typed debt hit and owning detail connected | Canonical debt reads | Query, filters and scroll survive; edits refresh results |
| See Accounts, Plan and Home agree | Shared forecast, budgets and savings support | Same owner: shared debt movements and concise summaries connected | Recording and one Plan snapshot | Partial, missed, extra, cleared/reopened debt; budget and goal regressions |

### Chosen implementation shape

Two bounded readers compared a single canonical payment with a parent aggregate
of separate principal and cost entries. A fresh judge favored the single activity
(25/30 versus 18/30). The captain selected it because every existing reader can
keep using the same identity, receipt, revision and account-leg ownership.
Recording extends its paired activity to explicit unequal loan movements and
one derived spending contribution. Planning extends its existing definition,
claims and repeatable-read snapshot. No new ledger or receipt owner is added.

An actual returned payment is a new dated inverse activity linked to the original
payment. The original and its original-period costs remain. Explicit component
limits prevent returning principal, interest or fees twice. Correcting an
erroneous entry remains its existing revision operation. Partial debt payments
leave the unpaid occurrence amount outstanding; extras do not automatically
fulfill future dates. Existing bill and savings occurrence behavior is preserved.

The native payment editor is shared by account-first recording and Plan-origin
fulfillment. Optional payoff estimates reuse compatible local calculations with
stated terms and visible assumptions. Missing terms yield no invented estimate.
The alternative's hidden child activities and separate lifecycle/receipt stores
were rejected. Additional future-payment split fields are unnecessary for the
short initial flow.

**Owners:** `debt_implementation` is the sole code/contract writer on
`codex/connected-debt-plans-core`; its commits enter the delivery branch in
verified units. This includes the existing `ios/Packages/ArgusSession` types,
transport and journal. The captain owns acceptance scripts, runtime, evidence,
manifest and publication. Design readers/judge have completed and stopped.

**Isolated local allocation:** API 59200, Supabase 59201, Postgres 59202,
synthetic CAPTCHA 59205, optional response-loss proxy 59212 and mirror 59213.
The two synthetic users are retained privately in the ignored allocation folder.
Reuse idle **Argus Foundation Compact** simulator
`1A90F684-345F-465C-AA50-6A5298F34156` with separate bundle
`local.argus.debt-demo`. Its prior foundation bundle/data stays preserved. No
additional simulator is created. All earlier demo allocations stay untouched.

### Delivery sequence and acceptance

1. Compare two compact storage designs and select the smallest canonical shape.
2. Implement payment truth and debt-plan lifecycle together with meaningful
   domain, API and Postgres tests and updated API/data/OpenAPI contracts.
3. Connect the native flow, Home and Search using existing components and
   English/Spanish. Demonstrate the journey as it becomes runnable.
4. Independently exercise payment linking, corrections, partial/extra/reversed
   payments, explicit interest/fees, payoff/reopening, balance-check consistency,
   currency/unknown behavior, identity isolation and budget/savings regressions.
5. Preserve screenshots and a short recording. Verify interrupted writes,
   duplicate retries, stale edits, Search/back and relaunch. Reconcile fresh
   integration one way, run merged-tree modularity and required checks, obtain
   one fresh scoped review, fix confirmed causes, then publish readiness.

Keep the short payment flow and locked native design. No web, rebrand,
navigation redesign, household, imports, notifications, voice or runtime work.
Preserve every existing demo and synthetic record. Phone ports 58700–58749 and
its checkout, services, simulator/device, certificates and signing are forbidden.
Temporary helpers belong only to this lane and are cleaned up after verification.

## PR #755 integration landing

The founder authorized merging #755 at its verified head, completing integration
landing and the necessary bounded documentation PR, then verifying CI and
local/remote parity. No deployment, hosted configuration change, next slice,
signing or phone-environment action is authorized.

- [PR #755](https://github.com/lagarcess/argus/pull/755) squash-merged at
  **September 30, 2026, 11:32:38 a.m. America/Chicago** as
  `dc48c074b457cfb461e128aee2dcc58f9db3a342`, from verified head
  `f6dfd482a1e4dc802f0d64eba22bc91a4f01d48f` onto unchanged integration
  `6a9d0338d2b2e7106877e0e5d1f9f5aaa70d67ec` (also the original base).
  There is no intervening semantic overlap or reconciliation merge. The approved
  head and integration merge trees are identical; canonical integration
  fast-forwarded cleanly and merged-tree modularity passes.
- The [terminal readiness audit](https://github.com/lagarcess/argus/pull/755#issuecomment-5906057156)
  retains green applicable PR/push CI and smoke, clean fresh independent review
  after the bounded lifecycle/harness fixes, and zero unresolved findings.
  Four native journeys, 310 assembled financial/API/OpenAPI/Postgres passes,
  recovery/localization evidence, 13 screenshots and the 62-second recording
  remain valid across the identical merge tree. Landing changes documentation
  only and does not repeat the accepted journey.
- Exact merge [integration CI](https://github.com/lagarcess/argus/actions/runs/36744979395)
  and [local smoke](https://github.com/lagarcess/argus/actions/runs/36744979517),
  the checked documentation PR and final clean local/remote integration parity
  are recorded in the merged PR's final landing comment after terminal checks.
- There are no linked closing issues. Only this manifest and the integration
  ledger need landing updates; API/data/OpenAPI contracts already landed with
  the implementation. No current document needs archiving.
- No new production environment variable or tracked-template change is needed.
  The inherited `ARGUS_FINANCIAL_ACCOUNTS_ENABLED` remains default-off in
  `.env.example` and `render.yaml`. `ARGUS_TEST_GOAL_SUPPORTED` is a synthetic
  native-test assertion input, not hosted configuration. The additive
  `20260930170000_connected_savings_goals.sql` migration was verified locally
  and by the existing automatic PR preview; landing applies no hosted migration.
- The [savings demonstration and restart guide](../reports/evidence/connected-savings-goals/README.md)
  remain on `codex/connected-savings-goals` in its unchanged delivery checkout,
  using the dedicated simulator and 591xx services. Every prior demonstration,
  synthetic record and the separate physical-phone environment (58700–58749)
  remain preserved. Physical-iPhone internet delivery and the whole MVEE are
  still incomplete; remaining debt-plan, shared and other journeys stay mapped
  below. No further implementation is assigned.

## Connected personal savings goals lane

**Founder assignment, September 29, 2026:** deliver the connected personal goal
journey through native iPhone simulator acceptance against an isolated real local
API/Postgres, scoped independent review and a merge-ready PR. Implementation,
local verification, commits, branch and PR publication are authorized. No merge,
deployment, Render action, hosted configuration change, production data, paid
provider, real-money movement, signing or physical-phone installation. Other
MVEE work stays with its existing owners; this lane does not start another slice.

**Fresh integration base:** `6a9d0338d2b2e7106877e0e5d1f9f5aaa70d67ec`,
including the budget implementation and landing (#753/#754).
**Recovery branch:** `codex/connected-savings-goals`.
**Delivery checkout:**
`/Users/garces/.codex/worktrees/connected-savings-goals/private-alpha-next`.
**Current state:** the complete personal savings journey passes on the dedicated
native simulator against real local Auth/API/Postgres. Existing allocation,
record/link, original correction, withdrawal/shared-shortfall recovery,
lifecycle, Home/Plan/Search, relaunch and English/Spanish are connected.
Implementation owner has relinquished a clean source tree. Independent review
is clean after one confirmed lifecycle-input fix and one native harness fix.
[PR #755](https://github.com/lagarcess/argus/pull/755) is merged;
[the landing checkpoint](#pr-755-integration-landing) owns current integration
CI/parity. Its accepted source, review and demonstration remain preserved.
All existing demos, synthetic data and phone resources are preserved. Ports
58700–58749 and the phone owner's checkout, services and signing are forbidden.

### Founder-approved savings policy

**Approved September 30, 2026.** Goals use explicit allocations backed by known
recorded account balances, kept separate by currency. Allocating money does not
move it or change account balances. A shared pool prevents multiple goals from
claiming the same money. Existing savings count when explicitly allocated;
linking an already included contribution adds provenance without another credit.
Planned contributions and projections remain separate from actual savings.

Withdrawals, reversals and corrections re-evaluate backing and linked activity.
If backing becomes insufficient, show the shortfall and **Needs review**. Do not
silently redistribute money or present unsupported amounts as fully saved.
Unknown balances cannot establish supported actual savings. The person chooses
how to reduce or reassign allocations; Argus invents no priority among goals.

This settles the product gap identified in the [MVEE Plan rules][mvee-plan] and
locked design. The prototype's reported-total checkpoint, which ignored ordinary
withdrawals, is superseded for production savings truth by this explicit founder
decision. Its native visual standard and contribution/detail interactions remain
the reference. Relevant API/data contracts record the approved policy and bounded
allocation/link/lifecycle semantics alongside implementation. No new product
approval is needed for routine technical choices within this policy.

### Ownership, dependency and acceptance map

The captain owns delivery, integration, manifest and independent acceptance.
Implementation owner `goals_implementation` owns the shared contracts, Planning
goal service/storage, Recording adapters, native goal module and integration
tests in exclusive branch `codex/connected-savings-goals-core`, checkout
`/Users/garces/.codex/worktrees/connected-savings-goals-core/private-alpha-next`.
The captain integrates its ordered commits into the delivery branch and owns
the simulator, local services, evidence and independent acceptance. Recording remains the only actual-money owner; Planning
owns goal intentions, allocation/linking and projections. Clients render server
results. Existing account and activity detail/correction screens remain the
money-edit controls. A fresh independent reviewer reviews the finished diff once
and only affected fixes afterward. Codex availability is not a dependency.

| User outcome | Inherited capability | Implemented connection | Actual dependency | Observable assembled proof |
| --- | --- | --- | --- | --- |
| Create, inspect and edit a named target, currency, optional date and account setup | Native Plan Goals destination, shared money inputs, versioned Plan commands | Goal definition and real detail/form; API/data contract | Goal definition/progress contract | Native create/edit, stale-version rejection and API readback after reopen |
| Assign existing savings; record or link contributions once across multiple goals | Canonical logical activity, paired transfers, Plan receipts and owner lock | One allocation/link owner and atomic record/link commands | Shared allocation contract; known same-currency backing | Independent expected amounts across two goals; unchanged balances on allocation; duplicate retry creates no second activity or claim |
| Separate actual, planned and projected progress in Plan/Home | Shared Plan/Home snapshot, recurrence and forecast, native summaries | Goal intentions and derived occurrences/progress; explicit exclusions | Accepted goal/link contract | Planned saving leaves balances and actual progress unchanged; internal transfer has zero combined-cash/spending effect; fulfilled movement disappears once |
| Inspect/correct contributions and handle withdrawals/reversals | Original activity detail, append-only correction, account reconciliation | Goal link re-evaluation and explicit allocation recovery | Accepted backing and link rules | Original correction updates Accounts, goal and forecast; insufficient backing is visible; no invented goal-priority rule |
| Archive and restore without copying money/history | Plan/Budget reversible lifecycle and CAS/idempotency | Goal lifecycle with retained identities and explicit allocation effect | Accepted lifecycle/allocation contract | Archive/restore/retry keeps IDs, history and consistent shared claims |
| Find a goal and return with context; English/Spanish | Typed Search, persisted query/filter/anchor, native localization | Goal hit and actual detail destination; localized controls | Real goal projection/detail | Search to goal to original contribution and back retains origin and refreshes edits; relaunch preserves state |
| Recover durable writes with owner isolation | Exact command journal, replay-before-CAS, repeatable-read Postgres, auth/RLS | Goal-specific transaction, API, package and simulator cases | Implemented shared command contract; dedicated local stack | Response loss/retry and concurrent writes commit once; stale update is explicit; another identity cannot read or mutate goals/allocations |

### Selected goal contract and architecture

**Named shapes:** `GoalDefinition` stores target/setup/lifecycle and explicit
unlinked allocation residuals. `GoalContribution` points at one current canonical
transfer and optionally its own planned occurrence. `GoalPool` derives backing,
claims, available money and shortfall for one owner/account/currency.
`GoalProgress` derives assigned intention, supported actual, remaining, review
reasons and separate planned/projection data. No actual saved total or balance
copy is persisted. The existing Plan snapshot, owner lock, receipts and CAS own
both reads and commands; Recording supplies current position, activity and the
single ownership-share rounding function.

| Candidate | Independent assessment | Captain decision |
| --- | --- | --- |
| Current goal intentions and linked attribution in Plan snapshot | 5/5 money truth, 5/5 contribution correction, 5/5 existing owner reuse, 4/5 interface/storage | Selected; fewer persistence/replay stages and correct included-credit correction. |
| Append-only allocation intention events | 4/5 money truth, 1/5 included correction, 4/5 reuse, 2/5 interface/storage | Rejected; no separate allocation-history requirement justifies the extra fold, and provenance-only inclusion leaves old contribution credit in the assignment. |

The independent architecture reviewer was `goals_architecture_judge` in a fresh
context. This is design judgment, not implementation review. The captain grafted
its explicit deficit-improvement rule: reduction of existing claims remains
admissible while underfunded; new/increased claims require known sufficient
backing. No event history or partial activity split is introduced.

- Cash, checking and savings are the backing/funding/destination accounts in
  this slice, following the locked design. Capacity uses personally attributable
  current known positive position; unknown is not zero. Per-account pools prevent
  unrelated accounts or currencies silently rescuing a shortage. Account archive
  retains backing; goal archive retains claims and suspends pending goal schedule.
  Restore retains identity and derives current support, including Needs review.
- An eligible contribution is one current transfer into an allowed same-currency
  destination, assigned wholly to one goal. Income received directly can be
  allocated as existing money; it is not another goal transaction kind. Source,
  destination, currency and current revision remain reviewable.
- **Already included** partitions an existing unlinked allocation. Allocated 600,
  linked transfer 200 already included becomes residual 400 plus current transfer
  200, still 600. Correcting that transfer to 150 yields 550; to 250 yields 650.
  Accepted original amount is provenance only. Linking never posts money. A new
  transfer plus its allocation/optional fulfillment commits in one transaction.
- One shared activity claim owns attribution and optional occurrence fulfillment.
  Preserve existing expectation links, owner-qualified references and uniqueness.
  Ad hoc goal claims must not enter income/bill-only readers. Release of counting
  leaves fulfillment intact; it does not recreate a completed forecast movement.
  Changed/unavailable activity shows review, never an older fallback amount.
- A reverse-direction transfer is new canonical activity that changes backing,
  not evidence that the original transfer never happened. No amount/date matching
  invents a reversal. The lane adds no global financial-activity remove/restore
  API; acceptance uses original correction, reverse transfers and goal recovery.
- A fully backed component supports its assigned amount. A known shortfall with
  one claimant goal supports `min(assigned,backing)` and Needs review. A shared
  shortfall or unknown/ineligible backing leaves affected component support null.
  Any unresolved component leaves the goal total null; separately backed portions
  remain inspectable as partial support. Reached requires resolved support and
  no review issue. Count distinct goals, including archived goals, rather than
  contribution rows when deciding whether backing is shared.
- Goal-owned optional transfer schedules derive occurrences through the existing
  recurrence/cutover owner; no duplicate editable expectation. Two selected fully
  owned cash legs net zero. With one selected side or differing ownership shares,
  show the actual selected/personal cash effect without classifying it as income,
  bills or spending. Fulfilled or disputed linked occurrences do not silently
  create another payment. Planned contributions never become actual savings.

**Local allocation:** API 59100, Supabase 59101, Postgres 59102, synthetic CAPTCHA
59105; optional response-loss proxy 59112 and simulator mirror 59113. Dedicated
simulator `A466756C-1478-4FA9-8604-3D9FEE15A601`, iPhone 17e/iOS 27, named
`Argus Connected Savings Goals`. Ignored local users/config belong only to this
checkout. Restart existing services; never remint users or reset the database.
The read-only inherited baseline passed 236 financial/Plan/Budget/Search tests
with zero skips and native registered sign-in/relaunch/sign-out acceptance.
[Baseline evidence](../reports/evidence/connected-savings-goals/baseline.json)
records source/environment; no goal acceptance is claimed by those checks.

### Delivery workflow and throughput checkpoint

- [x] Read the Principles section of poteto-mode; frame the falsifiable local
  journey and preserve the scope/authority in this manifest.
- [x] `how` over the affected subsystem. Financial/native scouts recovered the
  canonical Recording, Plan snapshot/receipts, native detail/journal and Search
  flow without rebuilding them.
- [x] `architect` for parallel design exploration. Two bounded read-only
  candidates compared current intentions with allocation events. Independent
  cross-judgment and captain selected current intentions; synthesis below.
- [x] Write the throughput checkpoint as four todo items, below; update it at
  ownership handoff.
- [x] Delegate code-writing to one exclusive implementation writer/worktree.
- [x] Verify on the matching surface: real local API/Postgres and native simulator.
- [x] Deliver small ordered commits, verifying each unit before the next.
  Repository one-way integration merges override the playbook's rebase step.
- [x] If the design is contested, interrogate before shipping. Skip: the
  independent grounded selection resolved the invariant without a contested design.
- [x] Run Opening a PR and the approved independent review/fix loop.
  Exact-head applicable CI and the terminal audit are owned by
  [PR #755](https://github.com/lagarcess/argus/pull/755). Its terminal
  readiness audit is green with zero unresolved findings; the authorized merge
  is recorded in the landing checkpoint. No deployment or next slice.


1. **Blocking first steps:** the founder policy is settled. Select the bounded
   allocation/link/lifecycle contract before writing dependent code. Selection
   is complete; the shared contract is handed to the single writer.
2. **Independent workstreams:** read-only financial/native recovery is complete.
   Local acceptance preparation runs alongside the implementation writer
   without editing its checkout; independent review follows the finished diff.
   Backend/native changes stay with one writer because contribution attribution,
   activity claims and forecast fulfillment are one code-coupled feature.
3. **Shared mutable state:** Planning snapshot, receipts, financial owner lock,
   activity links, Swift response types, Search union and localization each have
   one writer. No parallel ledger, editable saved total, web or rebrand work.
4. **Smallest safe decomposition:** goal definitions and derived progress;
   atomic contributions and linked forecast; native lifecycle/original-activity
   continuity; assembled recovery/localization evidence and scoped review.

Acceptance uses synthetic records, explicit expected amounts independent of the
reducer under test, real local API/Postgres and a dedicated native simulator.
Screenshots and a short recording are committed with restart instructions and
exact-head provenance in the implementation PR. Component checks are reported
separately from the working local journey; physical-phone internet delivery
remains pending outside this lane. Before readiness, fetch integration, perform
one-way reconciliation when needed, assess semantic overlap, run affected
acceptance and merged-tree modularity checks, finish applicable CI and record
reviewed SHA and zero unresolved findings. Stop at merge-ready.

### Local delivery evidence and PR gates

The assembled source is `83523335d43e6f6e98ac1ddd05fb47a0531ddc83`.
[Runnable demo, short recording and restart instructions](../reports/evidence/connected-savings-goals/README.md)
retain the registered synthetic scene and its exact source provenance.
[API proof](../reports/evidence/connected-savings-goals/goal-api-proof.json)
independently checks current contribution corrections, shared pool shortages,
manual resolution, archived reservations, recurrence/fulfillment, separate
currencies, unknown backing, stale commands and owner isolation.
[Read-only SQL](../reports/evidence/connected-savings-goals/goal-database-proof.json)
confirms two retained goals, four canonical activities, two claims and one
receipt for the retried create. Unrelated native test fixtures remain preserved.

Four native cases passed with zero failures/skips: the complete manual journey;
response-lost goal creation; response-lost actual transfer; retained Home/Search,
reopen and Spanish. [Native evidence](../reports/evidence/connected-savings-goals/native-proof.json)
records their exact results, direct API restoration and the financial-only
62-second recording. 310 assembled financial/API/OpenAPI/Postgres tests passed
with zero skips. Fourteen independent tool/launcher checks and nineteen inherited
fault-helper checks passed. The unchanged Swift package retains 55 passed tests
and four inherited opt-in live-auth skips; real native auth passed separately.

The retained goal **Savings goal a 4fab425f** shows actual 400 of 1,000, planned 100
separately, conditional projected 500 and 600 remaining. Goal B claims 10 from the
same account's 410 backing. Native **Emergency 82C9D** retains allocation 600,
transfer 200, original correction 150, resulting 750, release/relink, edit to 2,500
and archive/restore. A temporary correction of the existing reverse transfer
made shared backing 390 against 410 claims: native support became unavailable,
**Needs review** and shared shortfall 20 were visible. Restoring that correction
restored 400/10 support. No allocation priority or second money activity was added.

Fresh reviewer `goals_independent_review` (`gpt-6.1-sol`, fresh context) reviewed
`756340afdd38fba9dffaba179faa13edfaf14501` once. Its confirmed P2 was explicit
`archived:null` persisting an unreadable goal. Fix
`09994ce2a01c594c0be092b207fd20cb5cdd9dad` independently preserves archive state
and date clearing, with Goal/Home/Plan/Search read regressions. The affected fix
review was clean. Final test-only delta
`4689e81ae799be67948fb0e8b54ba91a661fd231` removes an Accounts-only assertion
from goal confirmation and passed its scoped review plus real native acceptance.
[Review record](../reports/evidence/connected-savings-goals/review-proof.json)
retains coverage and limits. Zero confirmed findings remain. No exhausted Codex
review or new reviewer swarm is required.

Integration re-fetch remained `6a9d0338d2b2e7106877e0e5d1f9f5aaa70d67ec`.
There is no intervening semantic overlap or reconciliation merge. The assembled
worker already contains current integration; merged-tree modularity and lint
pass. Source acceptance remains valid when only this manifest/evidence changes;
the terminal PR audit must record the published exact head, final CI and zero
unresolved threads after review completion.

**Concrete limitations:** personal cash/checking/savings backing and whole
same-currency transfer attribution; no contribution splitting, conversion,
investment valuation or household permissions. Direct income can be explicitly
allocated as existing savings. Original source/destination/currency changes need
review, never silent retargeting. Linked fulfillment stays fulfilled on attribution
release. The inherited full-owner snapshot and surviving navigation anchors
remain the scale/continuity limits. These are recorded contract boundaries, not
new deferrals of assigned work.

**Remaining visual polish:** an Xcode transient invalid-frame diagnostic appeared
in the full native run without a visible defect in the inspected financial frames.
Retain it for the existing visual-polish work; there is no demonstrated money or
navigation failure. The unfinished Cuadrao identity and broader native polish
retain their existing owners; this lane did not rebrand or redesign navigation.
Physical-iPhone internet proof, debt-plan lifecycles and all other MVEE work
remain tracked below. The authorized merge and bounded documentation landing
are recorded above; no deployment or next slice occurs.

## PR #753 integration landing

The founder authorized the owner to merge #753 after rechecking its head and
integration, then complete the bounded landing workflow. No next slice,
deployment, hosted configuration change, signing or phone-environment action
is authorized.

- [PR #753](https://github.com/lagarcess/argus/pull/753) squash-merged at
  `2026-09-30T03:53:28Z` as `ff1d9795af50ad1566d59e7e986e2cc31be2ca82`, from
  verified head `55d211636bc187cda2fe88fba152c5724a95907c` onto unchanged
  integration `9f51912198c2c77e239f670a2b3f78da2942afed`. Approved-head and
  merge trees are identical; no reconciliation or semantic overlap arose.
- Applicable PR/push CI and smoke were green, independent review was clean
  through `ced256196c04eae6cfcd18f456f3dc00017315c7`, and zero unresolved
  findings remained. The [terminal audit](https://github.com/lagarcess/argus/pull/753#issuecomment-5903364607)
  records exact-head simulator acceptance and retained API, recovery, visual and
  review evidence. No application behavior changed during landing.
- The canonical integration checkout fast-forwarded cleanly to the merge.
  Exact post-merge [CI](https://github.com/lagarcess/argus/actions/runs/36666427091),
  [smoke](https://github.com/lagarcess/argus/actions/runs/36666427084), landing
  housekeeping and final local/remote parity are recorded in the merged PR's
  landing comment after terminal verification.
- No linked closing issues require reconciliation. There is one additive
  owner-scoped budget migration; real local Postgres and the authorized automatic
  PR preview verified it. No new production environment variable or template
  change is needed. The inherited UI-test query input remains test-only.
  Financial exposure remains default-off; landing applies no hosted migration.
- The [budget demo, recording and restart guide](../reports/evidence/connected-budgets/README.md)
  remain runnable from the existing delivery checkout, direct API 59000 and
  loopback mirror 59013. Records, journals, installed simulator and all earlier
  demos remain preserved. The separate phone-testing environment, including
  ports 58700–58749, is untouched.
- This completes the assigned personal-budget journey locally. Physical-iPhone
  internet proof, other Plan lifecycles and remaining MVEE coverage remain with
  their existing owners; no deployment, main promotion or next slice occurred.

## Connected personal spending budgets lane

**Founder authorization, September 29, 2026:** deliver personal spending budgets
through implementation, real local API/Postgres and iPhone simulator acceptance,
review fixes and a merge-ready PR. Commits, publication and existing automatic PR
previews are authorized. Merge and deployment require separate approval. No
hosted changes, production data, paid providers, signing or phone installation.
Household, goals, debt plans, imports, voice, runtime redesign, web, billing and
analytics are excluded. Those MVEE outcomes remain in the coverage map.

**Integration base:** freshly fetched
`9f51912198c2c77e239f670a2b3f78da2942afed`, including #751 and #752.
**Delivery branch:** `codex/connected-budgets`.
**Delivery checkout:**
`/Users/garces/.codex/worktrees/connected-budgets/private-alpha-next`.
**Isolation:** API 59000, Supabase 59001, Postgres 59002, synthetic CAPTCHA
59005; dedicated iPhone 17e simulator
`CC81C737-2F0A-48EA-961C-D9ECFFACA219`, named `Argus Connected Budgets`.
The optional fault proxy and mirror use 59012 and 59013. All earlier demos,
synthetic records, checkouts and services remain intact. Ports 58700-58749 and
the separate physical-phone environment are forbidden. Global simulator-tool
settings are shared and must not change.

### Budget contract and policy gate

The [MVEE Plan rules][mvee-plan] own the journey. Expenses minus received refunds
are actual spending; transfers and card payments are zero spending. A budget
limit never creates a forecast cash movement. Actual amounts remain full recorded
transaction amounts; account-share position attribution is a different result.
Negative net spending is valid. Corrections re-evaluate current activity, while a
refund never reopens a fulfilled bill. Existing Recording owns refund category,
link validity, caps and currency rules. No editable spending total is introduced.

The locked prototype demonstrates a calendar-month category/currency budget,
no rollover, contributing-entry navigation, create/edit/confirmed removal and
prevention of duplicate buckets. Its `JOURNEY-EXPANSION.md` explicitly leaves
production period/time-zone, account coverage, uncategorized and retention
contracts open. These are not approved product deferrals.

**Founder-approved policy, September 29, 2026.** The founder approved the
original question and resumed this existing lane through merge readiness. Budgets
use a calendar month in the saved Plan reporting zone, one currency, explicitly
selected accounts and categories, an explicit uncategorized option, and no rollover.
Linked refunds reduce matching spending in the month received using the current
original purchase's account/category even when received in a different account.
Unlinked refunds use their recorded account/category. The saved zone and resolved
interval remain visible. Changing that shared zone re-evaluates month boundaries
without changing recorded timestamps. The relevant existing API and data contracts
record this policy before implementation. Routine engineering choices belong to
the delivery owner; merge and deployment still require separate approvals.

Removal reuses Plan's reversible archive/restore command pattern, retaining
the definition ID, activity and receipts. The delivery owner selects this existing reversible lifecycle without introducing
a permanent-deletion or retention promise. Exact duplicate active scopes
need one storage guard as well as domain validation; restoration must report a
conflict instead of silently replacing an existing definition.

**Named data shapes:** `BudgetDefinition` stores stable ID, owner, version,
name, limit in integer minor units, currency, explicit account/category scope,
month and lifecycle. `BudgetProgress` derives the visible interval, purchases,
refunds, net spent, remaining, over-budget amount and contributing logical
activity IDs from current canonical records. None of those totals is persisted.
Budget definitions belong to Planning; actual spending rules belong to Recording.

| Architecture candidate | Decision and reason |
| --- | --- |
| Extend the existing Plan snapshot | Selected. Definitions, accounts, activity, Home and Plan share the existing repeatable-read transaction and command receipts. One Recording-owned spending reducer feeds Home and budget progress. |
| Add budget-specific indexed activity queries | Not selected for this implementation. No measured scale requirement justifies a second current-activity query and consistency boundary. The existing full-owner snapshot limitation remains explicit. |

Budget create/edit/lifecycle commands extend the existing scoped idempotency and
version-check owner. One additive owner-scoped definition table has registered
owner read isolation and service-only writes. Detail totals and contributing rows
come from the same matched collection. Existing financial activity detail and
correction screens retain money-write ownership. Search receives a typed budget
hit and live budget destination, using its existing origin/back and refresh rules.
API and data contracts change in the same implementation PR.

### Budget ownership and throughput

- **Blocking first steps.** Recover canon and locked design, record the approved
  financial policy, then commit the bounded API/data contract before code.
- **Independent workstreams.** Backend/native scouts and architecture synthesis
  are read-only. The captain prepares isolated services, simulator and acceptance.
- **Shared mutable state.** One implementation writer owns budget backend,
  native connections and tests in an exclusive branch/checkout. The captain owns
  the separate delivery/demo checkout and this manifest. No concurrent writer or
  suite runs in the implementation checkout.
- **Smallest safe decomposition.** One coherent owner keeps budget inclusion,
  summaries, detail and Search consistent. The captain verifies the assembled
  result after handoff. One fresh independent reviewer replaces unavailable
  Codex review capacity; subsequent review covers affected fixes only.

`budget_financial_scout`, `budget_native_scout` and `budget_architecture_judge`
completed read-only reports at the integration base and relinquished ownership.
The exclusive implementation checkout is
`/Users/garces/.codex/worktrees/connected-budgets-core/private-alpha-next` on
`codex/connected-budgets-implementation`. The policy gate is resolved. `budgets_implementation` owns the existing
implementation branch and commits the approved contracts before code. A bounded acceptance-setup writer prepared
canonical synthetic financial records and the reusable HTTP fixture script
without choosing budget behavior. `budget_acceptance_setup` completed that
bounded task as `4a28bfa0d`; the captain integrated it as `95d54dc7f`, verified
the real API/database and native reopening, then stopped the writer. The captain owns
scope, financial contracts, integration, acceptance, publication and readiness.
All agents have bounded outputs and are stopped after their handoffs.

### Budget acceptance and execution checklist

| User outcome | Inherited capability | Connected work | Observable acceptance |
| --- | --- | --- | --- |
| Create, inspect and edit a scoped monthly limit | Plan tabs, account/category catalog and versioned writes | Durable definition, visible scope/interval and canonical progress | Existing eligible expense 120 gives spent 120 and remaining 30 for a limit of 150; definition writes leave balances unchanged. |
| Spend, correct and refund once | Canonical recording/corrections/refunds | Shared spending reduction in Plan, Home and detail | Add 80 gives spent 200/over 50; correct it to 60 gives 180/over 30; refund 25 gives 155/over 5. Independently specified expectations, not reducer-generated values. |
| Exclude other activity and preserve cash truth | Transfer/payment, currency and forecast contracts | Scope and interval filtering | Transfers, card payments and other currencies/accounts/categories add zero; card purchases count; limit creates no forecast movement; unknown balances remain unknown. |
| Inspect contributors and return | Existing activity detail/correction and Search origin | Budget-to-activity/back and budget Search hit | Correct a contributing entry through its real screen; return to refreshed progress, same budget and preserved list/query/scroll context. |
| Reopen and recover writes | Owner-scoped write journal and receipts | Budget commands and persisted navigation | Relaunch retains definitions/current progress; interrupted committed responses replay once; stale versions fail without mutation; owner B cannot read or write owner A's budget. |
| Understand the same result in both languages | Native design, currency formatting and localization | Budget copy/controls and error states | English and Spanish screenshots and a short connected recording; month/zone boundaries, received-month negative refund and over-budget presentation verified. |

The bespoke delivery workflow follows poteto-mode Feature and figure-it-out.
These steps live here instead of a competing task board.

- [x] Read the poteto-mode principles and frame the completion predicate.
- [x] `how` over the affected subsystem.
- [x] `architect` for parallel design exploration.
- [x] Write the throughput checkpoint as four todo items.
- [x] Prepare reusable canonical-activity acceptance fixtures independently.
- [x] Resolve the financial policy gate and bind `budgets_implementation` as the
  sole contract, backend, native and test writer in its existing exclusive checkout.
- [x] Delegate code-writing to `budgets_implementation` in its exclusive worktree.
- [x] Verify on the matching surface with real API/Postgres and simulator.
  The final recorded rerun revalidates the contributor amount layout fix.
- [x] Sequence verified commits. Skip rebasing published/evidenced branches;
  repository one-way integration merges override Feature's rebase step.
- [x] Design follows the locked reference. No disputed contract requires another
  architecture round; the demonstrated contributor clipping received a focused fix.
- [x] Publish [PR #753](https://github.com/lagarcess/argus/pull/753). Full independent
  review and affected fixes are clean; terminal CI belongs to its exact-head audit.
- [x] Re-fetch integration, audit semantic overlap, reconcile one-way if needed,
  rerun affected checks and modularity budgets, then report merge readiness.

| Decision checkpoint | Evidence | State |
| --- | --- | --- |
| Preserve integration and existing demos | Fresh integration `9f51912198c2c77e239f670a2b3f78da2942afed`; prior demo guides below | New 590xx allocation and dedicated simulator created; no prior environment changed. |
| Keep one financial owner | Existing Recording/Planning contracts and the three bounded scout reports | Snapshot architecture selected; original policy approved by the founder. Contract commit `b60e416d3` precedes implementation. |
| Resume preserved local acceptance | Existing 590xx allocation and the [restart guide](../reports/evidence/connected-budgets/README.md) | Restored without reset or seed. Additive budget migration `278d94a8b` applied only to DB59002; all 15 baseline API readbacks still pass. The captain owns independent API acceptance; the sole writer owns backend/native/tests. |
| Continue independent acceptance preparation | [Fixture API/database proof](../reports/evidence/connected-budgets/fixture-api-proof.json) and [retained Home](../reports/evidence/connected-budgets/pre-implementation-home.png) | Five accounts/eight canonical activities remain after two setup runs; 15 real API readbacks and native Home reopening pass. One unknown balance remains unknown; DOP spending 140 and USD spending 50 stay separate. No budget progress is claimed. |
| Verify inherited connected access early | Isolated API `/health` returns healthy; local Postgres seeded with two synthetic users | Inherited registered sign-in, relaunch, sign-out and signed-out relaunch passed on the dedicated simulator against real local Auth/API/Postgres. Result `ui-20260930T001256Z.xcresult` is ignored local diagnostics. The inherited recording, Plan and Search baseline also passed 203 tests with zero skips against this lane's disposable Postgres. Budget implementation followed this inherited baseline; it is not budget acceptance. |

Completion requires the full assigned journey, durable visual/interaction evidence,
runnable restart instructions, green applicable CI, clean independent scoped review
and zero unresolved findings. Simulator verification is local delivery only;
physical-phone internet delivery remains pending under its separate owner.
The [budget environment restart guide](../reports/evidence/connected-budgets/README.md)
preserves the clickable mirror and synthetic records. The lane-owned local stack
is running with retained records. Backend and native implementation are integrated;
236 focused money/Plan/Search/budget checks pass against DB59002 with zero skips.
The full [independent review](../reports/evidence/connected-budgets/review-proof.json)
covered `538626c583c59aa5baa6c0fafb24aa95b779e893`; confirmed findings were fixed
at their shared causes and subsequent review covered affected deltas only. The
source review is clean through `ced256196c04eae6cfcd18f456f3dc00017315c7`.
Archive tolerates changed account eligibility while restoration validates scope;
contributor restoration waits for loaded rows. Native detail controls retain their
identifiers, contributor amounts retain all digits, and test locators address the
visible destination. The founder-approved fresh independent reviewer substitutes
for unavailable Codex capacity; no Codex-clean claim or paid review is made.

The complete native connected journey passes, including spending/correction/refund,
contributor position, budget edit/archive/restore, live Search/back, reopen and
Spanish presentation. The committed-response-loss test also passes: relaunch and
retry recover one canonical budget from the saved command. Durable images, the
short recording and [native proof](../reports/evidence/connected-budgets/native-proof.json)
record the source and scope. The recorded run revalidates the last amount
layout fix and financial lifecycle. Its preserved-query test setup was corrected;
the affected Home/Search/reopen/Spanish test then passed at `ced256196`. The ordinary demo uses direct API59000 after proxy acceptance.
[PR #753](https://github.com/lagarcess/argus/pull/753) retains publication,
applicable CI and the terminal exact-head merge-readiness audit. The first CI
attempt identified a stale generated OpenAPI artifact; regenerating it from the
canonical API passed all 23 compatibility checks. A merge-ready verdict requires
green applicable checks and zero unresolved findings at the published head.

Original base and freshly fetched integration both remain
`9f51912198c2c77e239f670a2b3f78da2942afed`; no reconciliation merge or semantic
overlap is required. The would-be merged tree passes modularity budgets. The PR
terminal audit records final fetch, exact head, retained evidence and CI state.
Personal budgets are locally assembled; physical-phone internet delivery remains
pending. The inherited full-owner snapshot is still the scaling limit. Other
Plan/MVEE outcomes remain in the coverage map; no additional slice starts here.

The [real API/database budget proof](../reports/evidence/connected-budgets/budget-api-proof.json)
records independently specified 120 → 200 → 180 → 155 spending, a limit edit to
160, four canonical contributors, scope/currency isolation, owner rejection and
accepted-response loss followed by one replay. Read-only SQL counts confirmed
one definition/activity per command. This proves backend assembly, not native
interaction or physical-phone delivery.

## PR #751 integration landing

The founder authorized merging approved head
`f753d5111876457c98be9ffe0235123dbf107eb9`, completing integration verification
and the necessary bounded landing-documentation PR. No next slice, deployment,
hosted configuration change or physical-testing environment change is authorized.

- [PR #751](https://github.com/lagarcess/argus/pull/751) squash-merged at
  `2026-09-29T22:46:19Z` as `5c143e642249872cd1d807a92dc4dd367c698671` onto
  unchanged integration `22f9c8cda8a65c74985e367d8cef68e55515e16b`.
  Approved-head and merge trees are identical. No reconciliation or semantic
  overlap arose; accepted native/API/visual evidence remains valid.
- Applicable PR CI and smoke are green; the independent affected-delta review is
  clean through `c775b0cdd1e05f4088fd9eb5d0ccf798d50882a4`, with only reviewed
  provenance documentation/media afterward. Zero unresolved threads remained.
  The [terminal audit](https://github.com/lagarcess/argus/pull/751#issuecomment-5900394900)
  records exact-head acceptance and review provenance.
- The canonical integration checkout fast-forwarded cleanly to the merge, with
  zero ahead/behind and passing modularity budgets. Exact post-merge CI, final
  landing-documentation PR and local/remote parity are recorded in the merged
  PR's final landing comment after those checks reach terminal state.
- No linked issues require closure. The configuration audit found no production
  environment variable, migration or hosted activation requirement. The added
  `ARGUS_TEST_SEARCH_QUERY` is an opt-in UI-test input; the existing local
  fault-proxy input remains test-only. Financial exposure remains default-off.
- The [Search demo, recording and restart guide](../reports/evidence/connected-search/README.md)
  remain usable from their existing checkout, API 58800 and loopback mirror
  58913. All older demos and the separate phone-testing checkout, device,
  signing, services and ports 58700–58749 remain untouched.
- This closes the assigned local Search journey, not physical-iPhone internet
  delivery or the whole MVEE. Remaining retrieval domains and the documented
  full-owner snapshot scale limit remain tracked below. No new slice starts.

## Connected Search on iPhone lane

**Founder authorization, September 29, 2026:** implement connected Search over
existing accounts, transactions and Plan expectations through a runnable local
simulator demonstration and a merge-ready PR. Local tests, commits, pushes,
publication and existing automatic Supabase PR previews are authorized. No merge,
deployment, hosted configuration change or paid-provider call. Documents,
household, web and chat-runtime work are excluded. Other MVEE retrieval types
remain in the complete coverage map; this batch does not claim to finish D10.

**Integration base:** freshly fetched
`22f9c8cda8a65c74985e367d8cef68e55515e16b`, including #749 and #750.
**Delivery branch:** `codex/connected-search`.
**Checkout:** `/Users/garces/.codex/worktrees/connected-search/private-alpha-next`.

**Goal and completion predicate:** search owned accounts, transactions and Plan
expectations; open each actual domain detail screen; inspect or edit using its
existing controls; return to the same query, filters, loaded results and scroll
position with edits reflected. Relaunch preserves the appropriate owner-scoped
search origin and reloads current records. Empty, loading, retryable failure and
unavailable/deleted destinations are explicit in English and Spanish. Completion
requires real API/Postgres and native acceptance, a short recording, restart
instructions, green applicable CI and one clean independent fresh-context review
(or an explicit pending verdict if no reviewer is available).

**Isolation:** Search owns local allocation `58800` (API), `58801` (Supabase),
`58802` (Postgres), `58805` (CAPTCHA bridge), `58913` (loopback simulator mirror)
and dedicated simulator
`01CBA853-5183-41AF-B1B8-024EF6DB8FFB` (`Argus Connected Search`). The physical-phone
owner's checkout, device, signing, certificates, services and ports 58700–58749
are untouched. Existing 584xx, 585xx and 586xx demonstrations remain intact.
Do not change global simulator-tool defaults shared with another agent.

### Search ownership and throughput

- **Blocking first steps.** Recover current source, locked Search design and
  financial/detail contracts. Record the bounded contract before implementation.
- **Independent workstreams.** Read-only backend and native scouts inspect
  distinct owners. The captain prepares the isolated local stack and simulator.
- **Shared mutable state.** One implementation writer owns the Search backend,
  native navigation and tests in the exclusive `connected-search-core` checkout
  on `codex/connected-search-implementation`. The captain owns the separate
  delivery/demo checkout and does not edit or run suites in the writer checkout. Detail editing keeps its existing domain owner.
- **Smallest safe decomposition.** One coherent implementation owner avoids
  dividing search identity, pagination and return-state behavior across agents.
  The captain takes over assembled verification after handoff. One independent
  reviewer inspects the finished diff, then affected fixes only.

The captain owns this manifest, contract decisions, integration, native acceptance,
recording, publication and readiness. `search_backend_scout` and
`search_native_scout` are read-only and finish after their bounded reports.
The implementation owner receives a consolidated scope and reports its changed
files, exact commit and focused verification before relinquishing the checkout.
No design/reviewer swarm or competing execution board is needed for this locked
surface. The existing account, activity and Plan services remain the only money
and persistence owners.

### Search acceptance

| User outcome | Existing capability | Connected work | Proof |
| --- | --- | --- | --- |
| Find existing financial records | Canonical account/activity/expectation storage; current text-search patterns | Owner-scoped typed search, bounded pages and type filters | Real Postgres and HTTP searches, corrections/current revisions, accents, literal query characters, pagination and second-owner isolation |
| Inspect and edit a result | Native account details, activity detail/correction and Plan expectation editor | Typed destination opens the existing screen with live authorization/read | Native search-to-detail/edit/back for all three types; balance rules remain domain-owned |
| Resume the same search | Native session lifetime and app navigation | Query/filter/result/scroll origin, current-request guards, refresh after detail edits | Native deep-scroll return, changed-match removal, pagination, relaunch and owner switch |
| Recover without losing context | Existing error/empty and localization controls | Loading, empty, retry and unavailable destination states | Local API failure/retry and missing-record cases; English/dark and Spanish/light recordings |

### Search execution checklist and decisions

- [x] `how` over the affected subsystem. Two bounded code scouts plus captain synthesis.
- [x] `architect` for parallel design exploration. Native and backend scouts compare reuse with domain-specific adapters; retain locked UI and existing detail owners.
- [x] Write the throughput checkpoint as four todo items.
- [x] Delegate code-writing to a subagent using your configured feature model. `search_implementation` owns the complete bounded implementation.
- [x] Verify on the matching surface. Five assembled Search journeys passed against the isolated real API/Postgres.
- [x] Preserve small, ordered commits. Skip rebasing published/evidenced work under repository policy; use ordered commits and one-way integration merge if needed.
- [x] No design contest arose; `interrogate` was not needed. Locked design and existing editors were retained.
- [x] Run **Opening a PR**. [PR #751](https://github.com/lagarcess/argus/pull/751) targets integration; no merge or deployment performed.

Model the Domain chooses typed financial destinations and one owner-scoped search
origin rather than independent booleans. Separate Before Serializing Shared State
chooses an exclusive writer, isolated stack and simulator. Prove It Works requires
the assembled native journey against real local records, beyond unit tests and
screenshots. The existing manifest is the specification and decision trail;
no additional planning board or housekeeping PR is part of this assignment.

September 29 contract checkpoint: existing `/search` returns conversation dossiers,
so financial retrieval gets a separate `/financial-search` adapter behind the
existing registered financial context. It reads canonical account, current logical
activity and expectation projections. Transfers appear once and corrected text
replaces old text. The client uses typed destinations, an owner-scoped search
origin and one shared presentation owner for existing detail/edit screens.
Category and currency filters narrow results without inventing bilingual domain
aliases or money calculations. The first implementation reuses the existing
owned financial snapshot; response pagination is bounded, but that snapshot
still reads the owner's records. No new search index or embeddings are implied.

September 29 local setup checkpoint: the Search-owned stack is seeded with two
synthetic identities, and native sign-in/relaunch/sign-out passed with Xcode exit
zero on its dedicated simulator. The local read-fault extension passed 19 focused
checks and preserves the inherited write-response-loss behavior. Its optional
proxy is 58812; normal retained builds use direct API 58800. The
[restart guide](../reports/evidence/connected-search/README.md) records commands
that preserve data. These setup checks do not claim connected Search acceptance.

September 29 backend checkpoint at `78e65a026`: 205 focused financial/Search
tests passed against the isolated local Postgres with zero skips. The real
Auth/API proof passed 15 checks covering current corrected activity, one transfer
hit, literal/accent queries, pagination, stale cursors, archived records, unknown
currency balances and cross-owner search/detail denial. Sanitized evidence is
[api-proof.json](../reports/evidence/connected-search/api-proof.json). Native
Search acceptance and independent review are recorded in the later completion checkpoint.

September 29 review checkpoint at `12ade77d98ac74864ad05ca629548be055e89452`: the
fresh-context `search_independent_review` agent returned clean after one full
diff review and affected-fix checks. Its three P2 findings are closed: retained
account navigation/read isolation, obsolete destination-request cancellation and
recovery tied to the acted-on account. Native model verification passes 20 tests.
The [review record](../reports/evidence/connected-search/independent-review.md)
records exact commits and limits. Assembled simulator gates and CI are still
in progress; this is not a merge-ready claim.

September 29 local delivery checkpoint: the complete assigned Search journey
passes in the isolated simulator against real local Auth/API/Postgres. Accounts,
current activity and Plan expectations open their existing editors; edits refresh
Search. Query, category, currency, loaded pages and exact position survive Back
and two successive relaunches. Separate Accounts/Search details and owner switching
pass. Delayed loading, 503/retry and unavailable detail states pass. The final
three-editor run at `c775b0cdd1e05f4088fd9eb5d0ccf798d50882a4` also verifies
English/dark and Spanish/light reopening. All confirmed independent findings are
closed; the final affected-delta review at that SHA is clean.

The [demo, recording, restart instructions and evidence table](../reports/evidence/connected-search/README.md)
are durable in this PR. The 49-second excerpt shows activity correction, refreshed
Search, Plan editing and reopening; the same successful test separately proves
account rename/removal from old matches. Backend evidence includes 205 focused
financial tests, 15 real HTTP checks, nine shared PostgreSQL CI scenarios,
23 generated-API compatibility checks and 22 native model tests. A missing generated
OpenAPI update found by CI was corrected. The PR's terminal readiness comment owns
its exact published head, final CI result and evidence revalidation.

Fresh integration remains `22f9c8cda8a65c74985e367d8cef68e55515e16b`, identical
to the original base: no reconciliation merge or semantic overlap arose. Final
modularity checks run on this already-reconciled tree. The local demo remains on
58800 with preserved data; all old demos and the 58700–58749 environment remain
untouched. Workers/reviewer have finished and relinquished their surfaces.

Remaining scope is explicit: physical-phone internet delivery is not proved by
this lane; Search still uses the canonical full-owner snapshot behind bounded
response pages. Other MVEE Search types and conversation continuity remain in
D09/D10 below. No new product deferral, hosted change or signing authority is
implied by this locally verified result.

Stop only for a concrete product conflict, inaccessible required tooling, or an
action beyond the grant. Routine implementation choices and local fixes proceed.

## Connected Plan and Home lane

**Original implementation authorization, September 29, 2026:** deliver commitments, recurrence,
fulfillment and the connected cash forecast as one local iPhone journey. Own
implementation, local builds/tests, commits, pushes and one reviewable PR with
existing automatic PR previews. No merge, deployment, signing changes, hosted
configuration, production data or paid-provider calls. Preserve both existing
584xx and 585xx demonstrations. Search, household, imports, web, voice and the
chat-runtime redesign are untouched. Budgets, savings goals and debt-plan
lifecycles remain assigned work in the complete MVEE map, outside this batch.

**Integration base:** freshly fetched
`21309f0832d438fd18651f47209e8c789a8fcc53`, containing #747 as `6eb057e9a`
and #748 as `21309f083`. **Delivery branch:** `codex/connected-plan-home`.

**Goal:** enter expected income and bills, including one-time and recurring
items; inspect the same dated, currency-separated forecast in Plan and Home;
record or link one canonical actual activity; inspect and correct that activity
or edit the expectation; reopen with the same durable state. A bill due before
later income must show the intervening shortfall. Expected money never changes
actual balances. The [MVEE connected-plan rules](argus-minimum-viable-ecosystem-experience.md#connected-plan-status)
and [locked design](../reports/mobile-design-lock-2026-09-28.md) own acceptance.

### Ownership and throughput

The captain owns shared contract decisions, this manifest, the delivery branch,
local simulator/backend integration, evidence, PR publication and readiness.
`plan_core` owns expected-record storage, recurrence, fulfillment/link rules,
forecast, backend routes, migrations, backend tests and canonical API/data docs.
A single native writer owns Swift types, transport, Plan/Home presentation,
localization and native model tests on a separate branch. The captain owns the
assembled UI tests and recording. Writers must not edit each other's files.

Start backend contract grounding alongside native design inspection and isolated
local verification setup. Agree the wire contract before dependent UI wiring.
Prove recurrence and canonical posting with real Postgres, integrate both
implementations, then verify the assembled journey. Keep one final independent
reviewer in a fresh context; review only affected fixes after that pass. Do not
request Codex review for this batch. If no independent reviewer is available,
publish with review pending instead of inventing a verdict.

The main risks are duplicate fulfillment, stale links after corrections, calendar
boundaries and inconsistent actual/forecast snapshots. Reuse the landed activity
service, owner locking, exact money types, revision checks, confirmation preview,
receipts, account observation coverage and native uncertain-write recovery.
No second balance or activity ledger is permitted.

### Acceptance and checkpoints

| User outcome | Inherited capability | Implementation in #749 | Responsible owner | Assembled proof |
| --- | --- | --- | --- | --- |
| Enter expected income and bills | Registered identity, account catalog, exact money input, native forms | Durable editable expectations; one-time, weekly, every two weeks, monthly and twice-monthly schedules | Core rules; native presentation; captain integration | Real API/DB and native create/edit/reopen; month-end, leap-date and zone tests |
| Understand cash before next income | Canonical account balances, unknown markers and locked Plan design | One dated forecast in Plan/Home, explicit accounts/currency, shortfall and partial-share rounding | Core projection; shared native Plan model | DOP 100 minus bill 200 before income 500 shows an interim shortfall; USD unknown stays unknown |
| Record receipt/payment or link existing activity | Landed preview/confirm and balance-check coverage | Atomic occurrence-to-activity link and matching review; no second ledger | Existing recording owner and Plan link transaction | Payment/correction plus existing-income link; duplicate/concurrent retries and rollback tests |
| Correct and continue | Append-only activity corrections and stable identity | Links re-evaluate actual revisions; expectation edits preserve fulfilled identity | Shared core link owner and native refresh | Correction 200 to 180 changes actual cash; expected 500 to 600 does not add a fulfilled receipt again; refund does not reopen bill |
| Reopen the assembled app | Keychain and owner-scoped pending-command recovery | Shared refresh, durable links and existing retry journal | Captain acceptance, native/core fixes as needed | Simulator relaunch and loaded second identity; retained demonstration, recording and API readback |

### Execution checklist and decision trail

- [x] Read the Principles section of poteto-mode.
- [x] Phase A: Frame. Recover approved rules, current integration, locked design and the bounded verification predicate.
- [x] Phase B: Design the workflow. Inspect inherited owners, settle the shared contract and assign isolated writers.
- [x] Phase C: Run the loop. Implement and verify bounded backend/native units, then integrate and exercise the whole journey.
- [x] Phase D: Keep the audit trail. Record technical decisions, ownership, evidence and limitations here as work progresses.
- [x] Phase E: Verify and hand back. Preserve a runnable simulator, short recording and restart recipe; publish one PR with applicable CI and honest independent review status.

This section is the lane specification and decision trail. It replaces separate
planning/checklist documents for this assignment. Poteto design panels and
reviewer swarms are omitted under the founder's explicit proportionality rule.
The backend owner's code-grounded proposal and captain's independent inspection
settle the contract. Final independent review is a separate fresh-context pass.

September 29 grounding: Plan is a sample destination today. Home already consumes
canonical financial position and monthly recorded activity. Keep those owners;
add expected records and derived occurrences without copying actual balances.
The new delivery checkout is isolated from the retained demos. No other MVEE
batch is activated and no new product deferral is introduced.

September 29 contract checkpoint: the [connected Plan API contract](../API_CONTRACT.md#connected-personal-plan-and-home-september-29-2026)
uses derived dated occurrences and one durable link to an existing canonical
activity. Fulfillment composes with the recording transaction under the same
owner lock. Activity amount/date corrections retain fulfillment; a changed
account or currency requires link review. Refunds never reopen a bill.
Schedule/account cutovers preserve linked occurrences; monthly dates clamp
without drifting, and duplicate month-end dates collapse to one occurrence.
Selected cash accounts and the saved IANA time zone are explicit. Forecasts
separate currencies, retain unknown balances, and order bills before income
on the same date as a conservative date-only assumption. The native app extends
its existing uncertain-command journal instead of adding another recovery owner.

The connected demonstration owns local allocation `58600` (API), `58601`
(Supabase), `58602` (Postgres), `58605` (CAPTCHA bridge), and simulator
`4E22655F-72DC-468F-AEBB-97FBDC58B514` (`Argus Connected Plan`). Synthetic
credentials remain ignored. The inherited app builds and the existing
sign-in/relaunch/sign-out UI acceptance passed with a clean Xcode exit on this
allocation. Existing `584xx` and `585xx` demos are intact.

### September 29 delivery evidence

[PR #749](https://github.com/lagarcess/argus/pull/749) contains the connected
backend, additive migration, native implementation and the
[runnable demonstration, recording and restart guide](../reports/evidence/connected-plan-home/README.md).
Plan and recorded Home derive from one repeatable-read snapshot. All actual
posting remains owned by the landed recording service. Included account shares
use that owner's minor-unit rounding; no second balance ledger exists.

- The assembled native journey passed: DOP 100 cash, a 200 bill before later
  expected income of 500, payment, correction to 180, an existing receipt of
  450 linked without duplication, expectation edit, and reopen at DOP 370.
  Weekly transport remains expected and does not change actual cash.
- Unknown USD stays unknown in Plan and Accounts. English/dark and Spanish/light
  presentation passed. Archived or retyped selected accounts remain removable.
- Real local HTTP acceptance: 16 checks passed after the clock fix, including
  refunds retaining fulfillment, changed-account link review and owner isolation.
  Financial/API/Postgres/OpenAPI matrix: 209 passed, zero skipped. Swift package:
  50 passed, four separately gated live tests skipped; native models: 12 passed.
- Interrupted-payment/relaunch acceptance passed with a clean Xcode exit:
  owner B saw neither A's records nor pending command; A retried the original
  committed payment once, with one activity and DOP 80 remaining. The
  [native acceptance record](../reports/evidence/connected-plan-home/native-acceptance.json)
  records each case and source checkpoint. Final-head CI and the terminal
  publication verdict are recorded in the PR audit.
- The independent fresh-context reviewer `plan_independent_review` reviewed
  `21309f08..196ccea2` once, found three confirmed issues, then returned clean on
  affected fixes at `ab1e3e63`. The UUID edit, proportional forecast and selected
  account fixes are recorded in the [review evidence](../reports/evidence/connected-plan-home/review-delta.md).
  The clock delta is clean at `36abc0bc`; keyboard focus is clean at `20750992`.
  This is the founder-authorized substitute, not GitHub Codex review.
- Original base and refreshed integration are both
  `21309f0832d438fd18651f47209e8c789a8fcc53`. Integration has not advanced;
  no reconciliation merge or semantic overlap invalidates retained evidence.
  Modularity passes on the would-be merged tree. Final publication head
  `a2b6ed2b` reached green applicable CI and local-smoke checks before merge.

**Remaining across the MVEE:** this delivers commitments, recurrence,
fulfillment and the connected forecast locally. Budgets, savings goals and
complete debt-plan lifecycles remain under D06. Physical-iPhone installation,
internet access, deployment and the rest of the coverage map remain incomplete.
No new deferral is introduced. Other MVEE lanes have not been activated.

**Visual follow-through:** preserve the locked quiet native hierarchy, dark/light
support, existing controls and icons. Plan chart points represent dated movements,
not equal time intervals; the readout names date/currency and the included accounts are listed below. Future polish
should tighten long occurrence lists and reduce repeated account/expectation copy
without losing the distinction between planned and actual amounts. This does not
reopen the web remake or authorize a broader redesign.

### PR #749 integration landing

The founder subsequently authorized merging the approved head and a necessary
docs-only landing PR after checks, with deployment and hosted configuration
changes still excluded. [PR #749](https://github.com/lagarcess/argus/pull/749)
squash-merged on September 29, 2026 at 19:52 UTC as
`88d513c0ef2791b4277eb571ce6b1f4f291d3a5c`, from approved head
`a2b6ed2bf849582de19aceedd61a3861d1c768e2` onto unchanged integration
`21309f0832d438fd18651f47209e8c789a8fcc53`.

- Integration had not advanced; no reconciliation merge was necessary. The
  approved-head and merge trees are identical, preserving all local acceptance
  and independent review evidence. No application behavior changed at landing.
- Applicable PR checks were green, the independent review was clean, and zero
  unresolved threads remained. The [terminal audit](https://github.com/lagarcess/argus/pull/749#issuecomment-5897315197)
  records the source checkpoints and review. Exact post-merge CI, the docs-only
  landing PR and final integration parity are recorded in the merged PR landing
  comment after their checks finish.
- There are no linked closing issues. The landing changes only this manifest
  and the integration ledger; it activates no other MVEE work.
- No production configuration was added. Financial exposure remains default-off
  in the existing environment template and Render declaration. The new
  `ARGUS_TEST_FAULT_URL` belongs only to the local recovery test launcher. The
  additive Plan migration is covered by local database and authorized automatic
  PR-preview checks; landing applies no hosted migration or configuration change.
- The 584xx financial loop, 585xx money-recording demo and 586xx connected Plan
  demo are preserved. The [recording and restart guide](../reports/evidence/connected-plan-home/README.md)
  remain the entry point for the runnable Plan simulator. Signing, physical-phone
  installation and internet delivery remain pending; budgets, savings goals and
  debt-plan lifecycles remain in D06. No deployment or main promotion occurred.

## Personal money-recording batch

**Founder authorization, September 29, 2026:** Deliver received income, spending,
transfers between owned accounts, credit-card payments and purchase refunds as
one personal journey, including inspection, corrections and reconciliation with
existing balance checks. Own backend, database and iPhone through a runnable
simulator demonstration and a merge-ready PR. Publication and existing automatic
PR previews are authorized. Merge, deployment, signing, production changes,
paid-provider calls, web, imports, household and chat-runtime work are not.
Do not invent exchange rates or unresolved loan rules. The earlier loop's scoped
stop statements below are historical; this grant activates only the work here.

**Integration base:** freshly fetched
`b4fed10fe5cd325a7cd3e6ac21b87e9fbf5eb819` (#745 plus #746).
**Delivery branch:** `codex/personal-money-recording`; [PR #747](https://github.com/lagarcess/argus/pull/747).
**Goal:** a person uses the native app with the real local API/Postgres to receive
income, spend, move money between owned accounts, pay a card and record a refund;
Accounts and Home agree after inspection, corrections and reopening. Unknown
balances stay unknown, currencies stay separate, linked movements commit once
and together, and earlier activity respects each account's balance-check answers.

### PR #747 integration landing

The founder authorized merge of reviewed head
`5a997df3142dd9ca2d73207f8e4d8822705a646d` after green checks and zero unresolved
findings. It squash-merged on September 29, 2026 at 17:20:38 UTC as
`6eb057e9abe23ecbbfa0228b9ba0e57623d2f696`, onto unchanged integration
`b4fed10fe5cd325a7cd3e6ac21b87e9fbf5eb819`. The merge and approved-head trees are
identical; no reconciliation or intervening semantic overlap invalidates the
accepted financial, recovery, isolation or transfer-label evidence.

The [terminal PR audit](https://github.com/lagarcess/argus/pull/747#issuecomment-5895015807)
records green exact-head CI/smoke and the clean final scoped review. Exact
post-merge CI/smoke and final local/remote parity are recorded in the merged PR's
landing comment. The canonical checkout fast-forwarded cleanly to the merge.

This lands the locally verified personal recording journey, not physical-iPhone
or full MVEE delivery. The [demo and restart guide](../reports/evidence/personal-money-recording/ios/README.md)
and [transfer-label proof](../reports/evidence/personal-money-recording/ios/transfer-label-review/README.md)
remain available; local services, synthetic identities and both demos are
preserved. Existing visual-polish notes below remain open; no further MVEE
implementation is activated by this landing.

No linked issue requires closure. No new production environment variable or
tracked-template change is required: `ARGUS_TEST_RESPONSE_LOSS_PROXY` is an
explicit local UI-test switch, and the existing financial exposure flag stays
default-off. The two additive personal-money migrations are landed source only;
no hosted migration, configuration change, signing, deployment or main promotion
was performed. The original implementation grant above remains historical;
this separate founder merge authorization applies only to #747.

### Delivery ownership and throughput

The captain owns the shared contract decision, this manifest, assembled branch,
independent acceptance, publication and scoped review. One backend writer owns
recording domain/API/storage/migrations and API/data documentation. One native
writer owns Swift features, localized presentation and native tests. Writers use
separate branches; neither duplicates money rules or edits the other's surface.
A bounded design comparison precedes the shared contract. Native presentation
planning and local harness preparation can proceed alongside backend grounding;
wire-dependent implementation consumes the accepted contract. Integration and
simulator ownership are serialized by the captain.

The main risk is atomic paired corrections and purchase/refund limits under
concurrent writes, not account setup. Prove those with real Postgres before
calling the assembled journey complete. Reuse existing auth, preview tokens,
version checks, durable receipts and observation coverage. Preserve the previous
runnable demo and its synthetic database while preparing this slice.

### Acceptance and checkpoints

| User outcome | Inherit | Delivered locally | Owner / real dependency | Observable proof |
| --- | --- | --- | --- | --- |
| Receive income and record spending | Account CRUD, expense preview/confirm, append-only correction/history | Typed income with optional source; connected recording and Home reads | Core and native; canonical activity contract | Native create/inspect/correct/reopen against real local DB; income does not become expense |
| Move money between owned accounts, including cash withdrawal | Signed balances, versioning, coverage | One atomic movement with linked legs and per-account review; same-currency validation | Core owns linked mutation; native consumes preview | Both accounts and Home agree; no spending/income; one-sided failure writes neither leg; duplicate retry writes once |
| Pay a credit card | Liability sign and credit-balance presentation | Payment from owned cash/bank to card, both sides correctable together | Same paired movement owner | Cash and debt change once; purchases remain the spending event; credit in favor stays explicit |
| Record money returned | Stable expense identity and category catalog | Linked partial/multiple refunds, actual destination, absent-purchase path and received-month reporting | Core owns purchase/refund cap and category; native review | Refund is separate from purchase and income; cumulative cap survives concurrent corrections; negative net spending remains visible |
| Reconcile and recover every supported activity | Immutable observations, explicit coverage, idempotency and session recovery | Multi-account coverage, revision consistency and native uncertain-write recovery | Shared core then assembled app | Existing check remains authoritative only for explicitly included activity; reopen, interrupted response and retry preserve one result; another identity sees nothing |
| Click through a complete local demo | Installed prior build, local stack and capture harness | Integrated build, short recording, restart recipe, durable evidence, CI and scoped review | Captain after component integration | Real simulator actions and DB readbacks; exact source provenance; merge-ready PR with zero unresolved findings |

Currency conversion and loan principal/interest allocation are not authorized.
The recorded peso/dollar transfer boundary remains blocked; a foreign-currency
refund uses the actual received amount with an explicitly unlinked purchase.
Existing technical limitations must remain visible and must not be relabeled as
founder-approved MVEE deferrals. The full MVEE coverage below remains the broader
assignment, not a claim that this slice completes the ecosystem.

### Execution checklist and decision trail

- [x] Read the Principles section of poteto-mode.
- [x] Phase A: Frame. Recover approved rules and the freshly fetched base; bind this bounded authorization and verification predicate.
- [x] Phase B: Design the workflow. Trace the inherited owners, compare contract shapes, record one accepted contract and isolated writers.
- [x] Phase C: Run the loop. Implement and verify the core and native journey in bounded units, then integrate on this branch.
- [x] Phase D: Keep the audit trail. Update this section with decisions, named owners, evidence and exact remaining work.
- [x] Phase E: Preserve the runnable simulator, recording and restart instructions. The terminal audit on [PR #747](https://github.com/lagarcess/argus/pull/747) owns exact final-head CI/review and the merge-ready verdict; this documentation does not waive those gates.

Current checkpoint: #747 is landed. All five recording kinds, inspection, corrections, balance-check
coverage and recovery passed assembled simulator acceptance against real local
Auth/API/Postgres. The [recording, retained accounts and restart guide](../reports/evidence/personal-money-recording/ios/README.md)
make the demonstration repeatable. The shared
[API contract](../API_CONTRACT.md#personal-money-activities-authorized-september-29-2026)
and additive storage contract are committed. The isolated 585xx stack and Argus
Personal Money simulator remain running; the earlier 584xx demo is preserved.
Workers have completed their bounded assignments and released the simulator to
the captain. This is local synthetic-user evidence, not physical-phone delivery.

| Named owner | Branch / exclusive surfaces | Next usable result |
| --- | --- | --- |
| `money_core` | `codex/personal-money-core`, recording domain, API, additive migration, backend tests, API/data contracts | Complete through `79032245`; five kinds, paired correction, refund rules, monthly Home, preserved legacy receipts and additive revision integrity. Final scoped core review clean |
| `money_iphone` | `codex/personal-money-iphone`, Swift feature/transport/models, localization and model tests | Complete through `3a6e5873`, integrated as `2e678d3d4`; 47 package cases with four expected environment skips and nine model tests. Scoped native review clean; simulator acceptance also verified the full-row tap fix |
| `money_demo_setup` | `codex/personal-money-acceptance`, connected UI tests, isolated launcher and new evidence; exclusive simulator owner | Complete through `5de47c00`; original seven native cases plus the strengthened isolation case passed, nine original retained accounts checked against canonical reads, recording and restart guide committed; simulator released to captain |
| Captain | `codex/personal-money-recording`, manifest, assembled source, independent proof and PR | Assembled source and independent HTTP proof complete; owns final CI/scoped review and retained local services; no merge |

Design decision, September 29: two code-grounded alternatives and an independent
cross-judge favored extending existing account records and exact-revision coverage
with an atomic activity group. Replacing the ledger or rebuilding coverage foreign
keys adds migration risk without a user benefit. Preserve old expense IDs and retry
receipts. Correcting an account selection retires the old leg with retained history
and applies the new leg in the same operation; do not edit one side independently.
A single owner-scoped activity transaction lock, taken before sorted account locks
by every new and legacy activity writer, serializes refund/correction invariants.
Account-only check/opening/metadata writers retain their existing account lock.
No SQL or native layer becomes a second financial rule owner.

The canonical native contract exposes one operation, all affected account effects,
per-account observation questions and a normalized reviewed request. Confirmation
binds the complete affected versions and exact request; idempotent replay precedes
stale-version rejection. A protected owner-scoped pending command survives native
process death and supports explicit same-key recovery. Monthly Home reporting uses
one explicit reporting zone and period, gross purchases/refunds/net spending and
received income; negative net spending remains visible. Refund categories follow
the linked purchase without rewriting historical provenance. Changing a purchase's
category while refunds remain linked is rejected with explicit correction/unlink
instructions; historical categories are not silently rewritten. Currency conversion
and loan allocation remain outside the assigned operation set.

The captain's local response-loss proxy forwards to loopback only and drops one
successful activity response after the API accepts it. Five proxy checks pass.
Use it for assembled process-restart and same-key recovery proof, not as a substitute
for database atomicity and isolation checks. It does not change application behavior
or hosted configuration.

Backend verification includes 143 owner-run financial checks against the isolated
database, plus the captain's real Auth/API identity check. The HTTP proof covers
all five kinds, paired replay and inspection, wrong-account correction and history,
refund caps, positive card credit, unknown USD investment balance, cross-owner
refusal, durable reopening and refunds reducing received-month spending. The captain reran
[HTTP acceptance](../reports/evidence/personal-money-recording/http-proof.json)
against the assembled local API; its runtime source `062fd2aa8` is identical to
`2e678d3d4` across backend, migrations and the proof script.
The source-timezone and omitted-versus-explicit-null refund correction fixes passed
independent delta review. Reusing grouped activity reads reduced a synthetic
3,000-record projection from 2.598 seconds to 0.009 seconds without another cache.

The native review corrected terminal authentication propagation, rejected-recovery
explanations and retired-leg labels. A final delta review confirmed the Accounts
view observes the recovery state directly. The captain's combined local financial,
real Auth/API/Postgres, launcher and response-loss-proxy matrix passed 163 tests
with no skips. The canonical OpenAPI artifact has been regenerated; its 23
compatibility checks pass. The initial GitHub review at `b18050fcf` returned clean
with zero threads and CI at `2e678d3d4` passed. Final-head CI/review are recorded
in the PR terminal audit rather than duplicated as a moving SHA in this manifest.

[Native verification](../reports/evidence/personal-money-recording/ios/verification.json)
records the original seven selected cases plus a strengthened isolation case: row taps; income/spending/refund corrections;
paired transfer and wrong-account correction; card payment/refund/credit;
per-account reconciliation, currencies, unknowns and Spanish presentation;
committed-response loss with same-key recovery after process restart; and a
read-only Home relaunch; and pending-write isolation across loaded identities. The two fault-opt-in launcher tests also pass. Six long
cases logged terminal passes but Xcode stalled finalizing their result bundles;
they do not claim clean full-run exits. The final read-only run exited 0.
Screenshots and canonical readbacks independently preserve the observations.
The 2:55 recording is an explicitly edited demonstration, not the exhaustive test.

The final scoped GitHub review found the original native isolation assertion could
run before B loaded and had no pending A command. That claim is superseded by
`testPendingMoneyWriteRemainsIsolatedAcrossIdentities` (`3106f2f6`, integrated as
`b8aea0c0f`): a known B-owned account must load before absence assertions; an actual
committed-response-loss A command stays absent from B, survives the switch back,
and recovers once with the same record after reopening. This case passed in
232.846 seconds with a clean test-runner exit. The fix changes tests and evidence
only; no runtime defect was observed. Final CI and latest-delta review remain
owned by the PR terminal audit.

Application/backend source is unchanged after `2e678d3d4`; later commits add
acceptance harness, evidence and documentation. Exact source provenance is retained
in the evidence and revalidated against the final PR head. No physical phone,
founder identity, real production data, signing, deployment or paid providers were
used. Same-currency movements and chronological balance-check limits remain
explicit implementation boundaries. The full MVEE below is not complete.


### Founder acceptance and small clarity follow-up

The founder accepted the demonstrated financial behavior, then requested visible
**From / To** labels and removal of the redundant transfer-account heading before
merge. This follow-up changes only the native form presentation; recording rules,
records, API and migrations retain the accepted behavior. The existing English
and Spanish labels remain the single copy source. The focused simulator check
passed at `7a3bf64f`: English/dark and Spanish/light labels, both account menus,
reviewed transfer effects, existing correction labels and expense/card picker
regression checks. Both new-transfer previews were cancelled without confirmation.
The [clarity evidence](../reports/evidence/personal-money-recording/ios/transfer-label-review/README.md)
and final PR audit own verification. The later founder-authorized merge is recorded above.

Remaining visual polish is tracked here, not silently treated as complete or as a
new MVEE deferral. The native experience owner should review visible role labels
on the other compact selectors (card payment, income source, category and linked
purchase), plus spacing and long-account-name/larger-text presentation against the
locked design. The focused Spanish screenshot also shows the existing
`Transferencia` type chip partially clipped at the horizontal row's right edge;
review selected-chip visibility in that polish work. These are follow-up
presentation checks, not claims of financial defects or permission for a broader
redesign. This requested fix is limited to
transfer clarity; the full MVEE and physical-phone gates below remain unchanged.

Model the Domain shaped the typed activity group. Separate Before Serializing
Shared State shaped the isolated writers. Prove It Works requires both real
Postgres invariants and assembled simulator acceptance; passing component tests
alone will not close this batch. The exact wire and storage amendments live in
API_CONTRACT and DATA_MODEL, owned by the core writer, rather than another board.

## Landed financial-loop batch (historical authorization)

The founder authorized this batch on September 29, 2026 after PR #744 merged.
The restart covers implementation, local verification, simulator builds, device
preparation and coordination for the first financial loop only. The full MVEE
map below remains the recovery map; no other journey is activated by this grant.
Merges, signing/account actions, deployment, hosted mutations and spending still
require specific approval. Local implementation and simulator proof exist; signed
installation, hosted rollout and physical-phone proof remain outstanding.

**GitHub publication authorized:** The founder explicitly approved pushing
`codex/financial-loop-delivery`, opening its review PR, and completing CI and
scoped review, including its existing automatic Supabase preview. Physical-device
signing, installation, Render login and deployment are deferred. Keep the simulator/local-backend
demonstration runnable with retained synthetic data and restart instructions.

**Accepted local deliverable:** The founder made the complete loop
working in the simulator against the real local API/database the acceptance target
for PR #745, with a short recording, restart instructions and honest limitations.
That deliverable passed CI and scoped review, then merged under the later explicit
grant recorded below. Keep its demo runnable. Physical signing, installation and
deployment are deferred; this completion does not activate another MVEE journey.

**Overall delivery goal:** Deliver the loop defined under [full-scope execution and early demonstration](#full-scope-execution-and-early-demonstration)
on the founder's physical iPhone over the internet using the existing user when
those deferred actions are authorized.
Preserve the [locked design](../reports/mobile-design-lock-2026-09-28.md).
Simulator acceptance closes the current local deliverable, not the full MVEE or
physical-phone outcome. Unknown balances, corrections, reconciliation, retry, persistence and
identity isolation follow the linked canonical requirements and technical handoff.

**Base:** freshly fetched `fcbb70cc2899ca6a05c03c49316e9a4e4cbf5333`.
**Captain:** main delivery agent on `codex/financial-loop-delivery`.
**No-touch:** production web/remake, Android implementation, new MVEE pillars,
agentic runtime, billing/growth, hosted records/settings and unapproved providers.

| Responsibility | Exclusive implementation ownership | Checkout | Current action |
| --- | --- | --- | --- |
| Financial core (`loop_core`) | Recording domain, financial routers/repositories, financial migrations/tests, relevant API/data contract sections | `codex/financial-loop-core` in `financial-loop-core` | Source `c2425f2e2` includes reviewed timezone/type-lock corrections; 126 focused checks, including real local Postgres, pass on published delivery source; earlier exact HTTP/Home proof retained |
| iPhone (`loop_iphone`) | Native feature/session/navigation code, native tests and localized copy; excludes project/signing configuration | `codex/financial-loop-iphone` in `financial-loop-iphone`, recovered from preserved iOS checkpoint | Source `bbfb3bff` with archive evidence in `129d2c876`: three original actual API/Postgres journeys plus focused archive/restore pass; six model tests and 39 session tests pass; four environment-gated session tests explicitly skipped |
| Device preparation (`loop_device`) | iOS project/signing/configuration, local release setup, narrow existing-web CAPTCHA adapter and approval evidence; no feature Swift files | `codex/financial-loop-device` in `financial-loop-device` | Checkpoint `ea3370606` independently reviewed clean and assembled as `78ec38464` on delivery branch; signing and hosted approval remain pending |
| Captain and independent acceptance | This manifest, contract synthesis, integration candidate and cross-owner verification | `5a42` | PR #745 landed; [landing result](https://github.com/lagarcess/argus/pull/745#issuecomment-5889046424) owns final integration verification status; retain runnable local demonstration; signing, Render login and deployment deferred |

### PR #745 integration landing

The founder authorized merging only approved head
`944b2cb70ab008aa2ed9385b5d81555bad84f7fd` while its checks remained green.
[PR #745](https://github.com/lagarcess/argus/pull/745) squash-merged on September
29, 2026 at 10:57:30 UTC as `afc3db5ae679a32676fae94ed7c5e9c9ef68b633`, onto
`fcbb70cc2899ca6a05c03c49316e9a4e4cbf5333`. Integration had not advanced; no
reconciliation merge or intervening semantic overlap existed. The merge tree
exactly matches the approved PR tree, preserving accepted evidence.

The [terminal PR audit](https://github.com/lagarcess/argus/pull/745#issuecomment-5888571700)
records green PR/push CI and smoke, the final clean scoped Codex review, zero
unresolved threads, source equivalence, runnable demo and limitations. Post-merge
[integration CI](https://github.com/lagarcess/argus/actions/runs/36558771357) and
[smoke](https://github.com/lagarcess/argus/actions/runs/36558771345) passed at the
exact merge SHA. The [landing comment](https://github.com/lagarcess/argus/pull/745#issuecomment-5889046424)
records final documentation publication and integration parity after #746.

No linked issues require closure. The configuration audit found no new production
environment variable: the existing financial flag stays default-off in
`.env.example`; the CAPTCHA adapter reuses the existing public Turnstile key;
device signing has its checked-in, unpopulated `Device.local.xcconfig.example`;
local XCTest controls come from the private fixture launcher. No ignored env file,
hosted configuration, production data, or deployment was changed. Existing core
and native worktrees remain owned by the runnable local demo and are preserved.

The local simulator deliverable is complete. The physical-iPhone internet outcome
and remaining MVEE coverage below are not completed or activated by this landing.

### PR #745 review checkpoint (pre-merge evidence)

[Review PR #745](https://github.com/lagarcess/argus/pull/745) was reviewed against
`codex/private-alpha-next`. Original reviewed head `b5cfedef998079f3978f9282e60bc287afa7dc25`
passed [CI](https://github.com/lagarcess/argus/actions/runs/36549243112) and
[local smoke](https://github.com/lagarcess/argus/actions/runs/36549243153).
At review time the original and freshly fetched integration base was `fcbb70cc2`;
no reconciliation merge or intervening integration overlap existed.

The first Codex review found three confirmed defects. Each has a thumbs-up and
an evidence-backed reply. All fixes below were published in `6d3f8e066`; this
documentation follow-up changes no product/test source. The linked terminal audit
records final green CI, resolution of all three threads and the clean scoped
review on approved head `944b2cb70`. Those publication/review steps are complete.

| Finding | Published correction and verification | Delivery commit |
| --- | --- | --- |
| Balance timestamps used the opening's timezone regardless of source | Canonical position retains its source revision's IANA zone; Home orders freshness by UTC instant, including repeated DST hours. Memory and real-Postgres regressions cover preview/save/reopen | `71ea905a7` from core `c2425f2e2` |
| Account type remained editable after a check without expenses | Existing type lock includes balance checks/value updates; opening-only behavior preserved | `71ea905a7` |
| Archived accounts remained in the active list | Active list filters archived rows; Manage accounts retains Active/Archived groups and existing Restore. Six model checks and one real-API simulator archive/restore journey passed, with unchanged Home and same record ID | `632ea5f49`, `08254e668`; [visual/behavior evidence](../reports/evidence/financial-loop/ios/archive-review.md) in `abd955f3c` |

The assembled local correction candidate `08254e668` passed 126 focused backend
checks including real Postgres, full Ruff and modularity checks. The original
financial-loop evidence remains historical at its recorded sources; the changed
timezone/type-lock and account-list surfaces have the focused replacement proof
above. At published head `6d3f8e066`, all 126 backend checks and all six native model
tests passed again. Modularity passed against the current integration descendant;
product/test source is unchanged from `08254e668`. Native sources match `bbfb3bff`
and financial sources match `c2425f2e2`, explicitly revalidating the focused
simulator and source-timezone/type-lock evidence for the published candidate.

**Preview cleanup and publication authorization:** the founder authorized
verification, removal of only PR #745's disposable preview, and disabling
automatic previews only for this PR. CLI and connected Supabase branch inventories
confirmed a real environment, not a skipped-preview notice: branch
`4d58c555-c26d-4a51-bdfb-c1765042aca3`, preview project
`yjuknxqpmgddgswvtgwk`, git branch `codex/financial-loop-delivery`, PR `745`,
non-default, non-persistent, and created without production data.

The existing integration checkout's environment credential authenticated CLI
reads, but CLI deletion lacked `branching_development_delete`. The connected
Supabase tool successfully deleted that exact branch. A fresh inventory confirmed
only the unchanged default branch remains on existing project
`lgdhvepyrzbnscqssgqq`. No new token, other branch deletion, main-project mutation,
or integration-setting change was made.

After reviewing the expected cost and isolation, the founder explicitly authorized
PR #745's existing automatic Supabase preview as a side effect of publishing its
fixes. The publication blocker is resolved. Preserve Automatic branching and all
other integration settings. No further infrastructure investigation, production
changes or application deployment is authorized. No new token is needed.

The fixes were published, exact-head CI passed, the addressed threads were
resolved and the scoped recheck returned clean before the founder approved the
merge. Do not repeat those completed steps. Preview status is automation evidence,
not application delivery or physical-phone acceptance. The broader MVEE and
deferred physical-phone work retain their existing authority boundaries.

**Runnable local demonstration:** the retained database and synthetic identities
are running again. Native `bbfb3bff` and core `c2425f2e2` are the locally verified
review corrections. Keep the owned API 58400, CAPTCHA 58405 and Supabase/Postgres
58401/58402 alive for founder use; restart instructions are in the
[evidence README](../reports/evidence/financial-loop/ios/README.md#reproduce-and-resume).
No physical-iPhone, signing, Render login or deployment work is active.

Throughput checkpoint: three implementation responsibilities, one financial
contract owner and one integration owner. Device access must not block local
financial/native work. CPU-heavy Xcode and database suites use separate owners;
shared simulator control is exclusive to the native owner until handed to QA.
The first stop requiring the founder is a concrete signing or hosted action,
not a routine engineering decision. Physical-phone completion remains unverified;
it is deferred beyond this explicitly authorized local review deliverable.

The execution checklist adapts poteto's figure-it-out workflow into this existing
manifest rather than creating another board.

- [x] Read the Principles section of the poteto-mode skill.
- [x] Phase A: Frame. Scope and authority recorded above.
- [x] Phase B: Design the workflow. Trace existing owners and settle the consumed contract.
- [x] Phase C: Run the loop. Implement and verify the complete authorized local simulator loop.
- [x] Recover the native baseline and capture locked-reference comparisons.
- [x] Implement durable activity, corrections, reconciliation and shared reads.
- [x] Connect the native loop and verify it against a local API/database.
- [ ] Prepare signing/install and exact hosted rollout actions for approval.
- [ ] Verify the approved installed candidate on the physical phone over the internet.
- [x] Phase D: Keep the audit trail. Record decisions and evidence here as work advances.
- [x] Phase E: Verify and hand back the authorized local simulator deliverable, recording, restart instructions and limitations. Phone acceptance remains deferred above.

### Historical implementation checkpoints

The following records describe intermediate states before #745 landed. Their
publication, process and integration statuses are historical, not current work
instructions; the landing checkpoint above owns current status.

- Restart uses three isolated writers and recovers the preserved iOS lineage.
  The fetched base and recovery checkpoint above identify their source. The
  native baseline builds and runs but still shows fixtures.
- Financial design extends the existing record/revision graph and one domain
  projection. Explicit inclusion decisions cover opening/check boundaries;
  immutable check confirmation facts remain separate from current residuals.
  The financial owner records the consumed wire contract in API_CONTRACT and
  data shape in DATA_MODEL before client integration.
- A dedicated existing-web `/auth/native-captcha` adapter may reuse the current
  challenge owner for native login. It contains no password or session state.
  This is a required auth connection, not web remake work. Its deployment still
  requires approval.
- Read-only access inventory found no valid local signing identity, a known
  but unavailable iPhone 15, and an expired Render CLI session. The existing
  Supabase project is healthy on its current Free plan; its applied migration
  inventory does not yet include the financial-account migration. Founder
  access work is now explicitly deferred. No hosted mutation or provisioning occurred.
- The consumed API contract is committed on the financial branch in
  `ee77772c9` and amended in `0de85dca`. Home aggregates use exact decimal-integer
  strings; one backend projection owns totals and ownership-share rounding.
  Native clients format those values without recomputing financial rules.
- Device checkpoint `ea3370606` is published for review. Its proof uses an
  unsigned build and synthetic local CAPTCHA responses. It does not establish
  production login, a signed installation, or physical-phone acceptance.
- Captain independently ran the core's local HTTP verification script against
  synthetic Auth and Postgres: expense, correction, check, late included expense,
  retry after intervening writes, unknown balance, second-owner refusal and
  reopened read passed. That provisional run was superseded by the final-source
  HTTP/Home proof and native simulator evidence recorded below.
- Automatic approval review blocked the native worker's combined commit/push
  because remote publication was treated as a reserved hosted change. Neither
  command ran. The worker subsequently committed locally. The founder later
  explicitly approved publication of the assembled delivery branch and its
  review PR, resolving that publication blocker only. Previously published
  device and captain checkpoints were preserved; no PR/integration merge had
  occurred at that checkpoint. The subsequent #745 merge is recorded above.
- Financial checkpoint `92020058d` passed independent review after fixes for
  stale metadata planning and native uppercase UUIDs. The captain reran the
  complete HTTP loop on a separate synthetic identity, including exact Home
  position/spending deltas after each write and replay. The five core commits
  are assembled locally; [component evidence](../reports/evidence/financial-loop/core-verification.json)
  records the source and limits. The owned local API/database supported native
  acceptance and were then stopped with their data retained. Integration was
  fetched again and remains `fcbb70cc2`.
- Native checkpoint `d5299f65` passed three real local API/Postgres simulator
  journeys: unknown balance through spending and an explicitly reviewed opening;
  known balance through expense, correction, check, included late expense and
  reopen; and Spanish Home/check review. Numeric Home deltas and foreground
  recovery are asserted. Session tests executed 39 passes with four explicit
  environment skips; five tests compile and exercise the actual native models.
  Independent review is clean after fixing expired-session recovery, editable
  inclusion review, and the foreground auth race that blocked Home refreshes.
- The captain assembled device, core and native source at `ba69fecd6`, reran
  108 backend checks and the modularity budget (all pass), and compiled the full
  app for generic physical iOS with signing disabled. The temporary unsigned
  device override was removed. Native feature/test sources match `d5299f65`;
  only the reviewed opt-in device configuration and setup documentation differ.
  Home, entry, check-review and reopened-account captures were compared with
  the locked visual reference. This supports local visual acceptance, not
  physical-device fidelity or internet completion.
- Post-merge integration CI and release smoke are green for exact integration
  `fcbb70cc2899ca6a05c03c49316e9a4e4cbf5333`:
  [CI](https://github.com/lagarcess/argus/actions/runs/36537496516) and
  [smoke](https://github.com/lagarcess/argus/actions/runs/36537496519).
  These results do not cover the unpublished implementation candidate.
- [Simulator demonstration and acceptance evidence](../reports/evidence/financial-loop/ios/README.md)
  were assembled in evidence-only commit `9b94c65c3`, preserving the tested
  application source. The recording, seven captures and sanitized XCTest results
  are committed locally and included in the authorized review publication.
  The evidence README records the exact existing-stack restart commands. All
  worker-owned build/recording/API/database processes are stopped; synthetic data,
  fixtures, worktrees and the installed simulator app are preserved. Writers and
  independent reviewers have completed their assigned local work. The captain
  retains signing, hosted compatibility, publication and physical acceptance.

### Financial-loop landing handoff

The locally verified loop is merged through #745. Keep its
simulator/local-backend demonstration runnable. PR #746 carries the
founder-authorized landing documentation; the [landing result](https://github.com/lagarcess/argus/pull/745#issuecomment-5889046424)
records its publication and final verification. This record does not assign a
repeat landing or another implementation batch. Physical-device signing,
Render login and deployment are explicitly deferred. No functionality on the
founder's phone is yet proved by this batch. When those actions are resumed, the
[device preparation evidence](../reports/financial-loop-device-preparation.md)
identifies the access needed; actual deployed API/web SHAs are required before fixing
the minimal deployment candidate. Account and loop migrations are
`20260928200000_financial_accounts_first_slice.sql` and
`20260929090000_financial_loop.sql`; neither is approved for application to the
production project. The earlier isolated automatic-preview grant is recorded above.


## Outcome and completion

The founder can use the agreed financial ecosystem on a physical iPhone, with
an existing account and real persistent data over the internet, away from the
Mac, and hand the phone to someone to demonstrate it. Public App Store release
is not required. The [MVEE private-delivery boundary](argus-minimum-viable-ecosystem-experience.md#12-private-iphone-delivery-the-immediate-finish-line)
explicitly defers the agentic runtime. That exception does not remove household,
planning, document intake, recovery or other agreed financial capabilities.
Full agent-first completion later adds every supported action through text and
voice. Capture/playback alone does not prove voice actions.

This is the single execution map and progress board. It replaces the unpublished
September 28 weekly-board draft. Do not create parallel manifest, roadmap and
status documents with copied requirements. The MVEE owns requirements; this file
owns sequencing and checkpoints; PRs, CI and acceptance artifacts own evidence.
A release manifest under `docs/release-manifests/` remains the evidence for one
specific deployment, not a competing product plan.

The founder assigns the full MVEE private iPhone outcome to this delivery captain.
The full-scope execution proposal below remains recorded. The completed restart
covered only the first local financial loop; additional MVEE work remains stopped. Record named owners and each consumed technical contract
before implementation of that dependency. Routine progression does not require
new batch approvals. No 24-hour delivery promise has been made.

## Verified starting point

This is the historical baseline before #745; current landed status is above.
The financial-loop batch started from integration
`fcbb70cc2899ca6a05c03c49316e9a4e4cbf5333`, the #744 merge. Its exact-commit
[CI](https://github.com/lagarcess/argus/actions/runs/36537496516) and
[Private Alpha Local Smoke](https://github.com/lagarcess/argus/actions/runs/36537496519)
were refreshed on September 29 and both succeeded. The earlier planning snapshot
used `12bccd4d6e173a5d8805e495fd30b7ead36741c6`, the #743 merge. The original
publication inspected `de8729843b726a3fd03210cebcedede5e44227c8`.
The account product commit is `296195e86c972e846c251d256b3cc211975bfd57`.
GitHub merge/closure state and the linked repository documents were inspected.
Existing production behavior is documented, not freshly exercised on a hosted
service in this publication. No private iPhone completion is claimed.

Post-merge [CI](https://github.com/lagarcess/argus/actions/runs/36528607001)
and [Private Alpha Local Smoke](https://github.com/lagarcess/argus/actions/runs/36528606830)
both completed successfully at `12bccd4d6`. These checks do not establish hosted
or physical-phone acceptance. Local commit `44dd019f908024ff0a7733091ca1d37edf6d529f`
remains preserved by `codex/preserved-pr743-landing`; its landing-ledger entry is
carried into this documentation change without restarting its publication work.

| Existing work | Evidence and scope | What it does not establish |
| --- | --- | --- |
| Existing Argus | [PRODUCT](../PRODUCT.md), [ARCHITECTURE](../ARCHITECTURE.md), [API_CONTRACT](../API_CONTRACT.md) describe chat, auth, calculations, research, simulations, history, search and settings to inherit | Native feature parity or current hosted acceptance of the pivot |
| Design lock | [#727](https://github.com/lagarcess/argus/pull/727) merged; [mobile reference](../reports/mobile-design-lock-2026-09-28.md) | Implemented financial flows; newer MVEE tester corrections take precedence |
| Native shells | [#729](https://github.com/lagarcess/argus/pull/729), [#730](https://github.com/lagarcess/argus/pull/730) merged; [iPhone setup](../../ios/README.md), [Android setup](../../mobile/android/README.md) | Real finances, production app identity or installation on the founder's iPhone |
| Native auth | [#738](https://github.com/lagarcess/argus/pull/738), [#739](https://github.com/lagarcess/argus/pull/739) and their landing records merged; [iPhone auth](../../ios/AUTH_SETUP.md) | Complete hosted registration, recovery links or private device distribution |
| Financial accounts | [#735](https://github.com/lagarcess/argus/pull/735) and [#742](https://github.com/lagarcess/argus/pull/742) merged; [scope](lanes/financial-accounts-first-slice.md), [API/Postgres evidence](../reports/evidence/financial-accounts-first-slice/README.md) | Full financial activity, plans, totals or completed client delivery. Feature remains default-off in its contract |
| Charts | [#733](https://github.com/lagarcess/argus/pull/733) merged as a prototype | Connected financial charts or resolved Android performance/dependency limitations |
| Web preview | [#732](https://github.com/lagarcess/argus/pull/732) open on visual hold | Adoption. All remake work is frozen |
| Research/proofs | [#723](https://github.com/lagarcess/argus/pull/723), [#724](https://github.com/lagarcess/argus/pull/724), [#725](https://github.com/lagarcess/argus/pull/725), [#726](https://github.com/lagarcess/argus/pull/726) closed unmerged | Live work queues. Carry useful evidence selectively; do not restart their review loops |

Stopped client work must be inspected and salvaged before replacement work is
assigned. These recovery checkpoints are not accepted deliveries. Remote
preservation is identified per row; retain worktrees and local-only artifacts.

| Branch | Last inspected commit | State at stop |
| --- | --- | --- |
| `codex/ios-financial-accounts` | `671ee6b0ff24115232eaac9204fd03da3b5cd55d` (remote checkpoint) | Unfinished client source and [recovery note with verification limits](https://github.com/lagarcess/argus/blob/671ee6b0ff24115232eaac9204fd03da3b5cd55d/docs/reports/evidence/ios-financial-accounts/README.md) preserved remotely; worktree and ignored local state retained. Native build/UI acceptance unverified; known form defects, missing setup guide and prior build approval rejection remain unresolved. No implementation PR; implementation stopped |
| `codex/android-financial-accounts` | `fb6e4d9455aec7abbf0d16d74e00be896804d472` (remote checkpoint) | Implementation remains `3aed3d2266f8ed5a31c87b8083ef114a33d905cd`; preservation commit publishes [recovery note and 16 synthetic screenshots](https://github.com/lagarcess/argus/blob/fb6e4d9455aec7abbf0d16d74e00be896804d472/docs/reports/evidence/android-financial-accounts/README.md). Worktree retained. Final restart proof, integration reconciliation, PR delivery, CI and terminal review incomplete; implementation stopped |
| `codex/web-financial-accounts` | `1b0c80d208ad6e73409c72ccba13407fbfb2ee34` | Spec commit plus uncommitted client work. Preserve only; no continuation now |

A replacement coordinator must locate the branches and working changes before
using those pointers. Missing local artifacts are a recovery issue, not evidence
that their work landed. Do not copy secrets or real user data into handoffs.

### Recovery refresh for the proposed restart

Both mobile remote branches were fetched again on September 29 and still point
to the checkpoints above. Read-only source inspection found the following.

- The iPhone checkpoint contains account creation, list/detail, metadata editing,
  opening corrections/history, archive/restore, localization and typed API calls
  through the existing session owner. Preserve this implementation. Its recorded
  worktree at `/Users/garces/.codex/worktrees/8be2/private-alpha-next` is now absent.
  Committed source remains recoverable; ignored local state has not been located.
- The iPhone source has concrete draft-freeze, local-validation/error handling and
  signed-amount entry gaps. Its historical package/API checks do not prove that
  the native app builds or works. The account setup guide is missing.
- The Android worktree at `/Users/garces/.codex/worktrees/611c/private-alpha-next`
  exists and is clean at `fb6e4d945`. Its retry/reconciliation implementation and
  synthetic evidence are useful references. Android implementation stays stopped.
- [iPhone configuration](../../ios/Config/Development.xcconfig) is simulator-only,
  uses a placeholder bundle identity and disables auth. Xcode is installed, but
  local inspection found zero valid signing identities. Apple membership, team
  access and a usable private installation route have not been established.
- [Existing auth](../../ios/AUTH_SETUP.md) provides reusable registered sessions,
  refresh and Keychain storage. Production CAPTCHA bridging and remaining access
  flows need work. Existing browser recovery is reusable. A successful first
  login cannot close the full D01 acceptance list.
- Hosted API revision, applied financial-account migration, feature flag and
  available capacity remain unverified. Checked-in Render configuration is not
  a hosted readback. No hosted settings, real account records or providers were
  changed during this recovery.

The recovery agents were read-only investigators, not implementation owners.
Confirm prior worker ownership and process state before assigning a writer.

## Reconciliation findings for founder review

The planning update corrects these omissions without changing MVEE scope.

- The published manifest proposed D01/D02 first and D03 contract preparation.
  That is too narrow for this assignment. The full coverage map now governs;
  D01-D05's first financial loop is only the first demonstration.
- Earlier dependencies could read as requiring completed upstream pillars.
  The plan now identifies the specific consumed contracts so independent work
  can proceed. Signing does not block finance; posting does not block previews.
- Native quality, charts, Temporary chat and profile controls were implicit in
  broad D rows. The work map now links these source areas to delivery owners and evidence.
- Native auth is reusable, but the current shell's financial destinations are
  samples. No source claim, old screenshot or merged PR is phone acceptance.
- The iOS recovery row describes the historical stop. Its once-retained worktree
  is now missing; the recovery refresh above is the current observation.
- MVEE section 1.2 explicitly defers the ecosystem runtime despite sections 4
  and 6 describing typed/spoken financial actions. D14 preserves that named
  exception only. Dictation/spoken conversation, permitted financial questions,
  household, ingestion and manual planning remain delivery work.
- Technical policy gaps are not deferrals. File, audio and recovery retention,
  household departure and notification choices now have owners and decisions
  below. The captain may not silently move them outside private delivery.

### Current code inheritance anchors

These sources support the coverage table's reuse claims. They are code/contract
inspection, not a new hosted verification.

- [Native shell](../../ios/ArgusFoundation/FoundationShell.swift) selects
  [sample destinations](../../ios/ArgusFoundation/SampleDestinations.swift).
  [SessionController](../../ios/Packages/ArgusSession/Sources/ArgusSession/SessionController.swift)
  and [auth setup](../../ios/AUTH_SETUP.md) own the reusable session boundary.
- [Financial service](../../src/argus/domain/recording/service.py),
  [balance read](../../src/argus/domain/recording/records.py) and
  [account router](../../src/argus/api/routers/financial_accounts.py) implement
  openings/accounts only. The database migration is
  [the landed first slice](../../supabase/migrations/20260928200000_financial_accounts_first_slice.sql).
  It is not an activity ledger, household or planning implementation.
- [Agent API](../../src/argus/api/routers/agent.py),
  [conversation API](../../src/argus/api/routers/conversations.py),
  [search API](../../src/argus/api/routers/search.py),
  [profile API](../../src/argus/api/routers/profile.py) and
  [personalization API](../../src/argus/api/routers/personalization_memory.py)
  anchor inherited services. Existing web settings are behavioral references,
  not permission to resume the web remake.
- [Architecture voice/chart direction](../ARCHITECTURE.md#voice-and-chart-direction)
  selects xAI and Swift Charts. It does not supply implemented production voice,
  financial chart series or provider/spending authority. Existing notification
  availability in PRODUCT is not proof of an ecosystem inbox or scheduler.

## Full-scope execution and early demonstration

**The local first-loop deliverable landed through #745; the current handoff above
owns the remaining authorization.** The full-scope proposal's first usable
outcome is a complete financial loop on the physical iPhone over the internet,
using the founder's existing user. Establish an account balance, record an
expense, see Accounts and Home reflect it, correct it, reconcile a checked
balance without double-counting, and reopen the app with everything preserved.
Unknown balances remain unknown. This spans D01/D02, D03 and D05; account CRUD
and installed login are intermediate checkpoints. This loop is an early
demonstration within the full assignment, not the ecosystem finish line.

Run three connected responsibilities in parallel. Names, exclusive paths,
branch/worktree and owner acceptance are filled at dispatch after restart.
The roles below are not live assignments. Independent acceptance accompanies
the assembled loop throughout implementation.

| Responsibility | First demonstration contribution | Ownership boundary |
| --- | --- | --- |
| Device and hosted access owner | Signing, installation, existing-user authentication integration and the minimum compatible deployment, including backup/restore verification and rollback | Own signing/project configuration, deployment files and the narrow hosted auth bridge. The iPhone owner writes session/UI code against the agreed auth contract. No replacement web work or new paid infrastructure |
| Financial backend owner | Implement durable expense activity, corrections, balance reconciliation and canonical account/Home reads; resolve API/data contracts and additive migrations within this implementation | One owner for financial contracts, posting, money rules, reconciliation and their backend tests/migrations. No competing ledger or standalone research/proof deliverable |
| iPhone experience owner | Recover the preserved client and connect Accounts, recording, corrections, balance checks and Home to the shared contracts; preserve the locked design | Own native feature, session and navigation code; exclude signing/project files assigned to the device owner. Reconcile current integration by merge, never rebase the evidenced branch |

The delivery captain owns this manifest, cross-owner decisions and integration
sequencing. Domain owners remain accountable until their assigned journey is
verified in the assembled app; a component handoff does not close the outcome.
An independent acceptance owner exercises each integrated increment and returns
defects to its writer. Separate test/evidence files prevent competing edits.

### Deliver the early demonstration while full-scope work progresses

1. Recover iPhone source and locate or account for missing local configuration.
   Inspect previous worker/process ownership. Record the fresh integration base,
   exclusive worktree, allowed files, commands and stop conditions before dispatch.
2. Start device access, backend implementation and native experience together.
   Resolve signing/team access and the shortest supported private installation
   route while the financial owner defines and implements the shared write/read
   contract. Agree each consumed contract before wiring its client; do not wait
   for a separate research project or all financial contracts to finish.
3. Install the connected shell as soon as its auth path is ready, with a stable
   app identity and update path. Demonstrate existing-user login and reopening
   away from the Mac. Backend and native financial work continue while device
   access is blocked. Simulator/local evidence is intermediate, not acceptance.
4. Integrate balance establishment, expense recording, Home/account reads,
   correction and reconciliation as working increments of the same loop. The
   backend owns arithmetic and financial facts. Clients render canonical reads.
   Verify exact money, unknown/zero distinction, atomic writes, identity isolation,
   retry idempotency, stale-edit handling and persistence as each increment lands.
5. Prepare one concrete hosted approval packet. Name the candidate SHA, current
   deployed revision, existing Supabase project, migration status, exact settings,
   production-web compatibility, backup/restore evidence and rollback. Prefer
   existing compatible Render capacity; justify any alternative and its cost.
   Use an auth-only release first if it speeds installation, without pausing
   backend or native financial implementation behind that release.
6. After the required signing/install and hosted grants, exercise the full loop
   using deliberate founder-entered records on the physical phone. Close and
   reopen the app, interrupt a write and retry, and verify Accounts/Home agreement.
   Use authorized test identities for isolation; redact committed evidence.
7. Replay the existing [balance handoff](argus-account-balance-reconciliation-handoff.md)
   cases on the assembled candidate. Compare observed results to that source and
   record the source revision with the phone/database evidence.

Do not wait for every registration, confirmation/resend, recovery/reset, guest
return-to-action or account-management case before advancing this loop. Keep
security and money correctness necessary for the connected path mandatory.
Sequence remaining access/account completeness and other D03/D05 acceptance in
the work map; accepting this loop does not mark those entire rows accepted.

Prepare builds, tests, source changes, draft PRs and the deployment packet under
the restart grant. Merges, deployment, hosted mutations, signing/account access
and paid-provider use require explicit authority. A routine build or scoped bug
fix does not need a repeated restart question. No paid model run is needed for
this manual financial loop. Do not bypass an earlier denied action through a VM
or another agent; request the correctly scoped access when needed.

### Allocate resources to accepted dependencies

Keep the iPhone writer and physical-device verification on an authorized Mac.
Use available VMs for isolated backend/Postgres tests and contract verification
when an assignment benefits from them. Direct VM coordination is not configured;
establish an authorized channel before promising unattended remote ownership.
Additional capacity earns a lane only when it has independent files, accepted
inputs and an observable user outcome. Keep one writer for each shared iPhone file and one financial-domain owner even
when more machines are available. Independent feature modules can have separate
writers under the team allocation below.

During execution, inspect active agents at completion, dependency changes and
at least every 30 minutes. Check actual process/build/commit/test evidence.
Re-scope stalled work, preserve unique changes and stop the old writer before
replacement. Do not retry an unchanged failure indefinitely. Publish useful
branch checkpoints so a lost VM does not erase work. No scheduler is armed by
this proposal.

Show a short interaction recording or live demonstration at first installation,
first recorded expense reflected on Home, correction/reconciliation and each
added connected journey. Include relaunch and a
failure/recovery case, not screenshots alone. Record build number, app SHA,
backend revision, environment, evidence and remaining gaps in this manifest.
Check concise copy, icons, locked navigation and native interaction quality
before repeating a pattern across screens.

## Cuadrao design dispositions

The native design preview history remains on
[checkpoint fc7650e](https://github.com/lagarcess/argus/tree/fc7650eab4eac9298a09eea37eddc3964a709fba/docs/reports/evidence/cuadrao-native-design).
The rows below preserve its follow-up decisions. Historical UI verification is
not connected-service verification or proof that every preview screen has landed
on integration. The [October 4 roadmap](#current-mobile-roadmap-october-4-founder-lock) owns current execution order; this register preserves design detail and follow-up ownership.

The [release UI landing order](#cuadrao-release-ui-landing-order) above retains the detailed release requirements. The
[UI checkpoint and evidence](../reports/evidence/cuadrao-release-ui/README.md)
records the release UI's shared presentation states, native journeys and service
dependencies. Review fixtures launch with `--cuadrao-release-ui` in DEBUG builds.
The connected Profile offers signed-in legal links and displays the current avatar;
avatar editing remains DEBUG-only until selections survive relaunch. Connected
Household management uses the shared invitation/QR presentation. Pending auth,
delete, admission, inbox delivery, moves, AI, sources and memory operations still
require their service owners. This is not external-TestFlight acceptance.

### Follow-up ownership and disposition

The October 4 roadmap owns current assignments. C01–C10 retain
follow-up ownership under the existing D01–D15 work map,
not a parallel delivery team. Owners below are responsibility areas, not a claim
that a named worker has been dispatched. Link the assigned lane and its evidence
here when work starts. Close an entry only against its stated remaining gap.

| ID / topic | Disposition and existing baseline | Remaining work and closure evidence | Existing responsibility |
| --- | --- | --- | --- |
| **C01 — Scan and itemized bills** | **UI preview delivered (October 2, build 3415).** Native source adapters, durable local drafts, shared Chat/Plan review, editable items, equal/item splits and repeat-safe confirmation are implemented. Real extraction and connected posting remain unassigned. | Retain the verified local capture/review/split journey below. The founder verified physical scan → Later → reopen on build 3419. Native simulator checks cover location allow/remove and denial recovery; physical GPS/VoiceOver acceptance remains distinct. Real extraction, shared storage and connected posting require the intake contracts. | Intake D08 + Planning/Home D06; Household D07 for shared access |
| **C02 — Shared plans and invitations** | **UI baseline preserved; connection outstanding.** Para ti / En grupo, trip estimates, recorded expenses, own share versus group total, shared savings, local invitation/guest preview and sample QR exist. Short-lived groups are distinct from durable Spaces. | Resolve group membership/guest access, link expiry/revocation, permissions and canonical expense/contribution/repayment ownership before connecting. Estimates must stay separate from actuals; repayments must not imply a bank transfer. Verify two participants, partial repayments, correction/recovery and no duplicate personal spending. | Planning/Home D06 + Household D07 + Financial core D03/D04 |
| **C03 — Forecasts and calculators** | **Preview built; canonical connection outstanding.** Spending-pace playground, low point, editable assumptions and goal/debt projections exist with illustrative data. | Reuse existing Argus forecast/calculation owners for Home, Plan and chat. Carry forward the Stake-style editable compound-interest assumptions and contribution/earnings curve as future UI work, with disclosed rate/cadence assumptions. Verify chart/readout agreement and actual versus projected values. Retain Apple Card-inspired explanations of upcoming payment and interest consequences as design input to the existing debt owner. A short contextual explanation may help; a blog/tips destination is not required. | Planning/Home D05/D06 + Conversation D09; domain series owners |
| **C04 — Voice and chat continuity** | **Interaction preview built; runtime outstanding.** Immersive/minimized voice, swipe-down, voice-choice carousel, short-message hold/lock/cancel/review, native dictation coexistence, temporary mode and Recents gestures are already previewed. | Connect xAI live voice through the existing chat brain; inherit agentic app actions only under D14 activation. Reuse existing Argus dynamic greeting logic. Resolve audio/transcript retention, Temporary context, actual provider voices/selection, interruptions and background/locked-screen policy. Verify one session across surfaces, draft recovery, mute/end, real capture and truthful progress. | Conversation/voice D09/D13/D14 + Native continuity |
| **C05 — Home, Accounts and household** | **Structure locked; detailed acceptance/connection outstanding.** Personal / Hogar / +, Movimientos / Próximamente, Ordenar Inicio, approved icons, cold starts and Personas-owned invitation status are preserved. | Finish Panorama meaning, realistic empty/unknown/loading/failure/long-content states and assembled account detail/correction/reconciliation presentation. Use existing financial semantics, including balance checks; do not invent another ledger. Connect household auth/install/acceptance/sharing/leave/remove flows under the MVEE. Inviting does not require an account first, expose private accounts or warrant a nagging Home banner. Verify relevant journeys and permission boundaries. | Planning/Home D05 + Financial core D02/D03/D04 + Household D07 |
| **C06 — Search, Files and Memory** | **Preview destinations preserved; remaining owner connections outstanding.** Keep supported Chats and Files alongside financial results; expose Memory only with its connected native feature and controls. | Connect the authorized record owners, destination/reopen flows, filters and recovery. Respect permissions, Temporary exclusions and memory consent/retention. Search and Profile read the same owners; this is not approval for generic RAG or new memory storage. | Native continuity D10 + Conversation D09 + Intake D08 |
| **C07 — Profile and Updates** | **UI support pass verified October 2; connected owners outstanding.** Profile grouping, shared identity, avatar themes, native settings and source-linked Updates with read/unread behavior exist. See support acceptance below. | Historical photo editing, feedback drafts and Settings clearance remain UI-verified. The release pivot hides unsupported settings rows and the avatar-editing entry in release builds while development builds show them, removes the email-notification toggle, and prioritizes deletion, legal access, social auth and Updates; use the landing table above. Connect only the assigned visible controls through their existing owners. Design Updates around actual domain events with source links, avoiding duplicate invitation reminders. Verify language/accessibility and working controls, not static menus alone. | Native continuity D12 + Planning/Home D11 |
| **C08 — Identity and social discovery** | **Local avatar UI verified October 2; connected identity decisions outstanding.** Native profile-photo selection supports Save/Cancel, replacement and removal in the preview. Group covers, local avatars and sample invitation QR do not imply server upload, live profile QR or contacts discovery. | The founder retains initials, themes and photos in the design; release builds hide the avatar-editing entry and development builds keep the full editor ([decision of October 3, 2026](argus-decision-log.md#october-3-2026-avatar-editing-in-release)). App-access and household invitation QR now join plan QR in scope. Public profile QR, usernames and discovery remain deferred. Use the landing table for quota, admission and guest-identity contracts; validate QR legibility and scan reliability. Contacts matching needs explicit opt-in and a data/access contract. Native sharing can hand off a link to WhatsApp; no automatic contact upload or WhatsApp integration is implied. Keep this separate from required household membership and parked growth work. | Native continuity D12 + Household D07; founder for unresolved product scope |
| **C09 — Extra Plan refinements** | **Unassigned refinements/research, not promised capabilities.** Art, customization and gentle progress already inform Plan. | Exact target-date entry and personal cover photos remain refinements; group cover photos already exist. Forecast uncertainty bands require a valid model, not decorative precision. Habit/streak ideas need a helpful, non-punitive purpose. Rotating savings (“san” / Egyptian-style circles) remains research: sequence, missed contributions, custody and consent are unresolved. Existing shared savings does not implement a rotating pool or payouts. | Planning/Home D06; founder for additional scope |
| **C10 — Consistency and phone handoff** | **Ongoing acceptance/connection work.** Accounts and Plan now share typography roles and one money-editing implementation; their contextual layouts remain distinct. New plan/group amounts begin empty. A living Cuadrao guide and native reference gallery own consistency. Both plan/group currency choices are fixed at creation. | Preserve welcome/sign-in/recovery UI and connect it to the existing auth/session owner. Final branding/assistant mark remain unresolved. Verify shared styling, approved icons, navigation/edge blur, Spanish-first/English parity, long values, Dynamic Type, VoiceOver, Reduce Motion, light/dark and physical touch. The October 2 continuity pass traced the keyboard invalid-frame warning to SwiftUI keyboard accessory sizing and removed the duplicate toolbar path; retain the native acceptance evidence below. Adapt preview views to canonical owners through the existing delivery lane; retain separate identities and truthful device evidence. | Native continuity D01/D15 + Device/release; domain owners for money/input contracts |

## Work map

The [six-lane handoff](lanes/mvee-five-lane-handoff.md) is the current lane
contract for Household invitations, account deletion, private Spaces and account
moves, Search documents and conversations, Home series data, and Updates. The table below
remains the coverage index.

### Complete MVEE coverage

The [MVEE scope checklist](argus-minimum-viable-ecosystem-experience.md#13-complete-scope-checklist)
is the requirement index. Read each linked source for the user outcome and its
expected behavior; this table stores execution metadata only. D01-D15 are work
identifiers, not a second specification. A row's next integration task and planned
evidence are not an exhaustive scope or a substitute for the linked requirement.

**Current phone evidence:** none of the assembled outcomes is verified on the
founder's physical iPhone. Reuse and gaps below include landed #745 and the
landed personal recording, Plan/Home and Search journeys. Those local batches are complete; their owners and evidence are recorded above. Connected personal spending budgets are landed through PR #753; its terminal audit and landing record retain the local evidence. Connected personal savings goals are locally verified through the complete journey and are published in [PR #755](https://github.com/lagarcess/argus/pull/755), under
the founder-approved account-backed allocation policy. Proposed owners must be bound to named
workers at dispatch. D14 follows the linked runtime
sequence rather than a separate deferral policy in this document.

| Canonical user outcome / work ID | Inspected reuse | Next integration task | Proposed owner | Execution dependencies | Evidence to collect against the linked source |
| --- | --- | --- | --- | --- | --- |
| [Access][mvee-access], D01 | Argus auth/recovery; Swift session/Keychain | Finish native/hosted auth adapter and guest conversion | Native continuity + Device/release | Identity API; signing/hosted access for phone proof | Physical-device auth recordings and session/identity test results |
| [iPhone experience][mvee-platforms], D15 | Native shell; localization; design archive | Replace sample destinations with connected modules | Native continuity | Domain reads per destination | Device navigation/accessibility recordings against [native quality][mvee-quality] |
| [Accounts and assets][mvee-accounts], D02/D04 | Landed #745 account/opening lifecycle; PR #759 landed locally verified personal assets, estimates, ownership shares, existing-debt links and net worth | Deliver existing space/shared ownership scope through its assigned owner; verify the assembled account/asset lifecycle on the phone after deployment/signing approval | Financial core | Existing account contract; D03 history; D07 for sharing | Device lifecycle recordings and persisted account/asset readbacks |
| [Activity][mvee-activity] and [refunds][mvee-refunds], D03 | #745 expense/correction core; landed #747 five-kind manual entry, paired correction/history and refunds | Local assembled acceptance and scoped review passed; authorized phone proof remains; intake, household and agentic adapters retain D08/D07/D14 owners | Financial core | Account identity; shared posting contract | Device entry/correction recordings plus atomicity, retry and concurrency tests |
| [Reconciliation][mvee-activity], D03 | #745 immutable balance checks and coverage; #747 per-account paired coverage; [handoff cases](argus-account-balance-reconciliation-handoff.md) | Paired coverage/recovery passed locally; authorized phone verification remains; checks before the latest observation remain an explicit technical limitation | Financial core | Account/activity identity | Replay the handoff cases on the candidate; retain before/after reads and relaunch evidence |
| [Home][mvee-home], D05 | #745 known/unknown positions; #747 monthly actuals; PR #749 landed locally verified commitments and dated cash forecast | Complete remaining approved Home contexts/chart/destinations through their owners; verify assembled Home on the physical phone | Planning/Home | D02/D03 position; D06 forecasts; D04/D07 contexts; D08 resume | Phone walkthrough with source-record/read-model comparisons |
| [Plan][mvee-plan], D06 | Existing calculators; locked design; PR #749 landed locally verified commitments, recurrence, fulfillment and forecast | PR #753 landed locally verified personal monthly budgets with actual progress, contributors and Search; PR #755 landed locally verified personal savings goals with approved account-backed allocations and retained native/API/database evidence; PR #757 landed locally verified personal debt-plan lifecycles with native/API/database evidence; shared variants landed locally verified in #773 (`f28b5642…`); physical-phone proof remains pending | Planning/Home | Financial posting/link contract; D07 for shared variants | Device plan lifecycle recordings and linked-record/forecast readbacks |
| [Spaces][mvee-spaces] and [account moves][mvee-moves], D04 | Personal default; fixed Cuadrao space/household flow in #762 | Assigned Household context adapter in the active lane above; private Business/Custom lifecycle and account moves remain unassigned work | Financial core + Household captain | Account identity; membership/grants for Household; affected links for moves | Two-user native context proof for this lane; later private lifecycle/move evidence remains required |
| [Household][mvee-household], D07 | #763/#766/#773 landed membership, invitations, explicit account consent, canonical activity and shared budgets/bills/goals/debt with retained native/API/Postgres proof | External invitation delivery, other authorized consumers and physical-phone/hosted delivery remain required | Household captain; existing membership, financial and allocation owners | Approved rights/departure policy; canonical Recording/Plan; fixed `7f72dfd7` presentation | Two member identities plus unauthorized C; four-kind native journey, recovery, English/Spanish, real Postgres privacy/removal tests; phone/internet proof still pending |
| [Intake][mvee-intake], D08/D03/D13/D14 | Manual account entry; synthetic review/retry kit | Build production source/review pipeline and shared posting adapter | Intake | File/provider policy; D03 confirmation; D07 shared sources; D14 language actions | Authorized sample corpus runs, source-preview recordings and interrupted-import readbacks |
| [Argus][mvee-argus], D09 | Existing runtime/SSE/tools and persisted artifacts | Connect native conversation client and authorized context adapters | Conversation/voice | Existing APIs; relevant domain reads; live-provider authority | Phone conversation replay and persisted artifact/evidence comparison |
| [Voice][mvee-voice], D13 | Existing conversation services; selected provider direction | Integrate audio transport with the existing conversation path | Conversation/voice | Audio policy/provider grant; D14 only for financial actions | Device speech/cancel/recovery recordings and latency/cost receipts |
| [Search][mvee-search] and [conversation continuity][mvee-continuity], D09/D10 | Omnisearch/history and recovery contracts; locally verified account/activity/expectation Search in #751 | Deliver remaining MVEE domain retrieval and conversation lifecycle continuity; retain the connected Search origin contract | Native continuity + Conversation/voice | Authorized domain reads; Temporary policy for that behavior | Search-to-destination/back recordings, draft/history readbacks and Temporary retention evidence |
| [Updates][mvee-updates], D11 | Existing operational infrastructure; notification contracts | Implement inbox, domain triggers and delivery jobs | Planning/Home | Trigger facts; permissions; channel/schedule decisions | Trigger/job receipts paired with phone inbox/source recordings |
| [Profile and control][mvee-profile], D12 | Existing profile/usage/data-control contracts | Connect native controls to existing and new domain adapters | Native continuity | Identity/settings; domain lifecycle policy; approved personalization rollout | Phone settings/control recordings and authorized export/recovery readbacks |
| [Charts][mvee-quality], D05/D06/D09/D15 | Selected chart direction and prototype | Connect canonical series to native chart components | Native continuity + domain series owners | Each domain's canonical series | Series-to-display checks, gesture/accessibility recordings and device performance receipts |
| [Operational delivery][mvee-infrastructure], D01/D15 | Existing hosting, CI and release safeguards | Prepare and execute authorized signed candidate rollout | Device/release + Captain + independent acceptance | Candidate and explicit access/merge/hosted grants | Exact app/backend release manifest and [connected-journey][mvee-acceptance] evidence |
| [Agentic financial actions / runtime sequence][mvee-runtime], D14 | Existing single runtime; no ecosystem action integration | Await the separate activation required by the source | Conversation/voice when activated | Manual contracts/UI; runtime assignment and eval gates | Source-linked action acceptance evidence after activation; no completion claim before it |

[mvee-access]: argus-minimum-viable-ecosystem-experience.md#guest-access-and-registration
[mvee-platforms]: argus-minimum-viable-ecosystem-experience.md#2-product-character-and-platforms
[mvee-quality]: argus-minimum-viable-ecosystem-experience.md#native-quality-and-tester-feedback
[mvee-accounts]: argus-minimum-viable-ecosystem-experience.md#accounts-organize-the-financial-facts
[mvee-activity]: argus-minimum-viable-ecosystem-experience.md#account-activity-and-balance-checks
[mvee-refunds]: argus-minimum-viable-ecosystem-experience.md#refunds-corrections-and-adjustments
[mvee-home]: argus-minimum-viable-ecosystem-experience.md#home-understand-where-i-stand
[mvee-plan]: argus-minimum-viable-ecosystem-experience.md#plan-decide-what-i-want-to-change
[mvee-spaces]: argus-minimum-viable-ecosystem-experience.md#financial-spaces
[mvee-moves]: argus-minimum-viable-ecosystem-experience.md#reassigning-accounts-between-spaces
[mvee-household]: argus-minimum-viable-ecosystem-experience.md#12-household-collaboration-approved-minimum-capacity
[mvee-intake]: argus-minimum-viable-ecosystem-experience.md#4-information-ingestion-one-destination-several-entry-methods
[mvee-argus]: argus-minimum-viable-ecosystem-experience.md#argus-ask-understand-and-get-things-done
[mvee-voice]: argus-minimum-viable-ecosystem-experience.md#43-speak-to-argus
[mvee-search]: argus-minimum-viable-ecosystem-experience.md#search-find-what-i-already-know
[mvee-continuity]: argus-minimum-viable-ecosystem-experience.md#temporary-chat-and-conversation-recovery
[mvee-updates]: argus-minimum-viable-ecosystem-experience.md#updates-tell-me-when-something-deserves-attention
[mvee-profile]: argus-minimum-viable-ecosystem-experience.md#profile-control-argus
[mvee-infrastructure]: argus-minimum-viable-ecosystem-experience.md#14-infrastructure-and-cost-constraints
[mvee-acceptance]: argus-minimum-viable-ecosystem-experience.md#15-connected-acceptance-and-delivery-discipline
[mvee-runtime]: argus-minimum-viable-ecosystem-experience.md#agentic-ecosystem-direction-and-sequence

### Acceptance source and evidence ownership

Derive expected results from the linked MVEE sections, including their linked
technical contracts, [shared trust requirements](argus-minimum-viable-ecosystem-experience.md#5-shared-ingestion-and-trust-requirements)
and [connected acceptance journeys][mvee-acceptance]. This manifest owns who
collects the evidence, when it is collected and where it is recorded. It does
not own another editable list of expected product behavior. The table's evidence
column selects verification methods, not a replacement acceptance specification.

At dispatch and acceptance, read the current MVEE source and record its commit
and section anchors with the task/evidence. If the source changes, assess the
affected assignment and evidence against that source; do not update a copied
requirement list here. A missing or renamed source anchor is a coverage gap to
resolve before accepting that work, never permission to infer its behavior.

The financial owner supplies the record/projection contract, the household
owner the permission contract, and the native lead the shared navigation/session
contract. Domain workers can own disjoint native files. The captain serializes
shared integration and compares the work map to the current canonical scope
index when allocating work; row count alone is not a completeness claim.

Dispositions derive from the [MVEE holds register](argus-minimum-viable-ecosystem-experience.md#16-holds-later-work-and-unresolved-decisions),
[runtime sequence][mvee-runtime] and [product boundaries](argus-minimum-viable-ecosystem-experience.md#8-differentiation-and-boundaries).
The decision register below tracks unresolved delivery inputs and owners; it
cannot convert them into approved deferrals. Any new disposition requires a
founder decision in the canonical product source before execution metadata changes.

## Proposed team and shared ownership

Use seven coherent delivery responsibilities plus the captain and independent
acceptance. These are proposed assignments for review, not dispatched workers.
Each lead owns a journey through native UI, service, persistence and integration,
using the shared owners below. Pair a bounded native or backend implementer only
when it shortens a ready task with exclusive files; do not create duplicate leads.

- **Financial core** owns accounts/assets/spaces, posting, reconciliation, all
  actual-money reads, their API/data contracts and migrations. The recovered
  iPhone Accounts module belongs here. Other teams request changes to these
  owners rather than writing balances or alternate storage.
- **Planning/Home** owns budgets/goals/debt plans, recurrence, allocations,
  expected-to-actual links, Home composition and Updates. This team consumes
  financial position; it never maintains another actual balance. Its native
  views, domain services and tests can progress together.
- **Household** owns invitations, membership, consent, editing rights and
  revocation, including do-blitz/Resend integration and household UI. Domain
  owners implement adapters to this one permission contract.
- **Intake** owns capture, sources, extraction/review, preview/resume and source
  visibility through native UI and backend/storage. Confirmation calls the
  financial owner. It does not implement its own transaction writer.
- **Conversation/voice** owns inherited chat/cards/history/Temporary chat,
  authorized context and spoken interaction. It preserves the single runtime
  and existing eval gates. D14 redesign is held under its explicit sequence.
- **Native continuity** owns access UI/session, shared navigation/design/chart
  components, Search and Profile/data controls with their existing API owners.
  It owns shared Swift types and localization files, not every feature screen.
  Teams above own their separate feature modules after explicit file allocation.
- **Device/release** owns signing/project configuration, private installation,
  hosted inventory, compatible rollout/migrations execution, secret delivery,
  jobs/operations and rollback. Financial schema design stays with Financial
  core; applying a reviewed migration requires the hosted grant.

The **captain** owns this manifest, dependency handoffs, integration order,
review proportionality, usable builds and founder reporting. An **independent
acceptance owner** runs cross-domain journeys and privacy/recovery checks against
the assembled candidate, including physical-phone demonstrations. Verifiers
return defects to writers. No team is complete merely because its PR merged.

Start available independent work with bounded agents on separate branches.
Use the Mac for Xcode/device work and available VMs for isolated backend/database
work. A VM needs a verified communication channel and checkpoint persistence
before autonomous assignment. Keep shared branches, migration execution and
shared Swift files single-writer. Publish exact branch heads and durable evidence
for handoff; stale chat status is not proof a writer is alive.

## Parallel delivery across the full scope

This is the proposed full-scope sequence, not the current batch authorization.
When separately authorized, activate full-scope ownership from the
coverage table. Begin the device/hosted, financial backend and native core-loop
responsibilities together. Also start independent household membership/invitation,
intake capture/preview, inherited conversation, existing profile/settings and
native navigation/chart work where ownership and inputs permit. These outcomes
do not depend on a completed expense loop. Provider-dependent work proceeds only
within its explicit authority; local implementation/testing continues separately.

The financial owner defines and implements each posting/read contract with its
first consumer. The planning owner can build plan lifecycle and expectations
alongside that work, then connect actual progress when posting/link contracts
are accepted. Household permission design proceeds before shared consumers;
it does not wait for every personal feature. Intake extraction/review proceeds
before financial posting is ready; confirmation must use that shared posting
contract. Search adds one authorized record type at a time; Updates adds one
accepted trigger at a time; controls accompany each domain's lifecycle. Voice
can connect to existing conversation independently of deferred financial actions.

A dependency applies to a specific read, write, permission or acceptance case,
not an entire department. Signing gates phone installation, not backend work.
Posting gates real financial confirmation, not document preview. Household rules
gate sharing, not private records. Plans gate forecasts, not recorded net worth.
No broad pillar-complete gate or new batch authorization is introduced.

Each domain has one accountable owner, a separate writer branch/worktree and
exclusive files. Backend API/data/migration ownership stays with the domain;
consumers do not invent alternate contracts. Native feature writers may work in
parallel on disjoint modules; the native lead alone changes shared session,
navigation and common UI models, while device configuration has its named owner.
Resolve overlapping writes by reassignment before dispatch. Integrate small
working increments continuously through the existing review/merge boundaries.

Independent acceptance starts with the first assembled behavior. Demonstrate
installation, then the financial loop, while other scope continues. Subsequent
builds add linked planning, imports, household and other completed journeys as
their actual dependencies clear, not in a fixed pillar order. Each demo reports
both the exact phone-proven behavior and remaining full-scope coverage. The
captain continues until all non-deferred rows and all five MVEE connected journeys
are accepted on the physical phone. The D14 gap stays visible at that milestone.

## Demonstration checkpoints

These are observable builds, not scope gates or successive authorization batches.
After the early phone connection, order subsequent demonstrations by ready
journeys. Other teams continue while a candidate awaits hosted access or review.

1. **Connected installation.** Existing-user login, reopen and logout work on
   the physical phone away from the Mac. Financial/backend and other independent
   teams continue. This proves access only.
2. **First financial loop.** Establish balance, expense, Account/Home change,
   correction, reconciliation and persistent reopen. Demonstrate known/unknown,
   retry and earlier-activity handling. Plans, household, intake, chat and controls
   continue independently. This does not close the full D03/D05 rows.
3. **Useful connected increments, in parallel.** Show a budget/goal/debt plan
   with recorded progress and forecast; a statement/photo with actual preview,
   reviewed import and resume; a two-person household with explicit sharing and
   revocation; and inherited chat with evidence, Search return and voice. Each
   reaches the same app when verified, without waiting for the other increments.
4. **Complete private candidate.** Demonstrate all five MVEE journeys and all
   non-deferred coverage rows together, including Updates, spaces/assets,
   access completeness, Profile/data controls, Temporary chat, localization,
   accessibility, charts, error recovery and safe app updates.

For every demonstration, identify the app build/commit, backend revision and
configured environment. Record a short live interaction or video showing the
successful action, a failure/recovery and relaunch; use synthetic/redacted
committed evidence. Real founder records are deliberate/authorized only.
Phone acceptance uses the physical iPhone over HTTPS on cellular or another
network with the Mac unavailable. Component tests, simulator runs and screenshots
remain supporting evidence. Backup restoration/rollback are verified in a safe
environment and linked to the deployment candidate, never exercised destructively
on the founder's data. Full private completion requires every applicable row's
acceptance, not merely completion of these demonstrations.

## Status, evidence and handoffs

Use these states on each assigned row: `stopped`, `queued`, `building`,
`verification`, `ready-to-land`, `landed`, `deployed`, `accepted`, `blocked`,
`deferred`. Record a date and reason for a block or deferral. A merged PR is
`landed`, not `accepted`. A deployed backend without phone proof is `deployed`.
`accepted` means the assigned user outcome works in the integrated iPhone build.
No current work row is accepted.

Before dispatch, record these fields in the assigned item or its linked bounded
spec: named owner, exclusive branch/worktree, fetched integration base, MVEE
anchors, reuse pointers, allowed/no-touch files, accepted API/data dependencies,
acceptance checks/commands, timebox, stop conditions and cleanup/handoff duty.
Unfilled fields mean the item is not ready to dispatch. Later changes need a
recorded reason; they must not silently shrink the MVEE outcome.

At each meaningful checkpoint, report two views: what the founder can actually
do on the phone, and what remains across every coverage row, including blocked
decisions and approved deferrals. The first loop never closes the ecosystem.
Update the assigned row and link its PR plus durable
acceptance artifact. Record the commit, app build, backend/environment revision,
checks actually run, reviewer outcome, unresolved findings, next action and any
required founder decision. Keep credentials and real personal documents out.
Use synthetic/redacted evidence for committed acceptance artifacts. Exact-head
and one-way reconciliation rules remain in AGENTS.md.

On restart, read the authority map, MVEE and this manifest. Inspect current GitHub
state, commits and actual process handles. Locate preserved local work. Confirm
one writer per branch before dispatch. A stale conversation, old report or
expired observation is not proof an agent is alive or a feature is complete.
Stop duplicate owners and preserve their unique work before replacement.

Poteto-mode is an available workflow aid, not required undocumented machinery.
Use its Orchestrate/session-recovery routines when available while keeping these
repository-visible pointers sufficient for another coordinator. Runtime work
records must survive the session and be reachable by their assigned local/VM
owners. Do not create a second handwritten product-status board. A scheduler,
store or automated phone acceptance runner has not been installed by this PR.
Their setup is future authorized work, not a claimed current capability.

## Authority and founder involvement

The delivery captain coordinates and verifies; domain owners implement; one
integration owner lands only within the founder's explicit grant. The founder
reviews usable builds and decides product choices, spending, credentials and
hosted/deployment permissions. One execution authorization covers the full assignment. Routine sequencing,
implementation, testing, scoped bug fixes and review triage do not need repeated
founder prompts or successive batch approvals. Merges, hosted changes, deployment
and spending still require the explicit grants recorded for those actions.
Current VM communication still goes through the founder until a direct channel
is explicitly established. Do not claim autonomous VM coordination exists.

No stop instruction, denied approval or missing contract may be bypassed through
another agent. Batch genuine decisions and continue independent authorized work.
Stop affected work for duplicate writers, contradictory contracts, repeated
unproductive failures or scope expansion. Review genuine reachable defects at
their shared cause; stop the review loop at the repository's clean-delta rule.

### Decisions and access that materially affect delivery

These are unresolved inputs, not requests for all answers before work starts.
Recommendations are proposals for review, not approved policy. Owners resolve
routine API/schema/locking choices themselves. They prepare a concrete decision
only when a product choice, access grant or spending authority is necessary.

| Decision or access | Owner and affected work | Recommendation for review; what can continue |
| --- | --- | --- |
| Single execution restart and action authority | Captain; entire assignment | Authorize continuous implementation/build/test/review/branch publication across all non-deferred coverage once the plan is accepted. Merge, signing/install access, hosted mutation/deployment and paid-provider grants remain explicit; no per-pillar restart prompts |
| Apple account/team, physical phone access, stable app identity, supported device/OS and private updates | Device/release; installation and phone acceptance | Inspect existing entitlement/team/device access and choose the shortest supported signed route with a stable identity and repeatable update path. Public App Store release is unnecessary. Device specifics remain unverified; backend and native implementation continue |
| Existing Render/Supabase access, deployed revisions/migrations/capacity and production-compatible rollout | Device/release; hosted proof | Reuse existing project/current plan and compatible Render capacity. Prepare exact migration/settings/candidate, production-web regression evidence, backup/restore and rollback before the hosted grant. No new project or spending by default |
| Financial/private-space recovery window, purge/export behavior and production limits | Financial core + Native continuity; lifecycle controls | Propose the unresolved limits under [account recovery][mvee-activity] and [space lifecycle][mvee-spaces] before release. Ordinary posting can progress |
| Household editing, departure, joint-record custody and recovery | Household; shared writes and revocation | **Founder-approved 2026-10-01:** view-only by default; explicit edit grants; leave/removal revokes membership and that member's grants; owners retain records/history. Further joint custody/export/retention product choices beyond that package remain open. Private journeys progress under MVEE consent boundaries |
| File formats/institutions, OCR, upload/page limits, encrypted files and retention | Intake; extraction/storage | Cover declared PDFs, structured exports and images/photos; select concrete supported samples. Recommend local type/readability checks, private source access and explicit sharing; do not accept unreviewed OCR as fact. Determine limits/provider from bounded synthetic evaluation, then seek any paid/data-handling grant. Do not drop photo/PDF intake because selection is unfinished |
| Notifications, schedule defaults, time zones and monitored external conditions | Planning/Home; delivery and scheduled updates | Recommend a persistent inbox and opt-in private push previews; no financial details outside the authenticated app. Founder selects external channels/defaults. Use existing jobs and sourced conditions; trigger/inbox implementation can progress independently |
| Audio and Temporary chat context/provider retention | Conversation/voice; Temporary behavior and live audio | Recommend no retained raw audio by default; verify provider feasibility and seek approval for unresolved retention under [voice][mvee-voice] and [Temporary chat][mvee-continuity]. Regular native chat can progress |
| Provider credentials, spend caps and consenting data/test identities | Relevant domain + Device/release; live voice/OCR/research/backtest/invite acceptance | Use existing approved providers, server-held secrets and bounded cases/caps. Request credentials via secure configuration, not chat. Use synthetic documents/accounts until real samples and second-user participation are authorized; no broad production data copies |
| VM access and direct coordination | Captain; remote workers | Verify secure connectivity, exact checkout, exclusive writer and pushed checkpoints before remote assignment. Use local agents for ready work until then; do not make additional machines a prerequisite |
| D14 activation | Captain + Conversation/voice | Respect the founder-approved runtime sequence. Keep its unmet action parity visible and request the separate runtime assignment when its prerequisites are satisfied; do not use it to defer ordinary voice, manual workflows or financial read-context |


Use the canonical disposition links above when assigning work. This documentation
change does not activate implementation or any held integration.
