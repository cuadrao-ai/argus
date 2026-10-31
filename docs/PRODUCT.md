# Cuadrao product

**Status:** Current product direction, approved September 26, 2026.
**Audience:** Founders, product/design, engineers, and collaborating agents.
**Detailed experience owner:** [Minimum viable ecosystem experience (MVEE)](specs/argus-minimum-viable-ecosystem-experience.md).

## 1. Purpose

Argus helps people understand where they stand, keep their money organized,
and know how their choices change their financial picture.

Its core promise is: **know what is already committed, what remains until your
next income, and how your choices change that.** The product connects recording,
understanding, planning, relevant updates, and returning to an up-to-date picture.
Conversation is one way to work across that experience; direct controls and
manual entry are equally valid paths.

## 2. Who we design for

Start with Dominican adults juggling cash, bank accounts, and debt who already
try to organize their money but cannot confidently tell what remains after
commitments. Income may arrive by quincena, commissions, remittances, or other
variable sources. This is a design focus, not an eligibility restriction.

People can manage their own finances and invite a partner into an explicitly
shared household view. Individual and joint accounts belong in the picture;
private information stays private unless its owner chooses to share it.

## 3. The connected experience

The [MVEE](specs/argus-minimum-viable-ecosystem-experience.md) owns the complete
surface definitions, ingestion paths, confirmation rules, household boundaries,
and pain-point coverage. In brief:

- Home explains the upcoming financial period and recorded position.
- Accounts organizes financial facts and corrections.
- Argus helps record, explain, and compare choices.
- Plan connects budgets, debts, and goals to the same money.
- Search recovers records and prior reasoning.
- Updates draws attention to relevant changes; profile owns app and data controls.

The experience should be useful with cash, manual records, and documents.
Bank connectivity can improve it but must not be a prerequisite for value.
Input methods converge on confirmed financial records; guesses and hypothetical
scenarios must not silently change actual balances.

## 4. Product principles

- Make the picture understandable without dense dashboards or financial jargon.
- Preserve current Argus typography, chat detail, motion, and grounded answers.
- Explain assumptions, currency, source coverage, and freshness.
- Complete the user job across capture, correction, understanding and return to evidence.
- Make corrections easy and consistent across surfaces.
- Keep manual records and capture useful when a connector fails. Preserve drafts
  and show how to recover without duplicating financial effects.
- Keep one identity usable across independent spaces. Membership, billing and
  conversation context do not grant access to another space's private records.
- Fit each interface to its task. Consumer mobile favors quick capture and return;
  business web can support detailed review without changing shared financial truth.
- Keep market questions and historical comparisons accessible without a debt gate.
- Show the limits of planning: an app cannot create income or guarantee outcomes.
- Design for phones, with native iOS/Android and web as intended platforms.

