# Argus Roadmap: Answers That Stay True

**Archived September 26, 2026.** This is a dated record, not standing product
or execution guidance. Its original present-tense claims and open questions
belong to the recorded period. Use the [MVEE](../specs/argus-minimum-viable-ecosystem-experience.md)
and [documentation authority](../DOCUMENTATION_AUTHORITY.md) for current work.

---

Status: **HISTORICAL PRODUCT BOARD / CARRIED-WORK REFERENCE**, updated
September 26, 2026. The [MVEE](../specs/argus-minimum-viable-ecosystem-experience.md)
supersedes conflicting product direction. The original September 18 board,
open questions, issue references, and operating rules below are preserved as
history; check the [decision log](../specs/argus-decision-log.md) before treating an
old question as unresolved. No new work is assigned by this board.

Use [documentation authority](../DOCUMENTATION_AUTHORITY.md) for current
ownership and [Wave 1](../specs/wave-1/README.md) for explicitly assigned packages.
This status change does not close carried issues or cancel authorized work.

Read [`docs/PRODUCT.md`](../PRODUCT.md) first. The previous board, which shipped
in full to production `a9286b21` on 2026-09-17, is archived at
[`2026-09-17-argus-grounded-finance-roadmap.md`](2026-09-17-argus-grounded-finance-roadmap.md).
Everything it left open is carried into this board, in "Carried over" below.

---

## Where we start

Production is `a9286b21`: every grounded-finance item, the seven regression
repairs found by measuring integration against production, the recovery and
year fixes, and sharing switched on with a follow-up box that forks into the
receiver's own chat.

The number that matters has not moved. Thirty days before that promotion saw
**one message from one person outside the team.** People ask, get an answer,
and leave. This board exists to give them a reason to come back.

## The idea

Chat stays the core. On top of it, **any answer can be saved, and Argus keeps it
true**: it records what the answer depends on, re-checks those inputs, and tells
the person only when *their* answer changes.

The loop: ask, save, record a baseline (inputs, result, date), track, notify,
return into the saved answer, weekly recap, share the updated answer.

## The pillars

1. **Living saved answers.** Save any answer with its baseline: the inputs, the
   result and the date. The saved item is what later checks compare against.
2. **Tracking.** Re-check what a saved answer depends on (rates, fees, prices,
   exchange rates, inflation) for the person's country, plans and products,
   built on the grounded math and home country that already shipped. Checks run
   on data and code; the model is called only when an answer actually changed,
   to explain the change.
3. **Telling people when their answer changes.** The channel is undecided.
   Argus has no iOS or Android app, only an installable web app, and no push
   code exists. Web push reaches Android broadly but iOS only when the person
   adds Argus to the home screen. Email, WhatsApp (dominant in the Dominican
   Republic) and an in-app note on the next visit are the alternatives. Decide
   the channel before building tracking, because it is what makes a living
   answer worth saving.
4. **Memory, personalization and private chats for every registered user.**
   Today they reach admin and developer accounts only
   (`MEMORY_EXPOSURE_ROLES` in `src/argus/api/personalization_memory.py`).
   Widening is a code change with tests and a walk of the memory screens, not a
   flag flip. Move the private-chat setting from the browser to the account so
   it follows the person across devices. Memory never shapes how a question is
   read. Guests stay out.
5. **Dominican data.** Two official sources, both assessed:
   - **Banco Central (BCRD):** the official peso rate, current and historical,
     and consumer price inflation. Six endpoints, a 500-call daily quota, and an
     IPv4 allowlist, so calls go through a fixed-IP proxy from one daily job.
   - **Superintendencia de Bancos:** per-bank average rates for savings,
     certificates and loans, and credit card rates and fees by product.
     Self-service access; wording must say "average rate paid on balances",
     never "the rate this bank offers".

   Both need **written permission to reuse the data** before anything is shown
   to users. Load once a day into the database; never call either source while a
   person waits.
6. **Answers that cite their evidence.** A question that needs a claim about
   the world (how something behaves, what it costs, what it pays, whether it
   suits a purpose) must reach research and publish with dated sources, plus an
   honest note when Argus cannot backtest what it named. The approved design is
   one required field on the primary interpretation,
   `requires_external_evidence`, filled by the same interpreter from meaning.
   **No phrase matching, language rules, ticker or category lists, or regex over
   the prompt.** This fixes both the uncited statistics in answers like "should
   I put my emergency fund in crypto?" and the dead end on "list the AFIs in the
   Dominican Republic and which pays best".
7. **Sharing as the growth loop.** Shipped and on. Measure it: how many links
   are created, opened signed out, and turned into a follow-up.

## Open founder decisions

