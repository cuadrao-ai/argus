# Argus Pivot Strategy

**Archived September 26, 2026.** This is a dated record, not standing product
or execution guidance. Its original present-tense claims and open questions
belong to the recorded period. Use the [MVEE](../specs/argus-minimum-viable-ecosystem-experience.md)
and [documentation authority](../DOCUMENTATION_AUTHORITY.md) for current work.

---

Status: **HISTORICAL STRATEGIC PROPOSAL — conflicting experience direction
superseded September 26, 2026.** Written September 23 from earlier research.
The [MVEE](../specs/argus-minimum-viable-ecosystem-experience.md) now owns approved
product experience. The body below preserves original reasoning and proposals;
it is not a list of approved features or a current capability audit.

Use [documentation authority](../DOCUMENTATION_AUTHORITY.md) for assigned-work
and technical boundaries, and the [decision log](../specs/argus-decision-log.md) for
founder decisions. Research and unresolved proposals remain useful context.

---

## 1. The problem

Argus today answers money questions with research, backtests and computed
calculators. It works. Almost nobody uses it: in the thirty days before the
2026-09-17 promotion, **one person outside the team sent one message**.

The deeper problem is not the funnel. It is that a chat that answers money
questions is the exact product the frontier labs ship for free, with users,
memory, connectors and distribution Argus cannot match. In May 2026 OpenAI
shipped consumer personal finance with bank connections through Plaid, which
covers saved plans and goals, not only conversation.

So the premise of this document: **chat cannot be the main feature.** Every
option below assumes that.

## 2. What the market already disproved

These were considered seriously this week and ruled out on evidence, not
taste. They are recorded so they are not relitigated.

| Idea | Why it is out |
| --- | --- |
| Social feed of commentary | Public.com shut its social feed in June 2025, stating that AI now writes the market recaps its users used to post. Stocktwits' own reviewers describe bots and subscription sellers. |
| Leaderboard or arena as a first move | At our scale a leaderboard is three names. Sleeper and Strava worked on density we do not have. |
| Paper trading sold as skill building | Anginer et al. (2024) linked simulator accounts to the same users' real accounts: the most active, most risk-taking simulator users were likelier to open real accounts, then traded more and underperformed. |
| Leaderboards as a confidence builder | Andraszewicz et al. (2023), 807 retail investors: seeing top performers raised risk taking and trading volume and lowered satisfaction with their own performance. |
| Ranking by returns | Bailey and Lopez de Prado's minimum track record length: an observed Sharpe of 0.5 needs about eleven years to establish it is above zero at 95% confidence. Any short leaderboard ranks luck. |
| Selling strategies to retail | QuantConnect shut Alpha Streams and published the reason: filtering for all-regime performance produced overfitting, and the surviving alphas underperformed the S&P 500. Collective2 was absorbed into a broker. Composer was bought by SoFi for about $70.1 million (SoFi 10-Q). |
| A generic daily brief chosen by the system | ChatGPT Pulse launched September 2025 and was retired in June 2026 in favour of standing queries the user chooses. |

Two findings survive from that research and shape what follows:

- **Mechanisms where the product changes while the user is away beat anything
  that relies on the user's discipline.** Contextual notifications are opened
  about 14% of the time against about 4% for generic ones.
- **Social features only survived where they were welded to brokerage
  revenue** (eToro, Darwinex, wikifolio), and the regulators still arrived.

## 3. The shift: Argus as leverage, not the attraction

Argus stops being the destination and becomes the layer that makes a decision
happen. Four jobs:

1. **Intake.** Read what the person actually has: statements, payslips, later
   accounts.
2. **Understanding.** Work out what they need, from meaning, not keywords.
3. **Routing.** Hand them to whatever resolves it: a computation, a product,
   an institution, a human.
4. **Proof.** Show the sources, the dates and the arithmetic.

Revenue never depends on the conversation itself. That is the point. Better
models make intake cheaper and routing sharper, while the money sits in the
placement. **AI improving becomes a tailwind instead of a substitution
threat.**

