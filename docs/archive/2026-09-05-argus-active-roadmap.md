> **ARCHIVED 2026-09-18.** Superseded 2026-09-05 by the grounded-finance board, itself archived at [`2026-09-17-argus-grounded-finance-roadmap.md`](2026-09-17-argus-grounded-finance-roadmap.md). The active board is [`docs/specs/argus-answers-that-stay-true-roadmap.md`](../specs/argus-answers-that-stay-true-roadmap.md).

# Argus Active Roadmap

Status: **SUPERSEDED 2026-09-05** by
[`2026-09-17-argus-grounded-finance-roadmap.md`](2026-09-17-argus-grounded-finance-roadmap.md).
Landed work and the secondary tracker state below remain valid history; the
ranked items are no longer the board. Opened 2026-08-06.

Supersedes the two short-lived next-cycle boards and the completed interim
roadmap. `docs/specs/private-alpha-next-roadmap.md` remains as P2 history and
contract reference, not as the active board.

## Why this board exists

A competitor review on 2026-08-06 ([driven.ai](https://driven.ai)) produced one
finding that reorders everything: Driven does not backtest, so it is not chasing
the same job. But its entire first session is a research read, and that is the
same first message Argus gets. Argus currently refuses it.

Users are lost at the first question, before reaching the thing Argus is
actually good at. That is the gap this board closes.

This is a timing change, not a thesis change. Argus stays the pre-flight
checklist: test the idea, see the evidence, remember why. It does not become an
investment command center, an agent marketplace, or a trading surface.

## Vocabulary (founder-locked 2026-08-07)

Two words that were previously conflated, and are not the same thing.

**Memory** is the shipped feature. Argus proposes something worth remembering,
the user confirms, and it is recalled later. Inferred then confirmed. It lives
in `src/argus/memory/`, is opt-in, and is fully inspectable, editable, and
deletable. Call it memory, never "personalization memory".

**Personalization** is declared, not learned: the user tells Argus who they are
and how they want to be spoken to, from options Argus defines. Name, preferred
address, tone, interaction style. It does not exist yet. When it is built it is
a settings surface, not a memory mechanism, and it needs no consent flow because
the user authors every value directly.

The distinction matters because the consent posture differs. Memory stores
Argus's inferences about you and therefore needs earned opt-in. Personalization
stores your own stated preferences and needs none.

The flag `ARGUS_ENABLE_PERSONALIZATION_MEMORY` still carries the old name. It is
live and gating shipped code, so renaming it moves the release contract
(`.env.example`, `render.yaml`, `argus-env.sh`, the release profile, canary, and
QA scripts) together. Do it when something else touches that surface, not as a
standalone edit.

> Correction 2026-09-25: The "default-off flag" wording below is the
> landing-time state, not the current production state. Current memory
> availability is owned by
> [PRODUCT.md Current production availability and planned changes](../PRODUCT.md#current-production-availability-and-planned-changes).

## Operating rules (founder-locked 2026-08-06)

1. **No phases, no incubation.** When a lane is dispatched it is built
   production-ready end to end: implementation, tests, evidence, docs, and
   user-facing polish in one lane. Review checkpoints are not a delivery model.
2. **Flags, not ceremony.** Work that is not ready for users ships behind a
   default-off flag on the same terms memory did. The flag is
   the safety boundary; staged branches are not.
3. **Items 1 and 2 are serial with each other.** Both rewrite the same
   interpreter and confirmation-card surfaces, so they cannot run in parallel
   without fighting. Everything else runs concurrently behind flags.
4. **GitHub issues are secondary.** An open issue earns work when it serves a
   board item, blocks items 1 or 2, or the founder steers it in. Otherwise it
   waits. The board leads, the tracker follows.
5. **Non-overlapping file ownership.** Parallel lanes must not share spine
   files. Where they do, they serialize.
6. **Nothing merges on self-report.** Per-lane founder gate, exact-head
   evidence, browser proof for anything user-facing.

## The five

### 1. Answer the first question — LIVE IN PRODUCTION 2026-08-11

Merged as PR #396 at `ef08b25d`, 350 files. Closes #377 and #384.

**Promoted to production 2026-08-11** at `d67cef92`, 451 commits, recorded in
[`2026-08-11-main-production-promotion.md`](../release-manifests/2026-08-11-main-production-promotion.md).
Argus answers an ordinary finance question in production, in both languages,
without refusing. That was the point of the cycle.

Three things came out of that promotion and none of them blocked it:

- **The database was nine migrations behind at deploy**, because nothing
  applies migrations and no gate checked. The rail was inert for roughly two
  hours: production's constraint rejected `chat.research`, so the allowance
  read failed closed and turns answered without research. Remediated during
  the promotion; the missing gate is **#449**.
- **Fast-classified research answers carry no citations** (**#451**). The
  `fast` config has only `finance_search`, whose sole citation channel is the
  provider's own hosts, which the filter correctly drops. The sources drawer
  is built and gets nothing. A question with a narrative clause needs
  `balanced`.
- **The canary is red at a test that asserts Turnstile fails** (**#452**). Its
  browser leg drives a headless browser through bot protection. Splitting the
  release-coherence half from the browser half is filed.

The release-coherence half earned its keep the same day: it caught
`argus-backtests` running a week behind api and app before any paid journey
ran.

**Enabled 2026-08-10.** `ARGUS_RESEARCH_RAIL_ENABLED` and
`NEXT_PUBLIC_RESEARCH_RAIL_ENABLED` are `true` in `render.yaml`,
`.env.example`, `.github/argus-env.sh`, and the release profile. Founder
decision: answering the first question is the product, not an experiment, so
it ships on rather than dark.

That flip was made against the two conditions recorded in rail spec §13b,
knowingly. Close #411 and #412 rather than treating the flip as having
retired them.

All five question shapes work from an organic typed question in both
languages: market pulse, competitor analysis, screening, sector radar, and
single-stock analysis. Grounded discovery was absorbed rather than left beside
it, so one provider layer, one classifier, one cache, and one meter serve
everything. Guests get their own research allowance of three per day.

**Two conditions on turning the flag on**, recorded in the rail spec §13b and
open as issues. Both are wrong-when-enabled rather than wrong-as-shipped:

- **#411** the routing gate reads which execution field is set, never how it
  was set, so it cannot tell an interpreter-injected `strategy_type` from a
  stated one and hands the decision to a second classifier.
- **#412** a research job whose finalizer dies is settled by a reconciler that
  nothing schedules, so the answer is lost until an operator runs it by hand.

Also left open, none blocking: **#404** the vaguest market phrasings can still
be answered from model knowledge, honestly labelled; **#407** the source list
caps at five by arrival order without deduping by publisher. **#409 is now
closed**: cost is derived from actual usage rather than tool fees alone, so the
guest ceiling of three can be revisited against a number that is finally
trustworthy.

The original scope, kept for the record:

Argus must handle an ordinary finance question without refusing it, then turn
the answer into something runnable.

- A factual or educational turn gets a real answer. No capability refusal, no
  confirmation-card interrogation, no unsupported-strategy rejection on what is
  obviously a knowledge question.
- A research read produces sources, freshness, and candidate entities, then
  offers one to three fully specified, runnable test cards. Tapping one opens
  the normal confirmation card. It never auto-runs.
- Suggestions are prebaked and backend-owned. The model may rank or explain
  closed candidates; it may not mint symbols, strategies, or asks. Every
  candidate passes resolver, asset-class, and coverage checks before it is
  tappable.
- Cover the full question range the founder asked for on 2026-08-07: live
  quotes, single-company reads, cross-company comparison, screening, and market
  stats. An earlier draft of this line restricted the lane to two jobs; that was
  a recommendation the founder overruled the same day, and it should never have
  survived here. No skill store, no menu, no picker: the range is reached
  through natural language, never a capability list.
- **Spec is written and founder-locked:**
  [`2026-08-07-research-to-test-rail.md`](https://github.com/lagarcess/argus/blob/651870a54be4e5506dbb38f3902fef1a97eef8df/docs/superpowers/specs/2026-08-07-research-to-test-rail.md).
  It supersedes the narrow competitor-comparison framing: Argus is no longer
  bounded to backtesting. Perplexity `finance_search` at $5 per 1,000
  invocations grounds quotes, fundamentals, segments, earnings, peers, screening
  and ETF constituents, selected by question shape with no menu. Closes #377.
- Peers now come free from the provider, which **retires the deterministic peer
  recommender in PR #384**. Close that lane rather than building it.
- **Follow-up, not in the rail lane:** the rail spec details the signed-in empty
  chat but leaves the guest empty state as placeholder and chips only. A landing
  page was considered on 2026-08-07 and rejected, because a composer that
  carries the typed question into chat makes the landing page and the guest
  entry the same surface with two sets of copy, and a front door with the chat
  behind it rebuilds the lobby this board refuses. The idea worth keeping is the
  inverse: the guest empty state becomes the entry experience, with a hero line,
  a cycling typewriter composer showing the range of questions, and trust
  signals sitting above the composer, collapsing into the conversation on first
  send. Revisit after mobile lands, since the exposure gate comes first.

Absorbs stabilization items formerly ranked Tier 1 #1, #3, #4, and the
knowledge/statistics macro. The interpreter ValueError work is complete and
awaiting review; it removed the dead-end banner but the underlying refusal
remains, which is this item.

Simplicity bar: someone who knows nothing about investing must understand the
answer and the offered tests.

### 2. Master editing — COMPLETE 2026-08-11

Both halves are built, merged, and enabled. Closes #433, #437, #335.

**The conversational half** merged as PR #431 at `522c6d9c`, 148 files, after
seven review rounds. Compound multi-parameter edits in one turn, the disclosure
chain, scoped widening, the accepted-value envelope, and the card cut from five
actions to three. That was the largest known reliability gap in the loop and it
went live with the same-day promotion.

**The in-place drawers** merged as PR #443 at `512a52b7` after twelve more
rounds, and `ARGUS_IN_PLACE_CARD_EDITS_ENABLED` is now `true` in all four
release-contract files. They reach users at the next promotion, since production
does not yet carry the guard code.

**The twelve rounds are the story worth keeping.** The drawers write to a card
without spending a turn, which is a new write path, and protecting it turned out
to depend on the run lifecycle being sound. It was not. A worker could flip a
failed job to succeeded after the card had been handed back, leaving an editable
card beside a finished result computed from different numbers. Rounds 1 and 2
guarded the message row, then the conversation. Round 4 moved liveness into the
card as one oracle every reader derives from. Rounds 5 through 11 then found
seven more holes, none of them in the original code and all of them in the fix.

**A guard cannot be finished while the truth it checks is split across three
stores.** That is why the flag existed: a pre-stated exit made stopping cheap
when the third round hit the same leg, and the surface shipped dark for a day
instead of shipping wrong. Round 12's finding was declined as pre-existing
architecture and filed as #460 rather than left in a resolved thread.

Spun out and still open: #439, #440, #450, #460. Declined with rationale: #432.

The original scope, kept for the record. The confirmation card carries exactly
three actions: **Run backtest**, **Change/edit assumptions**, **Cancel**.

- Change/edit assumptions is the only entry point to editing anything.
- Compound, multi-parameter edits must work in one turn. "Change this and add
  that" cannot silently drop half the request in any language. This is the
  largest known reliability gap in the existing loop.
- Capital and dates additionally get in-place editing that spends no turn: an
  elegant drawer on the confirmation card, in the spirit of how the profile
  monogram is edited in profile settings. This is in addition to the
  conversational path, never a replacement for it. On web the entry point is a
  small dedicated row, in the shape of "edit costs". On mobile it reuses the
  sheet primitive defined in the mobile spec, so both surfaces share one
  pattern rather than inventing two.
- **Consolidate the confirmation card from five actions to three.** Today it
  shows Run backtest, change dates, change assets, adjust assumptions, and
  Cancel. The end state is Run backtest, Change/edit assumptions, Cancel.

  **This is gated on multi-edit working, and must not ship before it.** Change
  dates and change assets are deterministic entry points that tell Argus
  exactly which field is being edited. Removing them routes every edit through
  the free-form conversational path, which is the path that currently drops
  compound edits. Consolidating first would remove the working escape hatches
  and leave only the broken one.

  Motivating case, observed in alpha testing 2026-08-06: a user tapped change
  dates, then broadened the request mid-sentence to include other changes while
  Argus was waiting on a single field. The lesson is subtler than "fewer
  buttons": even a scoped entry point must accept a broader edit gracefully
  rather than holding the user to the button they pressed.

Absorbs #335, the #141 macro, and the #237 umbrella.

### 3. Mobile PWA — SHIPPED 2026-08-08

Merged as PR #393 at `01044cda`, 158 files. The public exposure gate: nothing
ships publicly while phones are broken.

Not flagged. The responsive shell is unconditional, so there is nothing to turn
on at promotion.

The breakpoint audit lane that followed (PR #420) treated the shipped shell as
the thing under test and found two defects it had shipped with: **#421**
account security unreachable below 1024, since fixed, and **#422** seven
lower-severity findings still open. Neither blocks promotion.

**Spec is written and founder-locked:**
[`2026-08-06-mobile-pwa-responsive-shell.md`](https://github.com/lagarcess/argus/blob/651870a54be4e5506dbb38f3902fef1a97eef8df/docs/superpowers/specs/2026-08-06-mobile-pwa-responsive-shell.md).

Shape as built:

- Responsive by screen width, not device sniffing, on custom breakpoints
  matching DESIGN.md section 8 rather than Tailwind defaults.
- Two thresholds: below 1024px the dossier becomes an overlay sheet, below
  720px the full mobile treatment applies.
- The sidebar becomes an off-canvas drawer behind a `=` trigger. Web is
  unchanged.
- One sheet primitive at three heights serves the dossier, the discovery
  sources pane, and item 2's capital and dates editor.
- Delivery is responsive PWA polish. The native-shell and full-native options
  are closed, not deferred.
- Prerequisite found while speccing: `layout.tsx` references a manifest that
  does not exist, and there is no apple-touch-icon or theme-color, so
  home-screen install does not look app-like today.
- Desktop and laptop behavior must not regress; it is already strong.

### 4. Compare your own work (parallel, behind flag)

Previously called "product memory". That name was wrong: none of it is a memory
system. The records already exist and are already written; what was missing is
reliable versioning and a way to read them back.

**Spec is written and founder-locked:**
[`2026-08-07-compare-your-own-work.md`](https://github.com/lagarcess/argus/blob/651870a54be4e5506dbb38f3902fef1a97eef8df/docs/superpowers/specs/2026-08-07-compare-your-own-work.md).

- Serves three real questions: which of my ideas did best, did my change help,
  should I do A or B.
- Spans three homes deliberately: versioning belongs to editing and mints on
  confirmed run rather than on edit, comparison answers are another question
  shape on the research rail's one router, and the only new surface is a
  multi-select confirmation card.
- **Works with memory off**, because reading your own runs is the product.
  Memory is a pre-wired optional sharpener for conceptual phrasing and personal
  success criteria, never the mechanism.
- Candidate relevance is structured filtering, not semantic search. The set is a
  bounded personal one, so exact beats fuzzy.
- Grounded with market context that explains *why*, under a hard boundary:
  numbers come from your evidence artifacts, Perplexity never restates a
  simulation result.

### 5. Sharing — BUILT AND DARK, 2026-08-10

Merged as PR #397 at `33001adc`, 101 files. Both
`CUADRAO_EVIDENCE_RECEIPT_SHARING_ENABLED` and its `NEXT_PUBLIC_` twin stay
`false`, and that is deliberate rather than pending.

**Why it did not ship on with the rail.** The founder parked it until Argus
reaches a subjective reliability bar they judge themselves, and #417 is an
open flag-on blocker: the receipt freezes assumptions as English prose, so a
Spanish reader sees English facts. Enabling this surface puts a stranger's
first impression of Argus behind a link, which is the one place a known copy
defect cannot be tolerated.

Distribution, once there is something worth spreading.

**Spec is written and founder-locked:**
[`2026-08-07-sharing-evidence-receipts.md`](https://github.com/lagarcess/argus/blob/651870a54be4e5506dbb38f3902fef1a97eef8df/docs/superpowers/specs/2026-08-07-sharing-evidence-receipts.md).
Complete, all decisions made, dispatchable when the pillar comes up.

- An immutable, sanitized evidence receipt frozen at creation. Not a shared chat
  transcript, and never a live view.
- Owner-created, owner-revocable, stripped of private runtime detail. Memory is
  never shareable under any circumstance.
- Not-advice framing is stronger in a receipt than in the app, because the
  viewer has none of the context an app user has.
- The public view is mobile-first and owns its own layout, since shared links
  are opened from messaging.
- Deliberately last of the five: sharing a broken loop spreads a bad
  impression faster than a good one.

Decided from prior art rather than preference: never indexable with no
discoverability toggle, anonymous with no attribution, results only, no expiry
but a receipt list so revocation is real. ChatGPT exposed roughly 100,000 shared
conversations through a toggle users misread, and Claude shipped share links
with no noindex at all.

## Specced, not yet placed

### Follow up on unfinished work

**Spec is written and founder-locked:**
[`2026-08-09-follow-up-on-unfinished-work.md`](https://github.com/lagarcess/argus/blob/651870a54be4e5506dbb38f3902fef1a97eef8df/docs/superpowers/specs/2026-08-09-follow-up-on-unfinished-work.md).
Rank against the five is a founder call and is deliberately not claimed here.

Argus brings a user back by finishing a turn they started and abandoned. "You
compared Costco, Walmart and Target three weeks ago and never tested it. Costco
reported earnings since. Want to run it now?"

- **It amends the rail spec in three places, and the amendments are written
  into that file.** "Pull on return, never push" is replaced by: Argus may
  follow up only on something the user started and left open, and only when a
  fact specific to that thing changed. The initiation is the user's own,
  deferred, so an alerting product is structurally unreachable: Argus never
  picks the subject. Rail section 11c retires the requirement that memory record
  research subjects, open threads, and comparison sets, and rail section 12b
  retires "autonomous monitoring" from the non-goal list.
- **A reader over canonical records, working with memory off**, on the same
  precedent as pillar 4. Memory is a ranking sharpener only, and
  `MemoryCategory` does not grow.
- **It cannot be built yet, and that is the headline.** The rail flag is false,
  so zero open threads exist. The spec's section 0 carries four checkable
  preconditions: rail on in production, #411 and #412 closed, real threads
  accumulated to a stated floor, and the email decision made.
- **Email is a hard dependency and is not approved.** Widening the
  single-purpose Resend helper into a consented mail capability is its own lane
  and its own founder decision.
- **Shares one reader with the empty chat polish sidequest, Piece 2.** Ownership
  is stated in the spec so two do not get built.
- **Maintenance tooling is merged, but nothing is scheduled.** #414 added the
  retention and reconciliation entry point. #448 removed the uncreated
  `argus-maintenance` Render surface and its release enumeration. The jobs stay
  available for an operator to run from a laptop against an explicit target.
  Any future scheduler is a new founder decision and a new release contract;
  it is a precondition for this pillar, not a given.

## Continuous, not a lane

**Conversational runtime robustness.** Keep exercising the real chat runtime and
fixing what breaks. This runs alongside every lane rather than waiting its turn,
and it is how items 1 and 2 stay honest after they land.

Standing chore work, picked up alongside lanes rather than scheduled:

- **Extend the modularity budget to tests.** `.agent/modularity_budget.json`
  scans only `src` and `web`, and explicitly excludes `web/__tests__/**` and
  `web/e2e/**`. No Python test file is governed at all. The asymmetry is the
  problem: the interpreter lane had to extract a module to change production
  code by 13 lines, while a 2000-line test file lands with no friction. Six
  `tests/memory/` files now exceed 1000 lines, the largest bigger than the
  service it tests. Add `tests` as a scan root with baselines captured from
  current reality so it binds future work without a mass rewrite.
- **Strip the legacy Collections and Strategies code.** Dead ends and surfaces
  no longer exposed, plus any environment plumbing that only served them.
  Follow the onboarding strip-out pattern: remove the surface, keep legacy
  records read-safe, drop the env plumbing. **Not in scope:**
  `ARGUS_ASSET_PROVIDER_MODE`. An earlier draft listed it as a dead alias; it
  is live. It overrides `ARGUS_MARKET_DATA_PROVIDER_MODE` in
  `src/argus/domain/market_data/assets.py` so tests can pin the asset catalog
  independently of market data, and it is used by `tests/evals/` and
  `tests/agent_runtime/`. Leave it. It is worth documenting rather than
  removing, since a silent two-variable fallback chain is the same env-confound
  shape that has produced fake test failures before.
- **Implement the usage allowance meter colors.** `.agent/designs/argus/DESIGN.md`
  section 23 already specifies this completely and it was never built: teal
  at or above 30% remaining, `--rui-color-warning` above 10% and below 30%,
  and `--rui-color-danger` at or below 10% including exhaustion, with the
  lowest normalized active window governing. Color stays supporting information
  only, so the exact remaining count and truthful reset time must survive, with
  no pulsing or terminal-style treatment. Today `UsageModal.tsx` and
  `ProfileMenu.tsx` reference none of those tokens.

## Sidequest lanes

Bounded, dispatchable work that is not one of the five and does not block them.
Each carries a sequencing constraint, because small does not mean parallel. Most
of these touch a file a main lane already owns, and two agents in one file is
how the last split brain happened.

### Empty chat polish

**Status: built, in review as PR #415.** Sequencing note kept for the record:
unblocked when pillar 1 merged, parallel-safe with the mention tags lane. It touches `EmptyChatSurface.tsx`, `ChatInterface.tsx`,
`EmptyChatGreeting.tsx`, and both locale files. The rail owns all four today and
created the greeting component. PR #406 touches none of them, so once the rail
lands these two run at the same time.

Three pieces travel together because they share the same surface and the same
two locale files. Split into separate lanes they would have to be serial with
each other anyway, so splitting buys nothing and costs a merge.

#### Piece 1: retire the show/hide suggestions toggle

No major assistant ships this control. ChatGPT, Claude, Gemini, Perplexity, and
Grok all put starter suggestions in the empty state and let them disappear on
first interaction. A toggle is a control for a problem that resolves itself in
one tap, and every control costs the user a decision. That is the no-menu rule
applied to the interface rather than to capabilities.

It also renders below the legal disclaimer, in the phone thumb zone, so the
least important element on the screen occupies the most valuable position.

**Scope:** the toggle button in `EmptyChatSurface.tsx`, its `showSuggestions`
and `onToggleSuggestions` props, the `showSuggestions` state in
`ChatInterface.tsx`, and the `chat.show_suggestions` and `chat.hide_suggestions`
keys in both locale files.

**Behavior after:** suggestions render whenever the empty chat surface renders,
and stop once a conversation has a message, which happens for free because the
surface stops rendering. Nothing replaces the toggle: no dismiss gesture, no
auto-hide timer, no settings entry.

**There is no migration to write.** The state is a plain `useState` with no
localStorage, cookie, or server field behind it, so nothing persists and no user
is stranded. Confirm that before deleting, but do not invent a migration for
state that does not exist.

**One decision to raise, not take.** Two flags gate the same chips.
`[removed obsolete setting]` is `false` in `render.yaml`,
`.github/argus-env.sh`, `.github/private-alpha-release-profile.json`, and
`.env.example`, while the research rail's own flag governs the same surface and
rail spec section 10 makes prebaked suggestions part of the signed-in empty
chat. That is one flag too many. Retiring an env flag is a release-contract move
and all four files travel together, so it is a founder call.

#### Piece 2: the greeting needs variety it does not have

Four greetings exist, all keyed on time of day, one string per slot:

| Hours | English | Spanish |
| --- | --- | --- |
| 05:00 to 08:59 | Hey, early bird. What should we look at? | Madrugaste hoy. ¿Qué miramos? |
| 09:00 to 17:59 | What should we try today? | ¿Qué probamos hoy? |
| 18:00 to 22:59 | What should we look into tonight? | ¿Qué exploramos esta noche? |
| 23:00 to 04:59 | Hello, night owl. What are you curious about? | Hola, noctámbulo. ¿Qué te da curiosidad? |

Rail spec section 10 asked for time of day, memory, and geography. Only time of
day was built.

**The defect is repetition, not slot count.** The day window is nine hours wide,
so anyone opening Argus during a workday sees one identical sentence forever.
Adding a fifth slot does not fix that.

**Pool size.** Five or six per slot for `day`, since a weekday user lives
entirely in it and three would cycle visibly inside a week. Fewer elsewhere is
fine; nobody is in the 3am slot on a schedule.

**Rotation is day-stable, never per page load.** Refreshing into a different
greeting is exactly what makes these read as generated. Seed from the date so
one line holds all day and changes tomorrow, with no consecutive repeat.

**Market session lines are pool members, not overrides.** Time of day describes
the user, market session describes the market, and they decouple outside Eastern
time: 5am to 9am local overlaps pre-market only for an Eastern user. So when a
session is active its lines become eligible candidates inside the current slot's
pool, and the same day-stable seed picks from the widened set. Nothing overrides
anything, a session line cannot appear outside its session, and the generic lines
stay in play.

Weight them unevenly. Weekend and holiday closure is a two-day state where the
market fact is the most useful thing Argus can say, so it should speak often.
Pre-market and after-hours are transient and mostly irrelevant to backtesting, so
they surface occasionally rather than as a headline. The one place they genuinely
matter is the fast quote shape, which already returns pre and after-hours
figures.

**Closed markets must stay true for every asset class.** A bare "markets are
closed" is wrong for a crypto user, so say both: stocks are closed for the
weekend, crypto does not stop. That is true for everyone and teaches a real
difference between the asset classes Argus supports.

**Correction 2026-08-10: currency pairs are not in that sentence, and an
earlier draft of this line put them there.** Crypto trades continuously; forex
does not. It closes Friday evening and reopens Sunday evening, so a claim that
currency pairs never stop is false, and it shipped as user-facing copy before a
reviewer caught it. Name crypto only. Where a line covers a session boundary,
check the asset class actually has the property being claimed rather than
grouping it with a neighbour.

**The data already exists, including the part most likely to be faked.**
`src/argus/domain/market_data/capabilities.py` already carries
`fetch_alpaca_market_clock()`, returning `is_open`, `next_open`, `next_close`,
`is_market_day`, and `phase`, and `fetch_alpaca_market_calendar()`, which hits
the real trading calendar. No new integration, credential, or provider.

Two traps: session is computed in Eastern time, never the user's clock, because
someone in London at 2pm is in US pre-market and a local-time calculation gets
that backwards. And holidays come from the calendar endpoint, never a weekday
check. That assumption has already bitten this repo once, where synthetic
fixtures placed bars on weekends and holidays so date logic passed every test and
broke against a real calendar.

**Geography, as named in rail spec section 10, means market session here.**
Location data is a real privacy cost for a cosmetic gain, and knowing someone's
city says nothing about what they should ask. Knowing whether the market is open
does.

**Memory-driven greetings are the highest-value addition and are already half
built.** The rail emits research subjects, open threads, and comparison sets, and
nothing reads them. "You looked at Netflix last week and never tested it" is both
a greeting and the return hook, and it is the same seam the follow-up pillar
needs. A greeting is voicing, so this stays inside the S10 lock. Same rule as the
chips governs: memory-driven when memory has something, the rotating static pool
otherwise, guests always static.

**Correction, 2026-08-09: this is not half built, and it is not memory.**
`research_memory_block()` in `src/argus/agent_runtime/research_grounded.py`
writes a field named `memory` into the research sidecar at
`messages.metadata["research"]`. That is a sidecar field, not a memory record:
the memory system's four categories are in `src/argus/memory/contracts.py`
(`personalization_preference`, `workflow_preference`, `explicit_decision_note`,
`past_session_anchor`) and none of them is a research subject, an open thread,
or a comparison set.

The corpus is also empty. That block is emitted only on a research turn,
research is gated by `research_rail_enabled()`, and `ARGUS_RESEARCH_RAIL_ENABLED`
is `false` in `render.yaml`, so zero open threads exist today and none will until
the flag flips, which is itself gated on #411 and #412. The lane therefore built
the rotating static pool and the market-session lines only, and left the seam
marked in `web/components/chat/greetingPool.ts` for a reader that has something
to read.

**Keep it warm, not clever.** "Hola, noctámbulo" works because it is warm without
performing. A greeting that tries harder becomes a mascot, and the product
posture is the opposite of a mascot.

#### Piece 3: ask what to call the user, in its own field

Add a profile field, "What should Argus call you?", rather than reusing
`display_name`.

`display_name` exists and is editable, so reuse is free, and it is still wrong.
It is an identity field. People fill it with a legal name or whatever their email
gave them, because it is for the account rather than for being spoken to. "What
is next, Luis Garces?" reads like a form letter.

Being addressed by name is also not universally welcome, and some people find it
presumptuous from software. A dedicated optional field makes it a choice the user
made rather than a side effect of having an account. Blank means the greeting
uses no name, which needs no special handling because most of the pool will not
use one.

**The name appears in some pool members, not all.** Every greeting using someone's
name gets grating in about three days.

**This is a setting, never a memory.** Argus does not infer what to call you from
conversation. Memory infers, settings are stated, and guessing a nickname from
how someone types would be the creepiest thing in the product. Guests have no
profile and fall back to the nameless pool.

## Landed this cycle

- **The 2026-09-01 production promotion** (PR #534, `c7802b37`). Thirty-three
  commits, four merges, all three Render services. The additive settle
  migration was applied before the deploy per the runbook's ordering rule, and
  the readback through the real projection function showed **seven** locked
  research conversations settling, not the six recorded at draft time. The
  count grows while a defect is live; the manifest now says to re-count at
  application time rather than trust a written number.

  The candidate-only eval failure read as a rubric regression from PR #525,
  because the prose judge ships inside the tree and the two sides were graded
  v1 and v2. **A grader that ships in the tree cannot be held constant by
  re-running the suite.** Judge-only replay can: both recorded replies, judged
  by the candidate's own v2 judge with the candidate's recorded surface, passed
  13 of 13. Judge flake, not a regression, settled for about $0.02 against
  $1.33 for a suite re-run that could not have answered the question.

  Recorded because it cost a merge decision: PR #525 was merged on the
  recommendation that a test-only change needs no review. It changed the
  instrument that grades promotions, which makes it promotion-affecting.

- **Failure records are readable** (PR #536, #484). Route receipts were bound
  into Loguru extras, which Render does not display, so the log showed that a
  receipt happened and nothing it said. The fields now render in the message
  body, derived from the receipt rather than the logger's context so nothing
  sensitive leaks. Approved-window rejections print both compared ranges even
  when they match, which is what lets a hash-only failure prove the windows
  were identical. The `argus-backtests` task-log query was wrong, not the logs
  unreachable; the corrected query is in the runbook.

- **Research funnel dimensions are natively filterable** (PR #537, #408).
  `capability_class` was never on the PostHog top-level allowlist, so research
  work kind stayed nested and unfilterable. The real defect was the naming
  collision: `capability_category` is renamed to `product_capability` for the
  product activity, and `capability_class` keeps its meaning as the research
  work kind. New captures emit only the new name with no alias, and
  `API_CONTRACT.md` records that historical queries spanning the change must OR
  the two properties. Research settlement now emits a typed event, so a
  degraded research turn is a filterable fact rather than a log line.

  **Anything built on `capability_category` goes blank for new data.** The doc
  says so; nothing enforces it.

- **A finished research answer appears, and its conversation is usable again**
  (PR #532). The reported symptom was that the answer never painted until a
  reload. The real defect was worse: **every conversation that finished a
  research question was permanently locked**, composer disabled before and
  after reload. Six production conversations were in that state, found by the
  founder hitting one.

  The database decided "is this job settled" by looking for a completed
  backtest run with an evidence artifact. A research job has no run, so the
  answer was always "still working", forever.

  **Why the first attempt failed the split-brain rule.** The fix put one
  predicate in SQL and a twin in the memory store, held together by a shared
  scenario table. The review cited AGENTS.md back at it correctly: *a
  duplicated fact that is tested is still duplicated*. And the twins had
  already drifted, the memory side returning early on research scope where the
  SQL branched, invisible to a table that pinned a null run id in every row.

  The landed shape is one owner, `argus.domain.job_settlement`: the rule is
  stated once as an expression, the SQL function is rendered from it and pinned
  byte-for-byte, and the memory path evaluates it. Verified by tampering with
  one leaf of the rule and watching both sides fail.

  The doc sentence at `DATA_MODEL.md:1493` that encoded the old run-only belief
  is rewritten. That sentence is where the bug came from.

  **The SQL half heals the existing stuck conversations**, so this promotion
  fixes the six rather than only preventing new ones.

- **Every number Argus reports, audited** (PR #526, closes #468 and #469,
  closes the named scope of #456). Benchmark alignment now requires a real
  observation at the first and last bar for **every** strategy, not just DCA.
  Before this, `buy_and_hold` on the same data reported a benchmark return of
  **99.7%** where DCA honestly reported **-0.15%**, and the fix that was
  supposed to prevent it covered one of two consumers.

  Two lessons, both about the audit rather than the arithmetic:

  - **A documented behaviour that does not happen is worse than an
    undocumented one.** The first attempt added a contract sentence saying
    out-of-window bars were rejected. They were not, and the sentence made the
    fabricated number harder to find.
  - **An optional correction is not a correction.** The forward-fill mask was
    permissive when absent and unrecorded when it fired, so the fix was guarded
    by a suite that mostly skipped it. Requiring the mask immediately exposed a
    fixture that had never carried a valid `benchmark_symbol`.

  `performance.benchmark_coverage` now records observed and target points per
  symbol, so a silent revert shows up in the payload rather than in a user's
  numbers.

- **The prose judge can see what the reader saw** (PR #525, closes #516). It
  was failing honest answers on `honesty` because it received the voiced
  sentence without the discovery rows and sources rendered beside it. Verified
  by replaying recorded verdicts on the exact prose, three attempts per row:
  honest cases 4/4 matched at 3/3 passes, fabricated cases 3/3 matched at 0/3.
  It had been costing a false red on nearly every live eval run, including the
  2026-08-21 promotion gate.

- **Never dead-end, never invent** (PR #522, closes the discovery half of #499).
  A search that finds assets it cannot price now names them and says why,
  instead of answering "I could not confirm any of the names I found" and
  stopping. Provider outages no longer read as facts about the asset: the
  tradability probe returns three values, so `market_data_empty` is about the
  symbol, `market_data_unavailable` is about us, and an unknown takes the
  retryable route rather than telling a user Bitcoin is unconfirmable.

  The xhigh review found ten defects and every one reproduced. Its thesis is
  worth keeping: **each fix had been placed where the symptom was seen rather
  than where the fact is owned**, so the guard covered the path driven in a
  browser and missed the paths production uses. Three findings showed the very
  dead end this PR fixes still reachable through an unguarded route. The round
  closed by moving four facts to four owners instead of patching ten sites.

  Two measurement lessons came out of it:

  - **A dead assertion is worse than no assertion.** `named_unavailable` read
    the sidecar's ungated list while the prose named only what survived a
    different gate, so the case shipped green on the exact reply it was written
    to catch. The "draw dependence" explanation given for it was wrong, and was
    retracted on the evidence.
  - **Founder decision 2026-08-19:** naming discards is owed only when the turn
    offered nothing. Beside runnable rows it is noise, and the pipeline's
    deliberate silent-filtering contract stands.

- **Front-page chips now complete** (PR #524, merged `713b79d4`). Production data for
  2026-08-11 to 08-13 (37 real users, 42 sessions, **2 returning**) showed all
  three seeded chips failing: Netflix 0/3 in English, the Costco comparison
  complete server-side but invisible until reload, and Coca-Cola dying on
  "200$", "13,000 pesos", and "un millón de pesos". Root causes were a stale
  Perplexity `fetch_url` rate rejecting every URL-fetching grounded read, a
  three-seam stack under bare money answers, a research answer that never
  rendered in the open view, and a silent empty final frame.

  The lesson is where the constraint actually sits: **every lane run that week
  was invisible to those 37 people.** The product's front door was broken and
  the queue was full of work behind it.

  Verified by the captain in a browser on the merged tree **before** merging,
  after the lane's own report proved insufficient twice: Netflix returns a
  grounded answer with sources and a backtest bridge, the Costco comparison
  renders in the open view with no reload, and the chip plus "200$" reaches a
  KO recurring-buys card. The live DOM was grepped for the exact production
  death strings; zero hits.

  One review finding was called critical and could not be reproduced on either
  tree. The fix is harmless and stayed in, but the severity was repeated from a
  code trace rather than tested, which is the same error as calling a feature
  working because its eval case is green.

- **Production promotion** (PR #518, merged 2026-08-16 at `31343882`) — 100
  commits, one theme: **Argus stops discarding what the user said**. Editing a
  confirmation card applies every operation in all three shapes, category
  discovery routes on its typed payload and reaches the search path that was
  already built, DCA metrics measure performance instead of counting deposits,
  and confirmation prose renders in the workspace language. Recorded in
  [`2026-08-16-main-production-promotion.md`](../release-manifests/2026-08-16-main-production-promotion.md).

  Measured against the deployed build rather than asserted: production failed
  14 of 46 cases, the candidate failed 2 of 60, **zero candidate-only
  failures**, and the compound-edit tier moved from 1 of 9 to 7 of 9.

  Three lessons, each of which changed an outcome:

  - **Lane reports did not survive independent re-measurement.** #514 claimed
    ten fixes and two held after merge. #510 claimed an edit fix that a later
    interleaved A/B measured at 2 of 10 on the very baseline containing it. The
    working method is: re-derive every number from committed scorecards against
    a baseline you ran yourself, and settle any changed case with an
    interleaved A/B at frozen commits in one session.
  - **The model was right and the code threw it away.** On "remove AAPL" three
    independent model reads were correct and five deterministic layers
    destroyed them. The case only ever passed when the model *disobeyed* the
    schema. Two days were spent blaming the LLM for a defect that was never
    there.
  - **A green eval is necessary and never sufficient.** Discovery shipped with
    its case passing, and a user typing "find me trending cryptos" got a dead
    end, because the case asserted a routing tag and nothing the user receives.
    Nothing is called working until it has been used as a user, in the app, in
    both languages.

- **Model-facing text is a measured surface** (PR #513). The interpreter's
  system prompt and the response schema's field descriptions are fingerprinted
  against a committed scorecard; changing either requires evidence and one lane
  holds the surface at a time. This exists because #491 rewrote the shared
  prompt for a DCA change, passed its own tests and CI, and silently regressed
  asset extraction, date preservation, and discovery routing.

- **Copy matches the card** (PR #521, closes #509). Clipboard text derives from
  the same view model both card kinds render, so a Spanish user copying a
  Spanish card no longer gets English. The English clipboard was broken too,
  hiding behind a Spanish bug report. `confirmation.summary` is deliberately
  dropped from copy, founder-approved 2026-08-16: the card never paints it and
  it was unconditional backend English. The remaining backend half is #523.

- **Production promotion** (PR #441, merged 2026-08-11 at `d67cef92`) — 451
  commits, the first promotion in a month, recorded in
  [`2026-08-11-main-production-promotion.md`](../release-manifests/2026-08-11-main-production-promotion.md).
  Three findings came out of it and none blocked it: the database was nine
  migrations behind because nothing applies them and no gate checked (**#449**),
  the canary is red at a browser test that asserts Turnstile fails (**#452**),
  and fast-classified research answers carry no citations (**#451**).

  The lesson is about where verification lives. Every gate we had passed while
  the flagship feature sat inert for two hours, because production's constraint
  rejected `chat.research` and the rail failed closed exactly as designed. A
  green deploy, coherent SHAs across three services, and a clean config audit
  proved nothing about whether the product worked. The check that found it was
  asking Argus a question.

- **Run-consumption guard** (PR #443, merged 2026-08-11 at `512a52b7`) — pillar
  2's second half. Recorded above.

- **Breakpoint findings 2 through 8** (PR #447, merged 2026-08-11) — closes
  #422. Seven defects the audit lane found, repaired at an unchanged
  `maxDiffPixels: 100`. Finding 4 was never a breakpoint bug: the confirmation
  card printed its symbol twice at every width, in both languages, in 60 of 176
  captures, and survived #406 restyling that exact component. A visual audit
  found a defect that reading the code had missed twice.

- **Benchmark comparison localized** (PR #446, merged 2026-08-11) — closes
  #435. `user_phrase` was removed from `BenchmarkComparison` rather than given a
  language parameter, so the domain layer can no longer format prose in any
  language, and a structural test pins the dataclass to exactly three typed
  fields. The lane's own audit found seven consumers where the issue named five.

- **Master editing** (PR #431, merged 2026-08-11 at `522c6d9c`) — pillar 2.
  Recorded above. The transferable lesson is about where a guard belongs.
  Round 1 guarded the message row, round 2 moved to the conversation, round 4
  moved liveness into the card itself as one oracle every reader derives from,
  and rounds 5 through 7 kept finding holes not in the guard but in the run
  lifecycle underneath it. A guard cannot be finished while the truth it
  checks is split across three stores. When the same leg produces a third
  round, the answer is not a fourth patch, and the pre-stated exit is what
  made stopping cheap rather than a defeat.

- **Receipt payload freezes facts, not prose** (PR #436, merged 2026-08-11)
  — closes #417. A receipt froze the author's language, and a public link is
  opened by strangers, so no generator fix could reach it. Assumptions, the
  tested window, and metric labels became typed keys rendered at view time,
  the pattern `strategy_facts` already proved on the same payload.

  Three lessons worth more than the fix. **Translation-invariance is a blind
  guard on its own**: zero metrics is byte-identical to zero metrics, so an
  equality test watched a closed enum silently drop the only benchmark number
  a real card carries. It needs a content-preservation test beside it.
  **Typed facts do not license new copy**: the first attempt wrote seven
  past-tense sentences where the card had terse fragments, which rebuilt the
  receipt look #397 was redesigned to kill. And **frames are proof only if
  someone reads them**: two defects on this route, a white body showing under
  the dark shell and unreadable dark-on-dark tombstone text, were both visible
  in #397's own committed evidence frame and nobody had looked. A full-page
  capture is the wrong instrument for anything about viewport height.

- **Breakpoint audit and visual baselines** (PR #420, merged 2026-08-10 at
  `7989e62e`) — 74 committed Playwright baselines across legal, auth, and
  settings at 390, 720, and 1024, plus `docs/BREAKPOINTS.md` as the intent
  page pointing at the baselines as truth. Zero component edits. Its first
  output was a bug list rather than a document: #421 (account security
  unreachable below 1024, shipped dead in the mobile lane) and #422 (seven
  lower-severity defects). Two harness defects fell out of the same pass, and
  the second matters beyond this lane: `maxDiffPixelRatio: 0.01` allowed
  roughly 3,300 pixels of drift, so a 40 by 40 element was removed from every
  capture without the suite going red. The measured floor is zero and the
  budget is now `maxDiffPixels: 100`.

- **Ticker mention entity tags** (PR #406, merged 2026-08-09 at `d9e8a3c5`) —
  exact mention entity tags rendered through a shared `EntityToken` across chat
  messages, confirmation cards, and result cards. Held until the rail landed
  because it overlapped nine files, then reconciled once against a finished
  lane rather than a moving one.

- **Operator-run maintenance** (PR #414, merged 2026-08-09 at `70635831`,
  revised by #448) retains the existing retention and reconciliation jobs plus
  their shared entry point. The `argus-maintenance` Render service was never
  created, and #448 removed that phantom fourth surface from `render.yaml` and
  the release gates. At current scale there is no guest data to delete and no
  stranded job to rescue, so an operator runs the jobs from a laptop against
  an explicit target when needed. A future scheduler requires a new decision
  and must be added to the deployment contract intentionally.

- **Research sidecar rename** (PR #418, merged 2026-08-09 at `c69e7489`) —
  the sidecar's `memory` block became `follow_up`, because it never was a
  memory record and the name had already misled two readers. Done before the
  rail flag flips, since production writing the old key would have turned a
  rename into a data migration. Spun out #419: the key guard covers one of
  three producers.

- **Follow up on unfinished work, spec only** (PR #416, merged 2026-08-10 at
  `1ccdf825`) — the pillar is specced and parked behind four preconditions.
  Carries two named amendments to the rail spec, §11c and §12b, each with a
  pointer from the paragraph it supersedes.

- **Sidebar affordances answer pointer capability, not width** (#398, PR #428,
  merged 2026-08-10 at `f14f5406`) — Recents row actions were hover-only, so a
  touch device at 1024 and wider got a row whose controls could not be revealed
  at all. Width was the wrong signal: a 1280px touchscreen is still a
  touchscreen. Width now selects layout geometry while
  `(hover: hover) and (pointer: fine)` versus `(any-pointer: coarse)` selects
  the reachable affordance, centralized in `pointerAffordances.module.css`
  rather than scattered.

  Four hover-only controls got four decisions rather than one blanket rule,
  because their roles differ: sole action, full-row edit, decorative hint,
  dense cluster. The review round caught the first pass fixing touch by
  removing hover on fine pointers, which would have traded one broken surface
  for another.

- **Destructive ops jobs refuse to guess their target** (#413, PR #427, merged
  2026-08-10 at `7ac899cd`) — `stale_backtest_jobs.py` called a bare
  `load_dotenv()`, which resolves upward from the module's own directory to the
  repository root `.env`, a symlink into the integration worktree on a developer
  machine. A script whose job is deleting rows silently acquired real
  credentials and proceeded, with no flag, no prompt, and no line saying which
  database it had chosen.

  Both destructive jobs now require `DATABASE_URL`, `SUPABASE_URL`, and
  `SUPABASE_SERVICE_ROLE_KEY` explicitly and exit 2 without them, and each
  prints its resolved hosts before any destructive work. Discovering a
  connection string is never right for a destructive job; being handed one is.

  The review round caught the guard being bypassable through
  `.github/stale-backtest-jobs.sh`, the wrapper the runbook itself tells
  operators to run, and a second finding where the safety print corrupted JSON
  stdout. Both are fixed; the print moved to stderr rather than being dropped.

- **Rail follow-ups, three lanes in parallel** (merged 2026-08-10) — all three
  filed during the rail's own verification and closed after the flag went on,
  because enabling turned each from latent into live.

  **#419 / PR #424 at `42dac840`** — the sidecar key guard covered one of three
  producers, so a partial key change would have failed loudly on one path and
  diverged silently on two. One shared builder is now the only way to write a
  sidecar, so a producer added later cannot bypass the invariant by omission.

  **#409 / PR #425 at `171f97d6`** — recorded research cost counted the
  `finance_search` tool fee and nothing else, understating a thorough turn by
  roughly 40x. Cost is now derived from actual usage against a rate table.
  Its own review round caught the fix pricing cached, cache-creation, and
  cache-read tokens at one rate when they bill at three, so the correction was
  itself about to be wrong.

  **#421 / PR #426 at `04e6601b`** — account security was clickable at every
  width and navigated nowhere below 1024, with password change and session
  sign-out behind it, and it shipped that way in the mobile lane. The
  breakpoint audit's navigation test asserted the defect in both directions;
  it now asserts correct behaviour, and the surface has baselines at all three
  widths for the first time.

- **Answer the first question** (PR #396, merged 2026-08-09 at `ef08b25d`) —
  350 files behind a default-off flag. Grounded discovery absorbed into one
  rail: one provider layer, one classifier, one cache, one meter. All five
  question shapes proven from organic typed questions in both languages, each
  ending on a runnable next step. Guests carry their own research allowance.
  Two conditions on enabling are open as #411 and #412; see pillar 1 above.


- **PostHog native funnel repair** (PR #405, merged 2026-08-09 at `1b4555e2`) —
  product events were captured server side with the business label at
  `attributes.product_event`, which PostHog SQL can read and its native funnel
  builder cannot filter on, so the activation funnel returned no data while the
  events were present. A closed allowlist of categorical dimensions is now
  projected to top level inside `_posthog_event_properties()`, derived from the
  sanitized attributes in one place rather than written twice, so the copies
  cannot drift. Existing top-level properties win on collision and only scalars
  promote.

  **Two acceptance criteria remain open and are not the lane's to close.** A
  live PostHog event and a real native funnel both need a production promotion.
  Until then the projection is proven by tests only. The urgency was never the
  dashboard: events already sent cannot be backfilled, so every day without it
  was history that will never appear in a native funnel.

- **Memory** (PR #386) — complete loop behind a default-off flag
  scoped to `admin` and `developer` allowlist roles. Propose, confirm, inspect,
  explain, edit, delete, disable, reset, export, and temporary chat. Guests
  denied before any side effect.

  Correction 2026-09-25: current production memory availability is owned by
  [PRODUCT.md](../PRODUCT.md#current-production-availability-and-planned-changes).

  **Follow-up is specced and ready to dispatch, not pending decisions.** The
  recall loop is locked in
  [`2026-08-06-personalization-memory-recall-loop.md`](https://github.com/lagarcess/argus/blob/651870a54be4e5506dbb38f3902fef1a97eef8df/docs/superpowers/specs/2026-08-06-personalization-memory-recall-loop.md).
  Four Mem0 parameters
  are ratified: index-only over confirmed content, so Mem0 never sees
  unconfirmed material; storage on the existing Supabase database with no new
  datastore service; Mem0 as the OSS library running in-process inside the API
  service rather than the hosted platform; and its extraction, dedup, and
  conflict-resolution pipeline explicitly unused, because Argus owns extraction
  and the assisted-not-automatic rule forbids it.
- **Canary automation** (PR #385) — API-layer denial probe, deployed-SHA
  evidence binding, and the fix for the canary validating the wrong branch. A
  signup enumeration oracle and a false-evidence path were caught in review.
  Session injection for the browser golden path remains open on #383.
- **Retest current-data windows** (PR #363, in review) — the waste guard moved
  out of the chat turn into the dossier button, computed before any click.

## Deliberately not doing

From the competitor review: no agent marketplace, no model picker, no
multi-hundred-API integration story, no autonomous monitoring, no portfolio
system, no messaging channels, no trading workflow, and no auth-gated marketing
site standing between a visitor and their first test. Guest entry stays the
activation path, because a completed first backtest is activation, not account
creation.

## Secondary tracker state

Open issues serve the board or wait. Currently aligned: #377 (item 1), #335 /
#237 (item 2), #332, #367, #369, #365, #364 (robustness). Currently waiting:
#294, #244, #350, #236, #314, #376, #378, #383.
