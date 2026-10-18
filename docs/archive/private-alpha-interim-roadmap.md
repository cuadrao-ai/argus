# Private Alpha Interim Roadmap

Status: **ARCHIVED 2026-08-06 — COMPLETE.** The interim private-alpha pivot
finished with the 2026-08-05 production promotion. Active board is
[`docs/specs/argus-active-roadmap.md`](../specs/argus-active-roadmap.md).

Original roadmap date: 2026-07-16

Last reconciled: 2026-07-31

Latest integrated product changes: PR #331 at `ec3a0a52` and PR #330 at
`94476226`. Later commits may reconcile roadmap and issue state without changing
product behavior. New work must branch from the current remote integration head
rather than pinning either product SHA.

That checkpoint contains the founder-accepted outcome baselines delivered
through independently revertible vertical slices:

- adaptive result-chart range switching from PR #264 at `0c0d481`;
- account recovery and session controls from PR #261 at `a639566`;
- truthful Usage allowances and accounting from PR #259 at `2eb6874`;
- executable capability truth from PR #266, with final candidate `e10bdd2` and
  integration merge `bbd1d2b`; and
- the Always Progresses continuity baseline from PR #268 at `847c413`; and
- the default-on grounded-discovery baseline from PR #276, candidate
  `cc8b5563`, merged as `c212107a`.

The checkpoint also contains the bounded calendar-materiality correction from
PR #267 at `d6d1134` and the environment-documentation checkpoint at
`b7fd6f08`. Since that checkpoint, integration also received the chat-header
title/owner-menu correction from PR #274 at `291b58f7`, removal of the explicit
private-alpha onboarding product from PR #275 at `88ae8c77`, and truthful stale
Run settlement from PR #277 at `2d5a2b52`. Supported strategy transitions
through confirmation then landed from PR #278 at `b80d95a2`.
Modeled-cost preservation landed from PR #280 at `d16f7496`, followed by the
Guest experience from PR #279 at `53e812e9` and chat next-move presentation
from PR #281 at `8fde4ac1`. PR #282 then made ordinary backend tests
provider-free and added the alpha API suites to CI at `059f8e82`; PR #286 made
the complete backend `tests/` directory the required CI gate at `75e87206`.
PR #287 then delivered resolver-owned discovery selection identity and
candidate/entity corroboration at `ea2b3f35`. The two CI landings improve
verification truth without changing product behavior; PR #287 changes the
discovery selection and validation path. PR #285 then landed bounded Postgres
pagination and search at `7b7920bb` for Conversations, Messages, History, and
Omnisearch/Idea Ledger without changing public cursor, ranking, ownership, or
artifact contracts. Issue #232 is complete. Its accepted sparse/deep/final
History Run scan exception remains an explicit private-alpha boundary. PR #288
then landed canonical fact-preserving recovery at `9f3453a3`: stale or failed
actions restore the latest usable artifact anchor, already-owned facts are not
re-requested, genuinely absent facts receive one targeted clarification, and
prior results remain immutable without duplicate compute.
PR #298 later completed the Grounded Discovery/Guest second pass at `ba0aa2f6`:
visitor/day settlement survives temporary-session renewal, Search and
verification progress are truthful runtime events, and each discovery row owns
its citation action. Issue #293 closed with no-defect evidence after a real
guest session crossed the one-hour JWT boundary without losing its conversation
or workspace.
PR #299 then completed issue #252 as `f368febb`: conversation selection and URL
identity update immediately, fresh and stale transcripts render from the
bounded browser-session cache, cold misses use one delayed truthful retrieval
surface, retired requests cannot overwrite the newest destination, and
destination-owned Retry, scroll, auth clearing, localization, and accessibility
survive the exact-head browser matrix. No durable browser storage, prefetch,
virtualization, backend contract, or provider path was added.
PR #300 then landed comparison grounding and discovery-act continuity as
`c21f842f`: company names reach provider-backed resolution, unsupported named
comparison targets reconcile to the class default with a localized pinned
disclosure, and a discovery ask cannot be captured by a pending confirmation.
Issues #292 and #296 are closed. PR #302 completed issue #245 as `928dcdbb`:
Recents now uses bounded chat-only pages, caps each loaded unpinned time group
at five until explicitly expanded, and replaces silent scroll pagination with
an accessible single-flight Load older action while preserving PR #299's
switching and race guarantees. PR #303 then closed #301 as `da9f8500`: a
catalog-valid benchmark with an explicit zero-bars response reconciles at card
time to the class default instead of failing later with misleading recovery.
PR #304 then completed issue #249 as `59a274c3`: Quick take, Explain result,
Try next, and recoverable failure now have distinct typed owners. Completed
results carry capped, result-aware Try next rows; Explain contains only
grounded comprehension; retryable composition failures resolve in place; and
the same roles survive durable jobs, reload, English, and Spanish.
PR #305 then completed issue #253 as `88ab906d`: decision recall now leads with
the current decision state and the user's exact note, projects only canonical
evidence facts, refreshes after mutation, and keeps the decision-first panel
usable in English, Spanish, desktop, mobile, and keyboard navigation without
hover-time generation. PR #306 completed founder outcome 6 as `b71f1eaf`:
Omnisearch now returns one ranked row per conversation, searches bounded full
transcripts with object-first ranking and jump-to-match, projects deterministic
conversation dossiers and asset-history rollups, supports exact decision
filters and mutation, and offers provider-free **Run it fresh** composition
that stops at the ordinary Ready-to-run confirmation. Its memory and Postgres
paths preserve owner scope, bounded reads, cursor order, deletion refresh, and
the integrated #232/#252 contracts.
PR #316 then completed issue #309 as `9aa209d4`: one evidence-backed run anchors
each dossier, prior finalized runs load through bounded Decision history, and
decision edits refresh canonical truth without adding a durable dossier model
or provider work. PR #318 completed issue #313's founder-corrected recovery
ownership as `f6d0981e`, followed by test isolation at `1ed8d4f0`. PR #315
added the current-conversation activity rail as `6e20328c`, and PR #317 added
the centralized localized keyboard overlay and quick-navigation system as
`2ff6f3c6`. Cmd/Ctrl+K remains Omnisearch; rename remains F2 on macOS and
Windows/Linux. PR #324 then aligned Recents quick-jump hints with that shared
registry as `812c8fef`, and PR #311 closed issue #310 as `51984a42` with a
typed, provider-free **Retest with current data** action that reloads canonical
run truth and stops at the ordinary confirmation. These navigation/retest
surfaces do not add provider work or automatic execution.