This is the Credit Karma and NerdWallet structure (free tool, cash-flow data,
then product revenue), with an AI intake layer instead of a form.

## 4. The user: the open decision that gates the rest

Two candidate users, and several later decisions change shape depending on
which is chosen.

**A. Dominicans at home.**
11.5 million people (the 2022 census counted 10.77 million), 91% online, 76%
of adults on smartphones, and bank account ownership up from 51.3% (2021) to
64.8% (2024). But average labour income is about RD$29,000 a month, roughly
US$470, informality is 54%, and only 10.4% of adults have saved for old age.
About 78,000 people hold investment funds and 180,000 have any securities
account, which is 0.8% of the population against 5.6% across Latin America.
Fund accounts grew 40% in a year.

**B. The Dominican diaspora in the United States.**
1.3 million Dominican-born, 2.7 million counting ancestry, 55% in greater New
York and 68% in three metros. Median household income about US$50,500. They
sent home US$11.87 billion in 2025, up 10.3%, with over 80% of Dominican
remittances coming from the US, and a new 1% US tax on cash transfers from
January 2026.

**What the choice changes:** platform priority (the DR is Android-majority,
the diaspora skews iPhone and carries the purchasing power), pricing, payment
rails, language emphasis, and which institution is worth a conversation.

**Nobody serves either group.** No regional neobroker lists the Dominican
Republic (Trii, Cocos, Flink and Webull, Balanz, tyba, Bitso all stop
elsewhere). Local brokerage apps have 14 to 48 ratings while Banco Popular's
app has 104,525. The Dominican equity market is two listed stocks.

## 5. The pillars

Each pillar: who uses it, who pays, what gates it, what it feeds.

### Tier A, nothing blocks these

| Pillar | User / payer | Gate | Feeds |
| --- | --- | --- | --- |
| **Decision engine** (where to put my money, with receipts) | Saver / nobody yet | Self-service regulator API key | Creates the decision moment every other pillar monetizes |
| **Statement and payslip intake** | Same person | None. Replaces the neobank as the data layer | Every calculator, and the employer version |
| **Cost calculators** (card interest, loans, transfer and FX cost) | Same person | None | The highest-intent handoff, because a bill is in front of them |
| **Change alerts** | Anyone who saved a decision | None | Retention. Each alert is a fresh decision |
| **Marketplace handoff** (deposits, cards, loans) | Consumer uses, institution pays | Build free, monetize after one deal | Click volume is the argument that opens institutional conversations |
| **Public brief** | Spanish-speaking savers | Bank data only until fund rights exist | The acquisition pillar |

### Tier B, one relationship away

| Pillar | User / payer | Gate | Feeds |
| --- | --- | --- | --- |
| **Employer benefit** | Employee / employer | One meeting. First one free | A hundred users at once, plus payroll data with consent |
| **White-label for an institution's clients** | Their customers / the institution | A demo and click evidence | The largest revenue line available without a licence. Their licence covers the advice problem |
| **Advisor tool** | Advisor at a brokerage or fund manager | Same relationship, smaller ask | Champions inside the institution |

### Tier C, gated

| Pillar | Gate |
| --- | --- |
| Insurance comparison | Placing insurance is licensed work. Comparison and handoff may be fine; taking money for it needs local counsel |
| Human expert network | US: the SEC marketing rule allows paid referrals with written agreements and disclosure, and needs a US entity. DR: almost no independent adviser population, so it collapses into the institutional relationship |
| Investing, adviser registration | Entity plus registration. Micro-investing alone has poor economics |
| Neobank and card | Sponsor bank, capital and a compliance hire. Interchange yields a few dollars per active user per month |

### Business models available, and what each needs

| Model | Licence | Example |
| --- | --- | --- |
| Brokerage or order flow | Yes | Robinhood, eToro |
| Run a fund off a crowd | Yes | Numerai, Darwinex |
| Paid evaluations | Yes, to fund winners | Prop firms |
| **Subscription tool** | **No** | TradingView, Sharesight, Monarch |
| **Sell to institutions** | **No, theirs** | SigFig, and Origin's employer channel |
| **Audience** | **No** | Morning Brew, Rankia |