| Decision | Why it blocks |
| --- | --- |
| Consumer, or embedded in Dominican institutions | Decides who the living answers are for and which data matters first |
| The advice line: may Argus give sourced recommendations? | "Education, not advice" is why answers read weaker than competitors on should-I questions |
| Notification channel | Pillar 3; nothing in pillar 2 is useful without it |
| Which kind of saved answer comes first | Decides the first tracking lane |
| Decision 8: may saved plans hold salary or debt? | Memory and saved answers must agree on personal figures |

## Carried over from the grounded-finance board

These stay open and on this board until they close.

### Open issues

| Issue | What it is | Size |
| --- | --- | --- |
| #656 | A calculation answer can print a raw name such as `months_to_goal` | Small, code only, hotfix |
| #653 | A private-replay refusal named a capability the user did not ask about (cases 07/01 and 10/02) | Recheck in the next acceptance run first |
| #644 | Em dashes in model-generated discovery replies | Model-facing |
| #640 | A second tab misses a reply when focused before the turn is accepted | Small, deferred |
| #623 | Starting capital stated in pesos, converted at the official rate | Waits on the BCRD peso rate |
| #620 | Cited calculation inputs must match their rows; start-plus-deposit plans get their test row | Model-facing |
| #606 | A result follow-up prints the same next steps twice (PR #646) | Model-facing, cosmetic |

### Parked pull requests

- **#634, calculation follow-ups.** Its code-only fixes shipped as #649; the
  model-facing parts stay parked. It also holds the historical-drawdown
  calculator, no longer required by any acceptance bar.
- **#646, one next-step list.** Built; needs its measurement.

### Accepted at ship, watch in production

- A two-part edit can intermittently drop its start date (the case #648
  repaired passed three repeats and then failed paired).
- A stated budget can be recorded as supplied capital; it stops for
  clarification, so it is visible.
- A follow-up from a shared link does not continue a calculation. Founder: an
  acceptable limit, not a defect to chase.

### Reliability and tooling

- **No automated production check.** The canary was retired and #614 closed
  not fixed; nothing now tells us production broke.
- **Two CI flakes that cost several false alarms:** `bun install` failing with
  "Fail extracting tarball for next", and the canary session-tool test racing
  its stub server. Rerunning clears both.
- **A measurement case that depends on the day:** trending-crypto discovery
  fails whenever the day's trending coins are not in the catalog. It should
  assert an honest answer, not at least one row.
- **Spend caps count reserved amounts,** roughly three times what is billed.
  Size caps in billed terms or expect early stops.

## Operating rules carried forward

Learned on the last board, and they apply here:

1. **Measure integration against production before promoting,** not only
   branches. Seven regressions sat in integration until this was done.
2. **Repeat a failing case twice before assigning a fix.** Three "regressions"
   were run-to-run variance and cost four cents each to rule out.
3. **One change to model-facing text per release.** Free work lands first; the
   one measurement runs last, at the top of the stack.
4. **A browser check answers "does this work for a person" faster than any
   suite.** Suites answer "did this break something else".
5. **Acceptance bars are product decisions.** Question 10's drawdown clause
   failed the release against our own test, not the product. Write bars from
   what a good answer looks like.
6. **A lane flags a conflict between an instruction and a real defect** instead
   of applying the instruction literally.
7. **Stop a review loop** at the second finding on the same mechanism, and
   report.

---

## Brainstorm: finding Argus's angle (2026-09-18 to 2026-09-19)

Status: **brainstorm, not decisions.** Nothing here is committed scope. It
records a founder and captain session, informed by read-only research, so later
lanes start from it instead of from scratch. The founder may revise any line.

### The problem

A chat that answers money questions becomes redundant as AI improves. Personal
data, memory, connectors, users and network effects do not protect Argus: the
large AI labs have them or will. They are the baseline Argus must meet, not a
moat. The goal is an angle where **AI getting better makes Argus better**, with
the moat built piece by piece inside a finance app ecosystem, and with a real
retention mechanism first.

The current principles (`docs/PRODUCT.md`: social features out of scope, never
prescribe) were written for the chat. The founder intends to revisit them if
the angle below holds.

### The ecosystem, as pieces that feed each other

- **Paper trading strategy arena.** People learn and build confidence before
  risking real money. Strategies come from plain words, as expressive as
  Composer's (not a fixed menu of templates). Humans and AI models take part.
  A social feed lives in this category, not only a leaderboard. Paper trading
  runs on Argus's own ledger priced with Alpaca data, so nobody has to open a
  broker account first. "Retest with current data" in omnisearch is the seed.