The 2026-08-01 integration group then added registered-only avatar themes
(PR #312, `40eba1f6`), public-alpha technical readiness and recorded hosted
capacity/email evidence (PR #319, `1c3775aa`), one frontend failure vocabulary
(PR #320, `53c36d40`), bounded auth copy/error/card corrections (PRs #323,
#325, and #328), and the honest removal of the unavailable Release Notes row
(PR #327). Permanent account access remains explicitly disabled and founder
controlled. PR #329 added the durable backend/data conversation-activity and
read-state foundation as `8a5d621b`; PR #331 completed the chat/Recents UI
consumer as `ec3a0a52`, including manually unread controls and durable activity
projection. Its hosted migration application remains later promotion work. PR
#326 closed issue #321 as `8e2a6217` with bounded Turnstile acquisition and an
accessible localized interactive challenge. PR #330 then completed deferred
Guest bootstrap as `94476226`, moving anonymous identity and CAPTCHA acquisition
to first submission while preserving the integrated activity contract.

Two issue closures after that product checkpoint required no new application
commit. Issue #251 is closed: PRs #262, #267, and #268 collectively own
requested/effective period truth, calendar-materiality classification, and
durable recovery. PR #297 then reconciled the concrete trajectory ledger as
`09044231`: the obsolete #241 and #251 masks are removed, #239 retains only its
exact open-owner failures, and issue #243 is closed. Promotion evidence remains
exclusively with #233. Issue #246 is also closed after the exact checked-in
`20260702000001_add_cost_ledger_entries` migration was applied to the hosted
Argus Supabase project and its append-only service-role contract was verified.

PR #289 then landed the structural OpenAPI compatibility gate as `8a66f0ba`.
Generated FastAPI structure remains the machine-readable authority; the checked
artifact is regenerated from that authority and CI compares normalized paths,
methods, parameters, request/response schemas, required fields, and enums with
only the three approved internal/dev exclusions. Issue #234 is closed. PR #290
then landed the approved request-size and correlated RFC 9457 failure boundary
as `b073b1a0`; issue #235 is also closed.

Frozen archaeological reference: `claude/argus-alpha-audit-c2d919` at
`f1d03a1d847628e6a8d681b22337ad5fc6c5ebfd`. It is retained for exact historical
comparison only, not as an active donor or implementation base for the remaining
outcomes.

Last promoted `main` checkpoint: functional promotion merge `5d1eec11`, with
the [production-promotion record](https://github.com/lagarcess/argus/blob/main/docs/release-manifests/2026-07-14-main-production-promotion.md)
completed on `main` at `217ead12`.

This is the bounded pivot between the latest `main` promotion and the remaining
P2 compounding loop in
[`private-alpha-next-roadmap.md`](../specs/private-alpha-next-roadmap.md). Existing
issues #228 through #253 are supporting evidence and possible implementation
material, not the roadmap itself. #213 remains excluded.

The roadmap does not authorize implementation by itself. The founder selects a
user outcome. A fresh vertical slice then proves that outcome against the
latest integration checkpoint.

## Authoritative Founder Outcomes

These six outcomes are the interim roadmap:

1. **Argus always progresses.** A conversation never becomes trapped in a
   semantic loop, repeated recovery, unexplained terminal state, or
   deterministic cul-de-sac. Every accepted turn makes meaningful progress or
   gives the user a clear, actionable stopping point.
2. **Security and usage are unlocked for users.** Users can reach account
   security and session controls and can see truthful usage, remaining
   allowance, what counts, and when it resets.
3. **Graphs have range switching.** Users can change the visible result range
   without changing the approved backtest, corrupting the effective data
   window, or seeing frontend-invented facts.
4. **Argus knows what it can and cannot do.** It distinguishes supported,
   unsupported, and not-yet-supported requests without overpromising and helps
   the user reach a supported next step.
5. **Discovery is grounded and Argus can suggest.** Search and suggestions are
   source-backed, provider-validated where required, and limited to actions
   Argus can actually support.
6. **Omnisearch lives up to its full capability.** Omnisearch provides useful
   unified retrieval and navigation across the user's Argus artifacts, with
   truthful previews and actionable results.

### Current Completion Ledger

This ledger records accepted user-visible behavior, not issue activity or a
deterministic test result by itself.

| Founder outcome | State | Completion evidence |
| --- | --- | --- |
| 1. Argus always progresses | **Baseline delivered; standing quality bar** | PR #268 delivered bounded semantic progress, durable ordinary-turn recovery, exact-once Run reconciliation, stale-authority rejection, fact-preserving refinement, concrete trajectory adapters, EN/ES browser proof, one authorized real Run, and reload-stable result truth. Reviewed head `5585c6a` landed on integration as `847c413b`. PR #304 later closed the bounded result/recovery presentation follow-up as `59a274c3`. Later reproduced defects receive bounded follow-ups; they do not reopen an unbounded search for every possible conversational edge case. |
| 2. Security and usage are unlocked | **Complete** | #248/PR #261 delivered reachable recovery, password, and current/other/all-session controls with real Supabase Auth QA. #247/PR #259 delivered reachable Settings -> Usage, backend-owned hourly/daily message and simulation truth, exact reset instants, durable exactly-once accounting, EN/ES desktop/mobile behavior, and exact-head real-auth/local-persistence QA. |
| 3. Graphs have range switching | **Complete** | #250/PR #264 delivered adaptive presets, Custom/Reset, daily/intraday presentation, EN/ES desktop/mobile browser proof, reload-to-ALL, immutable full-run truth, and zero range-interaction network calls. |
| 4. Argus knows what it can and cannot do | **Complete** | #241/PR #266 proved supported golden-cross execution, fail-closed momentum-breakout and news-sentiment recovery, the general future-performance boundary, compatible fact preservation, explicit supported-alternative selection, localized Quick take, and exact-head founder-visible browser QA. Candidate `e10bdd2` landed as `bbd1d2b`. |
| 5. Discovery is grounded and Argus can suggest | **Integrated product work complete; deployment closure open** | #244/PR #276 delivered typed explicit discovery, bounded source-backed Search, provider-resolved candidates across supported asset classes, persisted EN/ES discovery UI, honest kill-switch recovery, provider accounting, review, browser QA, and locked eval cases. Candidate `cc8b5563` landed as `c212107a`; integration policy now treats the flag as a default-on emergency kill switch. PR #281 landed the presentation (`8fde4ac1`), PR #287 the selection identity plus ticker-collision correction (`ea2b3f35`), PR #295 cheap verified rows and the Search exception (`8f17a45e`), and PR #298 visitor/day Guest settlement, honest live progress, and per-row citations (`ba0aa2f6`). PR #300 then completed comparison phrasing, named-target grounding, unsupported-target disclosure, and pending-confirmation discovery continuity (`c21f842f`); PR #303 completed catalog-valid benchmark coverage reconciliation (`da9f8500`); PR #304 added capped, result-aware, typed Try next rows with distinct surface ownership (`59a274c3`). #244 remains open only for the accepted exposure-vehicle product decision plus hosted migrations, Render configuration, and exact-SHA canary evidence before tester exposure. |
| 6. Omnisearch lives up to its full capability | **Complete** | PR #305 completed the issue #253 decision-first recall slice as `88ab906d`. PR #306 then delivered the founder-locked full memory-inspector journey as `b71f1eaf`: one conversation row, object-first full-transcript recall, jump-to-match, deterministic dossiers, asset-history rollups, exact decision filters/counts, mutation refresh, and provider-free **Run it fresh** composition. PR #316 extended that accepted surface with bounded run-anchored dossier history and canonical effective-decision editing as `9aa209d4`, closing #309 without a new durable model or provider path. PR #311 then replaced prompt composition with the typed provider-free **Retest with current data** confirmation action as `51984a42`, closing #310. The accepted EN/ES desktop/mobile browser matrices, memory/Postgres parity, bounded-read tests, exact-head CI, and zero LLM/provider search path close this outcome without adding RAG or embeddings. |

Outcomes 2, 3, 4, and 6 must not be redispatched unless a new regression is
reproduced. Outcome 5's merged baseline must not be duplicated; its open work
is limited to the recorded exposure-vehicle decision and pre-activation gates.
Outcome 1 is a standing quality bar applied to each later slice: fix a
reproduced violation at its owner, but do not redispatch a broad, open-ended
continuity program. Existing evidence remains the regression baseline.

### Current Integration Additions And Remaining Work — 2026-08-01

| Surface | Integrated state | Exact remainder |
| --- | --- | --- |
| Public-alpha technical readiness | PR #319 landed as `1c3775aa` with capped hosted provider-key policy, measured capacity, requested access, delivered approval email, CAPTCHA wiring, and durable hosted evidence. | Keep permanent-account access disabled until the founder opens it. #233 still owns the one exact-candidate deployed Spanish Golden Path and release evidence; integration does not substitute for that promotion gate. |
| Conversation activity/read state | PR #329 landed the backend, additive schema, RLS, batch projection, strict cursor, and GET/PATCH contracts as `8a5d621b`; PR #331 completed the chat/Recents UI consumer as `ec3a0a52`. | Apply and read back the #329 migration only at an authorized hosted promotion checkpoint. |
| Guest bootstrap timing | PR #326 completed the bounded CAPTCHA boundary as `8e2a6217`; PR #330 completed first-submit Guest bootstrap as `94476226` while preserving durable activity ownership. | No integration implementation remains; tester exposure still follows the ordinary promotion/canary gates. |
| Rejected artifact-action evidence | Typed retest and current rejection behavior are integrated and allowance-safe. | Issue #314 remains open for one complete operational-evidence record across every rejected artifact-action admission site, without changing HTTP responses, visible transcript, or allowance settlement. |
| Parked/deferred work | Personalization memory PR #307 remains parked outside the interim; #236 remains a deferred behavior-preserving router extraction; #294 waits for real post-promotion funnel data. | Do not dispatch these as current interim blockers. |

No completed issue-level continuity or Omnisearch lane should be repeated for
promotion ceremony. The open coordination issues #228 and #237 remain release
owners only because #233's deployed exact-SHA browser proof is still open.

The bounded [Always Progresses closure evidence](../reports/always-progresses-closure-evidence.md)
remains valid. The
[same-conversation stress audit](../reports/2026-07-25-always-progresses-post-merge-stress-audit.md)
and [guest post-integration runtime observation](../reports/2026-07-25-guest-post-integration-runtime-regression.md)
record later signals without assigning unproven causality or authorizing a
broad repair lane.

### Continuity Follow-up Ownership Queues

These issues are bounded follow-ups to reproduced post-merge findings. They do
not reopen the completed Always Progresses baseline as one broad runtime
program.

The three ownership queues may run independently when their files and
canonical owners remain distinct. Issues **within one queue execute serially**
in the order below. After an issue lands, the next issue starts from the
updated integration checkpoint rather than stacking unreviewed worker branches.
This is shared-owner serialization, not a native GitHub `blocked-by` graph.

#### Runtime reliability

1. [#269 — Diagnose ordinary starter failures at the call ceiling](https://github.com/lagarcess/argus/issues/269)
   is **classified, fixed, and landed with Guest PR #279 at `53e812e9`**.
   The seven receipts covered two Guest requests rather than one exhausted
   turn. Guest terminal settlement failed while serializing the
   `guest_session` allowance; Guest commit `5adff1f4` owns the correction.
   Integration runtime policy, the seven-call allowance, provider routing, and
   fallback accounting were exonerated. Issue #269 is closed; this does not
   justify another runtime lane.

This queue is no longer an implementation queue. Guest public exposure remains
separately gated by the launch-safety register below. Do not open a second #269
runtime lane.

#### Protected interpreter/edit spine

Execute serially:

1. [#270 — Preserve supported strategy transitions through confirmation](https://github.com/lagarcess/argus/issues/270)
   is **complete**. PR #278 landed as `b80d95a2`; its eight acceptance criteria
   were reconciled and #270 is closed.
2. [#271 — Preserve modeled costs across asset edits](https://github.com/lagarcess/argus/issues/271).
   This is **complete**. PR #280 landed as `d16f7496` after proving cost
   preservation, evidence-owned natural-language and card edits, explicit
   zero, date/asset edits, launch agreement, and reload in its bounded
   same-chat integration journey.
3. [#272 — Recover without re-asking facts the conversation owns](https://github.com/lagarcess/argus/issues/272).
   This is **complete**. PR #288 landed as `9f3453a3`; canonical recovery
   restores the latest usable anchor, preserves its owned facts through reload
   and later edits, asks only for genuinely missing fields, keeps the prior
   result immutable, and creates no duplicate compute.

The protected interpreter/edit-spine queue is complete and #270–#272 are
closed. Any repetition of these journeys belongs to a later promotion
qualification checkpoint, not another issue-level implementation gate. Do not
combine these issues into another open-ended continuity rewrite.

#### Artifact lifecycle and presentation

Execute serially:

1. [#273 — Settle stale Run rejection to the latest usable artifact](https://github.com/lagarcess/argus/issues/273)
   is **complete**. PR #277 landed as `2d5a2b52`; all eight acceptance criteria
   were reconciled and #273 is closed.
2. [#249 — Restore result and recovery surface ownership](https://github.com/lagarcess/argus/issues/249)
   is **complete**. PR #304 landed as `59a274c3`: Quick take owns the glance
   readout, Explain result owns grounded comprehension, stacked typed rows own
   Try next, and generic recoverable failures render as failures rather than
   result prose. Retry resolves in place, jobs and reload preserve the same
   ownership, and English/Spanish surfaces passed the accepted lane evidence.

Issue #249 preserved the stress-audit lineage without duplicating presentation
ownership. The delivered correction covers:

- `TRY NEXT` / `WHAT HAPPENED` leakage on generic recovery;
- compact recovery parity between ownership paths;
- malformed option presentation; and
- Quick take structure and accessibility without pinning model prose.

[Coordination issue #237](https://github.com/lagarcess/argus/issues/237)
records all three queues. Lineage notes on #238, #239, and #242 preserve the
relationship to delivered work without reopening those completed boundaries.
Each correction still requires exact-head browser QA and integration
reverification before its issue can close.

### Next Ownership Handoffs

This is the current dispatch gate, not another speculative backlog:

| Ownership lane | Current owner | Next handoff |
| --- | --- | --- |
| Runtime reliability | #269 correction landed inside Guest PR #279 at `53e812e9`; #269 is closed | No runtime lane remains. |
| Protected interpreter/edit spine | #270–#272 are closed; #271 landed through PR #280 at `d16f7496` | No additional spine implementation lane is queued. Repeat representative journeys only at promotion qualification. |
| Artifact lifecycle and presentation | PR #304 completed #249 as `59a274c3` after preserving Guest hydration, conversation switching, and bounded Recents | No implementation lane remains in this queue. Reopen only for a newly reproduced owner-scoped defect. |
| Grounded discovery | PR #276 landed as `c212107a`; presentation PR #281 as `8fde4ac1`; selection identity/corroboration PR #287 as `ea2b3f35`; Guest allowance PR #291 as `f1e65dde`; cheap verified rows/Search-exception PR #295 as `8f17a45e`; live-progress/Guest-identity PR #298 as `ba0aa2f6`; comparison grounding/discovery continuity PR #300 as `c21f842f`; and benchmark price-coverage reconciliation PR #303 as `da9f8500`. Integration defaults on and #244 remains open. | Do not duplicate the landed implementation. Comparison work is complete. Keep only the exposure-vehicle product decision separately bounded; configure the hosted migrations/Render environment and prove the exact deployed SHA/canary. |
| Chat next-move presentation | PR #281 landed as `8fde4ac1` (stacked rows, sources panel, shared in-flight lock); PR #287 landed as `ea2b3f35` (Slice D: discovery selection carries the resolver's identity, plus a resolution-corroboration fix); PR #295 delivered the provider-offload prerequisite for Slice B; PR #298 landed Slice B's truthful Search/verification progress and per-row citation ownership. | Slices B and D are closed. Do not reopen this presentation arc without a new reproduced defect. |
| Discovery candidate resolution | PR #287 corrected a ticker-collision defect: a resolved candidate must now corroborate the entity the sources named, so a gold miner is no longer offered for a Tron question | Known limitation accepted and recorded in `docs/superpowers/specs/2026-07-25-grounded-discovery-search-v1-design.md` §5.1: crypto-exposure ETFs are dropped alongside true collisions because the two are structurally indistinguishable to a token check. Surfacing exposure vehicles deliberately is real product value and needs its own design. Owned by #244. |
| Guest grounded discovery | PR #291 landed the visitor/global discovery allowance at `f1e65dde`; PR #295 landed the cheap verified default and Search exception at `8f17a45e`; PR #298 landed visitor/day message and simulation settlement at `ba0aa2f6`. | Identity/lifetime implementation is complete. The additive `20260727230000_add_visitor_usage_counters.sql` and `20260728120000_visitor_keyed_guest_settlement.sql` migrations plus `ARGUS_DISCOVERY_GLOBAL_DAILY_CEILING` configuration remain promotion gates. #244 stays open. |
| Full Omnisearch | PR #305 completed issue #253 as `88ab906d`; PR #306 completed the founder-locked memory-inspector journey as `b71f1eaf` | No Omnisearch implementation lane remains. Preserve one-row-per-conversation recall, bounded deterministic dossiers, asset rollups, exact decision filters, mutation refresh, jump-to-match, and provider-free **Run it fresh** composition. Reopen only for a newly reproduced owner-scoped defect. |

No bounded continuity or Omnisearch implementation lane remains. The protected
interpreter/edit-spine, artifact-presentation, and full-recall queues are
closed; do not reopen them without a new reproduction. Remaining interim work
is limited to issue #244's separately bounded exposure-vehicle decision and
hosted activation register, plus the exact-candidate promotion evidence owned
by #228/#233/#237.

### Guest Main-Promotion And Public-Exposure Register

**Register executed 2026-08-05.** Promotion to `main` and production
deployment completed at `7ef89a90` with founder go/no-go and a recorded
browser-automation deviation; see
[`docs/release-manifests/2026-08-05-main-production-promotion.md`](../release-manifests/2026-08-05-main-production-promotion.md)
and the roadmap's "Production promotion complete" section. The 2-4 week
guest-canary/public-exposure observation window is now open. The checklist
below is preserved as the template for future promotions.

Guest code is integrated, not deployed or publicly exposed. The checked-in
product defaults are `ARGUS_GUEST_ACCESS_ENABLED=true` and
`NEXT_PUBLIC_GUEST_ACCESS_ENABLED=true`, with explicit `false` as rollback.
`ARGUS_PUBLIC_ACCOUNT_ACCESS_ENABLED=false` remains the separate permanent
account gate.

Before promotion to `main` or any internet-facing Guest traffic, the release
captain must:

1. validate the exact promotion SHA on the branch-deployed staging/private-alpha
   surface and retain the canary evidence;
2. configure hosted Supabase anonymous Auth and server-validated Turnstile,
   including `NEXT_PUBLIC_ARGUS_TURNSTILE_SITE_KEY`;
3. prove trusted-origin/client-IP handling, the Guest bootstrap limiter, owner
   isolation, replay safety, and global capacity rejection;
4. set a hard provider spending limit and record the accepted daily budget,
   first traffic cohort, monitoring owner, and alert destination;
5. schedule bounded Guest cleanup with an accountable owner and prove dry-run,
   deletion, converted-account protection, and failure alerting;
6. complete the release manifest and obtain founder go/no-go approval.

The authoritative operational checklist is
[`docs/GUEST_PUBLIC_LAUNCH_SAFETY.md`](../GUEST_PUBLIC_LAUNCH_SAFETY.md).
Execution commands and rollback order live in
[`docs/PRIVATE_LAUNCH_RUNBOOK.md`](../PRIVATE_LAUNCH_RUNBOOK.md), and the
promotion record uses
[`docs/release-manifests/TEMPLATE.md`](../release-manifests/TEMPLATE.md).

## Product Relationships, Not An Issue Order

```mermaid
flowchart LR
    LIVE["Argus always progresses — baseline delivered / standing bar"]
    ACCESS["Security and usage unlocked — complete"]
    RANGE["Graph range switching — complete"]
    TRUTH["Capability truth — complete"]
    DISCOVERY["Grounded discovery and suggestions"]
    OMNI["Full Omnisearch capability"]

    LIVE -. "applies to every conversational slice" .-> TRUTH
    LIVE -. "applies to every conversational slice" .-> DISCOVERY
    LIVE -. "applies to every conversational slice" .-> OMNI
    TRUTH --> DISCOVERY --> OMNI
```

Capability truth is a product prerequisite for grounded suggestions. Grounded
discovery is a product prerequisite for complete Omnisearch. Progress behavior
applies across all conversational work. This relationship does not prescribe
an issue order or require one giant implementation lane.

## Vertical-Slice Delivery Contract

For each founder-selected outcome:

1. name one complete user-visible journey and its expected behavior;
2. reproduce that journey on the latest stable integration checkpoint;
3. branch from that checkpoint and change only what the journey requires;
4. salvage donor code only when a specific hunk remains correct and useful;
5. run focused deterministic checks and production-parity local browser QA,
   including persistence and reload where the journey uses them;
6. compare the candidate with the integration baseline and reject regressions;
7. present the working behavior to the founder or private-alpha users before
   promotion;
8. record the exact candidate and merge SHAs, rollback boundary, and any later
   tester-exposure gates.

An issue can provide evidence or requirements. It is not the unit of completion
unless the selected slice explicitly makes it so.

### Live QA Is Required Before Merge

Deterministic tests prove contracts; they do not prove the product experience.
Every vertical slice requires live QA proportional to its surface:

- auth, history, and UI work uses real auth and verifies interaction,
  persistence, navigation, and reload where applicable;
- conversational runtime work uses real prompts and inspects the visible
  response, hidden typed state, recovery, and reload;
- backtest work completes the relevant approval, execution, result, and reload
  journey with real provider data;
- contract work starts the production-parity API and compares the generated
  contract before browser smoke.

An exact deployed canary is a later tester-exposure gate when the founder is
preparing a candidate for users. It does not replace slice-local QA.

### Guardrail Ratchet

Keep the minimum guardrails required for security, privacy, correct accounting,
durable state, grounded evidence, and duplicate-execution prevention. Do not
add speculative strictness that blocks the Golden Path. Tighten further in
response to observed user or operational evidence.

## Source Order

Every implementation owner reads, in order:

1. `AGENTS.md`
2. `docs/PRODUCT.md`
3. `docs/ARCHITECTURE.md`
4. `docs/API_CONTRACT.md`
5. `docs/DATA_MODEL.md`
6. `.agent/designs/argus/DESIGN.md`
7. this roadmap
8. the founder-selected vertical-slice brief
9. related issues as supporting evidence
10. relevant sections of `docs/specs/private-alpha-next-decision-memo.md`
11. release references only when the slice touches release evidence

Canon wins if sources conflict. The selected slice owns its journey, allowed
surfaces, no-touch areas, and acceptance evidence.

## Checkpoint And Salvage Discipline

The integration branch is the stable working checkpoint. Known corner cases do
not invalidate it or authorize unrelated scope expansion.

The audit donor records useful experiments and failure evidence, but it is not
an integration candidate. Never merge it wholesale. For each selected slice:

1. create a fresh branch from the latest integration SHA;
2. map donor code to the selected user journey;
3. reuse only dependency-clean commits or the smallest justified hunks;
4. prove the complete journey and relevant regressions;
5. merge one reviewed, revertible slice into integration;
6. update this checkpoint before selecting another slice.

Parallel investigation is allowed on genuinely independent surfaces. Shared
runtime, API, database, and web-shell changes integrate one owner at a time.

## Current Remaining Outcomes

The founder chooses among the remaining outcomes; this table is not an
implementation queue.

| Outcome | Product proof still required |
| --- | --- |
| Grounded discovery and suggestions | The default-on baseline, presentation, selection identity, Guest allowances, cheap verified rows/Search exception, honest live progress, per-row citations, comparison grounding, and benchmark coverage reconciliation are merged through PR #303. Keep #244 open only for the exposure-vehicle product decision plus hosted migrations/configuration and the exact-SHA canary. |
| Full Omnisearch | Owner-scoped conversations, results, decisions, and evidence are retrievable with truthful previews and useful navigation. |

Do not select the next slice from the archived issue dependency graph. Select
it by user value, regression risk, and the smallest complete live journey.

### Completed slice: Capability truth

Status: **COMPLETE — PR #266 merged as `bbd1d2b`; issue #241 closed**

The completed vertical-slice contract is archived at
[`2026-07-22-capability-truth-executable-boundary-design.md`](../archive/2026-07-22-capability-truth-executable-boundary-design.md).
The original path remains as a compatibility pointer for existing issue and PR
links. [Issue #241](https://github.com/lagarcess/argus/issues/241) and
[PR #266](https://github.com/lagarcess/argus/pull/266) contain the detailed
implementation and review evidence.

This is acceptance and narrow gap-closing for the founder outcome, not a rebuild
of the completed P2.1 registry work.

The slice proves four end-to-end classes: a supported golden-cross control, a
recognized but non-executable momentum-breakout request, an unsupported external
news-sentiment rule, and the general future-performance boundary. The last class
applies to any asset, strategy, amount, language, or future horizon. Argus says
it cannot predict future performance and separately offers a supported
historical test. Only an explicit user choice creates the historical draft;
compatible asset and capital facts carry forward, while a future horizon never
silently becomes a historical date range.

This slice adds no forecasting engine, Search/discovery behavior, strategy,
indicator, provider, or second capability registry. If exact-head reproduction
is already correct, align tests and evidence only rather than manufacturing a
runtime change.

Completion evidence:

- deterministic runtime, registry, mocked-eval, frontend, modularity, and CI
  gates passed on the candidate family;
- the sanctioned interpreter suite passed 27/27 at `497e2b8`;
- the final bounded correction passed independent review and exact-head
  founder-visible browser QA at `e10bdd2`;
- supported golden cross reached the ordinary confirmation/result path;
- momentum breakout, news sentiment, and future-performance requests remained
  non-executable and useful, with compatible facts preserved;
- an explicit supported alternative plus historical period produced the correct
  confirmation without carrying stale unsupported identity; and
- the founder approved merge, PR #266 landed as `bbd1d2b`, and issue #241
  closed as completed.

### Completed slice: Argus always progresses

Status: **BASELINE DELIVERED — PR #268 merged as `847c413b`; standing quality
bar remains active**

This pillar protects every later conversational surface.
The founder-approved end-to-end contract is
[`2026-07-23-always-progresses-continuity-design.md`](https://github.com/lagarcess/argus/blob/651870a54be4e5506dbb38f3902fef1a97eef8df/docs/superpowers/specs/2026-07-23-always-progresses-continuity-design.md).
The serialized execution plan is
[`2026-07-23-always-progresses-continuity.md`](https://github.com/lagarcess/argus/blob/651870a54be4e5506dbb38f3902fef1a97eef8df/docs/superpowers/plans/2026-07-23-always-progresses-continuity.md).
Together they require every accepted operation to advance typed state or reach
a clear, actionable stopping point across clarification, confirmation, Run,
result, retry, and reload.

Completion evidence:

- one turn-wide deadline, model-call allowance, semantic progress assessment,
  and first-wins internal terminal;
- durable accepted-turn lifecycle with owner-scoped reconciliation, adjacent
  Retry, supersession, and reload projection;
- server-owned response-option Retry and Run-action identity with exact replay,
  collision rejection, and no duplicate job, Run, action bubble, usage charge,
  or result;
- founder-visible production-parity journeys for clarification, edited
  confirmation, one real Run, ambiguous transport, ordinary failure and Retry,
  stale authority, no-progress recovery, result refinement, Spanish recovery,
  and reload;
- disposable-Postgres lifecycle/RLS/accounting proof, concrete runtime
  trajectory adapters, the zero-provider browser harness, the sanctioned
  interpreter scorecard, independent review, and exact-head CI; and
- reviewed PR head `5585c6a` merged into `codex/private-alpha-next` as
  `847c413b`, with byte-equivalent trees.

This completion does not claim deployment or tester exposure. #228, #233, and
#237 retain those release-owned gates. #239's exact dedicated trajectory
failures remain open. PR #297 completed the separate trajectory-ledger
reconciliation as `09044231`, removing stale #241/#251 ownership without
weakening the remaining #239 mask; issue #243 is closed. #251 remains closed;
promotion and evaluation bookkeeping must not reopen its completed product
scope.

## Retained Product Decisions

### Usage allowance (#247 — complete)

- Alpha uses backend-owned UTC calendar windows: messages are limited to 60
  per hour and 200 per day; simulations are limited to 10 per hour and 50 per
  day. These are operating limits, not pricing.
- The authenticated read contract returns both windows, exact `period_end`,
  and backend-derived `available_now` and limiting-window truth.
- Count one message only when an accepted turn reaches a durable substantive
  terminal product outcome. Malformed, unauthenticated, duplicate-replay,
  abandoned, and infrastructure-failed turns count zero.
- Count one simulation at first successful unique durable admission. Replays
  and pre-admission rejections count zero. A later execution failure does not
  erase the admitted unit.
- Chat and direct launches share the accounting rule.
- The frontend localizes backend reset instants and never derives quota truth.
- Billing, plans, credits, provider/model tokens, and internal CostLedger data
  remain out of scope.

Before tester exposure, the target environment must receive migrations through
`20260722000004`, enable `ARGUS_BACKTEST_JOBS_SHADOW_ENABLED=true`, and pass an
exact-SHA canary. Those are exposure gates, not reasons to reopen #247 or block
its integration completion.

The pre-existing stale direct-job GET reconciliation gap remains tracked by
#231; #230 owns any atomic database primitive it requires. It is not part of
the completed user-visible Usage slice.

### Requested/effective data-window truth (#251 — complete)

- PR #262 established one requested/effective coverage contract across
  confirmation, execution, result, persistence, evidence, and reload.
- PR #267 added the code-owned `adjustment_reason`, distinguishes ordinary
  exchange-calendar alignment from provider-driven truncation, and emits the
  period-adjustment sidecar only for material provider-driven changes.
- PR #268 preserves the resulting artifact and recovery ownership through
  continued conversation and reload.
- Fit to provider-supported data only when a viable common window remains; a
  material fit must not be silent.
- Ordinary weekend or holiday session normalization inside available coverage
  shows no warning.
- A material head or tail correction is explained in provider-neutral language
  immediately before the confirmation card. Preserve the LLM-authored voice
  through stream and reload; deterministic localized copy is degraded fallback.
- The card shows effective dates while requested dates remain durable
  provenance.
- Preflight consumes no simulation unit.
- If no viable common window exists, return typed recovery and no runnable card.
- The approved effective window remains identical across result facts, chart,
  prose, evidence, reload, replay, and Omnisearch.
- Founder-visible QA confirmed the product behavior in real conversation turns,
  and issue #251 is closed. Exact-SHA promotion/canary evidence remains #233
  work. PR #297 completed the seven-session expected-failure bookkeeping at
  `09044231`; issue #243 is closed.

### Cost-ledger visibility (#246 — complete)

- The hosted Argus Supabase project had skipped the existing
  `20260702000001_add_cost_ledger_entries` migration; the table had never been
  intentionally removed.
- On 2026-07-27, the exact checked-in migration and matching history
  version/name were applied without replaying unrelated pending migrations.
- Direct SQL and PostgREST now observe the table with RLS enabled.
  `service_role` has only `INSERT` and `SELECT`; `anon` and `authenticated`
  have no table privileges, and service-role `UPDATE`/`DELETE` remain denied.
- One privacy-safe append-only reconciliation row proves the hosted write/read
  path. Focused failure injection still proves chat and backtests continue when
  ledger persistence is unavailable.
- No repository change, application deploy, or PR was required. Issue #246 is
  closed; the durable evidence is recorded in
  [`issue-246-cost-ledger-closure-evidence.md`](../reports/issue-246-cost-ledger-closure-evidence.md).

### OpenAPI compatibility (#234 — complete)

- PR #289 landed as `8a66f0ba` and closes issue #234.
- FastAPI `app.openapi()` remains the canonical machine-readable authority.
  `docs/api/openapi.yaml` is generated from the corrected document and checked
  as a compatibility artifact, not maintained as a competing contract.
- CI now fails on unallowlisted path/method drift, server-prefix duplication,
  parameter and required-field drift, request/response schema drift, relevant
  enum drift, and overly broad exclusions.
- The only excluded operations are the named health, readiness, and local-dev
  reset surfaces; the SSE response-body normalization remains narrowly scoped.
- Both PR CI and post-merge integration CI passed. PR #290 subsequently landed
  the compatible request and failure boundary without reopening this authority.

### Chat request and correlated failure boundary (#235 — complete)

- PR #290 landed as `b073b1a0` and closes issue #235.
- Declared and streamed/chunked bodies above the approved ingress ceiling fail
  with 413 before request dependencies or expensive work.
- Typed field, list, nesting, and serialized-payload limits fail with the
  approved 422 contract while exact-boundary valid requests remain accepted.
- Rejection tripwires prove zero quota, persistence, gateway, provider,
  interpreter, or runtime work on every bounded failure path.
- Unexpected exceptions return sanitized RFC 9457 JSON with one correlation id
  shared by the response header, response body, and server log; CORS remains
  intact.
- Canonical SSE and typed recovery behavior remain unchanged. The regenerated
  OpenAPI artifact and #234 structural compatibility gate pass.
- Both PR CI and post-merge integration CI passed. No paid eval, provider-backed
  browser journey, schema migration, deployment, or hosted mutation was needed.

## Historical Planning Archive

The former eight-pillar taxonomy, issue dependency map, Wave 0 sequencing,
shared-surface matrix, quick-win analysis, and per-issue cards are preserved in
[`docs/archive/private-alpha-interim-issue-roadmap-2026-07-21.md`](../archive/private-alpha-interim-issue-roadmap-2026-07-21.md).
They are evidence only and must not drive dispatch or completion.

Issue-specific completion evidence remains in `docs/reports/`; canon and active
release-discipline documents are never archived merely because a slice lands.

### Legacy issue-link compatibility

Existing GitHub issue bodies link to the former roadmap's issue anchors. Keep
those links resolvable while directing readers to the archived cards:

- <a id="issue-228"></a>[#228 archived card](../archive/private-alpha-interim-issue-roadmap-2026-07-21.md#issue-228)
- <a id="issue-229"></a>[#229 archived card](../archive/private-alpha-interim-issue-roadmap-2026-07-21.md#issue-229)
- <a id="issue-230"></a>[#230 archived card](../archive/private-alpha-interim-issue-roadmap-2026-07-21.md#issue-230)
- <a id="issue-231"></a>[#231 archived card](../archive/private-alpha-interim-issue-roadmap-2026-07-21.md#issue-231)
- <a id="issue-232"></a>[#232 archived card](../archive/private-alpha-interim-issue-roadmap-2026-07-21.md#issue-232)
- <a id="issue-233"></a>[#233 archived card](../archive/private-alpha-interim-issue-roadmap-2026-07-21.md#issue-233)
- <a id="issue-234"></a>[#234 archived card](../archive/private-alpha-interim-issue-roadmap-2026-07-21.md#issue-234)
- <a id="issue-235"></a>[#235 archived card](../archive/private-alpha-interim-issue-roadmap-2026-07-21.md#issue-235)
- <a id="issue-236"></a>[#236 archived card](../archive/private-alpha-interim-issue-roadmap-2026-07-21.md#issue-236)
- <a id="issue-237"></a>[#237 archived card](../archive/private-alpha-interim-issue-roadmap-2026-07-21.md#issue-237)
- <a id="issue-238"></a>[#238 archived card](../archive/private-alpha-interim-issue-roadmap-2026-07-21.md#issue-238)
- <a id="issue-239"></a>[#239 archived card](../archive/private-alpha-interim-issue-roadmap-2026-07-21.md#issue-239)
- <a id="issue-240"></a>[#240 archived card](../archive/private-alpha-interim-issue-roadmap-2026-07-21.md#issue-240)
- <a id="issue-241"></a>[#241 archived card](../archive/private-alpha-interim-issue-roadmap-2026-07-21.md#issue-241)
- <a id="issue-242"></a>[#242 archived card](../archive/private-alpha-interim-issue-roadmap-2026-07-21.md#issue-242)
- <a id="issue-243"></a>[#243 archived card](../archive/private-alpha-interim-issue-roadmap-2026-07-21.md#issue-243)
- <a id="issue-244"></a>[#244 archived card](../archive/private-alpha-interim-issue-roadmap-2026-07-21.md#issue-244)
- <a id="issue-245"></a>[#245 archived card](../archive/private-alpha-interim-issue-roadmap-2026-07-21.md#issue-245)
- <a id="issue-246"></a>[#246 archived card](../archive/private-alpha-interim-issue-roadmap-2026-07-21.md#issue-246)
- <a id="issue-247"></a>[#247 archived card](../archive/private-alpha-interim-issue-roadmap-2026-07-21.md#issue-247)
- <a id="issue-248"></a>[#248 archived card](../archive/private-alpha-interim-issue-roadmap-2026-07-21.md#issue-248)
- <a id="issue-249"></a>[#249 archived card](../archive/private-alpha-interim-issue-roadmap-2026-07-21.md#issue-249)
- <a id="issue-250"></a>[#250 archived card](../archive/private-alpha-interim-issue-roadmap-2026-07-21.md#issue-250)
- <a id="issue-251"></a>[#251 archived card](../archive/private-alpha-interim-issue-roadmap-2026-07-21.md#issue-251)
- <a id="issue-252"></a>[#252 archived card](../archive/private-alpha-interim-issue-roadmap-2026-07-21.md#issue-252)
- <a id="issue-253"></a>[#253 archived card](../archive/private-alpha-interim-issue-roadmap-2026-07-21.md#issue-253)

## Program Boundary

The interim ends when the founder and the small private-alpha circle approve
all six live outcomes. It does not require closing every historical issue.

Out of scope for this pivot:

- A1b, A2, and A4 implementation;
- generic memory/RAG, embeddings, pgvector, or public excerpts;
- broker/export execution, voice-provider integration, native mobile, or a new
  engine platform;
- broad refactors not required by a selected user journey;
- production deployment or tester invitation without a separate founder
  decision.

## Global Stop Conditions

Stop and rescope when a lane:

- does not materially advance a remaining founder outcome;
- needs a canon/API/data-model decision the slice does not own;
- introduces an unapproved schema, public field, provider, or dependency;
- creates two owners for a protected runtime surface;
- restores phrasebook routing, a second chat brain, frontend-invented facts,
  generic RAG, or provider disclosure;
- spends real tokens or provider calls outside documented live gates;
- cannot roll back independently without discarding durable evidence;
- broadens into architectural refactoring;
- treats the audit donor as a merge source or acceptance evidence;
- reaches deterministic green without required live QA; or
- claims completion from a partial PR, scaffold, or checklist.

## Program Exit Criteria

- Representative conversations progress without loops or repeated recovery.
- Security, session, and Usage controls remain reachable and truthful.
- Result graphs continue switching ranges without changing canonical truth.
- Supported and unsupported requests receive honest, useful behavior.
- Search and suggestions are grounded.
- Omnisearch provides useful owner-scoped retrieval and navigation.
- Every promoted slice records exact SHAs, deterministic and live evidence,
  rollback, and remaining exposure gates.
- Tester exposure and production deployment remain separate founder decisions.
