# Private Alpha Next Roadmap

Status: **SUPERSEDED 2026-08-06 — P2 history and contract reference, not the
active board.** For approved experience and assigned-work ownership, use
[documentation authority](../DOCUMENTATION_AUTHORITY.md) and the
[MVEE](argus-minimum-viable-ecosystem-experience.md). References to an active
board in the historical body below are dated context. The interim pivot that
this document waited on completed with the 2026-08-05 production promotion and
is archived at
[`docs/archive/private-alpha-interim-roadmap.md`](../archive/private-alpha-interim-roadmap.md).
The P2 compounding loop, A1b linked versions, and A2 comparison below are
historical scope. Use this document for P2 history, the execution-realism
contract, and slice provenance. Do not take work from its dated queue.

P2.0 + P2.1 remain done. The Gate A/B loop landed through
2026-07-07: refine routing
(#141/PR #148), Idea Ledger portfolio browse (#147), latest-result fact answers
(#140/PR #153), messy company-name asset preservation (#142/PR #146), and the
B3 measurement trio (eval harness #143, PostHog product events #144, append-only
cost ledger #145). B4 retired the per-language copy tables — runtime prose and
recovery copy now compose from typed facts/codes (#154, PRs #174-177). Execution
realism (fees/slippage, #130/PR #178) is active by default with per-idea costs
still opt-in and an explicit kill switch, and a new interpreter cost/perf lane
added prompt caching + per-tier reasoning controls (#156/#157, PR #172).
After the interim exits, remaining P2 resumes with the compounding loop's back
half: linked versions (A1b), comparison (A2), and bounded freshness on return
(A4). A1b unlocks A2; A4 remains the phase-last arc that completes the promise
that Argus remembers, compares, and stays honest about staleness.

## Active Post-Promotion Pointer — 2026-08-01

The Private Alpha Next runtime history was promoted to `main` by merge
`5d1eec11`; the production-promotion documentation checkpoint completed on
`main` at `217ead12`. The latest integrated product changes are PR #331 at
`ec3a0a52` and PR #330 at `94476226`; new work must branch from the current
remote `codex/private-alpha-next` head rather than pinning either product SHA.
It contains the founder-accepted graph-range, account-security, Usage,
capability-truth, and Always Progresses baseline slices from PRs #264, #261,
#259, #266, and #268, plus the bounded calendar-materiality correction from
PR #267. It also contains the bounded chat-header correction from PR #274,
explicit onboarding removal from PR #275, and stale Run settlement from PR
#277, supported strategy-transition preservation from PR #278, the default-on
Grounded Discovery and Guest baselines from PRs #276 and #279, modeled-cost
preservation from PR #280, and chat next-move presentation from PR #281.
Provider-free test isolation landed through PR #282, and PR #286 replaced the
partial backend test list with the complete `tests/` directory gate. PR #287
then delivered resolver-owned discovery selection identity and
candidate/entity corroboration. PR #285 then pushed Conversations, Messages,
History, and Omnisearch/Idea Ledger pagination and search bounds into Postgres
without changing public cursors, ranking, ownership, or canonical artifact
identity. Its accepted private-alpha boundary permits sparse/deep/final History
Run pages to inspect more ordered rows; a maintained History read model remains
deferred scale architecture rather than unfinished #232 work. PR #288 then
completed fact-preserving recovery: stale or failed actions restore the latest
usable canonical artifact anchor instead of rebuilding an empty idea, while
genuinely absent facts still receive one targeted clarification. This
checkpoint also contains PR #289's structural OpenAPI compatibility gate, PR
#290's request-size and correlated RFC 9457 failure boundary, and PR #291's
visitor-owned Guest discovery allowance plus global daily attempted-search
ceiling. PR #295 then made resolver-verified candidate rows the default
discovery path and reserved paid Search for explicit requests or current-fact
needs, with typed retry, fair charging, async provider offload, and live
EN/es-419 continuity proof. PR #298 then completed the second pass with
visitor/day Guest message and simulation settlement, truthful Search and
verification progress, and one source-owned citation action per discovery row.
PR #299 then completed instant, race-safe conversation switching; PR #300
completed comparison grounding and discovery-act continuity; PR #302 added
bounded progressive Recents disclosure; and PR #303 reconciled catalog-valid
benchmarks that return zero price bars before confirmation.
The PR #291 and PR #298 migrations remain later hosted promotion operations;
these internal integration merges did not deploy or expose Guest traffic. This
pointer does not claim that the integration checkpoint is deployed or exposed
to testers.
PR #304 then completed the bounded result-surface ownership arc: Quick take,
Explain result, typed Try next rows, and recoverable failure now have distinct
owners through live turns, durable jobs, reload, and both supported languages.
Issue #249 is closed.
PR #305 then completed issue #253's decision-first recall projection and panel
as `88ab906d`. PR #306 completed the founder-locked Full Omnisearch outcome as
`b71f1eaf`: one ranked row per conversation, bounded object-first transcript
recall with jump-to-match, deterministic dossiers and asset rollups, exact
decision filters and mutation refresh, and provider-free **Run it fresh**
composition. The memory and Postgres paths preserve the integrated #232
pagination and #252 conversation-switching contracts. Issue #253 is closed;
there is no remaining Full Omnisearch implementation lane.
PR #316 then completed issue #309's run-anchored Omnisearch dossier history as
`9aa209d4`: users can inspect bounded prior finalized runs and their effective
decisions without leaving Omnisearch. PR #318 corrected accepted-turn failure
ownership and reload-stable Retry presentation as `f6d0981e`; the follow-up
test-isolation checkpoint is `1ed8d4f0`, and issue #313 is closed. PR #315 added
the conversation activity rail as `6e20328c`, and PR #317 added the centralized
keyboard overlay and quick-navigation system as `2ff6f3c6` while preserving
Cmd/Ctrl+K Omnisearch and the existing F2 rename binding. PR #324 subsequently
aligned Recents quick-jump hints with the shared exact-chord presentation as
`812c8fef` without displacing attention markers. PR #311 then completed issue
#310's provider-free typed **Retest with current data** action as `51984a42`;
it reloads canonical run truth, materializes the ordinary confirmation contract,
and stops before execution. Issue #310 is closed.

PR #312 added registered-only avatar monogram themes as `40eba1f6`. PR #319
integrated the public-alpha technical-readiness lane as `1c3775aa`: capped
registered/Guest provider keys, measured Render capacity, the requested-access
and approval-email path, CAPTCHA wiring, and recorded hosted evidence. At that
landing the permanent-account gate was still closed, so PR #319 itself did not
authorize public account access or a new tester cohort. The founder opened the
gate later, on 2026-08-12, and
`ARGUS_PUBLIC_ACCOUNT_ACCESS_ENABLED=true` is now live in production.
PR #320 unified the frontend failure vocabulary as `53c36d40`; PRs #323, #325,
and #328 delivered the bounded auth copy, error-localization, and card-container
corrections as `c1a13949`, `05fbef06`, and `403ea114`; and PR #327 removed the
unavailable Release Notes destination as `22bec7da` while preserving its later
public-beta re-entry contract.

PR #329 landed the backend/data foundation for durable conversation activity
and read state as `8a5d621b`. PR #331 then completed its frontend consumer as
`ec3a0a52`: activity and manually unread state now hydrate and render through
chat and Recents without restoring the retired global stream-state machinery.
The additive #329 migration remains a hosted-promotion operation. PR #326
completed issue #321 as `8e2a6217`, bounding invisible and interactive
Turnstile waits and presenting an accessible localized challenge dialog. Issue
#321 is closed. PR #330 then completed deferred Guest bootstrap as `94476226`:
anonymous identity and CAPTCHA acquisition wait for the first submission while
preserving #331's durable activity ownership. Issue #314 remains the only new
implementation follow-up from typed retest: rejected artifact actions lack
operational evidence even though their HTTP and allowance behavior is already
correct.

PR #348 self-hosted the canonical Inter and Space Grotesk variable fonts as
`38874bae`, removing Google Fonts from build, runtime, and browser QA while
preserving the DESIGN.md body/UI and display-font ownership. Issue #350 is a
separate low-priority fallback-order alignment; it is not unfinished font
delivery or a promotion gate.

PR #362 then repaired the sanctioned live-eval environment as `b2e8975c`,
closing issue #361: `ARGUS_EVAL_ENV_FILE` now preloads before Argus imports,
so calendar-aware cases exercise live market sessions instead of the synthetic
fixture calendar and report `calendar_alignment` truthfully. The 17
calendar-alignment failures lanes had waived as pre-existing are expected
green from this SHA forward. Deployed runtime behavior is unchanged; the
change is confined to `tests/evals/` and adds no configuration.

PR #355 then closed issue #336 as `c01d5730`: assets and capital named in a
terse opening turn ("let's test Apple with 10K") are provider-resolved and
preserved, so the first clarification asks only for the genuinely missing
field and the confirmation card inherits both facts without restatement.
Provider reconciliation removes only stale asset blockers after every
extracted traded-asset mention is accounted for; incomplete, ambiguous, and
cross-class contexts remain blocked. The one full-suite live red at the gate
was the baseline-reproduced comparison/category drift tracked by issue #364,
not a #336 regression.

PR #353 then closed issue #337 as `7e4c58f8`: stale rail attention markers
clear only on proven typed continuity between the clarification and a later
active confirmation, backed by backend-emitted `strategy_path_id` and
`source_result_run_id` metadata; unproven recovery fails closed and Guest
single-tick visibility is preserved. Its first exact-head gate run failed
(e2e seed lacked real workflow metadata) and was repaired before acceptance —
the independent re-verification discipline this batch exists for.

PR #357 then closed issue #340 as `9f97f1dc`: guest dossiers keep decision
actions visible and conversion-gate them through a typed availability
contract (server authoritative, additive client-capability handshake, legacy
clients unchanged), resuming the exact run, decision, and note after
conversion. Verified at the exact head with the 6/6 EN/es-419
desktop/mobile browser gate plus focused backend and web suites. Issue #341
(guest decision history) is unblocked and should dispatch from the
post-#357 integration head with a red-first reproduction before its fix.

PR #356 then closed issue #343 as `48de2f3f`: one rounded inset-pill
highlight geometry across all menu surfaces, colors and behavior unchanged,
with in-repo hover evidence. Landed tree verified byte-identical to the
independently pre-verified composed tree; founder overruled the absent
on-PR bot review after personal visual checks.

PR #352 then closed issue #334 as `0942507b`: one OS-aware keyboard behavior
registry across Omnisearch and chat, a contextual legend quiet at rest, and
bilingual labels from a single source — verified twice on composed trees
(1057/1057 web, 21/21 three-engine matrix) after a first-round send-back for
cross-PR modularity stacking. ChatInterface.tsx is now exactly at its budget
limit; lanes touching it must extract before adding. The completed
chat-header-title spec moved to `docs/archive/` with a tombstone stub.

PR #375 then closed issue #368 as `c334cf3e`: explicit stated capital now
survives unsupported-request turns (typed intent gating only), proven by a
red-first mocked regression and one exact-head targeted live rerun of the
original failing case — re-captured after the review fix moved the head.
Founder waived the ceremony reconcile commit on a verified no-overlap
disposition. PR #363's held evidence decision should be revisited: its
news-sentiment live failure now has a fixed root cause.

PR #370 then closed issue #341 as `c324f877`: guest Decision history loads —
the 500 was an untyped nullable first-page cursor in the Postgres dossier
reader, found only after the mandated real-browser re-evidencing overturned
an honest earlier non-reproduction from the non-Postgres reader. Fix is
explicit cursor casts with a red-first regression; same-session 500→200
evidence at the exact head lives in-repo. Guest isolation unchanged.

PR #360 then closed issue #349 as `42d96da7`: the activity/read-state
foundation is verified end to end with durable in-repo evidence (real local
Postgres/RLS, both personas, zero provider spend); guest applicability is
classified per state and manual-unread remains account-only.

PR #374 then closed issue #371 as `d8c7070a`: regex-free timestamp
normalization (founder-directed after the first-round regex missed the `Z`
shape Python 3.10 cannot parse) plus exception retention in the API failure
log. Unblocks the PR #351 live-proof rerun alongside #373.

PR #351 then closed issue #342 as `30af0dca`: Recents refreshes immediately
on guest-to-account conversion, proven by a founder-witnessed live journey
at the exact composed tree (claim 200, instant Recents, all polls 200) —
the same journey whose first attempt surfaced #371/#372.

PR #373 then closed issue #372 as `81e7a1ac`: first-login guest claims work
for brand-new accounts, email anti-enumeration is preserved through the
obfuscated-response guard, and username conflicts are serialized and typed —
three review rounds, three distinct real regressions caught and fixed.

PR #359 then closed issue #345 as `a35bb29f`: recommendation continuity at
the full clean bar — live 40/40 with no waivers (the 17-failure waiver era
formally over) and strategy-diverse acceptance evidence per the standing
rule (weekly DCA recurring contribution, SMA 50/200 inheritance).

PR #358 then closed issue #339 as `7b3221a1`: compound edits are
all-or-retry via required-target coverage over the full typed edit
vocabulary — a general completeness invariant, not a two-field patch — after
six adversarial review rounds. Issue #335 (inline confirmation-card editing)
is unblocked and stacked for the next cycle.

PR #354 then closed issue #346 as `4a6a237a`: truthful guest quota recovery
with a two-simulation allowance, atomic first-admission classification, and
the public-launch canary updated to the new policy — the stale cloud lane
taken over locally and finished with bilingual in-repo browser evidence.
Issue #294 keeps the funnel-data tuning mandate against this new baseline.

PR #366 then closed issue #344 as `2b023576`: honest, recoverable grounded
discovery — the sixteenth and final landing of the checkpoint-gap batch.
**The integration head at this landing is the promotion-freeze candidate:
everything after it stacks for the next cycle** (#335 inline editing, #332,
#369, #377, the parked #363 design, and the allowance session).

The [Private Alpha Interim Roadmap](../archive/private-alpha-interim-roadmap.md)
(archived, complete) was the authoritative founder-outcome and live-QA source
for this pivot, with #213
excluded by founder direction. Issues #228-#253 remain supporting evidence and
possible implementation material; they do not define the next slice or program
completion. The retired issue dependency map and waves are preserved in
[`docs/archive/private-alpha-interim-issue-roadmap-2026-07-21.md`](../archive/private-alpha-interim-issue-roadmap-2026-07-21.md).
A1b, A2, and A4 are paused—not cancelled—until the interim exit criteria are
met and the founder resumes P2.

## Resumption Signal And Pillar Sequencing — 2026-08-01

The interim roadmap is substantively complete: four of its six founder
outcomes are marked Complete, one (Argus always progresses) is a standing
quality bar rather than open work, and one (grounded discovery) has only
promotion/deployment gates left, not product work. Real promotion — the
Guest Main-Promotion And Public-Exposure Register in the interim roadmap —
is close, not speculative. This section amends how P2 resumes once that
gate clears; it does not reopen or correct the interim roadmap itself.

Founder-reviewed external user feedback (2026-08-01) validated the existing
direction rather than changing it: do not delay public exposure to build
memory/comparison features first, close the safety/reliability bar, launch
a controlled Guest canary, and let real usage decide what to build next.
This matches the interim roadmap's own sequencing already. What it adds is
new information about *how* to resume, not *whether* to.

**Locked decision: P2 does not resume in its original planned order by
default.** The prior assumption was that closing the interim hands control
straight back to the A1b → A2 → A4 sequence as originally planned. Instead:
after promotion, run a real Guest-canary/public-exposure window (target
2–4 weeks, per the same external validation) before committing engineering
time to any of A1b, A2, A4, or memory. Prioritize among
them using observed signal — return-visit rate, decision-note save rate,
refinement/version-creation rate, Omnisearch return-recall usage — not the
original planning order alone. If that signal is weak across the board,
that itself is the finding, and the response is strengthening reliability
and the core loop, not building further ahead of evidence.

**Three pillars govern what comes after the interim, not two:**

1. **Safety and reliability** — the interim roadmap itself. Already
   substantively closed; the remaining gate is #233's exact-candidate
   deployed Golden Path canary plus the operational checklist in
   `GUEST_PUBLIC_LAUNCH_SAFETY.md`. This pillar is not being reopened by
   this amendment.
2. **Product memory** — A1b (linked versions) and A2 (comparison), the P2
   compounding-loop items already named above. Paused pending founder
   resume; sequenced by the signal-driven rule above once resumed, not
   built in isolation from usage data.
3. **Memory** — the incubation lane (`codex/personalization-
   memory-incubation-persistence-v1` and its planned successors), tracked
   separately in
   [`docs/specs/lanes/personalization-memory-contract.md`](lanes/personalization-memory-contract.md).
   Continues independently in the background regardless of interim/P2
   status — it is not gated on promotion or on P2 resumption, and should
   not be redispatched with either's urgency.

**Options-capability idea (2026-08-01, founder-raised): deferred, not
roadmap work.** Real user interest in options strategies surfaced in the
same feedback pass. Reliable options backtesting needs historical option
chains with Greeks/IV, correct expiration/assignment/multiplier/fee
handling, and realistic wide-spread fill assumptions — none of which the
current equity/crypto data path provides or should be stretched to cover.
If this is ever built, it must be a separate capability registry and engine
slice, never an incremental flag on the equity engine, mirroring how
capability truth already fails closed on unsupported requests elsewhere in
the product. No vendor (Polygon, Tradier, ORATS, or otherwise) should be
selected before there is a real, demonstrated user cohort asking for it —
this is explicitly a wait-for-signal item, not a candidate for the next
planning cycle.

## Promotion Readiness — 2026-08-04

The freeze holds: the product tip is unchanged at `2b023576` (PR #366).
Everything landed after it is promotion housekeeping — env-template parity and
the three-key OpenRouter policy, the real support address
(`support@get-argus.com`, Cloudflare Email Routing to the founder's inbox),
and the Render spend-discipline lock (AGENTS.md local-compute rule, runbook
note, and a guard test pinning the mode scripts' dispatch posture). Promotion
candidate tip: `58fe1049`, CI green at every step.

Pre-flight is complete and its findings are the promotion agent's brief:

- Hosted migration census: exactly four migrations apply, in order — avatar
  theme, conversation-activity read states, guest allowance raise,
  simulation-limit handoff reason. Ten older “missing” stamps are renumbering
  artifacts of a past history squash — never re-apply them. The June
  `MIGRATIONS_FAILED` branch status is dead signage.
- Env truth is layered: render.yaml plus a dashboard-set layer. The ceremony
  reconciles declared-vs-live; the discovery stack (provider, search model,
  daily ceiling, Perplexity key) is the highest-risk gap and gets a hosted
  probe. `ARGUS_VISITOR_KEY_SECRET` (fresh high-entropy value) and
  `NEXT_PUBLIC_ARGUS_SUPPORT_EMAIL` are already set on the services; the
  deploy bakes them in. Hosted key identity must verify as the argus-prod
  OpenRouter key.
- The scheduled Private Alpha Canary has been red daily since 2026-07-13 for
  one structural reason: GitHub executes main's copy of the workflow yml,
  which predates the capture-path contract the integration scripts require
  (`missing_capture_destination` at stage `capture`, before any product
  check; the daily Render warmup passed throughout, so production stayed
  healthy). Promotion itself heals it by updating main. **The closing
  release gate is the first scheduled canary green after deploy.** That
  first green also writes the first real per-run cost into
  `cost_ledger_entries`; canary cadence (keep daily vs thin out) is a
  founder decision made from that measured number.

### Next-cycle boards — 2026-08-05

The interim roadmap is complete (promotion executed; #228/#233 closed). The
two next-cycle draft boards it pointed at were folded into the single active
board on 2026-08-06: [`argus-active-roadmap.md`](argus-active-roadmap.md).
Their drafts are archived at
[`2026-08-05-next-cycle-stabilization-roadmap.md`](../archive/2026-08-05-next-cycle-stabilization-roadmap.md)
and
[`2026-08-05-next-cycle-product-roadmap.md`](../archive/2026-08-05-next-cycle-product-roadmap.md).

### Acceptance walk amendment — 2026-08-04 evening

A founder-witnessed acceptance walk on the local candidate stack (guest lane,
conversion, signed-in journeys, adversarial Spanish) moved the candidate tip
from `58fe1049` to **`70ba33cc`** (all CI-green). It found and fixed in place:
the conversion resume 409 (stale idempotency key), two omnisearch dossier
divider strays, the presumptuous default decision state (now unchosen
end-to-end including the guest resume target), "public alpha" copy replaced
with "early access" (en/es-419), existing-email re-signup now points to sign
in on the conversion modal (409 `account_exists_use_login`; the public signup
page stays deliberately opaque for anti-enumeration), and an em dash purge
from all user-facing copy (rule locked in `AGENTS.md`).
Eyes-open guest metering postures are recorded in
`GUEST_PUBLIC_LAUNCH_SAFETY.md`. Findings filed instead of fixed: pending-card
NL edits ignored in any language (evidence on #335), reply language follows
workspace not message language (#378), and the Run-backtest action's shape
(fake English user bubble, message metering, no typed equivalent) which is
parked for founder design discussion (#379 closed pending it; the dossier
retest token chip is the candidate pattern). None are batch regressions;
promotion proceeds on `70ba33cc`.

### Production promotion complete — 2026-08-05

Promotion shipped: `argus-api`, `argus-app`, and the `argus-backtests`
workflow (version `wfv-d9p88253erlc73d3u8s0`) are live at `7ef89a90`, four
migrations applied, env contract reconciled (three red-gate rounds fixed the
contract itself: visitor secret + support email, then discovery/realism/
PostHog, then the runbook secret checklist). Full evidence:
[`docs/release-manifests/2026-08-05-main-production-promotion.md`](../release-manifests/2026-08-05-main-production-promotion.md).

Recorded deviation: Turnstile correctly blocks headless browser automation in
every widget mode, so the authoritative canary's browser phase cannot pass
unattended. The journey was founder-operated in a real browser and verified
server-side (job succeeded through `argus-backtests/run_backtest_job`,
+12.84% result, benchmark lag 13.30 points, cost ledger `$0.00015585` for the
turn); the requested-signup denial was proven at the API layer. Issue #383
holds the rework (API-layer denial probe, session-injected journey, staging
testing sitekey). **Until #383 ships, the scheduled daily canary will stay
red at its browser auth phase — an explained red, not a production alarm;
the meaningful daily signal is the warmup and pre-browser gates.**

Statements below that say “A1b is next” or describe `main` promotion as still
pending are preserved as pre-promotion history. They do not override this
active pointer.

**Release-integrity checkpoint (#192) — COMPLETE.** [#193](https://github.com/lagarcess/argus/issues/193)
approved the contract; [#194](https://github.com/lagarcess/argus/issues/194),
[#195](https://github.com/lagarcess/argus/issues/195), and
[#196](https://github.com/lagarcess/argus/issues/196) landed finalization,
signup-language persistence, and Spanish static parity; [#197](https://github.com/lagarcess/argus/issues/197)
landed the authoritative release profile and passed the exact-SHA Spanish
real-user canary; [#198](https://github.com/lagarcess/argus/issues/198) records
the as-built documentation and manifest. The validated runtime candidate is
`373d1a12dd5f538a81150b20903f4f43db27c639`; its authoritative live evidence is
the [#197 closure record](https://github.com/lagarcess/argus/issues/197#issuecomment-4965556704).
At the time, this validated only the branch-deployed private-alpha Render
surface—there was no `main` merge, production deployment, automatic production
deployment, tester invitation, or tester exposure. The later `main` promotion
is recorded by the active post-promotion pointer above. Tester exposure remains
a separate founder decision.
The 2026-07-08 burn-down pass landed the bulk of the interpret-surface cluster:
PR #182 fixed #171 Sig1+Sig2, #160(B), and #150's behavior half (with the #179/
#180 repro gates un-xfailed); PR #183 replaced the degraded-fallback English
copy with typed clarification contracts rendered by frontend static i18n
(es-419 parity restored, the 9 stale copy tests re-pointed at typed asserts);
and PR #169 landed the Agent Runtime Regression sweep — the full agent_runtime
suite + spine guardrails now run hermetically (synthetic_unit_fixture catalog)
on every runtime PR, zero hidden failures at tip (1023 passed, 0 xfailed at
`c081901`).
Current pointer: the interpret/edit spine is between owners; A1b (linked
IdeaVersion emission) is the next spine-chain slice and is unblocked.
The interpret/edit-surface burn-down is CLOSED (2026-07-10): PR #185 (#160(A)),
PR #186 (#151), PR #187 (benchmark-keep), and PR #190 (#188, tip `08d92f9`) are
all merged. #188's history is the arc's key lesson: #189 merged on green mocked
tests but broke live; founder browser QA caught it, it was reopened, and PR #190
fixed it — chip asset edits are now operation-agnostic, the two P1 desync corners
are closed, and the fix was proven live with real Grok before belief, then merged.
Promotion to `main` is UNBLOCKED on code — the suite carries zero xfails and every
interpret-surface issue is closed. Remaining steps are release mechanics: (1) full
live-eval rerun on the exact promotion SHA (now includes the chip cases); (2) the
clean-checkout suite gate (#134/#135); (3) founder waiver on the known grok
options-idea nondeterminism; (4) release manifest + `main` promotion PR (merge
commit, not squash, so this is the last all-of-history diff).
#164 (post-result followup typing / approval-vs-pending-clarify policy) is the
deferred follow-up, not a gate.
The P2 execution board below is paused historical-forward context during the
interim pivot. Do not dispatch one of its READY lanes until the founder closes
the interim or explicitly resumes P2. When resumed, the interpret/edit spine
still has exactly one owner at a time and A1b remains the next planned spine
lane.
Historical board date: 2026-07-09
Branch family: `codex/private-alpha-next`
Audience: Founder, Codex orchestrator, bounded subagents, reviewers

This is the preserved P2 execution board for after the interim pivot. It turns
the decision memo into ordered, testable slices without importing contaminated
runtime work from quarantine. The active interim board above decides current
work.

## Source Order

Every agent starts here:

1. `AGENTS.md`
2. `docs/PRODUCT.md`
3. `docs/ARCHITECTURE.md`
4. `docs/API_CONTRACT.md`
5. `docs/DATA_MODEL.md`
6. `.agent/designs/argus/DESIGN.md`
7. This roadmap
8. `docs/specs/argus-active-roadmap.md` for every current slice
9. `docs/specs/private-alpha-next-decision-memo.md`
10. `docs/specs/private-alpha-ci-cd-sota.md`
11. `docs/PRIVATE_LAUNCH_RUNBOOK.md`
12. `docs/release-manifests/TEMPLATE.md`
13. Supporting archived notes such as
    `docs/archive/private-alpha-performance-readiness-audit.md`, plus local
    memos such as `temp/bytebytego/bytebytego.md`

The decision memo is mandatory slice onboarding. Before a subagent works on a
slice, it must read the relevant memo sections and addenda for that slice.

## Current Checkpoint

P0 continuity is complete on the clean reintegration line at `bbd9f10`.

The explicit private-alpha onboarding product was removed as a bounded
strip-out lane (2026-07): no language/goal gate, no chat goal cards, no hidden
`__ONBOARDING_*` control protocol, no onboarding flags. Authentication lands
directly in normal chat with localized generic starter prompts; the first
successful backtest is the meaningful onboarding milestone. Legacy persisted
onboarding profile JSON and marker messages remain inert and hidden
(`docs/API_CONTRACT.md` section 10). Any lane that previously special-cased
onboarding (for example a guest-mode bypass) must reconcile against this
checkpoint when it next rebases.

Done behavior:

- `add` / `append` merge new symbols into the active strategy.
- `replace` swaps the traded asset universe.
- explicit benchmark changes update `comparison_baseline`, not traded assets.
- default benchmarks remain `SPY` for equities and `BTC` for crypto.
- explicit same-asset-class benchmarks remain sticky until changed.
- dates, capital, asset class, fees/slippage, and benchmark intent survive
  multi-turn edits, reload, and run handoff.
- max 5 symbols is enforced with clarification rather than silent truncation.

Do not reopen P0 unless a new reproducible bug appears. The quarantine work is
preserved as local tags `archive/quarantine-fc231e8` and
`archive/p2.1-quarantine` (branches deleted 2026-07-01, all salvageable content
verified landed or on the execution board) — read-only reference material for
ideas, tests, and failure evidence. Do not broad cherry-pick runtime code from
quarantine.

## What P1 Means

P1 is the first clean decision-memo product slice after P0 continuity.

Goal: completed backtests should become durable, evidence-ready idea artifacts
without pretending that every captured artifact is an explicit user commitment.

The P1 spine is:

- `Idea`: persistent user thesis or question.
- `IdeaVersion`: canonical snapshot of that idea at a point in time.
- `Strategy`: executable method inside an idea version.
- internal `Run` / user-facing `Backtest`: execution record.
- `EvidenceArtifact`: human-readable proof object from run or research context.
- `DecisionNote`: explicit user judgment after seeing evidence.

Default product rule: persistence is automatic, commitment is explicit. A
completed result can be captured as evidence, but only a save, pin, or decision
action should mark the idea as saved or decided.

## P1 Scope

In scope for the next implementation wave:

- product/API/data spec for Idea, IdeaVersion, Strategy, Run/Backtest,
  EvidenceArtifact, DecisionNote, and lifecycle labels;
- artifact payload boundaries, provenance, assumptions, digest, and immutable
  evidence fields;
- completed backtest capture into the idea/evidence model;
- decision capture attached to evidence artifacts;
- Omnisearch-ledger recall as the first user-facing wedge, not a dashboard;
- typed search results and right-panel previews for Conversation, Backtest,
  Evidence, Decision, and Idea;
- measurement-only event envelope for continuity, evidence capture, decision
  capture, recall, and eval readiness.

Out of scope until explicitly started:

- generic RAG/vector memory as canonical truth;
- automatic memory beyond explicit or assisted saved-decision
  moments;
- standalone Idea Ledger dashboard;
- broker account connection, broker execution, or order submission;
- public sharing/excerpts beyond design constraints;
- provider-backed voice implementation;
- native mobile.

## P1 Readiness Checklist

Before code:

- [x] Update spec/API/data-model docs for the exact P1 object contract.
- [x] Identify migrations, if any, and make them reversible and minimal.
- [x] Write failing backend tests for evidence capture, decision capture,
      hydration, reload, and search retrieval.
- [x] Write or update focused frontend tests for visible artifact states.
- [x] Define browser QA prompts before implementation, including messy language,
      reload, locale switch, and navigation during async changes.
- [x] Confirm rollback can be described as one clean commit revert per slice.

Before promotion to `codex/private-alpha-next`:

- [x] Focused backend tests pass for the final candidate SHA.
- [x] Focused frontend tests pass for the final candidate SHA.
- [x] Live Codex browser QA passes locally for the final candidate SHA.
- [x] Internal code review has no release-blocking findings.
- [x] Docs reflect the shipped behavior, not aspirational behavior.
- [x] No broad quarantine runtime diff was imported.

Verification note: these boxes must be checked only against the exact
`codex/private-alpha-next-reintegration` candidate SHA being considered for
promotion. Promotion to `codex/private-alpha-next` remains a separate
founder-directed action.

Current verification evidence for this recovery candidate:

- Backend P1/API: `poetry run pytest tests/test_alpha_api.py
  tests/test_alpha_api_supabase.py tests/test_supabase_gateway.py
  tests/test_alpha_artifacts.py tests/test_p1_evidence_spine.py -q` passed
  with 146 tests.
- Backend P0/date continuity: `poetry run pytest
  tests/agent_runtime/test_artifact_continuity.py
  tests/agent_runtime/test_llm_interpreter_date_window_repairs.py
  tests/agent_runtime/test_interpret_stage.py
  tests/agent_runtime/test_workflow.py -q` passed with 239 tests.
- Frontend: `cd web && bun test __tests__/alpha-frontend.test.ts
  __tests__/command-palette-items.test.ts __tests__/spanish-ui-smoke.test.ts`
  passed with 82 tests.
- Static checks: focused `poetry run ruff check ...` passed for touched backend
  files and focused tests; `git diff --check` passed.
- Codex in-app browser QA: `http://127.0.0.1:3031/chat` completed reload of a
  messy Spanish AAPL/MSFT/TSLA vs SPY result, verified one completed result
  card, no ready/failed duplicate card, saved decision hydration, Spanish
  period and benchmark prose, no raw internal search leaks, and Omnisearch rows
  ordered as Decision, Evidence, Idea, Backtest before Conversation for the
  `AAPL MSFT TSLA` ledger query.
- Internal review: two read-only reviewers found the same Omnisearch ranking
  blocker. The fix preserves pinned, exact, and symbol relevance ahead of P1
  artifact priority while keeping artifacts ahead of source conversation
  wrappers within the same relevance tier.

Stop immediately if:

- canonical payload and UI prose disagree;
- benchmark/traded assets regress from the P0 continuity contract;
- frontend invents state not supplied by backend artifacts;
- schema/API changes appear without matching docs and tests;
- slice size grows beyond one revertable commit;
- live browser QA fails after tests pass.

## Board

### P0 Done

- P0 continuity contract and canonical asset/benchmark edit semantics.
- Clean reintegration strategy from `codex/private-alpha-next` at the stable
  checkpoint.
- Quarantine branch preserved as read-only reference.

### P1 Done

P1 is closed, verified (see the readiness checklist and verification evidence
above), and promoted to `main` as part of the squash promotion `8b169e9`
("promote private alpha next checkpoint", validated against `3314e2c`). The
slices below describe delivered scope, not pending work.

1. **Object contract spec**
   - Define Idea, IdeaVersion, Strategy, Run/Backtest, EvidenceArtifact,
     DecisionNote, and lifecycle labels.
   - Update API/DATA_MODEL docs before implementation.

2. **Evidence capture**
   - Capture completed backtests into durable evidence artifacts.
   - Keep evidence automatic and commitment explicit.
   - Preserve immutable assumptions, metrics, provenance, and digest.

3. **Decision capture**
   - Add explicit user decision states such as watching, promising, rejected,
     and revisit later.
   - Attach notes to evidence artifacts.
   - Hydrate saved decisions back into result/artifact surfaces.

4. **Omnisearch-ledger wedge**
   - Promote recall through Omnisearch/search first.
   - Preview artifacts directly, with conversation as provenance.
   - Add artifact-aware hover/right-panel actions without duplicate action
     surfaces.

5. **Measurement envelope**
   - Define event schema for evidence capture, decision capture, recall,
     continuity mismatches, cost, and eval readiness.
   - Keep analytics measurement-only unless a later slice starts live reporting.
   - At P1 closure, the `argus_observability_event/v1` envelope and privacy
     sanitizer existed without live reporting. B3 later delivered server-side
     PostHog wiring and the append-only CostLedger. Durable eval-result
     persistence remains deferred.

### Design-Only Until Later

- Guided first-run tour (alpha-user suggested, 2026-08-05): not a wizard; a
  fluid one-click layer that makes Argus aware of where it is leading you.
  Founder wants a worth-it brainstorm before any build.
- Recency-aware suggestion context (2026-08-05): in-chat suggestions must
  weight the latest run heavily (never re-suggest the asset just tested;
  NVDA was suggested right after an NVDA backtest). Macro pattern spans chat
  context, product memory, and the personalization-memory incubation lane.
- Memory/data controls.
- Voice-to-composer STT.
- Public evidence excerpts.
- Broker/export handoff.
- Native mobile.
- Broad Research Lab / deep-research product work. Bounded, source-backed event
  context required by the later A4 freshness arc is not a general news feed or
  a broad Research Lab implementation.
- Allowance brainstorming session (founder-led): define what Guests versus
  registered users can do, and identify which capability boundaries naturally
  become tiers or plans once product-market fit is found. Today Argus stays
  deliberately open at near-full data capability to learn capability truth;
  every capability boundary added in the meantime (lookback windows,
  simulation allowances, discovery quotas) must stay policy-owned values so
  future tiering changes policy, not design. Session output feeds the
  allowance/tier design; no implementation before it.
- Current-data window truthfulness design (PENDING founder lock; PR #363 is
  founder-parked on it). Direction under discussion, not yet decided:
  feasibility-aware Retest disposition on the dossier button (ready /
  feasible-with-repair / impossible, with tooltip), a guided repair turn that
  pulses the affected confirmation-card input for manual editing, anchor-date
  clamping to earliest available riding the existing
  `effective_date_range`/`adjustment_reason` contract, a strict definition of
  "truly impossible," and a reconciliation path so users are never
  dead-ended. No lane resumes until the founder locks this design.

### P2 Board

P2 thesis: P1 proved Argus can capture evidence. P2 makes that evidence
trustworthy and comparable enough that five trusted alpha users can save
decisions and come back. P2 is measured against the PMF gates in
`docs/specs/private-alpha-next-decision-memo.md` section 15.8, not by feature
count.

The five-user PMF gate is currently unmeasurable: the production Render compute
plan prevents users from completing internet-based Argus tests. Treat the gate
as blocked on restored compute capacity, not as passed or failed product
evidence.

In scope for P2: capability honesty, backtest credibility (assumptions a user
can explain), the comparison loop, graceful Spanish recovery, and the
measurement to know whether any of it moved a gate.

Deferred to design-only for P2 (no runtime, schema, or UI): memory
inspector/opt-in (memo 15.3, Slice H), voice-to-composer STT (Slice J), public
excerpts (Slice K), broker/export handoff (Slice N), iOS shell (Slice L), and
external engines beyond read-only reference (Slice M). Producing design notes for
these is allowed; shipping them is not P2 scope.

#### P2 Agent Quality Pillars

The four pillars (Intelligence, Evaluation, Platform, User Experience) are
defined once, canonically, in `AGENTS.md` → "Agent Quality Pillars". They are a
quality lens for every P2 slice, not new lanes and not promotion blockers unless
this roadmap marks one as a gate (see the interpreter-facing live gate under
"Standing release discipline" below). Do not restate the pillar definitions
here. Only the P2-specific applications live in this doc:

- **Intelligence** → A1b makes refinement create linked IdeaVersions, not loose
  transcript state; A2 compares canonical versions/artifacts, not reconstructed
  prose. Memo-named retrieval/memory accelerators are leverage behind this
  contract, never a replacement for Supabase/Postgres product truth.
- **Evaluation** → cluster live-eval failures by roadmap concern (artifact
  grounding, comparison correctness, recovery/Spanish parity, hydration,
  capability honesty, cost/performance, release environment).

#### Why P2 is sliced this way: the quarantine lesson

Two branches attempted P2 work and both broke the language-agnostic, LLM-first
spine in the same way:

- `codex/private-alpha-next-quarantine-fc231e8` (broad umbrella) added
  deterministic ticker-shape classifiers (`$`-prefix, ALL-CAPS, length-2-to-5
  `.isalpha()`) and re-scanned `current_user_message` inside `interpret.py` to
  override the interpreter's grounding, deleting an interpreter-trusting
  short-circuit in the process.
- `codex/private-alpha-next-p2.1-quarantine` (narrow capability gate) substring-
  matched indicator names against LLM free-text and flipped intent to
  `unsupported` after interpretation, rejected RSI thresholds unless the number
  appeared literally in the raw message, and hand-wrote `if locale == "es-419"`
  copy tables to keep parity.

Single root cause: both implemented capability truth and continuity as
deterministic gates that run after the LLM and override it by re-scanning text.
Narrowing scope did not help; it produced a smaller copy of the same
anti-pattern. The earlier P2.1 board even sanctioned the seam with one sentence
permitting deterministic guardrails to "consult catalog-backed indicator tokens
after LLM interpretation." That sentence was the doorway. Note that neither
branch used `import re` or `if "word" in message`; the spine was broken with
heuristics that pass a naive grep, so the prohibitions below name mechanisms, not
just regex.

This work is preserved as local tags (`archive/quarantine-fc231e8`,
`archive/p2.1-quarantine`; the branches themselves were deleted 2026-07-01) —
read-only reference for product direction, anti-patterns, UI ideas, and test
inspiration. Do not broad cherry-pick runtime code from the tags.

#### Cross-cutting invariants (the P2.0 guardrail gate, inherited by every slice)

Sourced from `AGENTS.md` runtime rules, `ARCHITECTURE.md` agent-runtime decision
filter, and the quarantine autopsy above. Any P2 change that weakens these is a
release blocker.

1. No deterministic text re-scan to drive routing or grounding. Nothing in
   `interpret.py` or after it may re-inspect `current_user_message` to branch.
   Consume interpreter output only.
2. No post-LLM intent override. Code may not flip `intent` or
   `semantic_turn_act` (for example to `unsupported_or_out_of_scope`) from its
   own re-analysis. The `*_text_guardrail_response` shape is banned.
3. Capability and field validation read typed structured fields the LLM emits
   (for example a `strategy_type` enum or an `indicator.key` enum), never
   substring, keyword, or alias-span matching over prose or LLM free-text fields.
4. No "grounding" by literal text presence. Do not reject an LLM-extracted value
   because it is not a substring of the raw message; that punishes paraphrase and
   non-English phrasing.
5. No per-language copy tables or branches in the runtime (`if locale ==
   "es-419"`, `_english_*` helpers, `" y "` versus `" and "` connectors).
   Capability, clarification, and recovery copy is model-voiced; English/Spanish
   parity is proven by eval, not hardcoded. Localized stop-word lists, alias
   tables, or display-label token matching for semantic choice selection are the
   same anti-pattern; degraded fallbacks must consume typed ids / payloads.
6. Backend stays canonical truth; the frontend renders backend-provided state and
   never invents it; one LLM intent-classification call per turn.

These ship as a review checklist plus failing-test tripwires in P2.0 so the
disease cannot recur silently.

#### Milestones

Each slice owns a PMF gate, is demoable in a founder-guided session, and is one
revertable slice family.

##### P2 execution board: decision memo gates + unlock status (PAUSED, preserved 2026-07-07)

Evidence-grounded after a live walkthrough + code grounding pass. The decision memo's
moat is the loop where ideas are tested, remembered, compared, and trusted (memo §4.1,
§5.6, §5.7). P2's remaining work is closing that loop. Treat the items below as
future execution gates, not as a second current roadmap and not as hard order
dependencies. The P2.x specs further below remain the per-slice detail (PMF
gates, verification, stop conditions). None of these statuses authorizes work
while the interim pivot is active.

How to use this board after the founder resumes P2: each gate lists lanes with
an unlock status. At that time, a READY lane may proceed without waiting on
unrelated lanes. Status legend:

- READY-BUILD: implement now (fresh worktree from `origin/codex/private-alpha-next`,
  child branch, tests, browser QA, review, one revertable slice family).
- READY-SPEC: write the spec and ask the founder product questions now;
  implementation stays locked until the board flips the lane to READY-BUILD.
- SCOUT: diagnosis, reproduction fixtures, and failing tests only. No runtime
  edits.
- ASYNC: isolated lane in its own worktree; cherry-pick discipline, no merge
  pressure, never blocks the board.
- BLOCKED(x): do not start; waiting on the named unlock.
- DESIGN-ONLY: notes/mocks allowed; no runtime, schema, or UI code.

Spine ownership rule: exactly one lane at a time may edit the interpret/edit
spine (`agent_runtime/stages/*`, `agent_runtime/interpreter/*`,
`llm_interpreter*.py`, `artifact_edit_planner.py`). When P2 resumes, A1b is the
next planned spine lane. Parallel runtime lanes keep new logic in their own
modules, touch shared dispatch minimally, and take rebase duty; the spine owner
merges first.

**Gate A: memory-backed compounding loop (highest leverage).**

End-to-end shape: messy idea -> canonical idea -> backtest/evidence artifact ->
saved decision -> refine creates a linked version -> compare versions -> revisit
later with context. This includes structured Argus product memory earlier in the
plan than generic retrieval work: `Idea`, `IdeaVersion`, `EvidenceArtifact`,
`DecisionNote`, and retrieval from those product objects are the P2 contract.
That durable artifact recall is sufficient for P2 "memory." A user-confirmed
`MemoryRecord` or equivalent personalization layer remains post-PMF. RAG, graph
RAG, agentic RAG, Mem0, Zep, Graphiti, and similar tools are optional later
leverage behind an approved product contract, not the source of truth.

**Gate B: trust, recovery, and measurement (runs alongside Gate A).**

Wire product events, eval cases, cost/latency ledger, correlation IDs, recovery
tests, Spanish parity, and browser QA evidence as the loop lands. This is not a
separate product surface; it makes founder-guided sessions measurable and keeps
runtime behavior honest. PR #139 (merged `128818f`) was a Gate B/P2.4 repair
slice, not a replacement for the Gate A product swing; issues #140 and #142
continue this gate.

**Gate C: evidence credibility (parallel, isolated).**

Execution realism, fees/slippage, benchmark clarity, data assumptions, and the
current launch adapter boundary improve the trustworthiness of evidence
artifacts. The existing adapter is sufficient for P2. A formal multi-engine
`BacktestEngine` interface is deferred until Slice M demonstrates a concrete
second-engine need.

**Gate D: memory controls and privacy (required for memory expansion).**

Memory must be earned opt-in, inspectable, editable, deletable, resettable, and
explainable ("why was this used?"). Alpha legal/Data Controls work (#137) is the
surface to extend. Do not add automatic broad memory before these
controls exist.

**Parallel design/prototype lanes.**

These may progress without touching the runtime spine: sanitized public excerpt
design/mock, voice-to-composer STT prototype, thin iOS shell proof, broker/export
packet design, security/privacy review, and monetization/entitlement architecture.
They become implementation work only when the active gate explicitly starts them.

**Avoid for now.**

Do not add generic RAG as canonical memory, always-on automatic memory, a new
dashboard competing with chat, public raw conversation links, broker sandbox auth
or execution, speech-to-speech, a native iOS release, payments, or a second chat
interpreter/orchestrator.

DONE + landed on `codex/private-alpha-next`:

- P2.0 spine guardrail gate (tripwires live).
- P2.1.a capability registry (single derivation surface).
- Conversational edit contract (messy multi-op edits + chips -> one typed operation
  set, no silent drop, language-aware, model-voiced honesty note; 6 commits; verified
  unit + live probe EN/ES + EN browser). NOTE: the capability-honesty interpreter
  polish (the old "P2.1.b") was reassessed as LOW-VALUE — MACD is reachable via a
  generic `signal_strategy` rule, and draft strategies already 422 — so it is OFF the
  critical path.
- Idea Ledger — lightweight recall (loop Slice 3): saved-idea decision status surfaced
  in Omnisearch + a `?decision_state=` filter (#132, merged).
- Spine modularization: `llm_interpreter.py` + `stages/interpret.py` split into cohesive
  submodule packages behind behavior-preserving re-export facades (#133, merged;
  addresses #131 — issue kept OPEN until it lands on `main`).
- Gate B/P2.4 chat-continuity regression repair (#139, merged `128818f`):
  unsupported-recovery continuation, confirmation-card edits, pending date
  answers, RSI threshold edits, Recents attention, Omnisearch default-on QA;
  degraded fallbacks now consume typed ids/payloads instead of display-label
  text.
- A1 refine routing + loop repair (#141, PR #148): refine chip + NL edits route
  through the typed edit contract; same-period references bind to the latest run.
- A3 Idea Ledger portfolio browse (#147): saved ideas grouped by decision state
  in Omnisearch; backend-owned `ledger_groups` are the source of truth.
- B1 latest-result fact answers (#140, PR #153): peak-date/drawdown follow-ups
  answered from canonical `backtest_runs` facts, pending edit state preserved.
- B2 company-name asset preservation (#142, PR #146): messy multi-symbol
  company-name baskets survive to confirmation. CAVEAT: #171 reports this case
  regressed on the live eval at `4eae18e` — verify before `main`.
- B3 measurement trio: eval harness (#143), server-side PostHog product events
  (#144), append-only CostLedger (#145). The eval harness is a live landing gate.
- B4 language-gate retirement (#154, PRs #174-177): runtime prose composes from
  typed facts; degraded recovery copy and result chrome render from typed
  codes/keys; per-language copy tables retired, parity proven by eval.
- C1 execution realism — fees/slippage (#130, PR #178): active by default
  behind `ARGUS_ENABLE_EXECUTION_REALISM`, with costs opt-in per idea and an
  explicit `false|0|off|no` kill switch preserving the pre-realism path.
- Interpreter cost/perf (#156/#157, PR #172): automatic stable-prefix prompt
  caching on structured-artifact calls + per-tier reasoning-effort env overrides
  (`ARGUS_STRUCTURED_REASONING_EFFORT`, `ARGUS_CAPABILITY_REASONING_EFFORT`).
- #149 result-followup timeout recovery fixed for Python 3.10 (#168).
- `codex/p2.1a-capability-registry` is SUPERSEDED — its deploy work (onboarding-flag
  gate, grok-4.3/claude-haiku model swap, deploy contract, widened LLM timeouts) is
  already in integration; the branch carries no unique runtime. Retire it, no rescue.

LANES BY GATE (the board agents execute from):

**Gate A — compounding loop (highest leverage):**

- **A1 Refine routing + loop repair (#141).** DONE — merged as PR #148
  (`5fc7a9a`). Refine chip and natural-language edits now route through the
  typed edit contract; refinement pending state is a first-class edit context;
  same-period references bind silently to the latest run's window; the
  supported-edit discriminator counts date-window and cadence evidence.
  Regression suites added: `test_refine_action_edit_routing.py`,
  `test_post_result_edit_routing.py`, `test_latest_result_window_binding.py`.
  Spec: `docs/specs/private-alpha-next-refine-to-version.md`.

- **A1b Linked IdeaVersion emission.** READY-BUILD — next spine-chain slice;
  the spine is unowned until this lane starts. Emit a new `IdeaVersion` linked
  to the prior idea on refine (P1 spine supports lineage). Split out of #141
  by founder scope decision 2026-07-01; this is the slice that UNBLOCKS
  comparison (A2).
  Founder boundary locked 2026-07-16: assets, date range, benchmark, strategy or
  executable rules, cadence, capital, and modeled costs are material experiment
  changes that create a new version; multiple edits before one confirmed run
  collapse into one version; wording, explanations, retries, and abandoned
  edits do not.

- **A2 Comparison readout** (= P2.3 detail below). READY-SPEC (founder boundary
  locked; specification may encode it); BUILD is BLOCKED(A1b) — needs clean
  linked versions to compare. Stands on the BUILT P1 spine (each
  `IdeaVersion`/`EvidenceArtifact`
  carries its metrics; a `compare_started` event is pre-registered in the
  observability envelope). "vs your last version" — return Δ, drawdown Δ, what
  changed; short, model-voiced. The differentiator from one-off output.
  An updated date range is a material version change, so Argus compares the new
  version's assumptions and performance with the prior version rather than
  treating it as an unrelated run.

- **A3 Idea Ledger portfolio view.** DONE — merged as PR #147 (`e9180c8`).
  Saved ideas browse inside Omnisearch grouped by decision state
  (promising/watching/rejected/revisit) with filter chips; backend-owned
  `ledger_groups` are the source of truth for group order and counts (clients
  must not synthesize groups — recorded in `API_CONTRACT.md`); EN/es-419
  localized; live browser QA passed in both languages.

- **A4 Freshness on return** (memo §5.6 SOTA north — the MOAT-DEFINER, the
  biggest). BLOCKED(research/web lane; A1-A3 landing first); design notes
  allowed. Freshness infra (`context/freshness.py`) exists for context packets,
  not saved ideas. Smallest version: saved ideas show "Last reviewed" + a
  re-run-on-fresh-data delta + "what changed since I saved this?". Phase LAST;
  its own arc. When the canonical experiment is unchanged, a fresh rerun creates
  new immutable evidence on the same version; a changed date range or other
  material assumption creates a new version. The readout combines canonical
  numeric deltas with cited news, earnings, corporate-action, regulatory, macro,
  or other relevant event context. Mechanically verified corporate actions may
  be stated as facts; other event relationships use cautious language such as
  "coincided with" or "may have contributed." Argus must not claim unsupported
  causation, provide financial advice, or recommend buying, selling, or holding.

**Gate B — trust, recovery, measurement:**

- **B1 Latest-result answers from run facts (#140).** DONE — merged as PR #153.
  Peak-date/value and drawdown follow-ups answer from canonical
  `backtest_runs`/result facts; when pending edit state is active and a turn
  classifies as a result question, it answers and leaves the pending state
  intact (the #148 regression suites stayed green); `result_run_id` is preserved
  in response metadata. FOLLOW-UP: #164 (OPEN) tracks the residual refine wall
  for untyped fact questions — emit a typed result-followup fact focus/key.

- **B2 Asset preservation in messy company-name prompts (#142).** DONE — merged
  as PR #146. Messy multi-symbol company-name baskets (TGT + WMT + COST) survive
  through `interpret -> asset resolution -> canonicalize -> confirmation`;
  provider-backed name resolution feeds INTO interpretation as context, never a
  post-LLM text rescan. Historical regression note: #171 later reported this
  company-name case regressed on the live eval at `4eae18e` (alongside
  calendar-year windows nulled on recovery drafts), and PR #182 closed it on
  2026-07-08. Keep the `test_interpret_stage.py` basket assertions in the
  promotion gate.

- **B3 Measurement wiring** (= P2.5 below). DONE, off-spine. One lane delivered
  THREE atomic slices in this ORDER, each its own PR — never combined into one
  push:
  (1) **Eval harness** — MERGED (PR #143 at `e303aa3`, Fable-reviewed).
  `tests/evals/` with typed-outcome fixtures, prose-only judge
  (`argus-prose-quality-v1`), issue-tagged expected-fails (#142), gitignored
  scorecards, live spend behind `ARGUS_RUN_LIVE_EVALS=1`. Run policy: see
  `tests/evals/README.md` + the standing release discipline below. The
  landing gate is LIVE — runtime-behavior PRs run the live suite pre-merge
  from now on.
  (2) **Product events** — MERGED (PR #144): server-side-only PostHog capture
  through the sanitizer; US Cloud region recorded; frontend key stays
  present-but-empty per the launch runbook. Review fixes landed: off-loop
  emission (no event-loop stalls), payload built inside the guard, loud
  unrecognized-region warning, real `privacy_mode` emission.
  (3) **Append-only CostLedger** — MERGED (PR #145): reversible migration with
  structural append-only enforcement (revoke before grant), correlation ids,
  eval-run metering, shared entry normalizer; OpenRouter usage/cost parsers
  extracted to `openrouter_usage.py` to satisfy the merged-state modularity
  budget. Apply the migration to dev/prod Supabase at next deploy.
  B3 lane COMPLETE — harness gates merges, events flow, spend is metered.

- **B4 Recovery-copy / language-gate retirement (#154).** DONE — merged as PRs
  #174-177. Runtime prose composes from typed facts (#174); degraded recovery
  copy renders from typed codes (#175); result chrome renders from typed keys
  (#177); migrated language surfaces are test-guarded (#176). Per-language copy
  tables (`assistant_copy_for_result`, `recovery_messages.py`) are retired;
  prose follows the detected turn language everywhere and EN/ES parity is proven
  by the B3 eval harness, not hardcoded. Historical note: #171 previously
  flagged calendar-year windows nulled on recovery drafts; PR #182 closed the
  mocked/repro gates on 2026-07-08, and the live suite still must rerun on the
  exact promotion SHA.

- **B5 Interpreter cost/perf (#156, #157).** DONE — merged as PR #172. Automatic
  stable-prefix prompt caching on structured-artifact calls
  (interpretation/repair/field-fidelity/capability-conflict) and per-tier
  reasoning-effort env overrides (`ARGUS_STRUCTURED_REASONING_EFFORT`,
  `ARGUS_CAPABILITY_REASONING_EFFORT`) so dev runs cheap and production runs at
  full effort. OPEN follow-up on this lane: #159 (quality-gated model cascade —
  cheap primary, capable escalation; low-priority/deferred). NOTE: #160
  (interpreter dead-ends) surfaced from this lane's investigation but is a
  high-priority `main` blocker, not cost/perf polish — it lives in the
  main-promotion burn-down below, not here.

**Gate C — evidence credibility:**

- **C1 Execution realism — fees/slippage (#130).** DONE — merged as PR #178 into
  `codex/private-alpha-next` (9 atomic commits). Fees + slippage model end to
  end behind `ARGUS_ENABLE_EXECUTION_REALISM`. The capability is active by
  default, while modeled costs remain opt-in per idea, so runs without stated
  fees or slippage stay idealized. An explicit `false|0|off|no` value is the
  kill switch and restores the pre-realism path byte-for-byte. Cost-surface
  fields are recorded in API_CONTRACT and DATA_MODEL. Modeled costs remain off
  the required-idea path for the PMF stage, but the capability is integration
  truth, not an async cherry-pick lane.

**Gate D — memory controls and privacy:**

- **D1 Memory controls spec** (inspect/edit/delete/reset/"why was this
  used?"). POST-PMF READY-SPEC (extends the #137 Data Controls surface).
  Personalization-memory implementation is not required for P2 and remains
  blocked until PMF evidence justifies a user-confirmed `MemoryRecord` contract.
  No automatic broad memory before these controls exist.

**Design-only lanes** (all READY for notes/mocks; no runtime, schema, or UI
code): sanitized public excerpt design, voice-to-composer STT prototype, thin
iOS shell proof, broker/export packet design, security/privacy review,
monetization/entitlement architecture.

**Integration health (filed during #148 review verification; triaged
2026-07-03, refreshed 2026-07-07):**

- **#149** — FIXED (PR #168). Result-followup timeout recovery no longer dead on
  Python 3.10 (`asyncio.TimeoutError` vs builtin mismatch resolved); the failing
  test now passes on a 3.10 venv.
- **#150** — CLOSED (2026-07-08). Behavior half fixed by #166 (calendar-year
  audit drift) and PR #182 (stale provenance, cadence de-promotion, benchmark-
  owner repair — all #150 xfails removed). CI-visibility half fixed by PR #169:
  the full agent_runtime suite now runs on every runtime PR.
- **#151** — the last surviving #141 corner: an executable-complete draft plus
  model readiness prose never materializes the confirmation card, so bare
  affirmations re-confirm verbally (violates "canonical payload and UI prose
  disagree"). Still OPEN; queue before or alongside A1b. A `main` promotion
  blocker.
- **#171** — CLOSED (2026-07-08, PR #182). Sig1: refusal drafts materialize
  typed date intents into date_range (plus focused recovery for dropped
  windows); Sig2: missing fields recompute after the focused-repair context
  merge so provider-grounded baskets stay executable. The #179/#180 strict-xfail
  gates are un-xfailed and enforced by the #169 sweep. Residual risk is model-
  side only (grok options-classification nondeterminism), not spine logic.

##### Main-promotion burn-down — the interpret-surface lane (CLOSED 2026-07-10: #182/#185/#186/#187/#190 landed; #169 + #183 off-spine)

This was one regression cluster on the interpret/edit spine, most introduced by
the 07-06/07-07 merges, worked as a single-owner burn-down lane. All members are
fixed and merged. #188 is the arc's cautionary tale: #189 claimed to close it but
broke live; founder browser QA caught it, it was reopened, and PR #190 (`08d92f9`)
fixed it and was proven live with real Grok before merge (the interpreter-facing
live gate under "Standing release discipline" now enforces that permanently). No
code blocker remains between `codex/private-alpha-next` and a `main` promotion
candidate; the standing release-discipline reruns (live eval on the exact SHA +
clean-checkout gate) and the founder's options waiver remain after.

Shared surface (why they cannot be parallel implementers): `stages/interpret.py`,
`interpreter/artifact_assumption_edit.py`,
`interpreter/unsupported_request_context.py`,
`interpreter/date_window_repair.py`, `llm_interpreter.py`. This is the spine —
exactly one implementation owner at a time. Parallel SCOUT/repro is fine;
parallel edits are not.

Members and roots:

- **#171 — CLOSED (2026-07-08, PR #182).** Historical roots: Sig1
  (calendar-year windows nulled on recovery drafts) traced to #166 (`a5ac38b`,
  `date_window_repair.py` + `llm_interpreter.py`); Sig2 (#142 basket dropped,
  verdict flips to `unsupported`) traced to #165 (`a80d681`,
  `artifact_assumption_edit.py` + `unsupported_request_context.py`).
- **#150 — CLOSED (2026-07-08).** The mocked half of #171 Sig2 and the
  CI-visibility half are both closed: PR #182 removed the #150 strict xfails,
  and PR #169 landed the off-spine regression-sweep CI gate.
- **#160(A) — CLOSED (2026-07-09, PR #185).** Composer-`None` on a resolved fact
  key is now a typed decline that re-enters the planned-edit contract across all
  three anchors (pending refinement / active confirmation / completed run); the
  interpreter classifies change-requests naming a card fact as
  `refine_current_idea`. (B) was closed with #171 Sig1 in PR #182.
- **#151 — CLOSED (2026-07-09, PR #186).** Executable-complete post-result and
  confirmation-edit turns materialize the typed confirmation payload
  (`_stage_result_from_interpretation` + result-artifact-patch route-ownership);
  the benchmark-separation and `sizing_mode`-echo seams are fixed.
- **#187 — CLOSED (2026-07-09).** Demo-caught: benchmark separation must not empty
  an explicitly-owned traded universe; keep-evidence is planner provenance or
  active-draft continuity, never resolver echo.
- **#188 — CLOSED (2026-07-09, PR #189).** The pre-run chip-clarify twin: chip
  answers now route through the typed edit contract (`requested_field` is display
  scope only), so remove/replace apply set-complete, capital edits land, and
  changed-mind cross-answers apply.
- **#164 (med) — trailing follow-up.** Typed result-followup fact focus/key; the
  residual refine wall. Still open; deferred follow-up, never a promotion gate.

Landing order (serial on the spine):

1. ~~#171 Sig2 + #150~~ — DONE (PR #182): basket survives the underfilled
   repair; all #150 xfails removed.
2. ~~#171 Sig1 + #160(B)~~ — DONE (PR #182): typed-intent materialization on
   refusal drafts + year-contradiction guard on invented default windows; the
   #179/#180 gates are un-xfailed.
3. ~~#160(A)~~ — DONE (PR #185): composer-`None` decline re-enters the planned-edit
   contract; upstream classifies card-fact change-requests as refine_current_idea.
   Gate `test_workflow_fact_answer_then_composer_none_edit_reroutes_to_planner`
   un-xfailed.
4. ~~#151~~ — DONE (PR #186): confirmation card materializes from the
   executable-complete draft; gate un-xfailed. Demo follow-ups: #187 (benchmark
   keep) + #188/#189 (pre-run chip-clarify twin) also landed.
5. Full live eval on the exact SHA `c081901` → promotion candidate. Then #164
   (deferred, not a gate).

Off-spine, now LANDED: PR #169 (regression-sweep CI, hermetic
synthetic_unit_fixture catalog, runs on every runtime PR + nightly) and PR #183
(typed degraded-fallback clarifications + es-419 static rendering; the 9 stale
per-language copy tests re-pointed at typed asserts). Waiver valve: #171 permits issue-tagged scoped expected-fails to
unblock promotion if the founder accepts the regression short-term; the roots are
known data-dropping regressions, so fix is preferred over waive.

**Standing release discipline** (blocks `main`, not a lane): rerun the exact
clean-checkout suite gate (issue #134 / PR #135) before any branch or `main`
promotion instead of treating the repair as permanent proof for future SHAs.
Interpret-surface status (2026-07-10): #171/#150/#160(A)(B)/#151/#187/#188 are
all fixed and merged. #188 is why the gate below exists — #189's chip-clarify fix
passed mocked tests but broke live; PR #190 re-fixed it and was proven live before
merge. No interpret-surface blocker remains; promotion is unblocked on code.

**Interpreter-facing live gate (blocks issue-close, not just `main`):** an
interpret/edit/chat-facing fix is not "closed" on mocked-green alone. Before its
issue closes, a real-interpreter (live Grok) reproduction of its exact acceptance
case — driven through the running runtime, asserting typed state — must pass, and
that case must be added to the live eval suite so it guards the path permanently.
Mocked/injected-interpretation tests prove spine application, never interpreter
classification; treating them as sufficient is how #189 shipped a live-broken
fix. This graduates the AGENTS.md Evaluation pillar from lens to gate.
The eval harness (B3 slice 1, PR #143) is now a live landing gate:
runtime-behavior PRs run the live eval suite once pre-merge; every `main`
promotion candidate runs the full live suite on its exact SHA with no
unexpected failures (expected-fails only for open issue-tagged bugs); rerun
the suite after any interpreter model or provider change. #171 is fixed in the
mocked + repro gates; the live suite must be re-run on the exact promotion SHA
before promotion (known model-side risk: grok classifies options ideas
nondeterministically — a tier/prompt concern tracked with #159, not spine
logic). Integration stays a fast checkpoint; `main` is the heavyweight
gate.

"P2 done" = Argus **remembers, compares, and stays honest about staleness** — the
memo's moat, PMF-testable by one cohort of five trusted users (memo §15.8 gates).
The cohort gate remains unmeasured while the Render compute-plan bottleneck
prevents real internet-based testing.

##### P2.0 Spine guardrail gate (DONE — landed)

- Outcome: the six cross-cutting invariants above become an enforced review
  contract plus automated tripwire tests that fail when a deterministic text
  re-scan, post-LLM intent override, prose substring/alias match, literal-text
  grounding, or per-language copy table is introduced.
- Allowed surfaces: review docs (`CLAUDE.md`/`AGENTS.md` cross-reference),
  `docs/`, and focused guardrail tests under `tests/agent_runtime/`.
- Forbidden surfaces: any product runtime or UI behavior change. This slice only
  adds enforcement, not features.
- Verification: the new tripwire tests fail against a reverted/known-bad patch
  and pass against current `codex/private-alpha-next`.
- Browser QA: none required; not user-facing.
- Rollback: single docs+tests commit revert.
- Stop conditions: if enforcing a rule requires changing runtime behavior, stop
  and split that into its owning milestone.

##### P2.1 Capability truth (DONE — registry + executable boundary landed)

- Outcome: Argus stops overpromising. It honestly tells the user, in their own
  language, what it can and cannot run yet (for example "I can't run MACD yet,
  but I can test an RSI rule") without raw enums and without per-language copy.
- Mechanism: a canonical, typed Capability Registry with status per
  strategy/indicator (`executable`, `draft_only`, `future`). The registry is
  provided to the LLM interpreter as interpretation context/tools so the model
  itself knows what is supported. Post-LLM validation reads only typed canonical
  fields the LLM emits (`strategy_type` enum, `indicator.key` enum); it never
  scans prose and never flips intent from a text re-analysis.
- Folds in Slice D: inventory every current indicator/strategy code path (what is
  interpreted, validated, executable, rendered, documented), and feed truth into
  the registry. No broad indicator expansion until the audit proves current
  state.
- Surface containment: draft strategies (`momentum_breakout`, `trend_follow`) and
  draft/discovery indicators must have no user path. Today they are already hidden
  (the `@` indicator picker filters to supported only; the two draft strategies
  never appear in the frontend and are blocked at confirm), but containment is by
  convention, not construction. P2.1 makes it structural: derive the API template
  allow-list (`api/schemas.py` `StrategyTemplate`, `backtesting/config.py`
  `ALLOWED_TEMPLATES`), the save-passthrough set (`api/chat/strategies.py`), and
  discovery from the single executable registry; remove the latent frontend
  `draft_only` token plumbing (`web/components/chat/ChatInput.tsx`,
  `web/components/chat/types.ts`); and retire or guard the orphaned `signals.py`
  handlers for the two drafts. Stay narrow: do not widen the supported set in this
  slice. See `docs/archive/private-alpha-next-p2.1-capability-audit.md`.
- Allowed surfaces: capability registry domain module, interpreter
  context/tools wiring, typed post-LLM capability validation, registry-backed
  result/clarification copy that is model-voiced, docs (`API_CONTRACT.md`,
  `DATA_MODEL.md`, `CONVERSATIONAL_RUNTIME.md`), and focused tests.
- Forbidden surfaces: substring/keyword/alias matching over user text or LLM
  free-text; post-LLM intent override; per-language capability copy; reviving the
  quarantined `*_text_guardrail_response` or
  `non_alpha_indicator_text_guardrail_blocked_execution` paths; the legacy
  Strategies sidebar surface.
- Verification: focused backend tests for registry truth and typed-field
  validation; an eval set proving honest capability responses for messy English
  and Spanish prompts (capability honesty, not phrase gates); guardrail tripwires
  from P2.0 stay green.
- Browser QA: founder-guided run of an unsupported-indicator request in English
  and in Spanish; confirm honest model-voiced refusal-plus-alternative, no raw
  enums, no English leak in the Spanish session, supported path still runs.
- Rollback: revert the registry slice; capability behavior returns to current
  baseline with no schema debt.
- Stop conditions: any need to re-scan the user message, override intent
  post-LLM, or add language-specific copy. If the registry cannot express a
  capability truth as typed data, stop and redesign the data, not the gate.
- PMF gate: users describe a decision Argus clarified; trust foundation for all
  later slices.

Interim founder-outcome closure (2026-07-23): issue #241 and PR #266 completed
the supported-versus-non-executable product journey without expanding the
capability catalog. The final candidate `e10bdd2` preserved canonical strategy
identity and compatible facts across unsupported and future-performance
recovery, required explicit selection before creating a supported historical
draft, restored localized Quick take, and passed founder-visible browser QA.
It landed on `codex/private-alpha-next` as `bbd1d2b`. The completed design is
archived at
`docs/archive/2026-07-22-capability-truth-executable-boundary-design.md`;
existing links continue through a pointer at the former spec path.

Interim founder-outcome closure (2026-07-25): PR #268 completed **Argus always
progresses** at reviewed head `5585c6a`, which landed on
`codex/private-alpha-next` as `847c413b`. The slice proved bounded semantic
progress, durable ordinary-turn recovery, exact-once Run reconciliation,
fact-preserving continuation, concrete trajectory adapters, production-parity
browser journeys, one authorized real Run, reload-stable result truth, and
independent review. Deployment and tester exposure remain separate release
gates.

Evaluation-ledger closure (2026-07-28): PR #297 landed as `09044231` and
reconciled the concrete seven-session trajectory gate. The obsolete #241 and
#251 expected-fail masks are removed after complete concrete passes; #239
retains only its exact open-owner failures. Issue #243 is closed. The deployed
exact-SHA browser canary remains solely owned by #233 and was not duplicated by
this test-only landing.

Interim founder-outcome checkpoint (2026-07-27): PR #276 delivered the
default-on **grounded discovery and suggestions** baseline at candidate
`cc8b5563`, which landed on `codex/private-alpha-next` as `c212107a`. The slice
adds one typed discovery route, bounded source-backed Search,
provider-resolved candidates for equity, crypto, and currency-pair assets,
persisted EN/ES rendering, honest kill-switch recovery, and operational cost
evidence. PR #281 then landed
the frontend presentation slice as `8fde4ac1`: conversational next moves and
discovery candidates render as stacked rows under their owning message,
candidate reasons remain visible, and the persisted discovery evidence opens
in a sources panel without re-querying. PR #287 then landed Slice D as
`ea2b3f35`: discovery selection carries the resolver-owned identity through the
normal mention channel, durable Retry preserves it, and candidate validation
rejects unrelated ticker collisions. The chosen-state marker was cut, and
broader assumption carry-forward remains general interpreter work rather than
discovery debt. PR #291 then landed the visitor-owned Guest allowance at
`f1e65dde`. PR #295 landed as `8f17a45e` and completed the first continuity
pass: resolver-verified candidate rows are the cheap default, Search is the
explicit/current-facts exception, failure and charging remain typed, provider
work is offloaded, and J1/J2 continuity passed live in English and Spanish.
PR #298 landed as `ba0aa2f6` and completed the second pass: Search and
verification progress are truthful runtime events, each candidate owns its
source citation, and Guest message/simulation allowances survive session
renewal through visitor/day settlement. PR #300 landed as `c21f842f` and
completed comparison phrasing, named-target grounding, unsupported-target
disclosure, and discovery-act preservation through pending confirmations.
PR #303 landed as `da9f8500` and completed catalog-valid benchmark
price-coverage reconciliation. Promotion remains a separate gate. Issue #244
stays open only for the exposure-vehicle product decision plus hosted
migration, configuration, and exact-SHA canary proof. Full Omnisearch is the
remaining unbuilt founder outcome.

Integration-verification checkpoint (2026-07-27): PR #282 landed as
`059f8e82` and made the ordinary backend test environment provider-free by
default while adding both alpha API suites to CI. PR #286 then landed as
`75e87206`, closed #283 and #284, corrected the stale pure-approval fixture, and
made `backend-checks` run the complete `tests/` directory instead of a curated
file list. These are test/CI truth improvements, not product behavior changes,
provider-backed evidence, deployment, or tester exposure.

Discovery-selection checkpoint (2026-07-27): PR #287 landed as `ea2b3f35` and
closed Slice D of the chat next-moves lane. The selected asset's resolved symbol
and class now survive initial submission and durable Retry as a normal mention;
interpretation, guardrails, and confirmation remain mandatory. The same PR
added candidate/entity corroboration to prevent unrelated cross-class ticker
collisions. It intentionally filters crypto-exposure vehicles along with true
collisions; #244 remains open for that product decision, hosted configuration,
and exact-SHA canary evidence. Comparison-phrase reliability is complete
through PR #300.

Conversation/discovery checkpoint (2026-07-28): PR #300 landed as `c21f842f`
and closed issues #292 and #296. Comparison company names now reach
provider-backed resolution, unsupported named targets reconcile with a
localized pinned disclosure, and pending confirmations cannot capture typed
discovery asks. PR #302 landed as `928dcdbb` and closed #245: Recents now
discloses loaded chats in bounded five-row time groups and fetches older pages
only after an explicit accessible action while preserving PR #299 switching
truth. PR #303 landed as `da9f8500` and closed #301: catalog-valid benchmarks
with an explicit zero-bars response reconcile at card time instead of failing
later with misleading recovery. #244 no longer owns comparison phrasing; it
remains open for the exposure-vehicle product decision and release-owned
hosted migration/configuration/canary gates.

Post-merge stress-audit qualification (2026-07-25): the bounded closure evidence
above remains valid, but a longer same-conversation exploration at integration
SHA `b7fd6f08` exposed untriaged gaps in cost preservation, stale-action
presentation, fact-preserving recovery, supported strategy transitions, and
recovery-heading ownership. Quick take voice variance and one provider-timeout
fallback were recorded separately from confirmed continuity defects. Those
observations are now owner-bounded as #269-#273 and updated #249. Stale-action
settlement (#273) is complete through PR #277 at `2d5a2b52`; #269 was
classified as a Guest-only settlement defect, landed with Guest PR #279 at
`53e812e9`, and is closed.
Supported strategy-transition preservation (#270) is complete through PR #278
at `b80d95a2`; modeled-cost preservation (#271) landed through PR #280 at
`d16f7496` and is complete based on PR #280's bounded same-chat integration
journey.
#272 is complete through PR #288 at `9f3453a3`: recovery restores the current
canonical artifact anchor, preserves already-owned facts, asks only for
genuinely missing fields, keeps prior results immutable, and creates no
duplicate compute. No further protected-spine implementation lane is queued;
#270–#272 are closed, and representative repetition belongs to later promotion
qualification. #249 is complete through PR #304 at `59a274c3`: Quick take,
Explain result, stacked typed Try next rows, and recoverable failure have
distinct ownership while preserving PR #281's stacked-row/source-panel
contract, PR #299's conversation-switching cache, and PR #302's Recents
disclosure. See
`docs/reports/2026-07-25-always-progresses-post-merge-stress-audit.md`.

##### P2.2 Backtest credibility — fees/slippage realism (DONE — merged as PR #178, active by default)

- Status: DONE (PR #178, 9 atomic commits). Fees + slippage model end to end
  behind `ARGUS_ENABLE_EXECUTION_REALISM`. The capability is active by default;
  costs remain user opt-in per idea, and no-cost runs remain idealized. The
  explicit `false|0|off|no` kill switch preserves the pre-realism path
  byte-for-byte. Cost-surface fields are recorded in API_CONTRACT and
  DATA_MODEL. The scope below is delivered, not pending.
- Outcome: results carry assumptions a user can explain without founder help.
- Scope: the current launch adapter is the sufficient P2 engine boundary (no
  engine internals leaking into product objects); audit and surface fees,
  slippage, splits/dividends, missing-data behavior, benchmark correctness, and
  drawdown/risk metrics into the EvidenceArtifact with provenance and digest.
  A formal multi-engine interface is deferred to Slice M and activates only
  when a second validated engine or workflow proves a concrete need.
- Forbidden surfaces: building a new quant engine; expanding metrics beyond the
  audited, trustworthy set.
- PMF gate: users can explain artifact assumptions without founder help. Full
  verification/QA/rollback spec is authored when this slice activates.

##### P2.3 Comparison loop

- Outcome: a user can compare the current backtest against a prior
  same-asset/same-strategy idea or a previous IdeaVersion and get a short,
  grounded, model-voiced readout.
- Surfaces: entry points from Omnisearch and the result card; readout-first, no
  new heavy comparison dashboard.
- PMF gate: at least two of five users voluntarily revisit or compare. This is
  the retention loop. Full verification/QA/rollback spec authored at activation.

##### P2.4 Failure and recovery trust (recovery pattern DONE via B4; live parity gate open)

- Status: the model-voiced, language-agnostic recovery pattern is DELIVERED — B4
  (#154, PRs #174-177) retired per-language copy so recovery/degraded prose
  renders from typed codes/keys in the detected turn language. The PMF gate below
  (Spanish-preferring users complete the loop unaided) is validated by the live
  eval harness; #171 is closed in mocked/repro gates, and the interpret-surface
  cluster (#160/#151 + demo follow-ups #187/#188) is fully fixed and merged — the
  remaining promotion step is the exact-SHA live-eval rerun.
- Outcome: when Argus fails or hits an unsupported request, recovery preserves
  the user's idea, clarifies without making the user feel wrong, explains
  unsupported capability in product language, and never leaks raw provider/runtime
  errors or English fallback into a Spanish session.
- Establishes the model-voiced, language-agnostic recovery pattern (the hotspot
  where the quarantines hardcoded per-language copy).
- PMF gate: Spanish-preferring users complete the loop without founder help. Full
  spec authored at activation.

##### P2.5 Measurement and eval harness (DONE)

- Outcome: the loop is instrumented so founder-guided sessions can produce
  PMF-gate signal once testing capacity is restored. B3 wired the
  `argus_observability_event/v1` envelope to PostHog product events, delivered
  the append-only first-party CostLedger, and established a portable eval
  harness over the locked built-surface categories.
- Posture: analytics is measurement-only; privacy follows memo 15.5
  (`raw_alpha -> redacted_default -> metadata_only -> disabled`), never sending
  credentials, balances, holdings, audio, or route receipts to analytics.
- Add comparison, freshness, and other future-feature categories only when
  those product lanes land; instrumentation must not pretend an unbuilt surface
  exists.

##### Guest experience — integrated checkpoint (PUBLIC EXPOSURE GATE OPEN)

- Status: PR #279 landed on `codex/private-alpha-next` as `53e812e9`. Blocks
  1–3 implement verified anonymous identity, fixed temporary
  workspace policy, lifetime allowances, cleanup, guest shell, conversion, and
  owner-scoped capability gates. Block 4 adds the approved privacy-safe funnel
  through the existing observability envelope. PR #298 then landed as
  `ba0aa2f6`, re-keying Guest message and simulation limits to a privacy-safe
  visitor/day identity so renewing the temporary session cannot reset them.
  The integrated code is not a public-ready or deployed release.
- Guest is now an accepted part of the normal product shape:
  `ARGUS_GUEST_ACCESS_ENABLED=true` and
  `NEXT_PUBLIC_GUEST_ACCESS_ENABLED=true` are default-on emergency kill
  switches. `ARGUS_PUBLIC_ACCOUNT_ACCESS_ENABLED=true` is the independent
  permanent-account gate and the founder opened it in production on 2026-08-12,
  so public registration is open.
- Public exposure still requires a branch-deployed exact-SHA canary, hosted
  anonymous-Auth and Turnstile controls, trusted-origin/rate-limit proof, a hard
  provider budget, cleanup scheduling, cost/latency calibration, a completed
  release manifest, and founder go/no-go. The authoritative checklist is
  `docs/GUEST_PUBLIC_LAUNCH_SAFETY.md`.
- Grounded Discovery and Always Progresses are integrated dependencies. Guest
  Omnisearch remains owner-scoped, while the ordinary chat runtime preserves
  the integrated provider-backed discovery contract.
- Authentication now lands both guest and registered identities directly in
  ordinary chat. There is no guest onboarding bypass or registered
  onboarding/`primary_goal` branch; guest behavior differs only through
  verified identity, persistence, allowances, and conversion policy.
- Founder decisions still open: first traffic size, CAPTCHA/provider posture,
  acceptable cost and latency bands, cleanup cadence/owner, and canary approval.
  Public-account enablement is no longer among them, because the founder enabled
  it in production on 2026-08-12 as recorded in
  `docs/release-manifests/2026-08-12-main-production-promotion-716221f.md`. Two
  prerequisites were written for that gate, and the flag being on does not waive
  either. The account-method proof is owned by `docs/API_CONTRACT.md`, where
  whether its evidence was produced is an open founder question. The abuse
  controls are owned by the minimum bundle in
  `docs/GUEST_PUBLIC_LAUNCH_SAFETY.md`, which enumerates the Turnstile, velocity,
  and origin-truth checks for internet-facing exposure.

##### Conversational edit contract (macro pattern) — DONE (landed `0fb32c1`)

Status: BUILT + LANDED on `codex/private-alpha-next` (6 commits). Typed `EditOperation`
(add/remove/replace/set/clear × assets/benchmark/dates/capital/DCA/timeframe/fees/
slippage), deterministic applier (multi-op, no silent drop), language-aware planner,
conflict-aware prompt, model-voiced honesty note. Verified unit + live probe EN/ES + EN
browser. Spec: `docs/specs/private-alpha-next-conversational-edit-contract.md`. The
remaining seam is loop **Slice 1 (refine -> linked version)** above — refine routes to
the wrong brain. Original design notes preserved below for reference.

- Idea: the confirmation-card action chips (Run backtest, Change dates, Change
  asset, Adjust assumptions, Cancel) and natural-language turn edits should be two
  entry points to ONE canonical set of edit operations on the pending artifact. A
  user can say it in their turn ("change the start date to the beginning of this
  year and also add AMZN") and Argus interprets and applies it, or click a chip to
  be direct, or Argus can offer "what would you like to change?". Chips become a
  convenience layer over the contract, not a separate path (consistent with the
  "no duplicate action surfaces" rule and the LLM-first spine).
- Why it matters: a multi-intent natural-language edit currently applies one
  operation (asset add) but can silently drop another (the date change). That
  observed behavior is a symptom of an under-specified multi-operation edit
  contract, not a one-off bug. Designing the contract (what operations exist, how
  multi-op NL edits compose, how chips and NL both map to the same operations) is
  the adequate fix; a point patch risks baking in the wrong model.
- Spine constraint: relative dates ("beginning of this year") must be resolved by
  LLM interpretation and the planner must apply ALL operations in a turn. No
  regex/text-scan for date phrases, no per-language gate (P2.0 guardrails apply).
- Sequencing: candidate near P2.1, since both live on the confirmation/edit
  surface. Spec before implement.

#### P2 stop conditions (whole wave)

Stop immediately and escalate to the founder if:

- a slice requires re-scanning user text, overriding LLM intent post-hoc, or
  per-language runtime copy;
- canonical payload and UI prose disagree;
- the frontend invents state the backend did not supply;
- schema/API changes appear without matching docs and tests;
- a slice grows beyond one revertable commit family;
- live browser QA fails after tests pass, especially Spanish parity.

Until a lane is READY on the execution board, do not implement its runtime,
backend, schema, or UI changes. The board status is the authorization:
READY-BUILD lanes may implement now, READY-SPEC lanes may write specs and ask
the founder questions only, SCOUT lanes may add fixtures/failing tests only,
and BLOCKED/DESIGN-ONLY lanes stay out of runtime. The interpret/edit spine has
one owner lane at a time (currently A1, #141); parallel runtime lanes take
rebase duty.

## Parallelization Rules

Serialized:

- canonical object contract;
- migration/API contract if needed;
- evidence capture;
- reload/hydration path.

Parallelizable around the serialized spine:

- docs/spec updates;
- UX preview/action spec;
- analytics event schema;
- security/privacy review;
- indicator/evidence audit;
- voice, public excerpt, and broker/export design-only specs.

## Archive And Classification Rules

- Canon docs are never archived.
- This roadmap and the decision memo are active for Private Alpha Next.
- CI/CD SOTA, the launch runbook, and the release manifest template remain
  active release-discipline references, not product-roadmap owners.
- Historical superpowers plans and closed milestone specs should receive
  historical banners or move to `docs/archive/` only after confirming no active
  doc points to them as command sources.
- `temp/bytebytego/bytebytego.md` remains a supporting local memo unless the
  founder promotes it into `docs/specs/`.

## Integration Workflow After P0

The P0 reintegration strategy worked directionally:

- stable remote integration checkpoint stayed clean;
- contaminated autonomous work was preserved under quarantine instead of being
  mixed into the gate;
- reintegration restarted from the clean branch;
- P0 landed as a focused, tested, revertable slice.

Future P2 work should keep that discipline:

- work on a focused child branch from `codex/private-alpha-next`;
- promote to `codex/private-alpha-next` only after tests, browser QA, and review;
- keep each slice revertable;
- use bounded scouting, specs, tests, and reviews only when they reduce risk;
- keep architecture, prioritization, and final promotion with the main
  orchestrator and founder.