## 6. What is actually buildable, and what blocks the rest

### Data rights, verified

| Source | Status |
| --- | --- |
| **Superintendencia de Bancos** | **Clear.** Terms are two paragraphs, informational and no-warranty, with no IP claim, no redistribution limit and no attribution requirement. Bank rates and card fees. API needs registration only |
| Banco Central (BCRD) | Site terms forbid commercial redistribution without written authorization. The same institution's datasets on datos.gob.do carry an open licence (1,028 of 1,064 portal datasets are ODbL). The conflict is unresolved and needs counsel |
| Banco Popular API | Rates and locations only, no account data. Production needs an RNC and a licence agreement, so it is gated on forming a company |
| Investment fund and AFI returns | **Not licensed.** No official source. Diario Financiero compiles 12 AFIs and 73 funds daily and forbids bots and commercial reuse |
| Alpaca | No public display without written consent, with a notice-and-consent route. This already applies to backtest results Argus shows today |

**The legal line and the data line are the same line.** Bank deposit products
are supervised by the banking regulator, not the securities regulator, so
their data is free to use and they sit outside SIMV's remit. Funds and AFIs
are the reverse on both counts. Version one stays on bank products.

### Regulatory boundaries

**Dominican Republic (Ley 249-17).** Investment advice is defined as a
**paid** activity. Article 173's paragraph expressly excludes generic
non-personalized recommendations, anything disseminated through mass media to
the general public, and general reports and analyses. The sharper exposure is
naming: holding the product out as a licensed market participant through any
publicity is criminal under article 354(3), independent of the content. Never
"asesor de inversion". Mirror the disclaimer the exchange itself uses.

**United States.** Three lines, from the SEC's Weiss Research order and the
publisher's exclusion cases:

1. General, impersonal and published to everyone: no registration. This is
   how Portfolio Visualizer, QuantConnect and Trade Ideas operate, none of
   them registered.
2. Individualized, investment-related interaction: the exclusion starts to
   fail **even without execution**, and a disclaimer does not cure it, because
   the registration violation requires no intent.
3. The signal reaching the account automatically: adviser or broker status,
   even if nothing is charged for it.

**Contests.** A free-to-enter, merit-judged contest needs only Pro Consumidor
registration (RD$1,500, filed 21 days ahead); the regulator SIMV registers its
own contest that way. Paid entry or any element of chance moves it to the
gambling regime. Prizes carry 25% withholding as a final payment.

## 7. The order of attack

1. **Prove the decision engine on real regulator data**, not fixtures.
2. **Hand recruit twenty people** and watch them use it. This is the step that
   has never happened.
3. **One employer pilot**, free, with a payroll file and consent. A hundred
   users from one meeting.
4. **Publish the brief** from data we are allowed to use, and let it be
   forwarded.
5. **Count outbound clicks**, then open the referral and white-label
   conversations with evidence rather than an idea.
6. **Everything else** only after one of those produces revenue or retention.

**Traffic, ranked by speed:** hand recruiting, one employer, answering real
questions where they are already asked (Dominican Facebook groups, Reddit,
creator comments), lending numbers to creators who already have audiences,
letting WhatsApp carry public content people forward themselves, and being the
sourced, machine-readable page AI assistants cite when someone asks what
Dominican banks pay. That last one turns better AI into a distribution
channel.

**Notifications.** A notification is a trigger, not content: no figures in the
message, the click opens the app. Push where available, in-app inbox always,
email as fallback. Personal data never travels through WhatsApp.

**Apps.** One shared shell across web, iOS and Android for push and camera
capture, with small native extensions where they earn their place (widgets,
on-device statement scanning that keeps the document on the phone). A full
native rewrite waits until the product stops changing weekly. Apple is $99 a
year, Google $25 once, and both stores have financial services policies, so
the listing uses the same careful wording as the product.