- **Discover feed.** A Perplexity and Robinhood hybrid: news mixed with movers,
  crypto, earnings, market, macro and upcoming events. The layout is a starting
  point, not fixed. The arena, Discover and paper activity can all feed one
  ranking, borrowing ideas from X's open-sourced feed algorithm
  (`xai-org/x-algorithm`).
- **A daily brief on a schedule,** the return feature.
- **Memory and personalization for every registered user.** Three chat modes:
  - regular (the default): memory and personalization on, under the user's
    control;
  - private: uses everything Argus knows about the user for that session,
    learns nothing, and is gone when the chat is thrown away;
  - incognito: no memory, gone when the user leaves or closes it.

  A fuller profile is built through chat or in settings at any time, not a
  wizard. Starting points: the removed onboarding goals (learn investing
  basics, build a passive strategy, test a stock idea, explore crypto) and the
  fields Robinhood's investor profile weighs most (time horizon, risk
  tolerance, objective).
- **Dominican banking.** Banco Popular's API (exchange rates, product rates,
  account verification, ATM locations), the Superintendencia de Bancos and the
  Banco Central feed product shopping, the grounded calculators and saved
  answers. Questions like the AFI one go to agentic research through
  Perplexity. The founder owns Dominican data access and outlet deals.
- **Options.** Alpaca's chain, Greeks, implied volatility and open interest
  support calculators, education and paper options.
- **Read-only connections.** No company is needed for crypto exchange keys,
  IBKR Flex or Alpaca OAuth. Bridge covers Dominican bank accounts. Argus does
  not build its own bank-login scraper.
- **Distribution.** Argus's data and calculators as a connector inside ChatGPT
  and Claude; share links; marketing content (Higgsfield's MIT skills repo).
- **Payments, later.** Lemon Squeezy for web and RevenueCat for a future iOS
  app, reconciled in one Argus-owned table of who pays for what, switched off
  until there is something to charge for.

### Distribution

- **Social posts, not ads, first.** An Instagram account is reserved. Posting
  can run through the X API (pay per use; a post with a link costs about 13
  times one without) and the Threads API (free, gated by Meta app review),
  using Threads and Instagram's cross-platform sharing.
- **The product writes the posts.** Arena standings, AI-versus-human results,
  movers explained and Dominican rate changes are generated from Argus's own
  data, and each post links back to a share page. Higgsfield can make the
  visuals once the marketing approach is chosen.
- **Measure by channel.** Tag every posted link, and count share opens,
  signups and follow-ups per channel.
- **Ads only after a return loop exists,** as a small, capped test against
  that baseline.
- Automated posts follow each platform's automation rules and never read as
  stock tips.
- OpenExecutive (SenteLabsAI) is the founder's own decision-support tool, not
  part of the product or of distribution.

### Data sources considered

- **Alpaca:** movers, most actives, news (Benzinga, full text), corporate
  actions and their live stream, fixed income (T-bills and corporate bonds with
  yields), options. No structured earnings data.
- **Perplexity:** Search API (title, link, snippet, date; country, language and
  domain filters), agentic research, and a code sandbox (Python, JavaScript,
  SQL) inside the Agent API.
- **News APIs:** not needed to start. GNews is a cheap fallback; NewsAPI.org's
  free plan does not allow production use.
- **Articles open inside Argus.** Most large publishers block being framed
  (Reuters, Benzinga and Bloomberg Línea do), so an embedded page does not
  work in general. Show licensed text natively, show Argus's own cited story
  otherwise, and open the original in an in-app browser once there is a native
  app.

### Facts that gate building

- **Alpaca display consent.** Alpaca's terms forbid publicly displaying its
  data without written consent and define a notice-and-consent route. This
  already applies to backtest results shown today.
- **Stored secrets.** Every connection that refreshes needs a stored, revocable
  secret (a token or read-only key, never a password). Decide whether that is
  allowed, encrypted and outside logs and model context, or whether
  connections are one-time imports.
- **No company yet.** This rules out Alpaca's Broker API, IBKR's third-party
  OAuth and most broker partner programs for now.
- **Bridge.** Ask whether an individual without an RNC can register, which
  banks are live, and what the paid plan costs.
- **Contest law.** No cash prizes.

### Research notes worth keeping

- Public.com closed its social feed in 2025 because AI now writes the recaps
  users used to post. Scored records and friends playing in seasons retained
  better than commentary.
- SoFi bought Composer in 2026. Idea-to-backtest alone is not a moat.
- The @ asset picker loads the whole symbol list on a user's request. Leading
  products build a search index ahead of time and search a small list in the
  browser first.
- A research turn takes about 68 seconds and nothing streams. Speed and
  quality both remain the target.