The [constitution source index](research/cuadrao-constitution-2026-10-04/PRINCIPLES.md)
records the rationale and technical owners for these principles. They do not add
features to the assigned launch scope. [Consumer launch scope](specs/argus-minimum-viable-ecosystem-experience.md#consumer-and-business-launch-boundary)
defines the public product boundary.

The [Argus web guide](../.agent/designs/argus/DESIGN.md) and
[Cuadrao native guide](../.agent/designs/cuadrao/DESIGN.md) own their platforms' visual conventions. Native
implementation contracts, sequencing, remaining providers, and the new account-onboarding flow remain
open as specified in the MVEE. The [voice and chart direction](ARCHITECTURE.md#voice-and-chart-direction)
is selected; integration and acceptance remain to be completed. Follow the [authority map](DOCUMENTATION_AUTHORITY.md)
when scoping implementation.

## 5. Existing capabilities and behavior to preserve

Argus is one evolving product. Existing production capabilities, interactions,
data, and access controls carry forward unless an approved change explicitly
replaces them. The lists in this overview and the MVEE are not exhaustive:
omission is not a decision to remove, rebuild, hide, or enable a feature.

The current foundation is grounded finance chat, calculations, research,
historical simulations, conversations/history, Omnisearch, and account/settings.
These are capabilities within the ecosystem, not a separate investing product.
The approved financial-record, household, and native-app experience is not
claimed implemented by this document.

Document intake follows the [MVEE capture flow](specs/argus-minimum-viable-ecosystem-experience.md#4-information-ingestion-one-destination-several-entry-methods):
save a durable private draft and source before preparation, then review and approve.
An upload alone creates no confirmed expense, balance change or amount owed.
The shared backend foundation is tracked in PR #776; native and Chat actions,
group approval and hosted enablement remain separate integration work.

For supported questions, Argus computes from supplied inputs or provides
source-backed explanations. General-knowledge responses must be distinguishable
from current research; assumptions and source freshness stay visible.

**Compute what the user gave you. Never prescribe what they should do.**
Arithmetic on someone's own numbers is a grounded calculator. This pivot does
not authorize discretionary trading, automatic money movement, or a change to
the existing advice boundary.

Guest chat remains a real entry path. The existing access policy is defined in
[Guest Entry](#guest-entry-default-on-kill-switch) below. The pivot's
[guest access boundary](specs/argus-minimum-viable-ecosystem-experience.md#guest-access-and-registration)
is now founder-locked; it preserves guest chat while gating other ecosystem
features behind registration. Its implementation is separate from this
publication and must not introduce an auth-first gate for chat.

The remaining sections specify capabilities and behavior to preserve. They do
not form a new feature queue or establish a backtest-only activation requirement.

### Current production availability and planned changes

This section owns the availability statements below. The founder confirmed this
production posture on September 26, 2026; this documentation update changes no
flags or rollout configuration.

| Capability | Current production state | Approved change |
| --- | --- | --- |
| Notifications | Hidden/flagged for Alpha | Enable as part of the next product push; behavior follows the MVEE Updates experience. Implementation and rollout still need their assigned work. |
| Subscriptions | Hidden/flagged for Alpha | No enablement change approved; preserve the existing gate. |
| Personalization memory | Shipped and flag-on in production (`ARGUS_ENABLE_PERSONALIZATION_MEMORY=true`). Exposure limited to `admin` and `developer` (`MEMORY_EXPOSURE_ROLES`). Semantic recall off (`ARGUS_ENABLE_MEMORY_SEMANTIC_RECALL=false`). Ordinary registered accounts see the unavailable state. | Widen to registered users only with earned opt-in plus inspect/edit/delete/reset/disable/"why was this used?" controls. Memory must not be required for the idea/evidence/comparison loop. |
| Evidence receipt sharing | Deployed `argus-api` code at `a9286b21` verified; production `render.yaml` / Blueprint on `main` declare `CUADRAO_EVIDENCE_RECEIPT_SHARING_ENABLED=true` and `NEXT_PUBLIC_EVIDENCE_RECEIPT_SHARING_ENABLED=true`. Hosted environment fingerprints and live env-var readback remain pending in [`2026-09-17-main-production-promotion.md`](release-manifests/2026-09-17-main-production-promotion.md), and `argus-app` was not independently verified, so neither hosted API nor UI flag value is confirmed live. Integration Blueprint may still declare both `false` until the next promotion aligns it. | Preserve shareable-by-default with owner turn selection and exact preview as the privacy boundary. |

An approved future experience does not contradict a currently hidden feature.
Update this table when the corresponding release changes availability. Design
and experience documents link here rather than maintain separate state lists.

---

# 6. Language Experience (Alpha)

Argus should feel globally accessible from first launch.

## Supported Languages

- English
- Spanish (Latin America)

## Principles

- Language selection should be intuitive and premium.
- New users should clearly understand multilingual support.
- First use should occur in the selected language.
- Surface UI should reflect selected language.
- AI should mirror user language preference dynamically.

Future languages may be added later.

---

# 7. Recents Surface

Recents are a mixed chronological feed of recent user activity.

Examples:

- Recent chats
- Recent completed backtests
- Prior idea/evidence activity reopened through Omnisearch

Purpose:

- quickly resume prior work
- reduce navigation friction
- reinforce continuity
- help users return repeatedly

Recents distinguishes work in progress from attention. A task may be working
without being unread; terminal activity becomes unseen only beyond the user's
durable read boundary. Registered users may also deliberately mark a task
unread as a reminder. These states come from backend lifecycle and read truth,
never message wording, client timers, or changes to recency ordering.

Recents and completed result cards remain part of the existing conversation
experience. Dedicated Strategies and Collections surfaces are retired.
Historical records remain readable so older runs and history never break, but
the product no longer creates or manages those legacy objects. This compatibility
requirement does not restrict the ecosystem's approved navigation.

---

# 8. Legacy Collections Compatibility

Collections are retired product records. Their tables and owner-scoped history
readers remain for compatibility with historical rows; there is no navigation,
picker, setting, search result, CRUD endpoint, or new write path.

---

# 9. Legacy Strategies Compatibility

The dedicated Strategies surface and result-card Save action are retired.
Completed runs remain revisitable through conversation/history/Recents, while
Refine idea remains available on the result card. Historical Strategy rows and
direct run `strategy_id` reads remain owner-scoped and read-compatible.

Saved-idea recall lives in Omnisearch, not a separate dashboard. Typed search
results and right-panel previews cover Conversation, Backtest, Evidence,
Decision, and Idea, and the Idea Ledger browse groups saved ideas by decision
state (promising, watching, rejected, revisit) with filter chips. Group order
and counts are backend-owned; the frontend renders them without synthesizing
its own groups.

Durable `Idea` / `IdeaVersion` / `EvidenceArtifact` / `DecisionNote` recall is
the existing idea/evidence remembering contract. It is distinct from a general
cross-conversation memory system. The ecosystem's new financial records and
chat integration still require explicit technical contracts; do not implement
them as an assumed extension of legacy Strategy rows or generic memory.

## Legacy Compatibility Goals

- keep historical Strategy and Collection rows owner-scoped and readable
- preserve old `strategy_id` links without creating or mutating legacy records
- route current recall through conversations, Recents, Omnisearch, and the Idea
  Ledger instead of rebuilding a retired dashboard

## Result Metrics

Current result cards render canonical high-level metrics. Historical
`metrics_preferences` fields may remain readable on legacy Strategy rows, but no
current UI configures them.

Examples:

- total return
- win rate
- max drawdown
- sharpe ratio
- profit factor
- trade count

Metric customization should remain simple and fast.

---

# 10. Object Management (Alpha)

Users should be able to manage their workspace cleanly.

## Chats

- rename
- archive
- delete

## Legacy Strategy and Collection Records

Historical rows and links remain read-compatible. There is no current rename,
pin, delete, restore, organization, search, or browse surface for either legacy
record type.

---

# 11. Supported AI Responsibilities (Alpha)

The AI assistant should:

- welcome first-time users into ordinary conversation
- explain financial terms simply
- **answer money questions by computing them or citing a source**
- **teach the method: when a question is too broad, offer specific questions
  derived from what the user actually said**
- gather requirements for supported backtests
- recommend **localized generic starter prompts**
- guide users toward successful flows
- explain results
- suggest next experiments, including **what the same money would have done in
  the market over the same period**
- remember thread context appropriately
- adapt to preferred language, **and to the currency of the user's locale**

The AI assistant should **not** pretend unsupported capabilities exist, **and
should not refuse a question it can compute or ground.** A refusal that names a
capability the user did not ask about is a defect.

Forward-looking and valuation questions are answered, as grounded scenarios
(decision 10, 2026-09-10). "What will $10,000 in NVDA be worth in ten years"
and "what price does NVDA need to grow into" get cited forecasts, analyst
targets and valuation multiples, the arithmetic written out, and the result as
labeled scenario ranges. Argus never presents one number as the future and
never says what the user should do. A projection on the user's own numbers is
arithmetic, not a prediction. The one thing that stays impossible is a backtest
over a future window, because that data does not exist: Argus says so, offers
the historical test, and can research what analysts expect instead.

---

# 12. Supported Strategy Model (Alpha)

Argus Alpha uses a controlled set of supported strategy templates.

Users may speak naturally, but AI maps requests into supported engine templates.

Examples:

- Buy and hold
- Buy the dip
- RSI mean reversion
- Moving average crossover
- DCA accumulation

Momentum breakout and trend follow are recognized by the interpreter but are not
yet executable. Argus does not present them as runnable strategies to users.

## Asset Class Grouping (Alpha)
Alpha supports:
- Individual symbols
- Grouped same-asset simulations (up to symbol cap)

Examples:
- Equity: `AAPL` + `MSFT` + `NVDA`
- Crypto: `BTC` + `ETH` + `SOL`
- Currency pair: `EURUSD` or a same-class group such as `EURUSD` + `GBPUSD`

Alpha does **NOT** support mixed-asset-class simulations. Equity, crypto, and
currency-pair runs each remain within their own class.

This ensures reliability and benchmark coherence.

---

# 13. Search Philosophy (Alpha)

Search should reduce friction and help users resume intent instantly.

## Global Search

Omnisearch covers the current Conversation, Backtest, Computed answer,
Evidence, Decision, and Idea record types. A computed answer is an assistant
message with a backend-declared computation; its dossier sits beside the run
dossier and its asset counts under the same row as runs. Search must not expose legacy Strategy or Collection rows as
current product surfaces. Alpha uses typed and text search; vector or semantic
search remains deferred until a concrete later need exists.

---

# 14. Feedback & User Listening

Users must have a clear way to provide:

- bug reports
- feature requests
- general feedback

Alpha can support:

- settings page feedback entry
- conversational capture via AI
- PostHog surveys later when enabled

Feedback velocity is strategic.

---

# 15. Boundaries

The [MVEE boundaries](specs/argus-minimum-viable-ecosystem-experience.md#8-differentiation-and-boundaries)
and [pain-point limits](specs/argus-minimum-viable-ecosystem-experience.md#112-pain-points-only-partially-addressed-or-outside-the-minimum)
own the minimum ecosystem's exclusions. Technical/provider choices that remain
open are not implied approvals to build them.

Historical simulation constraints still apply: no real brokerage execution,
unsupported custom strategies, or mixed-asset-class runs. Stablecoins remain
excluded from Alpha backtesting to prevent misleading outcomes. These engine
limits do not prohibit users from recording diverse personal assets or asking
supported finance questions.

# 16. Product outcomes

The ecosystem should help people resolve uncertainty, maintain useful records,
understand choices, and return when their situation changes. Its experience
loop and pain-point coverage are defined in
[MVEE section 11](specs/argus-minimum-viable-ecosystem-experience.md#11-pain-points-limits-and-the-reinforcing-loop).

A successful backtest demonstrates one capability; it is not the universal
onboarding or activation milestone. There is no newly approved numeric target,
instrumentation schema, or replacement experiment schedule in this document.
Existing assigned measurement packages retain their scoped definitions until
explicitly reconciled.

---

# 17. Product Experience Standards

Every user session should feel:

- fast
- intelligent
- elegant
- low friction
- helpful
- confidence-building

# 18. Product Anti-Patterns

Argus should avoid:

- **Spreadsheet Software**: No dense data tables or parameter overload.
- **Broker Terminal**: No dashboard-first UX or blinky, intimidating charts.
- **Toy Chatbot**: No generic, shallow, or purposeless "AI chatter."
- **Generic Finance App**: No "top 10 gainers" lists or generic news content feeds.

**Argus chooses:** Progressive disclosure, simple cards, focused actions, and equally usable conversational or direct entry.

# 19. Result Trust Standard

Every result card must include a lightweight assumptions footer to maintain integrity. Benchmark comparisons are class-based:
- **Equities** compare to **SPY**
- **Crypto** compares to **BTC**
- **Currency pairs** compare to the tested pair itself

Example: *Long-only • Equal weight • No fees/slippage • Benchmark: SPY*

The default private-alpha footer discloses no fees or slippage. Execution realism
(fees + slippage modeling) is active by default behind
`ARGUS_ENABLE_EXECUTION_REALISM`, while modeled costs remain opt-in per idea.
Runs without stated fees or slippage stay idealized; when a user states costs,
the assumptions footer reflects them. Set the flag explicitly to
`false|0|off|no` only as a kill switch; that restores the pre-realism path
byte-for-byte.

Result cards and explanations must describe executed backtest behavior, not raw
strategy triggers. A strategy may produce many buy/sell signals, but Argus only
shows trades, markers, trade counts, and win-rate inputs after the execution
layer has applied long-only position state, cash, sizing, and policy constraints.
Ignored signals can be explained in breakdowns when useful, but they are not
presented as real buys or sells.

Freshness and "what changed" explanations must keep two evidence layers
separate:

- canonical run/evidence deltas state what the backtests and mechanically
  verified corporate actions show;
- source-backed news, earnings, regulatory, macro, or other event context may
  explain what coincided with or may have contributed to a change.

Argus must not present contextual correlation as proven causation. Context
should carry sources and freshness, acknowledge uncertainty, and remain
informational. It is not financial advice or a recommendation to buy, sell, or
hold an asset.

## Guest Entry (Default-On Kill Switch)

Guest mode is part of the normal Argus product shape and supersedes the
auth-first landing page by default. A guest is a
real Supabase anonymous authenticated user with one temporary workspace, never
the unauthenticated Postgres `anon` role, the mock developer, or a synthetic
email profile.

The checked-in policy opens guest entry and permanent accounts alike:

- `CUADRAO_GUEST_ACCESS_ENABLED=true`
- `NEXT_PUBLIC_GUEST_ACCESS_ENABLED=true`
- `CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED=true`

The frontend presentation flag cannot grant access. The server remains
authoritative. The two Guest flags default on when unset; explicit `false` is
their emergency rollback kill switch. Public-account access is an independent
gate that fails closed when unset, so the checked-in `true` above is what opens
it and a deployment that omits the variable denies registration. The founder
opened it in production on 2026-08-12. Public registration is now open. Anyone
may create a permanent account, and the guest surface offers account creation
alongside **Sign in**. The only email the server turns away is one carrying an
explicitly disabled allowlist row. When that gate is off instead, permanent
signup and login are
limited to active allowlist roles and guests are offered an access request
rather than account creation. Existing admin and developer roles are unchanged
either way, because opening the gate grants access without granting a role.

Two clocks govern a guest, and they are deliberately distinct. The
**workspace** lives seven fixed days with one conversation: that is how long
the temporary chat survives and the window to claim it to an account.
Activity never extends the expiry. **Allowances** follow the visitor
(decision 2026-07-28, re-keyed by operation class 2026-09-08): two unique
simulations and three searches with sources per visitor per day, resetting at
UTC midnight. The workspace separately caps the temporary chat at two unique
simulations over its fixed lifetime, plus five feedback submissions.
Conversation is not an allowance: it is free, and the usage panel says so with
no limit. An anonymous endpoint is still not unbounded, so guest turns carry a
silent anti-abuse ceiling per visitor per day, sized so no real person reaches
it; it is never rendered or promised as an allowance. A signed-in account
carries its own silent daily chat ceiling (200, `CUADRAO_REGISTERED_DAILY_TURN_CEILING`)
and a daily research ceiling (15, `ARGUS_REGISTERED_DAILY_RESEARCH_CEILING`) so
one login cannot run unbounded LLM spend. Those caps are never projected as
allowances. Honest heavy chat users can hit 200 in a day. A fresh session cannot mint a fresh daily allowance—the visitor
counter keys on a keyed digest of the caller—and Start over preserves the
workspace counters. Simulations keep a workspace-keyed reservation as replay
identity; the visitor charge beside it is best-effort past admission, and
settlement enforces the cap. The current
landing implementation and its centered auth modal remain intact for
configuration rollback and later conversion work.

---

# 20. Historical Simulation Journey

A user opens Argus and says:

> What if I bought Tesla whenever it dipped hard?

Argus responds by:

1. clarifying needed inputs
2. proposing a supported simulation approach
3. running the test
4. showing outcomes
5. explaining what happened
6. suggesting what to test next

This is one supported journey. The ecosystem also supports recording, planning, household coordination, and general finance questions; its connected journeys are defined in the MVEE.

---

# 21. Product Decision Filter

When evaluating any feature, ask:

## Does this help someone understand, maintain, or improve the same financial picture?

Use the MVEE to decide experience fit and the assigned package to bound work.
A feature need not end in chat or a backtest to be useful.

---

# 22. Strategic Direction and Preserved Foundation

The [MVEE](specs/argus-minimum-viable-ecosystem-experience.md) owns approved
product direction. The [authority map](DOCUMENTATION_AUTHORITY.md) distinguishes
that direction from existing assignments and technical decisions still to come.

Preserve these Alpha foundations while adding the ecosystem:

1. Working AI chat loop
2. Real backtests
3. Reliable persistence
4. Great web/PWA usability
5. Fast iteration from user feedback

---