## 8. Settled and open

**Settled, by founder decision or by evidence**

- Chat stops being the product and becomes intake, routing and proof.
- The decision engine with receipts is the prototype, piloted in the Dominican
  Republic, without stripping US functionality.
- Arena, social feed and leaderboard are out as a first move.
- Bank deposit products only in version one. No funds, AFIs, securities or
  trading.
- Statement and payslip intake stands in for the neobank as the data layer.
- Legal copy guardrails: never "asesor de inversion", never framed as advice,
  "average rate paid" and never "offers", always the note that a branch may
  quote differently, no em dashes in user copy.
- Notifications carry no figures.
- Shared shell across three targets, native extensions where they earn it.

**Open**

- **Who the user is: Dominicans at home or the diaspora.** This gates several
  of the others.
- Whether sponsored placement ever touches an answer, or stays on a separate
  labelled surface. The recommendation here is the latter, because a bought
  answer makes the citations decoration.
- Employer first or institution first, and which one.
- Monetization and its timing.
- Company formation, and in which country.
- Whether Argus today and this become one product or two.
- What happens to the carried-over issues on the existing board, including
  #656.

## 9. What would prove this wrong

Written before starting, so the answer is not negotiated afterwards.

- Fewer than about one in three answers saved when saving is offered.
- Alerts producing under 30% return within 72 hours. Contextual notifications
  should beat generic push by a wide margin, or the mechanism is inert.
- Fewer than half of saved items showing a real change in eight weeks, which
  would mean there is no fuel regardless of design.
- More mutes than returns.
- Nobody can get their own statement into the product, which would kill the
  data layer.
- No institution will take a second meeting after seeing click evidence.

Any of those means people want a correct answer once, not a relationship with
it, and the pivot needs rethinking rather than more building.

## 10. Where the work currently sits

An incubation lane built a local prototype between 2026-09-20 and 2026-09-23.
It is **not** production qualified and is deliberately isolated.

| Item | Value |
| --- | --- |
| Incubation branch | `codex/money-placement-pilot`, merge commit `026be6d3` |
| Reviewed head | `9628d5c5` on `codex/argus-finance-experience` |
| Pull requests | #657 deposit pilot, #658 platform expansion, #664 Argus experience rebuild |
| Location in tree | `money-view/`, React, TypeScript and Vite with FastAPI and local SQLite |
| Production | `main` at `a9286b21`, untouched. Integration untouched. No Supabase migrations applied |

**What it demonstrates:** one ledger owning balances, chat and direct controls
calling the same domain operations, the model proposing structured meaning
while code owns arithmetic and persistence, explicit currency provenance with
no silent conversion, provider data loaded by jobs with the last good
publication preserved, and a provider interface proved against a synthetic
second country.

**What it does not:** regulator publications, inflation, prices, credit and
service workflows are seeded or simulated; statement import handles only
CSV and TSV, not the PDF statements Dominican banks actually issue; free-text
interpretation was never evaluated against a live model; capacity figures came
from an earlier snapshot on a development laptop.

**Before anyone outside the team sees it,** every surface running on simulated
data has to be hidden. Receipts are the entire claim, and a fabricated credit
score or balance destroys it.

## Work in progress: founder review before roadmapping

This document is a first pass and the founder has said plainly he intends to
pull it apart. Do not turn it into lanes yet.

The review needs to settle, in this order:

1. **The user** (section 4). Several later choices change shape with it.
2. **Which pillars are in the first slice** and which are explicitly parked.
3. **The entry route**: employer, institution, or consumers first.
4. **The sponsored placement question**, because it decides whether the
   product's honesty is structural or negotiable.
5. **Entity and country**, which gate Banco Popular data, payments and any
   paid tier.
6. **What happens to existing Argus:** one product or two.

Once those are answered, this becomes a roadmap with lanes, acceptance bars
and an order of work. Until then it is an argument, and it should be read as
one.
