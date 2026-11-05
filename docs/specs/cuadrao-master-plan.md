# Cuadrao master plan: execution roadmap

**Status:** Planning roadmap, drafted October 4, 2026 (CT). It merges the product half by the Product Lead (Iris) and the engineering half by the Head of Engineering (Yelena), and the docs seat (Maya) assembled it. It is not an authority over the [MVEE](argus-minimum-viable-ecosystem-experience.md), the [execution board](argus-execution-board.md) or the [decision log](argus-decision-log.md). Nothing here authorizes a merge, deploy, migration, hosted flag, paid provider or new runtime work. The Oct 4 mobile roadmap lock in [#813](https://github.com/lagarcess/argus/pull/813) is the delivery checkpoint, and the execution board keeps delivery authority. Founder locks live in the decision log; this plan links to them instead of restating them as new decisions.

**Sources:** Lucas's two October 4 documents, recorded verbatim as [go to market vision](../research/2026-10-04-cuadrao-gtm-vision-source.md) (cited as **GTM**) and [product and business architecture](../research/2026-10-04-cuadrao-product-business-architecture-source.md) (cited as **Blueprint**). Repo facts were read on integration `codex/private-alpha-next` at `a8c37d3a` (Oct 3, 6:09 AM CT). Open issues and PRs are as of October 4. Lucas approved keeping both source records public as recorded, with no summaries (Oct 4, 2:22 PM CT).

**Related documentation:** [#813](https://github.com/lagarcess/argus/pull/813) (execution board Oct 4 roadmap lock) and [#808](https://github.com/lagarcess/argus/pull/808) (profile hidden rows backend; touches the decision log, MVEE, board, handoff, FK census, `DATA_MODEL.md` and `API_CONTRACT.md`). This plan doesn't edit the execution board.

## October 7 update: approved offline fiscal development

The [connected Business specification](cuadrao-business-connected-flow-spec.md)
and [E0 implementation plan](cuadrao-business-e0-implementation-plan.md) now own
the approved connected-flow design and bounded offline engine work. The
[decision log](argus-decision-log.md#october-7-2026-business-connected-flow-and-offline-e0-plan)
records Lucas's approval and documentation-only merge grant.

Cuadrao owns the engine, with replaceable signing and transport. E0 prepares
synthetic unsigned artifacts and local evidence. Its P0 source/profile gate
remains open. It neither persists business records nor signs or submits invoices.
The broader Business workflow remains capture, money, customers, invoices,
collections, source evidence and accountant handoff.

The October 4 partner-first passages below retain live-route history. Their
"first fiscal work", "lower priority" and paperwork dependencies do not govern
E0. Supplier discussions remain open; this approval neither cancels a vendor
nor authorizes a direct live route, certificate custody or issuer eligibility.
Lucas will coordinate the existing Business agent. Consumer keeps its release
and shared migration sequence; Marketing keeps its separate launch. No other
lane priority changes.

## How to read this plan

- **Labels.** **[fact]** comes from the repo, GitHub or a cited source. **[proposed]** is a recommendation that still needs a lock. **[estimate]** is a rough size, not a commitment. "For Lucas to lock" marks a proposal waiting on the founder. "Unverified" marks a claim nobody re-checked, including the PSFE requirements and e-CF signing details taken from the Blueprint.
- **Parts.** [Part A](#part-a-product) is Iris's product half and [Part B](#part-b-engineering) is Yelena's engineering half, kept close to how each author wrote them. Section references inside each part use that part's letter: §A3 is the pillar table, §B2 is the space model. Notes marked **Maya's note** are the docs seat's, not the authors'.
- **Where the halves disagree,** [the conflict table](#where-the-two-halves-disagree) lists each case with a suggested resolution. Where the plan combines product and engineering content, engineering detail follows Part B.
- **Where the plan disagrees with repo canon,** [the canon table](#conflicts-with-repo-canon) lists it. The canon docs are not edited here; the [side-track checklist](#side-track-checklist) holds the follow-ups.

## Locked on October 4

Lucas set the launch shape in the room on October 4 at 12:30 PM CT. The [decision log entry](argus-decision-log.md#october-4-2026-cuadrao-launch-shape) is the record; in short:

1. **Consumer iPhone app:** personal and household only. A short invite-only TestFlight under the existing October 2 invite rules, then a public launch and fast iteration.
2. **Cuadrao for Business:** the full service is on the web. The business space in the iPhone app stays thin (capture, quick approvals, where money stands) and goes only to the first business testers on TestFlight. Public consumers never see it. How to keep it out of the public build is the Head of Engineering's call; her decision is Option C in §B3.4.
3. **cuadrao.ai** promotes the whole suite and carries the waitlists.
4. **Stack:** stays on Resend, Render and Supabase.

**Historical live-route correction (Lucas, Oct 4, 12:39 PM CT, recorded in Yelena's engineering notes; see the [October 7 offline update](#october-7-update-approved-offline-fiscal-development)):** partner first. Connecting to a DGII-certified provider (PSFE) is the fastest route to a full business service and to live invoicing through Cuadrao. Cuadrao's own DGII backend is the parallel track while Lucas handles the DGII paperwork. The pilot starts by tracking the invoices owners already issue, then issues through Cuadrao once the provider connection is live. Choosing the provider is part of Lucas's partner track. The Blueprint names Alanube and Alegra as references; no provider is chosen.

**Lucas's further Oct 4 calls (about 12:44 PM CT, relayed by Iris):**

1. **Plaid is kept,** not an open decision. The Plaid sandbox plus Faker-generated data is how the team stress-tests financial data. Real Plaid serves Dominicans in the US and Dominicans with accounts abroad. Manual entry stays available for anything Plaid doesn't cover. Production Plaid access needs Plaid's application and security review; that's a light partner step on Lucas's founder track, next to the US entity, not a blocker.
2. **Dominicans in the US** is a named consumer segment. This is Lucas's Oct 4 addition next to the locked first users (people living in the Dominican Republic); it doesn't replace the DR-first lock. See [canon row 11](#conflicts-with-repo-canon).
3. **Market-data providers are parked for the pilot, not deleted:** Alpaca, Kraken, BCRD and the other market-data providers. BCRD is fully parked. Their keys come out of the live setup and the code stays. Perplexity covers general finance questions in chat.
4. **Gmail import stays an open decision.**

**Currency rule (Lucas, Oct 4, about 12:45 PM CT, relayed by Iris):** Cuadrao never converts currencies, because converting would blur the numbers and make Cuadrao responsible for their accuracy. Lucas's design lane owns the final screens.

- Every account stays in its own currency. Cuadrao never shows a blended total.
- Home shows one total per currency on separate lines (for example "RD$ 85,400" and "US$ 1,250"). The person's primary currency comes first; they set it at onboarding and can change it later.
- Charts and comparisons show one currency at a time, with a switcher when the person holds more than one.
- Plans keep a fixed currency. When an account in another currency pays toward a plan, the person records both amounts exactly as their bank charged them. The rate comes from their real transaction, never from Cuadrao.

Where integration code and docs differ from this rule is listed in [canon rows 12-17](#conflicts-with-repo-canon). No code is changed by this plan.

**AI providers (Lucas, Oct 4, 2:20 PM CT, relayed by Yelena):** all three stay behind the server, and none of them writes saved balances. Details are in §B4.1.

1. **OpenRouter** is kept, for the chat models (GPT and Grok) and for vision extraction.
2. **Grok voice** is the provider for the chat voice-call feature. It's new and not wired yet. Once built it gets a server-only key; the phone never holds it.
3. **Perplexity** is kept, for finance search. Cuadrao integration requires a separately assigned runtime slice; #813 records the delivery sequence.

**Space model timing (Lucas, Oct 4, 2:21 PM CT, relayed by Iris):** the space-model change lands before TestFlight, which is a few days out. This settles [conflict row 5](#where-the-two-halves-disagree). Which migration steps that covers is Yelena's sequencing (§B2.3). The model itself, including roles and the business retention rule, still needs Lucas's lock (§B9 question 1).

The rest of this plan is proposals. F1 to F5 in §A7 and the questions in §B9 stay open.

## Roadmap at a glance

This summary combines both halves. Sizes are Yelena's estimates (§B6). Order inside each stream is a proposal.

| Stream | What it delivers | First step | Waits on |
| --- | --- | --- | --- |
| **Consumer TestFlight** (personal + household, iOS) | The connected candidate from #813 in invite-only TestFlight, then public | The must-do issues in §B7 and the minimum in §A4 | Apple team and bundle id (§B3.2), cuadrao.ai DNS, email and AASA |
| **Shared foundation** | Space and membership model (§B2), entitlement service (§B5), scoped storage (#778), audit and approvals | Space model steps 1-2 (§B2.3) for personal and household, landing before TestFlight (Lucas's lock) | Lucas's lock on the model itself (§B9 question 1) |
| **Business ledger** (web first, thin app space for pilots) | Web shell, roles, money and ops, Inbox and Vault, customers, non-fiscal invoices, external e-CF tracking, matching, accountant export | Space model step 4, then the web shell | Roles matrix lock; about 12-18 eng-weeks [estimate] |
| **Fiscal: certified-provider bridge** (partner first) | Live e-invoicing through Cuadrao via a PSFE | Adapter against the provider's sandbox, behind the shared fiscal-backend interface | A PSFE agreement for the historical live route; the October 4 estimate does not sequence E0 |
| **Fiscal: owned offline E0** | Synthetic unsigned preparation and local validation/evidence under the [approved spec](cuadrao-business-connected-flow-spec.md) | [E0 plan](cuadrao-business-e0-implementation-plan.md), with P0 before Type 31 rules | Lucas coordinates execution; official sources/profile must pass P0. No supplier or issuer paperwork dependency for E0. |
| **Brand and domain** | `ai.cuadrao.app`, cuadrao.ai web, API host, AASA, email domain, redirects | Entity and Apple team choice (§B3.2 step 0) | F3 |
| **Founder tracks** | Entity, Apple enrollment, PSFE partner, Plaid production access, pilot recruitment, DGII answer | See §A5 | Lucas |

**What runs in sequence:** the space-model change before TestFlight (Lucas's lock) and before any business data exists; the invoice record and its fiscal-state fields locked before the fiscal streams touch the ledger; no compliance promise to a customer before a live issuance route exists; own PSFE status after at least three pilot issuers.

**Issue placement for #686 and #694:** both are must-dos at the time of the next integration-to-`main` promotion, not TestFlight blockers. Any promotion that carries #674 applies its migration and env keys first (#686), and the forged-header check runs in that promotion window (#694). This matches Yelena's reasoning in §B7 and Iris's deferral in §A6.

## Where the two halves disagree

Each row gives Iris's current position (her Oct 4 corrections included), Yelena's position in Part B, and the status. Iris's positions are positions, not locks: Lucas or Yelena still decide. A row is **converged** when the two positions agree or Iris adopts Yelena's text; otherwise it stays **open** and names who decides. Rows 23 to 28 also compare Yelena's §B4.1 with Lucas's later Oct 4 calls.

| # | Topic | Iris's position | Yelena's position (Part B) | Status |
| --- | --- | --- | --- | --- |
| 1 | **e-CF route** | Partner first. A DGII-certified provider is the path to a full business service; our own DGII backend and certified-provider status run in parallel while Lucas does the DGII paperwork. Pilots record invoices issued elsewhere, then issue through Cuadrao (§A7 contradiction 1). | Same, per Lucas's 12:39 PM CT correction (fiscal route line, §B6). | Historical October 4 live-route position. See the [October 7 offline update](#october-7-update-approved-offline-fiscal-development). |
| 2 | **Fiscal order** | New pillar 7, certified-provider integration built against the provider's sandbox; own fiscal tooling (pillar 8) is a parallel track behind it. Yelena sets the exact sequence against capture. F2 is which provider and when. | §B6: external e-CF tracking is the first pilot step; the provider bridge (3-5 eng-weeks) is the first fiscal work; the own backend (6-10 eng-weeks) runs in parallel at lower priority. | Historical October 4 sequencing. The [approved E0 plan](cuadrao-business-e0-implementation-plan.md) now owns offline scope; Lucas coordinates execution. F2 remains a separate live-route question. |
| 3 | **Keeping business out of the public build** | Yelena's Option C. The in-app business space stays thin; the full service is the web. | §B3.4: Option C, a compile-time `CUADRAO_BUSINESS` build plus server authorization. | **Converged** (Head of Engineering's decision under lock 2). |
| 4 | **Business roles** | Yelena's 6 roles plus billing admin in the data model; Iris's 3 presets (owner, associate, accountant) in the pilot interface. | §B2.2: owner, admin, bookkeeper, approver, accountant, viewer, plus a billing admin flag. | **Converged.** Lucas still locks the matrix with the space model (§B9 question 1). |
| 5 | **Space model before TestFlight** | Yes, because it's cheapest with no real data. | §B2.3: steps 1-3 are cheapest before external TestFlight; consumer TestFlight needs steps 1-2; the business kind (step 4) comes last, web first. | **Settled by Lucas's lock** (Oct 4, 2:21 PM CT): the space-model change lands before TestFlight. The exact steps are Yelena's sequencing. |
| 6 | **#686, #694** | (No new position.) | §B7: listed under consumer TestFlight because the TestFlight API is `argus-api` on `main`. | **Settled by steering:** must-dos at main-promotion time, not TestFlight blockers. |
| 7 | **#807** | Yelena's sequencing. Iris only needs the deletion sweep (item 15) before TestFlight. | §B7: item 15 for TestFlight; items 3 (alerting) and 5 (per-worker limiter) before public launch. | **Converged.** |
| 8 | **#671, #676** | Yelena's sequencing. | §B7: before public launch (the iOS app relies on web recovery; limiters scale with workers). | **Converged.** |
| 9 | **#803, #804** | Yelena's sequencing. | §B7: before public launch. | **Converged.** |
| 10 | **#700, #656** | Yelena's sequencing. | §B7: before public launch (#700 if the Cuadrao agent reuses the chat turn path; #656 because calculations stay). | **Converged.** |
| 11 | **#690** | Yelena's sequencing. | §B7: re-scope to the business, agent and file surfaces before real business data. | **Converged.** |
| 12 | **#684, #685** | Tie both to F5 (§A6). | §B7: close when the guest flow and backtests retire; until then they matter on arguschat.ai. | Compatible. **Open** on F5 (Lucas). |
| 13 | **Archive or close Argus-era issues** (#640, #606, #644, #653, #623, #620, #696) | Keep deferred; re-check against the chat runtime (§A6). | §B7: archive or close as obsolete after the pivot. | **Open.** Lucas or Iris confirm before any closure. |
| 14 | **Android** | Partially built (shell #730); parked until after the public iOS launch. | §B1.1: park; no Android release is committed. | **Converged.** Canon row 7 still applies. |
| 15 | **Guest flow** | Drop it: an invite-only TestFlight with sign-in makes it unnecessary. Still tied to F5 and the MVEE guest lock. | §B1.1, §B1.3: drop from Cuadrao; delete it with the chat retirement. | **Open** for Lucas (F5 and canon row 6). |
| 16 | **WhatsApp intake** | Yelena's 1-away, because it needs a Meta business account (§A3 pillar 3). | §B6: 1-away (Meta WhatsApp Business Platform). | **Converged.** |
| 17 | **Purchase record and entitlements** | RevenueCat is the record of purchases; our table mirrors it so the server can check entitlements. Final call is Yelena's. | §B5, resolved by Yelena: our own entitlement table is the source of truth. RevenueCat, Stripe and Lemon Squeezy webhooks are only inputs to it. Business entitlements are per space, and Lemon Squeezy web billing is invisible to RevenueCat, so the API is the single reconciler. RevenueCat stays the StoreKit layer on iOS. | **Converged** (Iris defers to Yelena). F4 (business premium route) stays open for Lucas. |
| 18 | **`GUEST_PUBLIC_LAUNCH_SAFETY.md`** | Archive it with the guest flow. | §B8: archive with the guest flow and web chat retirement, not before. | **Converged.** |
| 19 | **Execution board** | Shrink it. | §B8: keep it (#813 section). | **Open.** Out of scope here: no board edits until #813, #808 and #790 land. |
| 20 | **Staging** | Yelena's call. | §B4 and §B9 question 2: TestFlight against production (MVEE §1.4) or a staging project after #811. | **Converged** on owner. §B9 question 2 still goes to Lucas because a new project reopens MVEE §1.4. |
| 21 | **Sole-owner deletion** | Block account deletion until the owner transfers ownership or closes the business, keeping records for DR tax retention. A Lucas call. | §B2.4 gap and §B9 question 3: the same proposed rule. Retention period is counsel's input. | **Converged** on the rule. **Open** for Lucas. |
| 22 | **Docs archive or keep** | Archive anything only about the Argus web, guest or chat; everything else follows Yelena's list. | §B8: keep and rewrite list, plus archive candidates. | **Converged** on the rule; the web, guest and chat archive is **pending F5**. #815 isn't widened for it. |
| 23 | **Plaid** | Kept: sandbox plus Faker for stress tests; real Plaid for Dominicans in the US or with accounts abroad, a named consumer segment; manual entry for everyone else. Production access needs Plaid's review, next to the US entity (§A2, §A5). | §B1.1: salvage, US-only. §B6: "Gated for DR users", "Keep only for foreign accounts". §B4.1 and §B9 question 4 originally had Plaid as "Lucas decides"; now Keep. | **Settled by Lucas's 12:44 PM CT call** (keep). §B4.1 and §B9 question 4 are updated in Part B (Yelena accepted). |
| 24 | **Market-data providers** | Alpaca, Kraken, BCRD and other market data parked: keys removed, code kept. Perplexity answers general finance questions in chat. | §B4.1: Alpaca (`ALPACA_*`), Kraken (keyless), FRED and the market-data mode names are "Park (pilot)": runtime reads stop, keys leave Render, code and provider keys stay, no revoke. BCRD has no env names and is "Park (pilot)". | **Converged** for Alpaca, Kraken and the others. BCRD: see row 26. |
| 25 | **OpenRouter** | Stays, because receipt capture depends on it. | §B4.1: `CUADRAO_PROD_OPENROUTER_API_KEY`, `ARGUS_VISION_MODEL` and the document-extraction timeout are Keep. The Argus chat tier names are Drop (blocked), and the guest OpenRouter key is Drop (blocked). | **Locked by Lucas** (Oct 4, 2:20 PM CT): OpenRouter is Keep for the chat models (GPT and Grok) and vision extraction. Note from §B4.1: `ARGUS_VISION_MODEL` isn't in `render.yaml`, so extraction fails with `missing_vision_model` until it's set. |
| 26 | **Currency conversion and BCRD** | Lucas's currency rule: no conversion, one total per currency with the primary first, one currency per chart with a switcher, plans in a fixed currency, both bank amounts recorded (§A2). | §B4.1, corrected with Yelena's agreement: BCRD is a parked data source with no planned use and no rate-source role; there's no rule for future conversion. `calculation_rows.py` `dollar_rate` converts in the frozen Argus web chat only: a known violation, nothing new builds on it, it goes with the chat retirement, and it isn't a TestFlight blocker. | **Converged.** |
| 27 | **Gmail import** | Still open for Lucas. | §B6: 1-away. §B4.1: `GOOGLE_OAUTH_*` are "Lucas decides". | **Converged**; the decision stays open for Lucas. |
| 28 | **When to park the market-data keys** | Not covered. | §B4.1: Yelena recommends pulling them later with the chat freeze, not now. The `/ops` readiness check probes market data (`api/routers/ops.py:73`), so pulling the keys first breaks it as well as the frozen chat, and idle keys cost nothing. If Lucas wants them out now, the ops probe has to change first. | **Open** for Lucas, tied to F5. |

**Maya's note on the product half:** Part A is Iris's Oct 4 draft with her later Oct 4 corrections rewritten in place: partner first, Plaid and the US segment, providers, the currency rule, the thin in-app business space with Option C, and the new certified-provider pillar. For the public repo, the prospect-list file path is removed and the source paths point to the committed records.

## Conflicts with repo canon

These canon passages conflict with the October 4 sources, the locks above or the plan. None of them is edited in this PR. Each needs a founder lock or a docs rewrite, listed in the [side-track checklist](#side-track-checklist).

| # | Canon | What it says | What conflicts | Suggested follow-up |
| --- | --- | --- | --- | --- |
| 1 | [Decision log](argus-decision-log.md#locked), 2026-09-28 (clarified 2026-09-29) | "Revenue, pricing, paywalls and billing remain deferred." | GTM "What we have decided": "Both products can earn revenue." §A3 pillar 8 and §B5 plan entitlements and billing in sandbox. | Lucas confirms a decision-log entry that lifts the deferral for revenue direction while prices stay open. Then update [DOCUMENTATION_AUTHORITY](../DOCUMENTATION_AUTHORITY.md#founder-deferral). |
| 2 | Decision log, 2026-09-24 | "Argus keeps all its existing grounded chat and calculation capability." | §B1.1 drops the web chat UI and retires backtests; §A6 retires backtest and quant research as the product center. Calculations and grounding are kept. | Lucas confirms what "keeps" now covers (calculations and grounding yes; web chat UI and backtests retire). |
| 3 | Decision log, 2026-09-26; [DOCUMENTATION_AUTHORITY](../DOCUMENTATION_AUTHORITY.md) | "Preserve Argus visual identity"; the authority doc says the product "retains the Argus visual identity". | Cuadrao brand, design graft (#783/#785/#786/#792) and the cuadrao.ai cutover (§B3). | Rewrite the authority doc for Cuadrao (§B8) after a decision-log entry on the brand. |
| 4 | [MVEE](argus-minimum-viable-ecosystem-experience.md#financial-spaces) "Financial spaces" | Business is a named private space and "does not imply employees, payroll, invoicing or tax accounting". | Premium business with roles, invoices and e-CF (GTM, Blueprint, §A2, §B6). | Iris's resolution (§A7 contradiction 2): the MVEE limit becomes the consumer release scope; business gets its own spec. |
| 5 | [MVEE §1.6](argus-minimum-viable-ecosystem-experience.md#16-holds-later-work-and-unresolved-decisions) and DOCUMENTATION_AUTHORITY | "Web remake: frozen"; "replacing web with a landing page is not decided". | Lock 2 (full business service on web) and lock 3 (cuadrao.ai landing page with waitlists). | Iris's resolution (§A7 contradiction 3): the freeze covers the Argus consumer web. Amend §1.6 after the decision-log entry. |
| 6 | MVEE "Guest access and registration" (locked guest boundary) | A locked guest access boundary. | §B1.1 and §B1.3 drop the guest flow from Cuadrao and delete it with the chat retirement. | Ties to F5. Needs a founder lock before deleting guest code. |
| 7 | Decision log, 2026-09-26; MVEE §1.6 | Native iOS and Android plus web intent; Android "remains an intended native product"; "retain the existing web/PWA stack". | §B1.1 parks Android; GTM gives no Android date; F5 may retire arguschat.ai web. | Compatible if "park" means not scheduled. Record when F5 is answered. |
| 8 | [MVEE §1.4](argus-minimum-viable-ecosystem-experience.md#14-infrastructure-and-cost-constraints) | Reuse Render and the existing Supabase project on the current plan; preserve existing chats, research and backtests. | Lock 4 agrees on the stack. §B4 and §B9 question 2 ask whether to reopen §1.4 for a staging project; §B1.4 names a fresh project as a flip condition. | Stays locked unless Lucas answers §B9 question 2 otherwise. |
| 9 | [PRODUCT.md](../PRODUCT.md) | Argus product overview, approved September 26. | One Cuadrao with three contexts (GTM, §A1). | Rewrite for Cuadrao (§B8). |
| 10 | MVEE §1.2 private iPhone delivery | Private physical-iPhone delivery as the immediate finish line. | Lock 1: invite-only TestFlight, then a public launch. | Superseded in direction by lock 1; amend the MVEE when the board's next checkpoint lands. |
| 11 | [Decision log](argus-decision-log.md#locked), 2026-09-24 | "The first user is people living in the Dominican Republic, not the diaspora." | Lucas's Oct 4 addition of Dominicans in the US as a named consumer segment, served by real Plaid. | **Resolved.** Recorded as Lucas's Oct 4 lock in the [decision log's Oct 4 section](argus-decision-log.md#connectors-data-providers-and-segments): the segment is added next to the DR-first lock without replacing it. |
| 12 | [Decision log](argus-decision-log.md#locked), 2026-09-27 | "Preserve currency-separated net worth; combined conversion remains undefined." | The Oct 4 currency rule decides it: never convert, never blend. | **Resolved.** Recorded as Lucas's Oct 4 lock in the [decision log's Oct 4 section](argus-decision-log.md#currency), which replaces "undefined" with "never". |
| 13 | [Blueprint source](../research/2026-10-04-cuadrao-product-business-architecture-source.md), data model page | "Save exchange-rate value, source, effective time and rounding policy when conversion occurs. Preserve original-currency amounts alongside translated views." Allocations also mention "FX differences". | The currency rule: no conversion and no translated views. A rate only exists as the one implied by a person's real two-amount transaction. | The Blueprint is Lucas's own source and stays verbatim. The later Oct 4 rule wins; allocation FX differences are recorded as real settled amounts, not computed. |
| 14 | `docs/API_CONTRACT.md` (calculation market counterfactual, about L5745-5750) and `src/argus/agent_runtime/calculation_rows.py` (`dollar_rate`, L15, L168), `research_grounded.py`, `domain/market_data/assets.py` | An amount in another currency "is converted at Argus's own latest close for its pair with the dollar". | Currency rule (no conversion) and the market-data park. | Known violation in the frozen Argus web chat only (§B4.1): nothing new may build on it, it goes away with the chat retirement, and it isn't a TestFlight blocker. Not changed here. |
| 15 | Backend plans: `domain/planning/budgets.py` L78, `planning/model.py` L52, `planning/debt_model.py` L56, `recording/money_plan.py` L155 and L215 | Plans and transfers reject accounts in another currency ("Choose accounts with the same currency"). | Plans keep a fixed currency (matches), but the rule also lets an account in another currency pay toward a plan by recording both bank amounts. There's no two-amount path today. | Gap for engineering: a cross-currency contribution or transfer that stores both real amounts. Same for transfers between a DOP and a USD account. |
| 16 | iOS Home (`ios/ArgusFoundation/Cuadrao/CuadraoHomeOverview.swift` L8-9) | Home shows one currency at a time with a switcher; currencies are ordered alphabetically; the default is the first alphabetically. No primary-currency setting exists for Home. | Rule: one total per currency on separate lines, primary currency first, set at onboarding. Charts with a switcher already match. | For Lucas's design lane and the iOS owner. The profile's `currency_override` (`docs/DATA_MODEL.md` L191, L231) comes from the Argus home-country feature; whether it becomes the primary currency is an engineering call. |
| 17 | iOS design sample (`ios/ArgusFoundation/Cuadrao/CuadraoSampleData.swift` L14, `CuadraoDesignSample.swift` L70-71) | Sample accounts have no currency field; the sample screen sums every account and labels the total "DOP". | Every account keeps its own currency; no blended total. | Low risk if the sample stays in the design preview only. Give sample accounts a currency before any of it reaches a tester build. |

Checked and consistent with the rule: `financial_accounts.currency` is required (`20260928200000_financial_accounts_first_slice.sql` L17); account, activity, loop and forecast responses carry currency and return per-currency summaries (`recording/loop_schemas.py` `CurrencySummaryResponse`, `planning/responses.py` `ForecastCurrency`); the household projection keeps currency per account (`household/projection.py` L109-112); goals and budgets store a fixed currency; the iOS balance chart, insights and spending history filter to one currency; MVEE capture and refund rules already say never convert or assume a rate (MVEE about L390, L854, L867); `.agent/designs/cuadrao/DESIGN.md` L261 says "never add or convert them"; `docs/DATA_MODEL.md` L1946 derives currency-separated subtotals; §B2.4 says DOP and USD are never added together.

## Side-track checklist

These run beside the main streams. Each item names an owner where one is known. Docs that conflict with the plan are not edited until the conflict is resolved by a lock.

**Docs pass** (Maya; combines §A6 and §B8 where they agree)
- [ ] Archive the Argus-era specs both halves list: `docs/specs/private-alpha-next-*` (roadmap, decision memo, p2.1 audit, refine-to-version, chat header title, conversational-edit contract), `docs/specs/wave-1/`, `graded-interpretation-routing.md`, `evidence-aware-idea-loop.md`, `conversation-sharing.md`, and the pointer stubs `argus-active-roadmap.md`, `argus-grounded-finance-roadmap.md`, `argus-pivot-strategy.md`, `argus-answers-that-stay-true-roadmap.md`. Check inbound links first. Proposed as a separate docs-cleanup PR.
- [x] Remove the agent working notes in `docs/superpowers/` after checking inbound links. Done in the legacy agent-docs cleanup; one spec stays because a held design guide links it.
- [ ] Pending F5: archive anything only about the Argus web, guest or chat (Iris's rule, conflict row 22). Not part of #815.
- [ ] Hold until the guest flow and web chat retire: `docs/GUEST_PUBLIC_LAUNCH_SAFETY.md`, `docs/QA_CONVERSATIONAL_TRANSCRIPTS.md`, `docs/BREAKPOINTS.md`, `.agent/designs/argus/DESIGN.md`. Update domain references in `GUEST_PUBLIC_LAUNCH_SAFETY.md` during the domain move (conflict row 18).
- [ ] Rewrite for Cuadrao after the canon locks: `DOCUMENTATION_AUTHORITY.md`, `PRODUCT.md`, MVEE "Financial spaces" and §1.6 (canon rows 1-5, 9).
- [ ] New docs once locked: the space and ownership spec (§B2), a business spec or business MVEE section (§A7 contradiction 2), and `docs/CUADRAO_CODE_MAP.md` (§B1.3).
- [ ] Update during the domain move: `PRIVATE_LAUNCH_RUNBOOK.md` (email records, canary inbox), `docs/release-manifests/`, `ios/*.md` setup docs.
- [ ] Evidence size: consider moving dated `docs/reports/evidence/` files (about 4,950, 2,195 of them PNGs) out of the main tree while keeping links. Start from `docs/maintenance/docs-classification-inventory.md`.
- [ ] Execution board: no edits until #813, #808 and #790 land; #813 and #808 each conflict with #790 in the board (§B8).

**Founder locks to record** (Lucas; Maya records them in the decision log once confirmed)
- [ ] Space and membership model, roles matrix and business retention rule (§B2, conflict row 4).
- [ ] Revenue direction lifted from "deferred", prices still open (canon row 1).
- [ ] Cuadrao brand replacing the Argus visual identity (canon row 3).
- [ ] Business scope beyond the MVEE private Business space (canon row 4).
- [ ] Web freeze scope and the landing page (canon row 5).
- [ ] Gmail import: ship or not (Lucas's Oct 4 call keeps it open).
- [ ] Sole-owner deletion: block deletion until ownership is transferred or the business is closed, keeping records for DR tax retention (conflict row 21, §B9 question 3).
- [ ] F1 to F5 (§A7) and §B9 questions 1-5.

**Open engineering checks** (Yelena)
- [ ] Currency rule gaps (canon rows 14-17): the chat market counterfactual conversion goes with the chat retirement (nothing new builds on it), add a two-amount cross-currency contribution and transfer, Home lines per currency with the primary first, and a primary-currency setting at onboarding. Lucas's design lane owns the screens.
- [ ] Take the market-data provider keys (Alpaca, Kraken, BCRD and the others; BCRD fully parked) out of the live setup; keep the code. Follow the safe removal order in §B4.1, and take the asset check out of `/ops` readiness before the Alpaca keys go.

**Issues** (Yelena files the business issues after the space-model lock)
- [ ] File issues for space model steps 1-4, roles and permissions, audit log, entitlement service, business Inbox/Vault, thin app space and its release-check CI, the certified-provider bridge adapter, and the offline fiscal backend.
- [ ] Confirm closure or archiving for #640, #606, #644, #653, #623, #620, #696 (conflict row 13).

**Founder tracks** (Lucas)
- [ ] Entity (US, DR or both) and Apple organization enrollment before the first external build (F3, §B3.2 step 0).
- [ ] PSFE partner choice for the bridge (fiscal route correction).
- [ ] Plaid production access: Plaid's application and security review. A light partner step next to the US entity, not a blocker.
- [ ] DGII answer on a foreign, non-certified software provider (pending per the Blueprint).
- [ ] First business segment and who recruits about 10 pilot owners (F1).
- [ ] Argus web during the transition (F5).

---

## Part A: Product

**Author:** Iris (Product Lead). **Date:** October 4, 2026. **Status:** Draft for Lucas to lock, with Iris's later Oct 4 corrections applied in place. This is direction, not a list of shipped features. "Exists" means code is on integration `a8c37d3a` or in an open PR, usually behind a default-off switch. It does not mean the feature is live.

**Sources:** Lucas's Oct 4 GTM and Blueprint (now recorded in `docs/research/`, see §A7); PR #813 (Oct 4 roadmap lock); PRs #790, #808, #809, #810, #812, #781; the MVEE, the decision log and DOCUMENTATION_AUTHORITY on integration; open issues as of Oct 4. Outside facts are cited at the end of this part.


### A1. Vision

Cuadrao is **one product with three contexts: personal, household and business.** A person has one identity and joins spaces. Personal is private by default. Household shares only what members choose to share, and each member keeps their own finances. Business is a premium workspace with its own records, collaborators and workflows. A business role gives no access to anyone's personal or household space, and any combined view follows each space's permissions. All three share identity, money records, documents, capture, search and authorized actions, including AI actions. That shared base is one platform and **one codebase**, delivered on two tracks.

**Why business is the stronger thesis.** Consumer money trackers compete with free spreadsheets. Many Dominican small businesses run the owner's money and the business's money as one pile, spread across WhatsApp, paper receipts, bank exports and the accountant. E-invoicing makes this urgent now. Under Ley 32-23, the last group (small, micro and unclassified taxpayers) has until **November 15, 2026**, after DGII's six-month extension in Aviso 06-26 [1][2]. That deadline gets us in the door. People keep paying because their records stay organized and ready for the accountant. Consumer still ships first: it's the product already taking shape, it lets us learn from real use, and it can also earn revenue. The Oct 4 vision dropped the idea that consumer is a free loss leader.

### A2. Product map

Tags: **[exists]** code on integration (mostly default-off) · **[partial]** foundations or UI exist, connected journey open · **[new]** not built.

#### Consumer (personal + household): iPhone first, Android after

| Subproduct | State | Grounding |
| --- | --- | --- |
| Identity and access: email, Apple and Google sign-in, invite gate, 10 beta invites, founder group link, cuadrao.ai waitlist | partial | Backend #788/#794; Apple/Google #793/#795/#802 (off, gates in #800); iOS invites in #810 (open) |
| Spaces: Personal, Household, private Business, Custom; moving accounts between spaces | partial | MVEE §1.4: "space ownership and authorization still need production contracts" |
| Accounts, activity, balance checks | exists | Account first slice, local financial loop (#735, #745) |
| Plans: budgets, goals, debt, shared plans | exists/partial | Shared household planning #773 |
| Household: membership, grants, leaving, deletion with "Exmiembro" | exists/partial | #763, #766, #788, #799, #801; frozen balance is still open (#805) |
| Capture and receipts: camera, upload, drafts, review | partial | UI #785, durable drafts #776; extraction blocked by #778 |
| Imports and connectors: statement/CSV, Plaid, Gmail, Shortcuts, review queue | partial | #768–#772 as foundations, not enabled; no DR bank feeds. **Plaid is kept** (Lucas, Oct 4): the Plaid sandbox plus Faker-generated data is how we stress-test financial data, and real Plaid serves Dominicans in the US or with accounts abroad. Manual entry covers everyone else. Gmail import is still open for Lucas |
| Home, Search, Updates inbox, private push | partial | Designs #786; connected paths and push setup open (#813) |
| Ask Cuadrao (chat, then agentic actions) | partial/new | Argus runtime exists (explanations, calculations, research); Cuadrao chat design #785; agentic runtime not implemented (#813). Lucas starts chat work Oct 5 |
| Voice | new | Included in release 1 (founder, Oct 6, [decision log](argus-decision-log.md#october-6-2026-first-release-assistant-and-memory-and-voice-scope)); provider Grok voice; not built or wired |
| Profile, controls, AI consent, deletion, legal | partial | Release UI #790 (open), deletion #799/#801, Terms/Privacy draft #781 |
| Android | partial | Shell #730; accounts branch stopped |


**Consumer segments.** The locked first users are people living in the Dominican Republic (Sep 24). Lucas's Oct 4 addition names a second segment next to it: **Dominicans in the US or with accounts abroad**, served by real Plaid. Manual entry covers everyone else.

**Providers (Lucas, Oct 4).** Alpaca, Kraken, BCRD and the other market-data providers are **parked** for the pilot: their keys come out of the live setup and the code stays. Perplexity answers general finance questions in chat. **OpenRouter stays**, because receipt capture (document extraction) depends on it. Gmail import is still open for Lucas.

**Currency rule (Lucas, Oct 4).** Cuadrao never converts currencies, because converting would blur the numbers and make us responsible for their accuracy. Every account stays in its own currency, and there's never a blended total. Home shows one total per currency on separate lines, with the person's primary currency first (set at onboarding, changeable later). Charts and comparisons show one currency at a time, with a switcher when the person holds more than one. Plans keep a fixed currency; when an account in another currency pays toward a plan, the person records both amounts exactly as their bank charged them. Lucas's design lane owns the final screens.

#### Business (premium): thin in the app, full service on the web

Lucas agreed the **business space in the iPhone app stays thin**: capturing receipts and invoices, quick approvals, and checking where money stands. **The full service is the business web workspace**, so we don't build business twice. Keeping it out of the public App Store build uses Yelena's Option C (§B3.4). Everything below is **[new]** unless noted. Much of it reuses consumer foundations.

| Subproduct | Surface | Notes |
| --- | --- | --- |
| Business space, roles (owner, associate, accountant), invitations, leaving, ownership transfer | web + app (join/switch) | Starts from household grants; business records belong to the business (Yelena's model) |
| Personal ↔ business money moves ("paid a supplier with my personal card", "took cash from the register") | app + web | Two linked records, one in each space, never one shared record |
| Document inbox and vault: camera, upload, then WhatsApp Business forwarding | app (capture) + web (review) | Reuses capture and drafts [partial]. WhatsApp intake is planned, not built |
| Customers (light CRM) | web | Collections-focused, not a sales pipeline |
| Invoices without fiscal issuance: quotes, drafts, tracking invoices issued elsewhere, collections | web; app approves and checks | Commercial, fiscal and payment status kept separate |
| Payment matching and allocation (partial payments, fees) | web | Exact-money rules from consumer |
| Reports and accountant period package (CSV plus documents) | web | Deterministic numbers; AI only explains |
| e-CF fiscal backend and Cuadrao DGII MCP | web/backend | Blueprint goal. Live issuance is gated (§A3) |
| External assistants (API or MCP with scoped grants) | API | Later |
| Projects and time, tax preparation, tax filing | web | Optional or future; filing is separately gated |

### A3. Pillars ranked by leverage

There's no fixed order. Higher pillars unlock more of the ones below them. **No access** means no certified partner, regulator or bank is needed.

| # | Pillar | Access | Why it's high leverage | First shippable slice |
| --- | --- | --- | --- | --- |
| 1 | **Spaces and permissions foundation** | No access | Every other pillar depends on who owns a record. It's cheap to fix now while there's no real data | Yelena's ownership model locked; personal and household running on it; a business space with three role presets |
| 2 | **Consumer core loop to TestFlight** | No access | It's the product closest to done, and first-tester learning starts here | The connected candidate from #813: onboarding, accounts and activity, plans, household, sign-in, deletion |
| 3 | **Capture and document inbox** | No access for camera and upload; WhatsApp is 1-away (it needs a Meta business account, which is platform onboarding, not a regulator) | Shared by consumer and business, and the main time-saver for owners | Photo or upload → draft → review → record into the chosen space |
| 4 | **Personal ↔ business separation** | No access | It's the owner's real pain and the hardest test of the space model | Two money-move actions that create linked records in each space, plus the owner's combined view |
| 5 | **Business admin without fiscal issuance** | No access | The blueprint (p.13) says business can launch before e-CF. It works for owners who already invoice through DGII's free invoicing tool or another provider | Customer → invoice draft → PDF → mark paid / match → accountant export |
| 6 | **Ask Cuadrao (agentic)** | No access (needs AI consent and a model provider) | One interface across all contexts, using the same actions and permissions as the screens | Read-only answers over the user's own space, then a proposed draft record that needs confirmation |
| 7 | **Certified-provider integration** | 1-away: an agreement with a DGII-certified provider (PSFE), picked in Lucas's partner track | It's the path to a full business service and to issuing e-CF through Cuadrao (partner first, Lucas, Oct 4) | Integration built against the provider's sandbox; pilots then issue through Cuadrao once the connection is live |
| 8 | **Own fiscal tooling, prepared offline** ([E0 plan](cuadrao-business-e0-implementation-plan.md); no dependency on pillar 7) | No access to build; live use is gated | Lets us detach from the provider later | e-CF XML builder and validator against DGII's published technical specs, with no live submission |
| 9 | **Revenue capture** | Gated by company entity and store agreements, not regulators | Both products can earn revenue | Paywall and entitlements in sandbox; no prices (§A5) |
| 10 | **Live e-CF issuance** | Gated by each customer's DGII issuer certification, a compliant signing route (INDOTEL-authorized trust service), and the certified-provider connection (pillar 7) [3][4] | It's the regulatory way in | One pilot issuer issuing through the provider connection once it's live (§A7, F2) |
| 11 | **Own PSFE status** | Gated by DGII: our own RNC with software activity, e-CF issuer status, three certified customer issuers, and a full dossier [3] | Independence from providers | After at least three pilot issuers |
| 12 | Bank feeds, money movement, cards, tax filing | Gated by banks, aggregators, licenses and DGII channels | Long-term vision only | Not in this plan's first push |

**What can run in parallel:** 1 alongside 2 (separate owners); 3 and 4 once 1 is locked; 5 and 7 alongside each other on the web track, with 8 as a parallel track behind 7 while Lucas does the DGII paperwork; 6 starts with Lucas's chat work but its runtime design waits for its own scoped assignment (#813). Yelena sets the exact fiscal sequence against capture. **What must run in sequence:** 1 before any business data exists; 7 before 10; 10 before any compliance promise to a customer; 11 after 10.

> **Maya's note:** pillar numbers moved on Oct 4. Part B's "Iris pillar 7" (§B6, own fiscal backend row) refers to own fiscal tooling, now pillar 8.


### A4. Path to first real testers

#### Consumer TestFlight (personal + household)

**Minimum, from #813's release gates and open issues:** one connected candidate assembled and checked on the phone (#790 → #810 → #812, then #808 and #809); onboarding end to end (install → invite code → sign-in → first useful action); connected accounts, plans and household journeys including revoking access; sign-in gates (#800, plus #798 items 2–3); deletion that actually completes (#805, #806); #811 fixed before any fresh real-user database is built; #784 Mac verification of the real candidate; #778 if receipt extraction is in the build; AI consent enforced before chat or documents send data to a model; Privacy and Terms live at cuadrao.ai (#781); privacy manifests, permission strings and accessibility; reviewer access through the invite gate. External TestFlight builds go through Beta App Review and must follow the guidelines. Testers can't be charged or paid for access (guideline 2.2) [5].

**Success signals (proposed, thresholds set after the first baseline):** time to first useful record or plan; return in week 2; household invites accepted and activated; invites sent per person and their conversion; zero money-math or cross-space leak defects; crash-free sessions; deletions that complete; support load per tester.

#### Business TestFlight + concierge

**Shape:** about 10 owners from one segment, served hands-on. The earlier research lane produced a first batch of DR small-business prospects; the list stays off the public repo. Owners use the **thin business space in the iPhone app** (capture, quick approvals, where money stands) and the **business web workspace** for everything else. The first loop runs **without live e-CF**: owners keep issuing through their current route (for example DGII's free invoicing tool [6]), and Cuadrao records those invoices. Pilots issue through Cuadrao once the certified-provider connection is live.

**Keeping business out of the public App Store build** while it's in testing is required, because guideline 2.3.1(a) bars hidden or dormant features [5]. **Yelena chose Option C** (§B3.4): a compile-time business build that only the business TestFlight group gets, plus server-side authorization for what any client may do.


**Minimum:** pillar 1 locked; a business space with role presets; capture into the business space; the two money-move actions; customer → invoice draft → payment matched → accountant export on the web; a written support and responsibility boundary for the concierge service.

**Success signals:** time to first completed workflow; how often the accountant accepts the export without rework; exception and unmatched rates; owner time saved; repeat use per month; support minutes per owner; willingness to pay (a stated price or a commitment, no price set by us yet).

### A5. Founder tracks running in parallel

**Institutional access (historical October 4 live-route planning; not an E0 prerequisite).** (a) Each pilot customer's issuer certification and signing route [3][4]. (b) **Partner first:** an agreement with a DGII-certified provider (PSFE), which is the path to a full business service. Picking the provider and timing is F2. (c) The DGII answer on a foreign, non-certified software provider, which was still pending on Oct 4 per the blueprint. (d) Our own DGII backend and certified-provider (PSFE) status, in parallel while Lucas does the DGII paperwork. (e) Banks and aggregators for the long-term vision. (f) **Plaid production access:** Plaid's application and security review, next to the US entity. A light partner step, not a blocker.


**Company entity: US vs DR.** For consumer, I agree with Yelena: the choice mostly changes which payment accounts we can open, not what we build. Plaid production access (founder track (f)) sits next to the US entity. For business it can change more, and Lucas should know:
- **Stripe:** stripe.com/global doesn't list the Dominican Republic (checked Oct 4) [7]. A Stripe account for Cuadrao's own billing likely needs a US entity. Stripe also can't be the payment rail for DR business customers collecting from their own clients. The blueprint already says to choose that provider by DR merchant eligibility.
- **Lemon Squeezy:** acts as merchant of record and lists the Dominican Republic for bank payouts [8]. It's the most entity-flexible web option.
- **Apple and Google:** apps in "banking and financial services" "should be submitted by a legal entity" rather than an individual (5.1.1(ix)) [5]. Whether a money manager counts is App Review's call. Enrolling as an organization is the safe path either way.
- **DGII:** a Cuadrao PSFE needs an RNC whose activity covers software, plus e-CF issuer status [3]. DR business customers may also expect valid fiscal receipts (comprobantes) from us. Confirm with a DR accountant before assuming a US-only entity works for selling to businesses.

**Revenue tools** (no pricing decided; Yelena owns the engineering detail):

| Tool | What it enables | Fits |
| --- | --- | --- |
| RevenueCat | Subscriptions and entitlements across App Store and Play. It also connects Stripe Billing so web purchases unlock the app [9]. It's not a payment processor itself | Consumer in-app billing; one entitlement across app and web |
| Apple IAP / Google Play Billing | Required to unlock digital features in the app (3.1.1) [5]. Small Business Program commission is 15% [10] | Consumer and business premium inside the app |
| Stripe Billing | Web subscriptions, invoices, tax tooling; needs a supported-country entity [7] | Business web, web purchases (US entity) |
| Lemon Squeezy | Merchant of record: handles sales tax and VAT, pays out to DR banks [8] | Web purchases if we stay DR-only or want an MoR |

**Open point: business premium's subscription route.** The business space is also used inside the same iPhone app, so its subscription must follow Apple's rules. What the guidelines (updated June 8, 2026) allow [5]:
- **Sell it through in-app purchase too** (via RevenueCat), alongside web billing. This always works. Under 3.1.3(b), people can use subscriptions bought on our website inside the app, *provided they're also available as in-app purchases*.
- **Sell only on the web and have the app unlock it.** This only fits narrow exceptions. 3.1.3(c) covers apps sold *only* to organizations for their employees, and "consumer, single user, or family sales must use in-app purchase", which a one-owner business may not satisfy. 3.1.3(f) covers free stand-alone companion apps with no purchasing inside, which Cuadrao isn't, since consumer sells inside the app. Outside the US storefront, the app can't point users to web checkout. We can still email our own users about it outside the app.
- **US storefront:** the guideline text now lets US-storefront apps include buttons and links to web checkout [5]. That follows the Epic v. Apple contempt ruling. The Ninth Circuit affirmed it in Dec 2025 but sent the commission question back to the district court [11]. Apple proposed 15% / 10% / 5% link-out commissions in Aug 2026 [12]. No rate is set, and the Supreme Court granted review on June 30, 2026 [13], so this can change. Our main market is the DR storefront, where this exception doesn't apply. The text also doesn't obviously remove 3.1.3(b)'s "also available as IAP" condition. Confirm with App Review before relying on web-only.
- **My recommendation:** plan for in-app purchase plus web billing on one RevenueCat entitlement, with no web-checkout prompts in non-US storefronts. Prices are still Lucas's call.

**Brand and domain.** cuadrao.ai is the home: site, waitlist, `/privacy`, `/terms`, and the universal-link file the invite links need (#810). Details in §A6.

### A6. Side tracks

#### Brand and domain rewire

**Found in the repo:** the old app is **`arguschat.ai`** (Lucas typed "argustchat.ai"; Yelena confirmed `arguschat.ai`). The API is **`api.arguschat.ai`** (since Aug 13), with Render hosts `argus-app-suz5.onrender.com` and `argus-ohr5.onrender.com`. Email runs on a **second domain, `get-argus.com`**: `noreply@` (Supabase Auth and Resend), `support@` (Cloudflare routing), with `send.`, DKIM and DMARC records (PRIVATE_LAUNCH_RUNBOOK). `api.argus.app` appears only as placeholder problem-type URLs in API_CONTRACT.md. cuadrao.ai is already referenced about 27 times on integration.

**What the rewire must deliver:**
1. `arguschat.ai` → `cuadrao.ai` redirects, with a short notice for existing Argus accounts. Moving domains signs people out, so plan for it.
2. Supabase auth redirect and recovery URLs moved to cuadrao.ai.
3. A cuadrao.ai sending domain in Resend (SPF, DKIM, DMARC) and `support@cuadrao.ai`. #781 P5 needs that address.
4. An API host on the new brand, plus a matching iOS config.
5. The universal-link file on cuadrao.ai.
6. Legal: the live Argus terms (investing research) archived and the Cuadrao terms published (#781).
7. A decision on Argus web (see F5).

**Product criteria for rewire vs a new repo** (Yelena decides):
- Time to first testers on both tracks.
- Keeping the landed native, financial, household, sign-in and deletion work, including its tests and FK census.
- Whether existing Argus accounts and data carry over.
- How much the space model forces a schema rework.
- Renaming "Argus" in code is cosmetic. It alone isn't a reason to start fresh.

**What must be inherited:**
- Identity and accounts
- Exact-money services, revisions and idempotency
- Accounts, activity and plans
- Household grants and deletion
- Capture and drafts
- The ingestion contract
- Explanations and calculations from chat
- Feedback, the Resend adapter, PostHog
- Invites and the gate

**Retire as the product center:** backtest and quant research.

#### Docs pass candidates (Maya runs it and checks each one first)

- **Rewrite for Cuadrao:**
  - `DOCUMENTATION_AUTHORITY.md`: still titled Argus, dated Sep 29; says web is frozen and revenue deferred.
  - `PRODUCT.md`: Argus alpha overview.
  - The MVEE: Argus naming. Its Business is "manual records, no invoicing, employees or tax".
- **New:** a business spec (or a business MVEE section), Yelena's ownership model, and this master plan.
- **Shrink:** `argus-execution-board.md` is 3,107 lines. Keep the Oct 4 section current and move the dated pre-Oct sections to `docs/archive/`.
- **Archive candidates in `docs/specs/`:** `private-alpha-next-*` (roadmap, decision memo, p2.1 audit, refine-to-version, chat header title, conversational-edit contract), `wave-1/`, `graded-interpretation-routing.md`, `evidence-aware-idea-loop.md`, `conversation-sharing.md`, and the pointer stubs (`argus-active-roadmap`, `argus-grounded-finance-roadmap`, `argus-pivot-strategy`, `argus-answers-that-stay-true-roadmap`).
- **Agent working notes:** `docs/superpowers/` and the old subagent task reports (both removed in the legacy agent-docs cleanup, except one held spec).
- **Update during the domain move:** `PRIVATE_LAUNCH_RUNBOOK.md`, `docs/release-manifests/` (Argus web history).
- **Archive with the guest flow (pending F5):** `GUEST_PUBLIC_LAUNCH_SAFETY.md` and anything else only about the Argus web, guest or chat. Everything else follows Yelena's list (§B8).

#### Open issues

> **Maya's note:** Iris's later Oct 4 positions on issue timing are in the "Iris's position" column of [the conflict table](#where-the-two-halves-disagree). Where they differ from this list, the column is current.

**Un-defer for the first-tester push:**

| # | Title | Why |
| --- | --- | --- |
| 800 | Apple/Google sign-in ship gates | Blocks turning on either sign-in switch; covers 4.8 and 5.1.1(v) |
| 805 | Lane 6: frozen closed-line balance | Blocks deletion in any distributed build |
| 806 | Lane 6: real PostHog deletion adapter | Deletion can't finish without it |
| 811 | Explicit client grants on 17 tables | Must be fixed before any fresh real-user database |
| 784 | iOS commits without Mac verification | The real candidate needs a Mac pass |
| 778 | Document sources to Supabase Storage | Blocks receipt extraction, which is core to capture |
| 798 | Sign-in follow-ups (allowlist orphans, Apple name, Hide My Email) | Tester-visible onboarding UX |
| 807 | Lane 6 ops follow-ups | Only item 15 (who runs the deletion sweep; revisit no-cron) and alerting. The issue says to do this before an external beta |

PR #809 (pytest gate) isn't an issue but should land too.

**Keep deferred:**
- #797, #803, #804. Bring #797 back when the space-model migration starts, and fold #804's worker-count check into #807.
- #700, #696, #656, #653, #644, #640, #623, #620, #606 (Argus chat and backtest quality). Re-check against the chat runtime assignment.
- #671, #676, #684, #685, #686, #694, #690 (security on the live Argus web). These become moot if `arguschat.ai` moves to a redirect or holding page. **If Argus web stays live, un-defer #676, #684, #685 and #686**, because they affect live production (F5).
  **Maya's note:** #686 and #694 are placed as must-dos at main-promotion time, not TestFlight blockers (see [Roadmap at a glance](#roadmap-at-a-glance)).
- **Missing issues:** nothing tracks business yet. Filing pillar 1 and pillars 3–5 slices is Yelena's call.

### A7. Conflicts and open questions

**Where the blueprint is:** two Oct 4 documents, *Cuadrao consumer and business go to market vision* and *Cuadrao Product and Business Architecture*. Neither was in the repo on Oct 4: no e-CF, DGII or Ley 32-23 text appeared on any recent branch, including #813. They are now recorded as the [GTM source](../research/2026-10-04-cuadrao-gtm-vision-source.md) and the [Blueprint source](../research/2026-10-04-cuadrao-product-business-architecture-source.md).

**Contradictions, each with a proposed resolution:**
1. **e-CF route (October 4 live-route history; offline scope now follows the [E0 plan](cuadrao-business-e0-implementation-plan.md)).** My earlier advice was to connect to a certified provider first; the blueprint makes our **own fiscal backend and DGII MCP** the goal. *Resolution:* **partner first** (Lucas, Oct 4). A DGII-certified provider is the path to a full business service. Our own DGII backend and certified-provider status run in parallel while Lucas does the DGII paperwork. Pilots record invoices issued elsewhere, then issue through Cuadrao once the provider connection is live (F2).
2. **The MVEE limits Business to a private manual space** ("no employees, payroll, invoicing or tax") while the blueprint calls for a premium business product. *Resolution:* the MVEE limit becomes the consumer release's scope. Business gets its own spec. Record it in the decision log.
3. **"Web remake frozen"** (MVEE §1.6, DOCUMENTATION_AUTHORITY) vs the business web workspace. *Resolution:* the freeze covers the Argus consumer web. The business web workspace is a new, scoped surface, per Lucas's Oct 4 decision.
4. **"Revenue deferred; don't assign free and paid features"** vs "both products can earn revenue". *Resolution:* the direction has changed. Still no prices. Billing can be built in sandbox, and TestFlight can't charge.
5. **Business in TestFlight while consumer is public, in one codebase.** Guideline 2.3.1(a) bars hidden features. *Resolution:* Yelena's Option C (§B3.4): a compile-time business build for the business TestFlight group plus server-side authorization.
6. **"Entity mostly changes payment accounts."** That's true for consumer. For business it may also decide the PSFE route and whether we can issue valid fiscal receipts to DR customers (§A5). *Resolution:* treat it as an input to F3, not as settled.
7. **"Stripe for business invoicing."** Stripe can bill for Cuadrao's own subscription with a supported entity. It isn't the rail for DR owners collecting from their own clients. *Resolution:* pick customer payment links by DR merchant eligibility, later.
8. **Domain.** "argustchat.ai" is `arguschat.ai`, and `get-argus.com` (email) also has to move. Lucas didn't mention it. *Resolution:* include it in the rewire.
9. **Deletion and "Former member" were built for households only.** *Resolution:* a business case goes into Yelena's ownership model: when an associate leaves, business records stay with the business and their personal space survives.

**True founder calls (kept short):**
- **F1. First business segment.** The blueprint lists independent service providers, small professional-service firms, or owners already collecting documents on WhatsApp. Who recruits the ~10 owners?
- **F2. Which live provider route, and when?** The October 4 decision was partner first. Supplier discussions remain open; no partner choice is required for offline E0. Lucas picks the provider in his partner track and the timing of the connection; pilots record invoices issued elsewhere until it's live.
- **F3. Company entity:** US, DR, or both, and in what order. Is the Apple developer account enrolled as an organization? That's needed for 5.1.1(ix) safety.
- **F4. Business premium route:** in-app purchase plus web on one entitlement (my recommendation) vs web-only under an exception. Prices stay open.
- **F5. Argus web during the transition:** a redirect or holding page now (the security backlog becomes moot), or keep serving Argus (un-defer the four security issues).

---

#### Part A references (checked October 4, 2026)

- [1] DGII, Aviso 06-26 (6-month extension from May 15, 2026): https://dgii.gov.do/publicacionesOficiales/avisosInformativos/Documents/2026/06-26.pdf · DGII community confirming Nov 15, 2026: https://ayuda.dgii.gov.do/conversations/discusiones/facturacion-electronica/69fba8306d5db755fb24def4
- [2] Ley 32-23, art. 37 schedule: https://dgii.gov.do/transparencia/baseLegal/Documents/Leyes/Ley%2032-23.pdf
- [3] PSFE and issuer-certification requirements, as cited in Lucas's blueprint pp.14–15 (DGII CA4409, FI-GDF-016/017). Not independently re-fetched.
- [4] DGII CA5198 certificate custody and signing models, as cited in the blueprint p.16. Not re-fetched.
- [5] Apple App Review Guidelines (last updated June 8, 2026): 2.2, 2.3.1(a), 3.1.1, 3.1.1(a), 3.1.3(b)(c)(f), 4.8, 5.1.1(v)(ix): https://developer.apple.com/app-store/review/guidelines/
- [6] DGII Facturador Gratuito (about 150 invoices a month): https://dgii.gov.do/cicloContribuyente/facturacion/comprobantesFiscalesElectronicosE-CF/Paginas/facturador-gratuito.aspx · https://ayuda.dgii.gov.do/conversations/facturacin-electrnica/ca5391-cuntas-facturas-e-tems-por-factura-puedo-emitir-a-travs-del-facturador-gratuito/6a26b5432794307d12297f61
- [7] Stripe global availability (DR not listed): https://stripe.com/global
- [8] Lemon Squeezy supported countries (DR bank payouts): https://docs.lemonsqueezy.com/help/getting-started/supported-countries · merchant of record: https://www.lemonsqueezy.com/reporting/merchant-of-record
- [9] RevenueCat × Stripe Billing: https://www.revenuecat.com/docs/web/integrations/stripe
- [10] Apple Small Business Program: https://developer.apple.com/app-store/small-business-program/
- [11] Ninth Circuit, Epic v. Apple, No. 25-2935 (Dec 11, 2025): https://cdn.ca9.uscourts.gov/datastore/opinions/2025/12/11/25-2935.pdf
- [12] Apple's proposed link-out commissions (Aug 13, 2026): https://9to5mac.com/2026/08/13/apple-proposes-commissions-of-up-to-15-for-off-app-store-purchases-in-the-us/
- [13] Apple proffer citing certiorari granted June 30, 2026: https://9to5mac.com/wp-content/uploads/sites/6/2026/08/Epic_Games_Inc_v_Apple_Inc__candce-20-05640__1708.0.pdf · status summary: https://www.macobserver.com/news/apple-app-store-link-out-injunction-live-what-changed-developers/

---

## Part B: Engineering

**Author:** Yelena (engineering). **Drafted:** Sunday Oct 4, 2026, CT. **Status:** draft input for Maya's merged draft PR. Iris owns the product half. Nothing here authorizes a merge, deploy, migration, hosted flag, paid provider or new runtime work; [#813](https://github.com/lagarcess/argus/pull/813) and the [execution board](argus-execution-board.md) keep that authority.

**Baseline read for this draft (read-only):** integration `codex/private-alpha-next` at `a8c37d3a` (#801 merge, Oct 3 6:09 AM CT). `main` (production) is `a9286b21` (Sep 17), 102 commits behind. Open PRs: #813 (draft, `c2748bbd`), #790 (`53a4d67d`), #808 (`a1ebf4b4`), #809 (`ecd2bb57`), #810 (`329fd00d`, stacked on #790), #812 (`5753b5d7`, stacked on #810). Source docs: *Cuadrao consumer and business go to market vision* (Oct 4), called **GTM** below, and *Cuadrao Product and Business Architecture*, called **Blueprint** below. File paths are relative to the repo root on integration unless noted.

**Scope locked by Lucas in the room (Oct 4, 12:30 PM CT), applied throughout:**
1. Consumer iOS launches with **personal + household only**, after a short invite-only TestFlight under the existing invite rules, then goes public and iterates.
2. **Cuadrao for Business is a full web service first.**
3. The business space in the iOS app exists **only for the first business testers on TestFlight**, next to personal + household. Public consumers never see it.
4. The cuadrao.ai landing page promotes the whole suite and carries the waitlists.

Iris's proposal fits this and I've used it here: one codebase, with a thin business space in the app (receipt and invoice capture, quick approvals, where money stands) and the full service on web.

**Aligned with Iris's product half** (Part A). Her half owns the vision, the product map, the leverage ranking, the tester paths, the revenue-tool options and the F1-F5 founder calls; this half doesn't repeat them. Two inputs shape the business sections here:
- **Deadline:** the e-CF deadline for small, micro and unclassified taxpayers is **Nov 15, 2026**, after DGII's extension in Aviso 06-26 (Part A references [1][2]).
- **Fiscal route (historical Lucas correction, Oct 4 12:39 PM CT; offline scope follows the [E0 plan](cuadrao-business-e0-implementation-plan.md)):** partner first. Connecting to a DGII-certified provider (PSFE; the Blueprint names Alanube and Alegra as references) is the fastest route to a full business service. Our own DGII backend is the parallel track while Lucas handles the DGII paperwork. The pilot starts by tracking the invoices owners already issue, then issues through Cuadrao once the provider connection is live. Picking the provider is part of Lucas's partner track.

Labels: **[fact]** comes from the repo, GitHub or a cited source. **[proposed]** is my recommendation and needs a lock. **[estimate]** is a rough size, not a commitment.

---

### B1. Rewire or new repo

**Answer: rewire in place.** Keep `lagarcess/argus`, its Supabase project and its migration ledger. Build Cuadrao on the financial, household, auth and deletion foundations that landed in the last week. Freeze the Argus-era chat, backtest and guest surfaces behind their existing flags and retire them on a schedule, instead of porting or deleting them now. Rename what users and Apple see (app name, bundle id, domains, email sender) before external TestFlight. Rename internals (`argus` package, `ARGUS_*` env vars, `argus_private` schema) later, or never.

#### B1.1 Inventory and classification

| Area | What exists (fact) | Size | Call |
|---|---|---|---|
| **Native iOS** | `ios/ArgusFoundation` app, with 109 Swift files in `ios/ArgusFoundation/Cuadrao` (design graft #783/#785/#786/#792) and the `ios/Packages/ArgusSession` client (40 Swift files) that calls the financial, household, invite and auth APIs. Release UI in #790; invites wired in #810; launch perf in #812. Build 3423 was installed on the founder's iPhone 15 with sample data and auth off (#813). Needs Xcode 27 (#784). | ~37k LOC Swift | **Keep.** It's the consumer product. Rename the target and display name (§B3). |
| **Backend API** | FastAPI modular monolith, `src/argus/api/main.py`, 40+ routers in `src/argus/api/routers/` | ~40k LOC `api/` | **Keep.** Split the routers into Cuadrao and legacy groups (§B1.3). |
| **Financial domain** | `src/argus/domain/recording` (accounts, activities, money, assets: 5.4k), `planning` (budgets, goals, debts, claims: 3.9k), `calculations` (2.5k), `finance` | ~13k LOC | **Keep.** It's exact-money, revision-protected and idempotent, and it's the reuse the Blueprint asks for (Blueprint §07 "Reuse the current foundations"). Imports from Argus-era modules: one `canonical_hash` from `domain/backtest_admission.py`. |
| **Household** | `src/argus/domain/household` (6.7k LOC): membership, consent, account grants, shared plans, invites with keyed digests (#788/#794) | | **Keep.** Becomes the household space kind (§B2). |
| **Ingestion** | `src/argus/domain/ingestion` (10k LOC): Plaid, Gmail, documents (vision extraction via OpenRouter, `documents/extractor.py`), iOS Shortcuts tokens, reconcile/duplicates/matching | | **Salvage.** Documents, reconcile and Shortcuts carry straight into the business Inbox. Document bytes sit in Postgres bytea until #778. Plaid is US-only (`render.yaml` `PLAID_COUNTRY_CODES=US`) and has no Dominican coverage (`docs/specs/lanes/financial-ingestion-connectors.md` L18). Gmail uses the restricted `gmail.readonly` scope (`ingestion/gmail/config.py:23`), which needs Google verification plus an annual security assessment (connector doc L36, L155). |
| **Auth** | Supabase GoTrue, email/password, native Apple and Google behind default-off flags (#793/#795/#802), and an invite gate (#788/#794) | | **Keep.** #800 gates stand. |
| **Account deletion (Lane 6)** | `src/argus/domain/account_deletion`, migration `20261004090000_account_deletion.sql`, placeholders, revocations, a manual sweep (`scripts/ops/resume_account_deletions.py`) | 1.2k LOC + 1.1k SQL | **Salvage.** The household path is correct. Business needs a different leave/delete rule (§B2.5). |
| **Supabase migrations** | 111 files, 91 tables, ~18k LOC SQL. FK census with a drift test (`docs/specs/lanes/account-deletion-fk-census.md`, about 100 user-id columns, see #797) | | **Keep the ledger.** The production migration gate (`scripts/ops/production_migration_gate.py`, runbook L125-150) compares against it. Starting over loses that safety net. |
| **Test and eval harness** | `tests/` has 776 files and ~317k LOC, with a real-Postgres CI matrix (`guest-release-gates`). Integration CI: 10,216 backend, 605 real-DB and 2,207 web tests (GrokTeam handoff on #790). There's also `agent-runtime-regression.yml` and the canary/smoke workflows. | | **Keep.** The 152 test files on financial, household, ingestion, deletion and invite code are the strongest asset. The Argus chat/backtest eval suites stay until the chat is retired. |
| **Chat and calculations** | `src/argus/agent_runtime` (62k LOC): research/backtest-oriented interpreter, stages and tools. `domain/backtesting`, `market_data`, `research`, `workflows/` (Render Workflows backtest jobs) | ~75k LOC | **Salvage selectively.** Locked direction keeps the grounded chat and calculations (room lock, MVEE "Agentic ecosystem direction"). But the runtime touches financial data in only 4 files, and #813 says the agentic runtime lane is unimplemented and needs its own bounded assignment. Keep calculations and grounding safeguards. The Cuadrao financial agent is a new lane on top of them. |
| **Web** | Next.js 16 / React 19 (`web/`, ~140k LOC TS). Routes: `/chat`, `/r/[receiptId]` share pages, login/signup/recovery, privacy/terms, `/auth/native-captcha`. **No financial UI.** | | **Salvage the shell, drop the chat UI.** Keep Supabase SSR auth, recovery (the iOS app relies on web recovery, `ios/AUTH_SETUP.md` L111), i18n, captcha bridge and legal pages. Business web is new routes in this app [proposed]. |
| **Guest flow** | Anonymous users, guest workspaces, Turnstile, visitor allowances: about 102 files across src/web/tests/migrations. Open security issues #671/#684/#685/#686 | | **Drop from Cuadrao.** The invite gate replaces it. Keep the code until arguschat.ai web is retired, then remove it in one PR. |
| **Android** | `mobile/android` foundation, 3.3k LOC, last touched #739 (Sep 29), `applicationId ai.argus.foundation.sample` | | **Park.** No Android release is committed (GTM p.5). |
| **Docs** | 5,765 files, about 4,950 of them under `docs/reports/evidence` (2,195 PNGs) | | Maya's pass (§B8). |

> **Maya's note:** Lucas's Oct 4 calls (12:44 PM CT) keep Plaid (sandbox plus Faker data for stress tests; real Plaid for Dominicans in the US and accounts abroad) and park the market-data providers for the pilot (keys out of the live setup, code kept). See [Locked on October 4](#locked-on-october-4).

#### B1.2 Rewire cost compared with a new build [estimate]

| Work | Rewire | New repo |
|---|---|---|
| Surface rebrand (bundle id, name, domains, email, AASA) | S (3-5 eng-days) | Same |
| Space and membership model (§B2) | M-L (3-5 eng-weeks), expand/contract on existing tables | M (2-3 eng-weeks) for the schema, but only after re-creating everything below |
| Re-create financial, planning, household, invites, deletion with equal tests | 0 | L-XL (10-16 eng-weeks): ~30k LOC domain, ~13k LOC SQL, ~150 real-PG test files |
| Re-create the iOS client package and connected flows | 0 | M-L (4-6 eng-weeks) |
| Quarantine the Argus-era surfaces | S-M (1-2 eng-weeks) | 0 |
| CI, release gates, migration gate, runbook | 0 | M (2-3 eng-weeks) |

On these numbers a new repo costs about 4-5x more before the first tester sees anything. The main risk in rewiring is people working on the wrong code: 75k LOC of chat/backtest code and thousands of evidence files can mislead an onboarding team. §B1.3 covers it.

#### B1.3 Containing the Argus-era leftovers [proposed]

- **Naming.** Users and Apple see "Argus Sample" (`ios/Config/Info.plist`), `local.argus.foundation` (`ios/Config/Development.xcconfig`), `noreply@get-argus.com` (`src/argus/domain/resend_email.py:21-22`) and `support@get-argus.com` (`render.yaml`). Fix all of these before external TestFlight (§B3). Internal names (`argus` package, 277 distinct `ARGUS_*` names in code, 71 of them in `render.yaml`, the `argus_private` schema) are invisible to users. Renaming a schema is a destructive migration under the gate, so leave it.
- **Web chat product.** Freeze `arguschat.ai` chat: no new features, keep security fixes. The landing page moves to cuadrao.ai (§B3), and business web is built in `web/` under new routes. Retire `/chat` and the share pages when Lucas decides; the production share-pages setting already differs from integration (handoff on #790).
- **Guest flow.** Keep it off Cuadrao surfaces. Delete it with the chat retirement. Until then, #686's migration and env keys still ship with the next promotion.
- **Code layout.** Add a CODEOWNERS-style map, `docs/CUADRAO_CODE_MAP.md` (Maya), listing Cuadrao-owned and legacy-frozen paths. Group routers under `/api/v1` by owner. Don't move files yet; `scripts/check_modularity_budget.py` already guards size.

#### B1.4 What would flip this to a new repo

1. The space model forces re-keying most of the ~100 user-id columns **and** production holds no financial data worth keeping. Every financial/household migration (20260928 onward) is newer than production `main` `a9286b21`. I couldn't verify whether any were applied out of band. If a fresh schema in a new Supabase project became cheaper than expand/contract, it would flip. It also conflicts with MVEE §1.4 ("reuse ... the existing Supabase project on the current plan"), so that would be Lucas's call.
2. The agentic-runtime decision (#813) picks a framework that can't share the domain services in-process. That affects `agent_runtime/` only, not the repo.
3. Counsel says the "independent Cuadrao implementation" (GTM p.6) requires a clean-room repo for the fiscal stack. As written, the GTM line concerns third-party code licenses, not Argus code.
4. CI time or onboarding confusion measurably blocks delivery after the §B1.3 containment.

---

### B2. Space, ownership and membership model [proposed, for Lucas to lock]

#### B2.1 Today [fact]

- **Every record belongs to a person.** `financial_accounts.user_id` is "one fact" of ownership, ON DELETE CASCADE (`supabase/migrations/20260928200000_financial_accounts_first_slice.sql` L4-12). Records and revisions copy it for RLS. `space_id text not null default 'personal'` exists on accounts, but it's a free-text label: there's no spaces table and no reader of it outside the deletion copy (`20261004090000_account_deletion.sql` L1071).
- **Household = grants and claims, not ownership.** `household_account_grants` (`20261001090000_household_membership.sql` L71), plan bindings, participants and claims (`20261002000000_shared_household_planning.sql`). The migration states "ownership or space_id" never moves (L6).
- **Deletion is the only place ownership moves.** Lane 6 creates one placeholder per sharing scope (`scope_kind in ('household','group')`, deletion migration L256-270), as an `auth.users` row with an `exmiembro+...@cuadrao.invalid` email (#799 B2). Rows the household depends on move to the placeholder. Private rows are deleted.
- **Business: nothing.** MVEE "Financial spaces" (`docs/specs/argus-minimum-viable-ecosystem-experience.md` L410-425) allows a named *private* Business space with no employees, invoicing or tax. Space ownership "still need[s] production contracts".

#### B2.2 Definitions

| Term | Definition |
|---|---|
| **Person** | One identity (`auth.users` + `profiles`). Never shared, never owned by a space. |
| **Space** | A container that owns records. `kind ∈ {personal, household, business}`. Each person gets exactly one personal space at signup, with one member, not transferable. Household and business spaces have members. |
| **Membership** | (space, person, role, status, valid_from, valid_until, granted_by). Roles belong to the space kind. Household: admin/member (as today). Business: owner, admin, bookkeeper (capture/enter), approver, accountant (read/export, time-limited), viewer. A separate **billing admin** flag grants no financial content (Blueprint §02). |
| **Record ownership** | A *root aggregate* carries `owner_space_id`: account, plan, document/inbox item, customer, invoice, vault file, export. Child rows (activities, revisions, allocations, invoice lines) inherit it through their composite FK, the way records inherit `user_id` today. **No mechanical `space_id` on every table** (Lucas, room). |
| **Grant** | Permission for a space or member to *see or act on* a record owned elsewhere. It never moves ownership. Household sharing stays grant-based. |
| **Transfer link** | Two records, one in each space, each created under that space's own authorization, plus a `cross_space_link` row naming both. Never one record shared across spaces (Iris; Blueprint §02). |
| **Actor reference** | Who did it, stored on revisions, approvals and audit rows. In shared spaces it points at the **membership**, not straight at `auth.users`. A person's deletion therefore never meets an FK RESTRICT (it hit 4 of them in Lane 6: census blockers 3-5 and `apple_sign_in_credentials`). |
| **Identity retention rule** | For a member's own personal space, delete everything (Lane 6). In a household, keep the history under the household placeholder "Exmiembro" (Lane 6 as built). In a business, keep the membership row with role and a name snapshot for audit while statutory retention applies; after that, pseudonymize to "Former member (role)". The retention period is counsel's input. |

#### B2.3 Mapping today onto it, and the migration path [proposed]

Use expand/contract, with each step passing the production migration gate (runbook L139-145) and updating the FK census in the same PR (census drift test).

1. **Expand (additive).** Create `spaces` and `space_memberships`. Backfill one personal space per auth user. Backfill one household space per `households` row, reusing `households.id` as the space id so grants and bindings stay valid. Add a nullable `owner_space_id` on root aggregates (start with `financial_accounts`, then plans and documents) and backfill it from `user_id`. Dual-write.
2. **Switch readers.** RLS and service checks move to `is_space_member(owner_space_id, auth.uid(), permission)`, one aggregate at a time. Add a real-PG cross-space leakage test for each aggregate (Blueprint §06 "test ... cross-space leakage").
3. **Contract.** Set `owner_space_id` to NOT NULL. `user_id` becomes `created_by` (a person or actor reference, not ownership). Drop the free-text `space_id`. This step is `contract-replacing`, so it needs a maintenance window or expand/contract plan per the runbook.
4. **Business kind.** Add the business kind, roles and permissions last, with the business record types (customers, invoices, inbox, vault).

The cheapest time to do steps 1-3 is **before external TestFlight**, while hosted production has no financial rows. Consumer TestFlight only needs steps 1-2 for personal and household. Step 4 is web-first (scope locks 2 and 3).

#### B2.4 Test cases

| Case | Outcome under the model |
|---|---|
| **An associate leaves a business** | The membership ends (`valid_until=now`) and access is revoked immediately, including signed URLs and search. Business records stay with the business, and actor references keep the membership with a name snapshot. The associate's personal and household spaces aren't touched. Nothing moves. |
| **The owner transfers ownership** | An owner-role handover between two active members, with consent from the receiver and an audit row. Records don't move (the space owns them). Billing admin is a separate step. A business always keeps at least one owner, as households already require an admin (`households_check`, census blocker 2). |
| **An employee enters receipts** | The bookkeeper role grants `document.upload` and `activity.draft` on that business only. Drafts need an approver. They can't see accounts outside their grant, and they never see the owner's personal or household spaces. |
| **An accountant gets time-limited access** | The accountant role has `valid_until` and is scoped to read and export for a period. Every export is versioned (Blueprint Module 8). Access ends without anyone acting; revocation is immediate. |
| **A household member leaves** | Already built: grants revoked, consent lifecycle, plan responsibility carry (`20261002030000`-`20261002050000`). Personal space untouched. |
| **A person deletes their account while in a household and a business** | Personal space: deleted (Lane 6 data step). Household: Lane 6 placeholder as built. Business: membership ended, actor pseudonymized per the retention rule, business records untouched. **Gap:** Lane 6 has no business branch, and a sole business owner can't delete until ownership is transferred or the business is closed (proposed rule). |
| **The owner pays a business expense personally** | A personal-space expense (card) plus a business-space expense with "paid by owner" status and a payable to the owner. A `cross_space_link` joins them. "Pay me back" later creates a business payment and a personal income or refund, linked the same way. Both sides need the owner's authority in each space. |
| **Combined owner dashboard** | A read-only projection across the spaces the viewer belongs to, computed per space and then summed per currency. Linked pairs count once: a payable to the owner and the matching personal expense net out. Household totals use only granted records, as they do today. DOP and USD are never added together (Blueprint Module 7). |

#### B2.5 Who keeps each record when someone leaves

| Record type | Personal | Household | Business |
|---|---|---|---|
| Accounts, activities, revisions | The person (deleted with the account) | The owner keeps it. The household loses the grant. | The business |
| Plans, budgets, goals, debts | The person | Shared plan: the household, under the placeholder on deletion (Lane 6) | The business |
| Documents, receipts, vault files | The person | The uploader's space, plus grants | The business, including files a departed bookkeeper uploaded |
| Customers, invoices, e-CF records | n/a | n/a | The business, kept for the fiscal retention period (counsel) |
| Approvals, audit log | The person | The household (actor becomes "Exmiembro") | The business (actor becomes a membership snapshot, then pseudonymized) |
| Cross-space links | Each side stays with its own space. The link survives as long as both sides exist. | | |
| Chat history and memories | The person, never shared | The person | Agent actions on business records are logged in the business audit. The conversation stays with the person. |
| Connector credentials (Plaid, Gmail) | The person (revoked on deletion, Lane 6) | n/a | The business connection, revoked when its admin leaves unless re-authorized |

#### B2.6 Scope has to travel everywhere [fact and proposed]

- **Search:** `src/argus/domain/financial_search.py` and `postgres_search_reader.py` filter by user today. They need to filter by membership, and each result must show its space (MVEE L422-424).
- **Jobs:** the Render Workflows tasks (`workflows/main.py`) and extraction, imports and reminders need `space_id` and `actor_membership_id` in the payload, and they must recheck the grant when they run (Blueprint §06).
- **File storage:** #778's bucket paths become `space/<space_id>/...`, with downloads proxied through the same grant check.
- **AI retrieval:** memory vectors key on `payload->>'user_id'` (#797 item 4) and context packets key on the user. Agent retrieval has to be scoped to the selected space plus the person's permissions (Blueprint §06 "Read only records visible ... in the selected space").

#### B2.7 Thin business space in the app (scope lock 3) [proposed]

The model and API are shared. Business web is the full client. The app's business space uses only three surfaces, all on the same endpoints: (a) capture a receipt or invoice photo into the business Inbox, (b) quick approvals (approve or reject drafts assigned to the member), (c) a read-only view of where the money stands. Anything more than that belongs on web. The Swift code for these lives behind a compile-time condition (§B3.4).

---

### B3. Brand and domain cutover

#### B3.1 Current state [fact]

- **iOS:** the default bundle id is `local.argus.foundation`, and the display name is "Argus Sample". Build 3423 was signed as `local.cuadrao.design.47R3855RTJ` (#813). Team and app ID aren't approved (`ios/Config/Device.local.xcconfig.example`). I didn't find an App Store Connect record (unverified). Android: `ai.argus.foundation.sample`.
- **Domains:** `arguschat.ai` (web on Render, A records 216.24.57.x) and `api.arguschat.ai` (Render `argus-ohr5.onrender.com`, #694). `get-argus.com` carries email: the Resend sender, plus Cloudflare Email Routing MX for support@. `cuadrao.ai` is on Cloudflare NS (the same NS pair as the other two) with **no A or MX records**, and HTTPS didn't connect (DNS-over-HTTPS check, Oct 4 ~12:30 PM CT). The invite universal-link base is already `https://cuadrao.ai/invite#` (`src/argus/domain/household/invite_codes.py:36`, flag `CUADRAO_INVITE_UNIVERSAL_LINK_ENABLED`). The AASA file and Associated Domains aren't done (#810 out of scope).
- **Supabase Auth:** the hosted Site URL and redirect list aren't in the repo. `supabase/config.toml` lists only localhost. Apple and Google OAuth callbacks are `https://<ref>.supabase.co/auth/v1/callback` (`ios/AUTH_SETUP.md` L80, L89).
- **Render:** `ARGUS_APP_ORIGIN=https://arguschat.ai`, with CORS listing arguschat.ai and `NEXT_PUBLIC_ARGUS_API_URL=https://api.arguschat.ai/api/v1` (`render.yaml`).

#### B3.1a Old-domain inventory (repo, integration `a8c37d3a`, `git grep`)

**`get-argus.com` (email domain): 13 non-docs files plus 62 docs files.** Every runtime and config hit:

| Where | What |
|---|---|
| `src/argus/domain/resend_email.py:21-22` | Sender `noreply@get-argus.com`, header `Argus <noreply@get-argus.com>`. Used by approval email (`access_approval_email.py`) and feedback notification (`api/feedback_notification.py`). |
| `render.yaml:232`, `.github/private-alpha-release-profile.json:118`, `.env.example:83-84,455`, `web/.env.local.example:22-23` | `NEXT_PUBLIC_ARGUS_SUPPORT_EMAIL=support@get-argus.com` |
| `web/argus_display_contract/support_contact.json:2` | The single owner of the support address shown in web (#596) |
| `docs/PRIVATE_LAUNCH_RUNBOOK.md:666-673` | Supabase Auth SMTP sends as `noreply@get-argus.com` through Resend. Custom MAIL FROM is `send.get-argus.com` (`v=spf1 include:amazonses.com ~all`), DKIM is at `resend._domainkey.get-argus.com`, and DMARC is at `_dmarc.get-argus.com` (reports to support@, started at `p=none`). Cloudflare Email Routing handles inbound support@ (MX `route1-3.mx.cloudflare.net`, DNS-over-HTTPS read Oct 4). |
| `tests/test_private_alpha_canary_split.py` (5×), `web/e2e/support/private-alpha-canary-session.ts:42`, runbook L403 | The canary signs up `private-alpha-canary+<hex>@get-argus.com` and depends on that inbox routing. |
| Tests that pin the strings | `tests/test_access_approval_email.py`, `test_feedback_notification.py`, `test_access_request_postgres.py`, `tests/evals/test_prose_evidence.py`, `web/__tests__/legal-pages.test.tsx` |

**`arguschat.ai`: 14 non-docs files plus 40 docs files.**
- **Runtime/config:** `render.yaml` (CORS, `ARGUS_APP_ORIGIN`, `NEXT_PUBLIC_ARGUS_API_URL`), `.github/argus-env.sh`, `.github/private-alpha-release-profile.json`, `.env.example`, `src/argus/domain/access_approval_email.py`, `AGENTS.md`, and the Android `AuthEnvironmentTest.kt`.
- **Tests:** release-profile, environment, canary and perf tests (`tests/test_environment_scripts.py` ×9, `test_private_alpha_release_profile.py` ×5, ...).
- **Render hosts:** `argus-app-suz5.onrender.com` and `argus-ohr5.onrender.com` appear in 14 non-docs files. Render subdomains are disabled for the API (`renderSubdomainPolicy: disabled`).

**Not a cutover item:** `api.argus.app` appears only as problem-type URIs (`src/argus/api/dependencies.py` ×4, `app_setup.py`, `openapi_compat.py`, `docs/api/openapi.yaml`). These are contract identifiers that clients may match on, not resolved hosts. Leave them, or version them in a deliberate API-contract change.

#### B3.2 Sequence that doesn't break TestFlight [proposed]

0. **Choose the legal entity and Apple Developer team before the first external build** (US or DR, §B9). Sign in with Apple identifiers are tied to the team, and an app transfer forces a user migration (old tokens return `invalid_grant`, #803). An organization enrollment needs a D-U-N-S number (unverified for timing).
1. **Register the permanent bundle id** (e.g. `ai.cuadrao.app`) and create the App Store Connect record "Cuadrao". The bundle id can't be changed once the record exists. Enable the Sign in with Apple and Associated Domains capabilities. Set `PRODUCT_NAME` and the display name to Cuadrao. Set `CUADRAO_APPLE_BUNDLE_ID` in Render to match.
2. **DNS on cuadrao.ai** (Cloudflare): add `cuadrao.ai` and `www` as custom domains on the web service (landing page), and `api.cuadrao.ai` as a **second custom domain on the same `argus-api` service**. `api.arguschat.ai` stays up. Add both to CORS and the origin settings. Point `app.cuadrao.ai` at business web when it exists. The first TestFlight build should use `api.cuadrao.ai`, so testers never need re-pointing.
3. **AASA:** serve `https://cuadrao.ai/.well-known/apple-app-site-association` from the web app, `application/json`, no redirect, with `TEAMID.ai.cuadrao.app` and paths `/invite*`. Add `applinks:cuadrao.ai` to the entitlements. Then turn on `CUADRAO_INVITE_UNIVERSAL_LINK_ENABLED`, both server and client (#810).
4. **Email (get-argus.com → cuadrao.ai):**
   - In Resend, verify `cuadrao.ai` with the same record set get-argus.com uses: MAIL FROM `send.cuadrao.ai` with SPF `include:amazonses.com`, DKIM `resend._domainkey.cuadrao.ai`, and DMARC `_dmarc.cuadrao.ai` at `p=none`, tightened after a week of clean reports (runbook L666-673 pattern).
   - Add Cloudflare Email Routing MX on cuadrao.ai for `support@`, and set the DMARC report mailbox.
   - Then, in one PR, switch `resend_email.py:21-22`, `support_contact.json`, the `NEXT_PUBLIC_ARGUS_SUPPORT_EMAIL` values (render.yaml, release profile, env examples) and the pinned tests, and move the Supabase Auth SMTP sender in the dashboard.
   - Move the canary to `private-alpha-canary+...@cuadrao.ai` in the same PR.
   - **Keep get-argus.com's MX, SPF, DKIM and DMARC records for at least 90 days.** Existing users reply to it, and old auth emails have its links.
   - The Privacy/Terms support address (#781 P5) follows the switch.
5. **Supabase Auth:** add the cuadrao.ai Site URL and exact redirect URLs (recovery at `/auth/recovery`). **Don't add a Supabase custom domain before TestFlight**, because it changes the OAuth callback that Apple's Services ID and Google's web client are registered against. Add the cuadrao.ai origin to the Google web client and Apple Services ID.
6. **arguschat.ai:** after the landing page is live, 301 every web path to cuadrao.ai, keeping the path so `/r/<id>` share links still resolve. Keep `api.arguschat.ai` serving for at least one release cycle of old clients, then retire it.
7. **Env renames last:** read `CUADRAO_*` with an `ARGUS_*` fallback in one config module, flip Render, then remove the fallbacks. This doesn't block testers.

#### B3.3 Landing page with waitlists (scope lock 4) [proposed]

The waitlist today is only an external URL (`CUADRAO_WAITLIST_URL`, `invite_codes.py:206`). There's no capture backend. Proposed: a static cuadrao.ai landing page in `web/` that promotes the suite, plus one `waitlist_signups` table with interest flags (consumer iOS, business web, Android) and a Resend double opt-in. Size S. The privacy text (#781) has to cover it.

#### B3.4 Gating business in the iOS app [engineering decision]

**The rule:** Guideline 2.3.1(a) says "Don't include any hidden, dormant, or undocumented features in your app; your app's functionality should be clear to end users and App Review" (App Review Guidelines, last updated June 8, 2026, https://developer.apple.com/app-store/review/guidelines/, read Oct 4). Guideline 2.2 says TestFlight builds "should be intended for public distribution and should comply with the App Review Guidelines".

| Option | How it works | 2.3.1 risk | Cost |
|---|---|---|---|
| A. Server-side entitlement only | One binary. The business space shows when the account has a business membership or entitlement. | **High in App Store builds.** Business code ships dormant for every public user. It's defensible only if described in review notes with a reviewer business account, which contradicts "public consumers never see it". | Lowest build cost |
| B. Compile-time flag, separate TestFlight build | A `Business-Beta` build configuration sets the Swift condition `CUADRAO_BUSINESS`. App Store and consumer TestFlight builds compile the business code out. Business builds go only to a "Business pilots" TestFlight group. | **None for App Store builds**, because the code isn't in the binary. The beta build is honest: its testers see the feature. | Two build flavors on one App Store Connect record, plus a CI gate |
| **C. B + server-side authorization (chosen)** | B for what's in the binary. Server-side membership or entitlement for what any client may do. | None | B + nothing extra, since the server checks are needed anyway |

**Decision (engineering, firm): Option C.** Server-only gating (A) is ruled out for App Store builds. Use the same app record and bundle id, so Sign in with Apple, invites and AASA stay single. Add a release-check CI step that fails when an App Store candidate has `CUADRAO_BUSINESS` set, or has business strings in the binary. That's the same pattern as the #800 gate 3 "release force-off" and the existing `CUADRAO_DESIGN_PREVIEW` compile and Info key. Business pilots join through the existing invite gate. External TestFlight groups need Beta App Review per significant build (Guideline 2.2), so plan review time for business builds. When business reaches the public App Store app, the flag flips on in the App Store flavor. Business becomes a documented feature with review notes and a reviewer business account, and IAP rules apply (§B5).

The server is the real boundary in both flavors. A consumer build that called business endpoints would still get 403 without a business membership.

---

### B4. Platform: Resend, Render, Supabase

| | Set up today [fact] | Needed [proposed] |
|---|---|---|
| **Render** | `argus-api` (Python, `standard`, Virginia, deploys `main`, autodeploy off, Render subdomain disabled). `argus-app` (Next.js on Bun, `starter`). A Render Workflows service for backtest jobs (`workflows/main.py`, `ARGUS_BACKTEST_*_TASK`), not in `render.yaml`. No cron service. | cuadrao.ai custom domains (§B3). One more workflow task family for extraction, imports and reminders when business needs them. Verify `WEB_CONCURRENCY`, because the in-process rate limiters scale with workers (#671, #804, #807). A cron for the deletion sweep stays **off** (Lucas, Oct 3, 2:04 AM CT; runbook L804-810), so an operator runs `scripts/ops/scheduled_maintenance.py` daily while any run is in flight. |
| **Supabase** | One hosted project, which MVEE §1.4 locks ("a second Supabase project or paid upgrade is not a prerequisite"). Supabase Preview branches run in CI but were skipped or cancelled at the concurrent-branch limit (Priya's #799/#801 evals). CI is pinned to CLI 2.109.0 because newer images change default grants (#811). | Staging and prod: today TestFlight would run against production. A separate staging project contradicts MVEE §1.4 and would be **built fresh**, which #811 says leaves 17 tables open until fixed. So fix #811 before any new project, or use branches as staging (Lucas, §B9). |
| **Migration gate** | `scripts/ops/production_migration_gate.py`, with additive / contract-replacing / destructive classes and founder approval for destructive (runbook L139-145). Pending in prod: #674's migration first (#686), the #794 destructive `20261003150100` (backup plus founder OK), and all migrations from 20260928 onward. | Run the gate for the integration-to-main promotion that carries the TestFlight backend. Set `CUADRAO_INVITE_CODE_SECRET` before any household or beta flag. |
| **Storage** | No buckets in migrations. Document sources sit in `financial_document_extractions.source_bytes` bytea (#778). | A private bucket keyed by space (§B2.6). #778 must land before `ARGUS_DOCUMENT_EXTRACTION_ENABLED` anywhere. Business needs it on day one. |
| **Resend** | SMTP `smtp.resend.com`, sender `noreply@get-argus.com` (`resend_email.py`). Used for approval and feedback mail. | cuadrao.ai domain (§B3.2 step 4). Waitlist opt-in, invites and business notifications. |
| **Costs to watch** | OpenRouter models on six routes (`render.yaml` `ARGUS_*_MODEL`), Perplexity research, PostHog, and Render `standard` + `starter` + workflows | Vision extraction per document, storage growth, Supabase branch hours, WhatsApp per-conversation fees (if adopted), and Gmail's annual security assessment (if Gmail ships). Track cost per space (Blueprint §11). |

#### B4.1 Argus-era env vars and data providers: keep, drop, park [fact for "where read"; proposed for the call]

**Method.** Snapshot of integration `a8c37d3a`. I took every name declared in `render.yaml`, `.env.example`, `web/.env.local.example`, `.github/private-alpha-release-profile.json`, GitHub Actions `secrets.*`/`vars.*` and `ios/Config/*`, plus every name the code reads (`os.getenv`/`environ`, `process.env`, Info.plist keys, shell `$VAR`), then matched each against non-test code. **238 names classified: 102 Keep, 121 Drop, 12 Park (pilot), 3 Lucas decides.** The planned Grok voice row (below) has no env name yet and isn't counted. 62 of the Keep names are `ARGUS_*` (or `NEXT_PUBLIC_ARGUS_*`) and become `CUADRAO_*` under §B3.2 step 7, marked **→C** below. Not counted: about 70 local QA/e2e harness names (`ARGUS_GUEST_QA_*`, `ARGUS_QA_*`, Playwright ports, evidence dirs, `ARGUS_EVAL_*`, `ARGUS_RUN_LIVE_*`). They never touch Render or GitHub. `ARGUS_GUEST_QA_*` goes with the guest flow; rename the rest as the scripts get touched. Names only; no values were read or printed.

**Call key.** **Keep:** Cuadrao needs it. **Drop:** stop reading it and delete it. "(blocked)" means it can only go after the Argus chat/backtest/guest freeze-then-retire (§B1.3). **Park (pilot):** code stops reading it at runtime and it leaves Render, but the code path, docs and provider keys stay so it can come back. No revoke. **Lucas decides:** product call.

**DOP/USD conversion check (BCRD) [fact]: no Cuadrao code converts between currencies; the one conversion path is in the frozen Argus web chat (last bullet). BCRD is Park.** No code, env var or migration mentions BCRD or a rate feed (`git grep -i 'bcrd|banco central|exchange_rate|fx_rate'` over `src`, `web`, `ios`, `supabase/migrations` finds nothing outside `docs/archive`). Every money aggregate is grouped or filtered by currency, never translated:
- Net worth, assets, debts, cash and recorded spending on Home: one subtotal per currency, `src/argus/domain/recording/loop_reads.py` `home_response` (groups keyed on `facts.currency`, L160-170). Spending is filtered by currency (`recording/spending.py` `spending`, L22-34).
- Household positions: per-currency groups, `src/argus/domain/household/projection.py` `positions` (L105-125). Shared plan actuals match on currency, `household/planning_projection.py` `public` (L209).
- Mixed-currency inputs are refused, not converted: budgets `domain/planning/budgets.py` `validate` (L78, `currency_mismatch`), expectations `domain/planning/model.py` `cash_account` (L52), transfers/plans `domain/recording/money_plan.py` `plan` (L155).
- iOS says so to the user: "Choosing a currency does not convert or combine your balances" (`ios/ArgusFoundation/Cuadrao/CuadraoProfilePage.swift:88`).
- Chat: `src/argus/agent_runtime` and `src/argus/api/chat` import nothing from `recording`, `planning` or `household`, so chat can't write balances. The legacy web chat routes an exchange-rate question to Perplexity research as a one-off answer (`agent_runtime/interpreter/unsupported_admission.py:105`), and nothing persists it. The Cuadrao iOS chat is a local preview: the 8 `Cuadrao/CuadraoChat*.swift` files make no network calls, and `CanvasChatCalculation` is a hard-coded 3,000 × 6 demo.
- Backtest #623 (open, "converted once to dollars at the latest rate", waiting on BCRD) was the only planned conversion. It goes with the backtest retirement and nothing picks it up. The archived pivot doc also notes BCRD's site terms forbid commercial redistribution without authorization (`docs/archive/2026-09-26-argus-pivot-strategy.md:160`). Under Lucas's no-conversion rule (Oct 4), BCRD is a parked data source with no planned use. Perplexity never supplies a number that's saved into a balance.
- **Known violation:** `agent_runtime/calculation_rows.py` `dollar_rate` converts amounts at Argus's latest close against the dollar, in the frozen Argus web chat only (the market counterfactual row; `docs/API_CONTRACT.md` about L5748). It breaks Lucas's no-conversion rule. Nothing new may build on it, it goes away with the chat retirement, and it isn't a TestFlight blocker.


**Perplexity [fact]: Keep. It's wired into the backend, but not into the Cuadrao app yet.** `PERPLEXITY_API_KEY` is read via `domain/research/credentials.py` `perplexity_api_key()`. The research rail (`domain/research/perplexity_agent.py`, `ARGUS_RESEARCH_RAIL_ENABLED=true` on Render) serves the Argus web chat. Memory embeddings reuse the same key (`llm/memory_embedding.py:301`). The iOS Cuadrao chat doesn't call it yet; a separately assigned Cuadrao runtime slice must connect it for finance search. #813 records the delivery sequence, not that implementation.

**AI providers (Lucas, locked Oct 4, 2:20 PM CT, relayed by Yelena).** All three stay behind the server, and none of them writes saved balances.
- **OpenRouter: Keep**, for the chat models (GPT and Grok) and for vision extraction.
- **Grok voice: Keep (planned)**, the provider for the chat voice-call feature. It's new and not wired yet, so it has no env name today. Once built it gets a server-only key; the phone never holds it.
- **Perplexity: Keep**, for finance search. Cuadrao integration requires a separately assigned runtime slice; #813 records the delivery sequence.

| name | where read | provider | call | reason |
|---|---|---|---|---|
| **Supabase** | | | | |
| `SUPABASE_URL`, `SUPABASE_PROJECT_URL` (alias) | `domain/supabase_gateway.py`, `scripts/ops/*` | Supabase | Keep | Core DB/Auth. Collapse the alias in the config module. |
| `SUPABASE_SERVICE_ROLE_KEY` | `supabase_gateway.py`, `scripts/ops/*` | Supabase | Keep | Server writes, deletion sweep |
| `SUPABASE_ANON_KEY`, `SUPABASE_ANON_PUBLIC_KEY` (alias) | `supabase_gateway.py`, `mobile/android/app/build.gradle.kts` | Supabase | Keep | Public client key |
| `SUPABASE_JWT_SECRET` | `api/account_deletion_auth.py` | Supabase | Keep | Deletion re-auth |
| `DATABASE_URL` | `scripts/ops/resume_account_deletions.py`, `force_account_deletion_step.py` | Supabase | Keep | Deletion sweep (manual, §B4) |
| `ARGUS_PRODUCTION_DATABASE_URL`, `ARGUS_PRODUCTION_DATABASE_SSL_ROOT_CERT` | `scripts/ops/production_migration_gate.py` | Supabase | Keep →C | Migration gate |
| `SUPABASE_POSTGRES_DIRECT_URL`, `_SESSION_POOLER_URL`, `_TRANSACTION_POOLER_URL` | `.github/qa.sh`, `scripts/qa/*`, `scripts/benchmarks/run_turn_latency.py` | Supabase | Keep | QA and ops |
| `SUPABASE_ACCESS_TOKEN`, `SUPABASE_PROJECT_REF` | `.env.example` only; the Supabase CLI reads them itself | Supabase | Keep | CLI |
| `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` | `web/lib/supabase-client.ts`, `supabase-server.ts` | Supabase | Keep | Web auth, recovery, business web |
| `ARGUS_SUPABASE_URL`, `ARGUS_SUPABASE_ANON_KEY` | `ios/Config/Info.plist`, `ios/ArgusFoundation/Auth/NativeAuthConfiguration.swift` | Supabase | Keep →C | iOS auth |
| **Render: platform and runtime** | | | | |
| `RENDER_API_KEY` | `.github/canary-*.sh`, `scripts/benchmarks/*`; on `argus-api` only `api/chat/backtest_jobs.py` | Render | Keep | Keep the GitHub secret for the canary's deploy lookup. Remove it from the `argus-api` service when backtest dispatch goes (blocked). |
| `POETRY_VERSION` | Render build (`render.yaml`) | Render | Keep | Build |
| `ARGUS_APP_ORIGIN`, `CUADRAO_CORS_ALLOW_ORIGINS` | `api/routers/ops.py`, `web/app/api/auth/recovery/route.ts`, `web/app/r/[receiptId]/page.tsx`; `api/app_setup.py` | Render | Keep →C | Values move to cuadrao.ai (§B3.2) |
| `ARGUS_TRUSTED_CLIENT_IP_HEADER` | `api/client_ip.py` | Render | Keep →C | Rate limits |
| `CUADRAO_OPS_TOKEN` | `api/routers/ops.py`, canary scripts, GitHub secret | Render | Keep →C | Ops endpoints |
| `CUADRAO_PERSISTENCE_MODE`, `ARGUS_DEV_MEMORY_FALLBACK` | `api/state.py`, `api/dependencies.py`, `api/client_ip.py` | Render | Keep →C | Storage mode; dev fallback must stay off in prod |
| `ARGUS_DEV_ENDPOINTS_ENABLED`, `CUADRAO_MOCK_AUTH`, `NEXT_PUBLIC_MOCK_AUTH`, `NEXT_PUBLIC_E2E_ALLOW_MOCK_SIGNUP`, `MOCK_USER_EMAIL`, `MOCK_USER_PASSWORD` | `api/routers/dev.py`, `api/dependencies.py`, `web/app/page.tsx`, `domain/supabase_gateway.py` | none (dev) | Keep (the 2 `ARGUS_*` →C) | Local and test only. #800-style release gate keeps them off. |
| `APP_ENV` | `observability/envelope.py`, `llm/openrouter_key_policy.py`, `scripts/documents/benchmark.py` | Render | Keep | Environment name |
| `ARGUS_APP_ENV`, `ARGUS_ENV`, `ENVIRONMENT` | `observability/envelope.py`, `api/dependencies.py`, `observability/analytics_deletion.py` | Render | Drop | Three aliases of `APP_ENV`; not set on Render. Not blocked. |
| `[removed obsolete setting]` | Set on `argus-app`; no reader | Render | Drop | Set but unused |
| `NODE_ENV`, `NEXT_DEV_ALLOWED_ORIGINS`, `NEXT_DIST_DIR` | `web/next.config.ts`, `web/proxy.ts` | Next.js | Keep | Framework |
| **Render Workflows: backtest jobs** | | | | |
| `ARGUS_BACKTEST_JOBS_{DISPATCH,SHADOW}_ENABLED`, `ARGUS_BACKTEST_JOBS_{GLOBAL,USER}_{QUEUED,RUNNING}_LIMIT` (4), `ARGUS_BACKTEST_WORKFLOW_EXECUTION_ENABLED`, `ARGUS_BACKTEST_WORKFLOW_TASK`, `ARGUS_BACKTEST_REAL_WORKFLOW_TASK`, `ARGUS_BACKTEST_WORKFLOW_TIMEOUT_SECONDS` (10) | `api/chat/backtest_jobs.py`, `domain/backtest_admission.py`, `workflows/main.py` | Render Workflows | Retire old tasks only after reuse audit | Backtest-specific settings; preserve Render Workflows for assigned Cuadrao job families. |
| `ARGUS_RENDER_WORKFLOW_PROOF_{TASK,POLL_SECONDS,TIMEOUT_SECONDS}`, `ARGUS_RENDER_WORKFLOW_RELEASE_{COMMIT,VERSION_ID}`, `ARGUS_WORKFLOW_PROOF_{PLAN,USER_ID}`, `ARGUS_WORKFLOW_DATABASE_URL`, `RENDER_TASK_RUN_ID`, `RENDER_USE_LOCAL_DEV`, `RENDER_LOCAL_DEV_URL` (11) | `workflows/trigger_proof.py`, `workflows/proof.py`, `workflows/main.py`, `api/chat/backtest_jobs.py`, release profile, GitHub secret `ARGUS_WORKFLOW_DATABASE_URL` | Render Workflows | Drop (blocked) | Backtest proof harness. Re-create the pattern as `CUADRAO_*` with the extraction/import task family (§B4). |
| `ARGUS_STALE_JOBS_SUPABASE_URL`, `_SERVICE_ROLE_KEY` | `scripts/ops/stale_backtest_jobs.py`, `.github/stale-backtest-jobs.sh` | Supabase | Drop (blocked) | Backtest job reaper |
| `ARGUS_BENCHMARK_LIVE_PROVIDER`, `ARGUS_ENABLE_EXECUTION_REALISM` | `scripts/benchmarks/backtest_infra_benchmark.py`, `domain/backtesting/config.py` | none | Drop (blocked) | Backtests |
| **Resend** | | | | |
| `CUADRAO_APPROVAL_EMAIL_SMTP_PASSWORD` | `domain/resend_email.py` | Resend | Keep →C | The Resend SMTP key. Rename it to a general email key, since invites, waitlist and business mail use it too. |
| `NEXT_PUBLIC_ARGUS_SUPPORT_EMAIL` | `web/lib/support-email.ts` | Resend/Cloudflare | Keep →C | Value moves to `support@cuadrao.ai` (§B3.2 step 4) |
| **PostHog** | | | | |
| `POSTHOG_PROJECT_TOKEN`, `POSTHOG_HOST`, `POSTHOG_REGION`, `CUADRAO_POSTHOG_TIMEOUT_SECONDS` | `observability/envelope.py` | PostHog | Keep (timeout →C) | Backend analytics |
| `NEXT_PUBLIC_POSTHOG_KEY` | Secret on `argus-app`; **no reader** (web has no PostHog SDK) | PostHog | Drop | Set but unused. Delete from Render; don't revoke (same project as the backend). Re-add when the landing page wires analytics. |
| **Apple** | | | | |
| `CUADRAO_APPLE_TEAM_ID`, `_SIGN_IN_KEY_ID`, `_SIGN_IN_PRIVATE_KEY`, `_BUNDLE_ID` | `domain/apple_sign_in/config.py` | Apple | Keep →C | Sign in with Apple; `_BUNDLE_ID` value changes at §B3.2 step 1 |
| `CUADRAO_APPLE_REVOCATION_CAPTURE_ENABLED` | `api/apple_sign_in.py` | Apple | Keep →C | Token revocation on delete (5.1.1(v)) |
| `ARGUS_APPLE_SIGN_IN_ENABLED` | `ios/.../Auth/NativeProviderSignIn.swift`, Info.plist | Apple | Keep →C | iOS flag |
| **Google Sign-In** | | | | |
| `ARGUS_GOOGLE_SIGN_IN_ENABLED`, `GOOGLE_SIGN_IN_IOS_CLIENT_ID`, `GOOGLE_SIGN_IN_IOS_URL_SCHEME`, `GOOGLE_SIGN_IN_WEB_CLIENT_ID` | `NativeProviderSignIn.swift`, Info.plist, xcconfig | Google | Keep (flag →C) | iOS Google sign-in |
| **Cloudflare Turnstile** | | | | |
| `NEXT_PUBLIC_ARGUS_TURNSTILE_SITE_KEY`, `NEXT_PUBLIC_ARGUS_LOCAL_QA_CAPTCHA_TOKEN` | `web/lib/guest-captcha.ts` | Cloudflare | Keep →C | **Not guest-only.** iOS sign-up captcha goes `web/app/auth/native-captcha` → `lib/native-captcha.ts` → `guest-captcha.ts`. Rename the file before the guest deletion PR. |
| `ARGUS_CAPTCHA_URL` | `NativeAuthConfiguration.swift`, Info.plist | Cloudflare | Keep →C | iOS captcha page URL |
| **Perplexity** | | | | |
| `PERPLEXITY_API_KEY` | `domain/research/credentials.py`, `research/search/selection.py`, `llm/memory_embedding.py` | Perplexity | Keep | Finance search (Lucas's Oct 4 lock); Cuadrao runtime integration remains separately assigned (see above) |
| `ARGUS_RESEARCH_RAIL_ENABLED`, `ARGUS_RESEARCH_BACKGROUND_DEADLINE_SECONDS` | `domain/research/config.py` | Perplexity | Keep →C | Research rail |
| `ARGUS_REGISTERED_DAILY_RESEARCH_CEILING`, `ARGUS_RESEARCH_GLOBAL_DAILY_CEILING` | `domain/usage_limits.py` | Perplexity | Keep →C | Cost caps |
| `ARGUS_GROUNDED_DISCOVERY_ENABLED`, `ARGUS_DISCOVERY_{SEARCH_PROVIDER,SEARCH_TIMEOUT_SECONDS,MAX_CANDIDATES,HOURLY_LIMIT,DAILY_LIMIT,GLOBAL_DAILY_CEILING,OPENROUTER_SEARCH_MODEL}` (8) | `domain/research/search/config.py`, `selection.py`, `domain/usage_limits.py` | Perplexity/OpenRouter | Drop (blocked) | Asset discovery for backtests ("5-symbol run cap") |
| `NEXT_PUBLIC_RESEARCH_RAIL_ENABLED` | `web/lib/private-alpha-flags.ts` | none | Drop (blocked) | Web chat UI |
| **OpenRouter** | | | | |
| `CUADRAO_PROD_OPENROUTER_API_KEY`, `OPENROUTER_API_KEY` (dev) | `llm/openrouter_key_policy.py` | OpenRouter | Keep (prod →C) | Locked Keep by Lucas (Oct 4, 2:20 PM CT) for the chat models (GPT and Grok) and vision extraction. Document vision extraction runs on it (`ingestion/documents/extractor.py:222`). |
| `ARGUS_VISION_MODEL`, `CUADRAO_OPENROUTER_DOCUMENT_EXTRACTION_TIMEOUT_SECONDS` | `llm/openrouter_model_env.py`, `llm/openrouter.py:244` (name built from the task) | OpenRouter | Keep →C | Business Inbox extraction. **`ARGUS_VISION_MODEL` isn't in `render.yaml`**, so extraction fails with `missing_vision_model` (`extractor.py:224`) until it's set. |
| `ARGUS_DOCUMENT_EXTRACTION_ENABLED` | `ingestion/documents/config.py` | own | Keep →C | Stays off until #778 |
| `ARGUS_DOCUMENT_EXTRACTION_MAX_BYTES`, `_MAX_PAGES` | `.env.example` only; no reader | none | Drop | Documented but unread |
| `ARGUS_{CHAT,CONTEXT,READOUT,STRUCTURED,UTILITY}_MODEL` + `_FALLBACK_MODEL` (10), `ARGUS_{CAPABILITY,STRUCTURED}_REASONING_EFFORT` (2) | `llm/openrouter_model_env.py`, `llm/openrouter.py` | OpenRouter | Drop (blocked) | Argus chat tiers. If the separately assigned Cuadrao runtime adopts the tier scheme, rename instead. The provider itself stays: Lucas's Oct 4 lock keeps OpenRouter for the Cuadrao chat models (GPT and Grok). |
| `ARGUS_OPENROUTER_<TASK>_TIMEOUT_SECONDS` for 13 chat tasks (`INTERPRETATION_REPAIR`, `ASSET_MENTION_PREFLIGHT`, `FIELD_FIDELITY`, `CAPABILITY_CONFLICT`, `CLARIFICATION`, `RESULT_SUMMARY`, `NAME_SUGGESTION`, `DISCOVERY_{EXTRACTION,VOICING,MODEL_KNOWLEDGE}`, `KNOWLEDGE_{ROUTE,VOICING}`, `MEMORY_SENSITIVITY`), plus `INTERPRETATION` and `CHAT_COMPOSER` (no such task) | `llm/openrouter.py:244`, `llm/openrouter_tasks.py` | OpenRouter | Drop (13 blocked; 2 dead now) | Chat stages |
| `CUADRAO_GUEST_ACCESS_OPENROUTER_API_KEY` | `llm/openrouter_key_policy.py` | OpenRouter | Drop (blocked) | Guest flow. Revoke the key at OpenRouter after the guest deletion. |
| **Grok voice (planned)** | | | | |
| Key name TBD (not counted) | Not wired yet; no code reads it | Grok voice | Keep (planned) | Chat voice-call feature (Lucas's Oct 4 lock). Server-only key once built; the phone never holds it. |
| **Alpaca** | | | | |
| `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, `ALPACA_PAPER_TRADING` | `context/providers.py`, `domain/market_data/{provider,assets,capabilities}.py` | Alpaca | Park (pilot) | Market data. Off Render; keys kept. |
| `ARGUS_MARKET_DATA_PROVIDER_MODE`, `MARKET_DATA_CACHE_TTL`, `ENABLE_MARKET_DATA_CACHE`, `ARGUS_ASSET_{PROVIDER_MODE,FIXTURE_PATH,UNIVERSE_LOADER_TIMEOUT_SECONDS}`, `ARGUS_READINESS_ASSET_TIMEOUT_SECONDS` | `domain/market_data/*`, `api/routers/ops.py:73`, `workflows/proof.py` | Alpaca/Kraken | Park (pilot) | **`/ops` readiness probes the asset universe**, so take it out of readiness before removing the Alpaca keys |
| **Kraken** (no env names) | `domain/market_data/provider.py`, `engine_launch/adapter.py` (`alpaca_crypto_with_kraken_fallback`) | Kraken (keyless public OHLC) | Park (pilot) | Nothing on Render, nothing to revoke |
| **FRED** | | | | |
| `FRED_API_KEY`, `ARGUS_FRED_CONTEXT_SERIES` | `context/providers.py` | FRED | Park (pilot) | Rate/macro context. **Read, but not in `render.yaml`.** |
| **BCRD** (no env names) | Nowhere in code; `docs/archive` only | BCRD | Park (pilot) | A parked data source with no planned use. Cuadrao never converts currencies (Lucas, Oct 4), so BCRD has no rate-source role. |
| **Plaid** | | | | |
| `PLAID_CLIENT_ID`, `PLAID_SECRET`, `PLAID_ENV`, `PLAID_COUNTRY_CODES`, `PLAID_WEBHOOK_URL`, `PLAID_CREDENTIALS_INJECTED` | `domain/ingestion/plaid/config.py`, `scripts/ingestion/plaid_*` | Plaid | Keep | Kept per Lucas (Oct 4): the Plaid sandbox with Faker data for stress tests; real Plaid for Dominicans in the US or with accounts abroad. US only, no DR coverage (§B1.1). Production access needs Plaid's review on Lucas's founder track. |
| **Gmail import** | | | | |
| `GOOGLE_OAUTH_CLIENT_ID`, `_CLIENT_SECRET`, `_REDIRECT_URI` | `domain/ingestion/gmail/config.py`, `api/gmail.py` | Google | Lucas decides | Restricted scope plus an annual security assessment (§B1.1) |
| **Cuadrao app flags and secrets (own)** | | | | |
| `ARGUS_FINANCIAL_ACCOUNTS_ENABLED`, `CUADRAO_HOUSEHOLDS_ENABLED`, `CUADRAO_BETA_INVITES_ENABLED`, `CUADRAO_BETA_INVITE_GATE_ENABLED`, `CUADRAO_INVITE_CODE_SECRET`, `CUADRAO_INVITE_CODE_SECRET_PREVIOUS`, `CUADRAO_INVITE_FOUNDER_USER_ID`, `CUADRAO_INVITE_UNIVERSAL_LINK_ENABLED`, `CUADRAO_TESTFLIGHT_PUBLIC_URL`, `CUADRAO_WAITLIST_URL`, `CUADRAO_ACCOUNT_DELETION_ENABLED`, `CUADRAO_PUBLIC_ACCOUNT_ACCESS_ENABLED`, `ARGUS_INGESTION_ENABLED` | `api/financial_accounts.py`, `api/households.py`, `api/routers/households.py`, `domain/household/invite_codes.py`, `api/routers/account.py`, `api/guest_access.py`, `api/ingestion.py` | own | Keep →C | The consumer product |
| `ARGUS_INGESTION_SECRET_KEY` | `domain/ingestion/secrets.py:24` (sealing for Plaid, Gmail **and Apple refresh tokens**, `domain/apple_sign_in/credentials.py:29`) | own | Keep →C | **Not ingestion-only.** Keep it even if Plaid and Gmail are dropped. Rotating it leaves stored Apple tokens unrevocable. |
| `ARGUS_API_URL`, `ARGUS_WEB_URL`, `ARGUS_AUTH_ENABLED`, `ARGUS_LOCAL_BUNDLE_IDENTIFIER`, `CUADRAO_DESIGN_PREVIEW` | `ios/Config/*.xcconfig`, Info.plist, `NativeAuthConfiguration.swift`, `Cuadrao/CuadraoDesignPreview.swift` | own (iOS) | Keep (4 →C) | iOS build settings |
| `NEXT_PUBLIC_ARGUS_API_URL`, `NEXT_PUBLIC_ENABLE_SPANISH` | `web/lib/argus-api-transport.ts`, `web/lib/guest-captcha.ts`, `web/lib/language-features.ts` | own (web) | Keep (API URL →C) | Web shell |
| **Argus chat, share pages and guest (own)** | | | | |
| `CUADRAO_CHECKPOINTER_MODE`, `ARGUS_CONTEXT_PACKETS_ENABLED`, `ARGUS_CONTEXT_PACKET_BUDGET_SECONDS`, `ARGUS_RUNTIME_EVENT_{TIMEOUT,KEEPALIVE}_SECONDS`, `CUADRAO_RUNTIME_STREAM_WORKER(S)` (2), `CUADRAO_TURN_DEADLINE_SECONDS`, `CUADRAO_TURN_CALL_ALLOWANCE`, `CUADRAO_REGISTERED_DAILY_TURN_CEILING`, `ARGUS_IN_PLACE_CARD_EDITS_ENABLED`, `ARGUS_ENABLE_ARTIFACT_NAMING_IN_TESTS` (12) | `api/chat/*`, `api/state.py`, `agent_runtime/turn_execution.py`, `api/routers/agent.py`, `domain/edit_contract_config.py`, `domain/usage_limits.py` | own | Reconcile before retirement | Old web-chat configuration (`web/lib/chat-runtime-timeout.ts` too). Preserve settings needed by the reused orchestration/checkpoint owner; #826 decides the migration. |
| `CUADRAO_EVIDENCE_RECEIPT_SHARING_ENABLED`, `NEXT_PUBLIC_EVIDENCE_RECEIPT_SHARING_ENABLED`, `NEXT_PUBLIC_OMNISEARCH_ENABLED` | `api/public_excerpts.py`, `web/lib/private-alpha-flags.ts` | own | Drop (blocked) | `/r/` share pages, chat omnisearch |
| `CUADRAO_GUEST_ACCESS_ENABLED`, `NEXT_PUBLIC_GUEST_ACCESS_ENABLED`, `CUADRAO_GUEST_SESSION_DAILY_TURN_CEILING`, `CUADRAO_VISITOR_KEY_SECRET` | `api/guest_access.py`, `domain/usage_limits.py`, `domain/visitor_usage.py` | own | Drop (blocked) | Guest flow |
| `ARGUS_TITLE_AUTOGEN_ENABLED`, `ARGUS_TITLE_AUTOGEN_TIMEOUT_MS` | Set on `argus-api`; **no reader** | own | Drop | Set but unused. Not blocked. |
| `ARGUS_ENABLE_PERSONALIZATION_MEMORY`, `ARGUS_ENABLE_MEMORY_SEMANTIC_RECALL`, `ARGUS_MEMORY_EMBEDDING_{MODEL,DIMENSIONS,TIMEOUT_SECONDS}`, `ARGUS_MEMORY_VECTOR_COLLECTION`, `MEM0_TELEMETRY` (7) | `memory/service.py`, `api/personalization_memory*.py`, `llm/memory_embedding.py` | Mem0 + Perplexity embeddings | Reconcile before retirement | Preserve reusable memory code and controls for #826. Existing settings may retire only after the successor and active consumers are established; Cuadrao memory is not thereby enabled. |
| **GitHub Actions, canary, benchmarks** | | | | |
| `ARGUS_CANARY_{API_URL,APP_URL,EMAIL,PASSWORD,SUPABASE_URL,SUPABASE_SERVICE_ROLE_KEY}` | `.github/canary-render.sh`, `.github/workflows/private-alpha-canary.yml` (3 are GitHub secrets), `scripts/benchmarks/render_internet_benchmark.py` | GitHub | Keep →C | Deploy canary. Re-point to cuadrao.ai; the canary inbox moves (§B3.2 step 4). |
| `ARGUS_DISPOSABLE_DATABASE_URL`, `ARGUS_LOCAL_SUPABASE_{URL,ANON_KEY,SERVICE_ROLE_KEY}` | `.github/workflows/ci.yml`, real-PG tests | GitHub | Keep →C | CI real-Postgres matrix |
| `ARGUS_CANARY_BROWSER_{CHAT_PROMPT,BACKTEST_PROMPT,RESEARCH_PROMPT,ARTIFACT_PROBE,REDACTION_PROBE_VALUE,CHECKS,CHECKS_HANDOFF,STORAGE_STATE,USER_ID}`, `ARGUS_CANARY_STATIC_LABELS_JSON` (10) | `.github/canary-browser.sh`, `web/e2e/private-alpha-release-canary.spec.ts` | GitHub | Drop (blocked) | The browser canary drives `/chat` |
| `ARGUS_PUBLIC_ALPHA_{API_URL,APP_URL,CANDIDATE_SHA,LOAD_IDENTITIES_JSON,LOAD_PROMPT,SUPABASE_URL,SUPABASE_SERVICE_ROLE_KEY}` (7) | `scripts/benchmarks/public_alpha_render_load.py` | none | Drop (blocked) | Chat load test |
| `[removed obsolete setting]`, `_SERVICE_ROLE_KEY` | `scripts/ops/alpha_readiness_metrics.py` (reads `backtest_jobs`) | Supabase | Drop (blocked) | Chat-era alpha metrics |
| **Dead (no reader anywhere)** | | | | |
| `[removed obsolete setting]`, `[removed obsolete setting]`, `[removed obsolete setting]`, `[removed obsolete setting]`, `EQUITY_SYMBOLS` | `.env.example` only | Tavily, Groq, none | Drop | Delete now. Revoke the Tavily and Groq keys if any were issued. |


Android (`mobile/android/app/build.gradle.kts` reads `API_URL` and `SUPABASE_ANON_KEY`) stays parked with Android (§B1.1).

**October 4 reuse correction.** The [canonical reuse decisions](../ARCHITECTURE.md#cuadrao-reuse-decisions)
govern the inventory above. Its Drop labels for old workflow/chat/memory tasks and
settings are retirement candidates, not authorization to delete Render Workflows,
LangGraph or reusable memory foundations. Reconcile each consumer and replacement
through [#826](https://github.com/lagarcess/argus/issues/826) before removal. Existing
service availability and secret consumers must be verified separately.

**Safe removal order [proposed].** For every Drop or Park, in this order:
1. **Stop reading it in code**, in one PR per provider family. Keep the Park code paths behind a default-off mode. Don't make them fail at import. Update `.env.example`, the release profile (`.github/private-alpha-release-profile.json`), `.github/argus-env.sh` and `.github/render-env-sync.sh` and the pinned tests in the same PR, because the release-profile tests fail on drift. Remove the asset check from `/ops` readiness before parking Alpaca.
2. **Promote it** through the normal integration → `main` path, and let one deploy run clean.
3. **Remove it from Render and GitHub** (`render.yaml` plus the dashboard env and secrets; GitHub `secrets.*`). Park ends here.
4. **Delete the secret values** you no longer hold anywhere (Render, GitHub, local `.env` files).
5. **Revoke at the provider**, for truly dead keys only: Tavily and Groq (if issued), `CUADRAO_GUEST_ACCESS_OPENROUTER_API_KEY` after the guest deletion, and the backtest-only GitHub secret `ARGUS_WORKFLOW_DATABASE_URL` (rotate that DB role's password). **Don't revoke** the Alpaca, FRED or `NEXT_PUBLIC_POSTHOG_KEY` keys (shared project), or `RENDER_API_KEY` (still used by the canary).

**What can go now, and what waits for the Argus freeze-then-retire:**
- **Not blocked (16 names):** the 3 env-name aliases, `[removed obsolete setting]`, `NEXT_PUBLIC_POSTHOG_KEY`, `ARGUS_TITLE_AUTOGEN_*` ×2, `ARGUS_DOCUMENT_EXTRACTION_MAX_{BYTES,PAGES}`, the `INTERPRETATION`/`CHAT_COMPOSER` timeouts and the 5 dead `.env.example` names. The Park group (12) can move now, but only if Lucas accepts that the frozen arguschat.ai chat loses backtests and market answers. Otherwise park it together with the chat freeze.
- **Blocked until arguschat.ai `/chat` is retired:** old chat-specific settings after the reuse assessment, research-rail web flag, chat model tiers and task timeouts, share pages, browser canary, load and alpha metrics. Blocked by the backtest retirement: Render Workflows backtest jobs, stale-job reaper, discovery and execution realism. Blocked by the guest deletion PR: the guest flags, `CUADRAO_VISITOR_KEY_SECRET`, the guest OpenRouter key and `ARGUS_GUEST_QA_*`.
- **The `→C` renames ride on §B3.2 step 7** (read `CUADRAO_*` with an `ARGUS_*` fallback, flip Render, drop the fallback). Do the renames after the drops, so dead names never get a `CUADRAO_*` twin.

---

### B5. Revenue capture: engineering view

**The rules and tool options are in §A5** (App Review Guidelines last updated June 8, 2026: 3.1.1, 3.1.1(a) US storefront, 3.1.3(b)/(c)/(f), 2.2; Stripe, Lemon Squeezy, RevenueCat). Facts I checked myself that change the build:
- Stripe's global page doesn't list the DR (https://stripe.com/global, fetched Oct 4). Stripe Managed Payments (merchant of record) is GA in 39 countries as of Apr 22, 2026, and the DR isn't on its business-location list (https://docs.stripe.com/payments/managed-payments/eligibility).
- Lemon Squeezy lists DR bank payouts and DOP selling (https://docs.lemonsqueezy.com/help/getting-started/supported-countries), and its 2026 update steers toward Stripe Managed Payments (https://www.lemonsqueezy.com/blog/2026-update).
- RevenueCat Web supports Stripe Billing, Paddle Billing or RevenueCat Billing (https://www.revenuecat.com/docs/web/overview), and **has no Lemon Squeezy integration listed**.
- TestFlight can't charge (Guideline 2.2), so billing is off the tester critical path; only entitlement plumbing is on it.

**Engineering consequences (Iris owns the commercial options):**
1. **One server-side entitlement table is the source of truth**, keyed on `(subject_type ∈ {person, space}, subject_id, entitlement, source ∈ {app_store, web, manual}, valid_until)`. A business premium entitlement attaches to the **space**. A consumer plan attaches to the **person**; household sharing of a plan is a policy on top. Every client checks the API, never a store SDK alone. Size M.
2. **Consumer iOS (public):** use StoreKit through RevenueCat with App User ID = Supabase user id. A RevenueCat webhook writes into the entitlement table. This needs the Paid Apps Agreement and banking for the chosen entity.
3. **Business web:**
   - **US entity:** Stripe Billing works, with tax handled by Stripe Tax or Managed Payments if eligible. RevenueCat can import it if one dashboard is wanted.
   - **DR entity:** Lemon Squeezy works, through a direct webhook into the entitlement table. RevenueCat can't see it, so the API stays the only reconciler.
   - With a merchant of record such as Lemon Squeezy, the MoR is the seller, so Cuadrao issues no DR fiscal receipt for the subscription (see §B6, "Entity consequences").
   - Write one `BillingProvider` adapter interface either way, so a later switch doesn't touch entitlement logic.
4. **When business reaches the App Store app** (§A5 recommendation: IAP plus web on one entitlement):
   - Add a business IAP product in RevenueCat. Its webhook writes the same space-level entitlement.
   - The App Store flavor shows no web-checkout prompt outside the US storefront. That needs a storefront check in the paywall (StoreKit `Storefront.current`).
   - Nothing else changes, because the entitlement already attaches to the space.

   During TestFlight, business pilots get a `manual` entitlement source (no charge, per 2.2).
5. **Membership vs billing:** the billing admin flag grants no content (§B2.2), and seat counts read from memberships.

---

### B6. Pillars with no institutional access: cost and feasibility

Sizes [estimate]: S = 1 eng-week or less, M = 2-4, L = 5+. **Now** = buildable now. **1-away** = one named relationship away. **Gated** = regulator, counsel or certification controls it. I'm not ranking them; order is Iris's call.

**Shared foundation (both tracks need these first)**

| Pillar | Status | Size | Depends on | Parallel? |
|---|---|---|---|---|
| Space and membership model, steps 1-3 (§B2.3) | Now | M-L | none | Must precede the business record types |
| Entitlement service (§B5) | Now | M | Entity for the live providers | Yes |
| Scoped storage (#778 plus space paths) | Now | M | Space model step 1 | Yes |
| Audit log and approvals framework | Now | M | Space model | Yes |
| Durable jobs beyond backtests | Now | M | Extend existing Render Workflows under the [reuse decisions](../ARCHITECTURE.md#cuadrao-reuse-decisions); receipt recovery acceptance in #823 | Yes |
| Agentic Cuadrao: financial read and propose tools | Now (OpenRouter), behind the AI consent gate (#813) | L | Bounded runtime assignment (#813), space-scoped retrieval | After the manual services |

**Consumer (personal + household, iOS)**

| Pillar | Status | Size | Notes |
|---|---|---|---|
| Accounts, activities, plans, budgets, goals, debts | Now, mostly landed | S-M to connect and verify | #813 "Accounts, Plans, Household" row |
| Household invites and sharing | Now, landed backend, iOS in #810 | S | AASA (§B3.2) |
| Onboarding and sign-in | Now | M | #800, Apple and Google keys (Lucas) |
| Receipt capture and document extraction | Now | M | #778, AI consent gate |
| CSV/statement import | Now | M | No file parser found in `ingestion/`; reconcile exists |
| iOS Shortcuts capture | Now, landed (`ingestion/shortcuts`) | S | |
| Push and reminders | 1-away: APNs key (Lucas) | M | Updates inbox |
| Gmail bank-alert intake | 1-away: Google OAuth verification plus annual security assessment | S code, L process | Connector doc L36, L155 |
| Plaid | Gated for DR users (no Dominican coverage) | n/a | Keep only for foreign accounts |
| DR bank data (Bridge, banks) | Gated (banks, Superintendencia de Bancos, Bridge) | n/a | Lucas's track |
| Consumer billing (RevenueCat) | 1-away: entity plus Paid Apps Agreement | M | Not on the TestFlight path |
| Account deletion enablement | Now | M | #805, #806 |

> **Maya's note:** per Lucas's Oct 4 call, Plaid is kept: sandbox plus Faker data for stress tests now, and real Plaid for Dominicans in the US and with accounts abroad once Plaid's production review clears. Gmail import stays an open decision.

**Business (full web first, plus a thin app space for pilots)**

| Pillar | Status | Size | Notes |
|---|---|---|---|
| Business web shell (auth, space switcher, roles UI) in `web/` | Now | M | Reuses Supabase SSR auth and i18n |
| Roles and permissions matrix | Now (needs Lucas's matrix lock) | M | Blueprint §02 presets |
| Money and ops: cash, manual accounts, imports, reconciliation | Now (reuses recording, reconcile) | M | Space model step 4 |
| Document Inbox and Vault | Now (reuses the extraction pipeline) | M-L | #778 |
| Customers / light CRM | Now | S-M | |
| Quotes, non-fiscal invoice drafts, tracking existing invoices | Now | M | Must never look like an e-CF (Blueprint §13) |
| Collections, allocations, payment matching (manual evidence) | Now | M-L | Blueprint §08 allocation rules |
| Reports and accountant package/export | Now | M | |
| Accountant time-limited access | Now | S on top of memberships | |
| Thin app space: capture, approvals, money view (§B2.7) | Now | M | Compile-time gated (§B3.4) |
| Telegram intake | Now (Bot API) | S-M | Candidate only |
| WhatsApp Business API intake | 1-away: Meta WhatsApp Business Platform (business verification, Cloud API or a BSP) | M | Per-conversation cost |
| POS read-only adapter (Alegra or Odoo) | 1-away: vendor API access plus pilot merchants | M | Discovery first (Blueprint §10) |
| Payment links | 1-away: a payment provider eligible for DR merchants (unnamed) | M | |
| External API/MCP over authorized actions | Now (internal), external after the permission model | M-L | Blueprint §06 |
| **Tracking externally issued e-CF** (owners keep issuing via DGII's Facturador Gratuito or their current provider; Cuadrao records e-NCF, issuer RNC, status, PDF/XML and links payments) | Now | M | **First pilot step** (Iris F2: track). Needed before Nov 15, 2026 for owners in the Aviso 06-26 group. Issuance moves to the provider bridge once that's live. |
| Own fiscal backend, offline: versioned e-CF XML builder, XSD/business-rule validator against DGII's published specs, sequencing, durable submission state machine, evidence store (canonical invoice, XML, hash, responses) | Now (no live submission) | L | Blueprint §14 and §16, Iris pillar 7. Broader target. The approved [E0 plan](cuadrao-business-e0-implementation-plan.md) defines the first offline subset and does not wait on issuer paperwork or promise provider replacement. It's designed so the issuer is the customer and private keys never enter the model or MCP payloads. |
| Cuadrao DGII MCP over that backend (schema retrieval, draft validation; submit and status later) | Now (read and validate tools) | M | Exposes only actions the permission layer already allows (Blueprint §06) |
| DGII test-environment submission and certification walk for one pilot issuer | 1-away: a pilot taxpayer with an RNC, Virtual Office access, a tax digital certificate and FI-GDF-016 | M of engineering, plus weeks of DGII process | Blueprint §15. The DGII foreign-provider question was still unanswered as of Oct 4, 16:32 UTC. |
| Signing adapter | 1-away: a trust service (Viafirma/AVANSI candidate, Blueprint §16) or customer-controlled signing. Custody legality is with counsel. | M-L | Pluggable, so a vendor swap keeps evidence and idempotency |
| Live e-CF issuance through Cuadrao's backend | Gated: each customer's DGII issuer authorization, plus the signing route and operating-entity eligibility | S on top of the rows above once gates clear | Not in the first pilot |
| **Certified-provider bridge (October 4 live-route plan)** | 1-away: a PSFE agreement (provider chosen in Lucas's partner track; Alanube and Alegra are the Blueprint references) | M | **The route to live e-invoicing through Cuadrao.** It sits behind the same fiscal-backend interface as our own backend, so we can switch later without touching the ledger. The interface and adapter can be built against the provider's sandbox before the contract is signed. |
| Cuadrao PSFE status | Gated: our own RNC with software activity, e-CF issuer status, three certified customer issuers, dossier and DGII tests (Blueprint §15) | L (process) | After the pilot issuers |
| Tax preparation (records readiness) | Now | M | Filing is gated (DGII Virtual Office, qualified professional) |
| Business web billing | 1-away: entity plus Stripe or Lemon Squeezy | S-M | §B5 |

**Broader integration streams from October 4:** persisted work uses the space model. The approved [offline E0 subset](cuadrao-business-e0-implementation-plan.md) is independent of those migrations:
- (a) the consumer TestFlight path, which needs only steps 1-2;
- (b) the business ledger: web shell, roles, money, Inbox, customers, invoice drafts, external e-CF tracking, matching and accountant export;
- (c) the offline fiscal backend and DGII MCP.

Persisted integration between streams (b) and (c) needs a reviewed invoice/fiscal-state contract. E0 uses synthetic in-memory inputs and local evidence only; it does not implement that persistence, entitlement or audit integration.

**Business-ledger sizing for the first pilot [estimate]:**
- The pilot is the space model step 4, roles, Inbox, customers, non-fiscal invoices, external e-CF tracking, matching, export, and the thin app space.
- That's roughly 12-18 eng-weeks of work, so 6-9 calendar weeks with two engineers in parallel on (b).
- None of it waits on DGII.
- Historical October 4 estimate: the certified-provider bridge adds about 3-5 eng-weeks. This does not make it a prerequisite for [offline E0](cuadrao-business-e0-implementation-plan.md).
- Historical October 4 estimate: the broad offline fiscal backend (c) adds about 6-10 eng-weeks. The [approved E0 plan](cuadrao-business-e0-implementation-plan.md) owns its bounded subset; no timing estimate, lower-priority assignment or paperwork wait is carried into E0.

**Entity consequences for the fiscal track (engineering only; Lucas decides, Iris F3):**
- **PSFE needs a DR RNC.** Our own PSFE requires an RNC with software activity and e-CF issuer status (Blueprint §15). If we're US-only, the backend must stay in the "customer is the issuer, Cuadrao is software" model, which depends on DGII's pending answer on foreign non-certified providers. Build that way anyway: it's the model every route needs first.
- **Valid DR fiscal receipts for our own subscription bills need a DR issuer.** If DR business customers need valid comprobantes for what Cuadrao charges them, a DR entity has to issue them. That entity would then become the fiscal backend's first issuer (which also meets the PSFE "existing e-CF issuer" prerequisite). Billing webhooks would trigger an e-CF per charge, and a merchant of record like Lemon Squeezy would conflict, because the MoR, not Cuadrao, is the seller of record.
- **A US entity with Stripe** gives us US billing, but no DR fiscal receipts from us.
- **Make the billing → fiscal hook configurable per entity**, so either answer fits without a rewrite.

---

### B7. Issues triage for the next push

27 issues are open (fetched Oct 4). **Correction to the brief:** #789 is **closed**: it was closed Oct 4 at 9:53 AM CT after #794 and recorded in #813.

**Must-do for consumer TestFlight (invite-only)**
- #800: Apple/Google sign-in ship gates (release force-off, 4.8, privacy manifest, revocation) before either flag goes on in TestFlight.
- #784: Mac verification of the combined candidate, plus the permission-key release gate.
- #811: explicit client grants on 17 early tables. #813 lists it as a release gate. It's mandatory before any fresh database (staging or rebuilt).
- #778: document bytes to private Storage before extraction is on, if receipts are in tester scope (#813 puts receipts in the journeys).
- #805: Lane 6 frozen closed-line balance. It blocks the deletion flag in TestFlight. Without it, testers only get the flag-off support fallback.
- #806: real PostHog deletion adapter. Same gate as #805.
- #798: Hide My Email linking and the allowlist-orphan decision are marked "before the beta". Apple name capture goes with them.
- #686: the promotion that carries the TestFlight backend must apply #674's migration and env keys first.
- #694: the forged-header check runs in that promotion window.
- #809 (PR, not an issue): land the pytest-gate fix so the gate line can't misreport failures.

  Iris keeps #686/#694 deferred unless Argus web stays live (her F5). I've listed them here because the TestFlight API *is* `argus-api` on `main`. Any promotion carrying #674 has to apply its migration and env keys first, whether or not arguschat.ai web stays up. They become moot only for the web-security residual.
- #807 (item 15 only): name the operator for the daily deletion sweep while runs are in flight.

**Must-do for business TestFlight pilots and business web** (no issue exists yet; Maya or Yelena should file them after the lock [proposed])
- Space model steps 1-4. #797 (census drift gaps) goes with it, since re-keying will move FKs the gate can't see today.
- Roles and permissions, audit log, and the entitlement service.
- Business Inbox/Vault on #778 storage, the thin app space with the compile-time gate (§B3.4), and its release-check CI.
- #690: re-scope the parked security rescan to the new business, agent and file surfaces before real business data.

**Needed before public launch**
- #807 items 3 and 5: alerting and the per-worker deletion limiter.
- #804, #803: invite-hardening and Apple notes.
- #671: in-memory auth rate limiters, which scale with workers.
- #676: password-recovery limiter on a spoofable header. The iOS app relies on web recovery.
- #700: chat idempotency, if the Cuadrao agent reuses the chat turn path.
- #656: a raw internal name in calculation answers, since calculations stay (room lock).

**Archive, or close as obsolete after the pivot** (Lucas or Iris confirm; most are already `triage:backlog`)
- #640, #606: web chat presentation and freshness (frozen web chat).
- #644, #653: Argus chat prose and acceptance traces (diagnosis already stopped).
- #623, #620: backtest capital and grounded-math research changes (founder-deferred).
- #696: share-receipt currency (share pages retiring).
- #684, #685: guest/research and backtest admission abuse. Close when the guest flow and backtests are retired; until then they still matter on arguschat.ai.

---

### B8. Docs pass inputs for Maya

**Current canon to keep, and rewrite for Cuadrao where noted:**
- `AGENTS.md`.
- `docs/DOCUMENTATION_AUTHORITY.md`: rewrite. It still says "Argus" and "retains the Argus visual identity".
- `docs/PRODUCT.md`: rewrite for three contexts.
- MVEE: amend "Financial spaces" L410-425, which excludes business invoicing and employees and now conflicts with the business premium scope.
- The execution board (#813 section).
- The decision log.
- `ARCHITECTURE.md`, `API_CONTRACT.md` and `DATA_MODEL.md`: these will need the space model.
- `PRIVATE_LAUNCH_RUNBOOK.md`, `docs/specs/private-alpha-ci-cd-sota.md`, `docs/release-manifests/TEMPLATE.md`.
- `docs/specs/lanes/*`: financial, household-permission-policy, document-extraction, financial-ingestion-connectors, account-deletion-fk-census, mvee-five-lane-handoff.
- `docs/specs/cuadrao-accounts-design-lock.md`, `docs/reports/mobile-design-lock-2026-09-28.md`, `.agent/designs/cuadrao/DESIGN.md`.
- `ios/*.md` setup docs.
- `docs/CONVERSATIONAL_RUNTIME.md`, until the agentic lane replaces it.

**Archive candidates:** §A6 list, which I agree with. Add `docs/GUEST_PUBLIC_LAUNCH_SAFETY.md` and `docs/QA_CONVERSATIONAL_TRANSCRIPTS.md` (archive with the guest flow and web chat retirement, not before), `docs/BREAKPOINTS.md` and `.agent/designs/argus/DESIGN.md` (web Argus), and the 146 files in `docs/superpowers/`.

**New, from this half:** the space and ownership spec (§B2, once locked) and `docs/CUADRAO_CODE_MAP.md` (§B1.3). The env and provider inventory in §B4.1 drives the `.env.example` and release-profile cleanup; keep `docs/archive` BCRD and market-data notes, since those providers are parked, not dropped. Also commit both source docs (§A7).

**Size:** `docs/reports/evidence/` is ~4,950 files, 2,195 of them PNGs. Consider moving dated evidence out of the main tree (an archive branch or release assets) while keeping the links. `docs/maintenance/docs-classification-inventory.md` already exists as a starting point.

**PR conflicts Maya will hit:** #813 and #808 each **conflict with #790** in `docs/specs/argus-execution-board.md` (`git merge-tree`, Oct 4). #813 and #808 merge cleanly with each other. #790 now merges cleanly with integration; the DESIGN.md conflict in the handoff is gone. #808 at `a1ebf4b4` already records the founder-approved flag-off support fallback; no further product decision is needed for it.

---

### B9. Open questions only Lucas can answer

Iris's F1-F5 cover segment, e-CF timing, entity, business premium route and Argus web. These are the engineering-specific ones on top:

1. **Lock the space model in §B2**, including the business identity-retention rule. The fiscal retention period needs counsel.
2. **Staging:** TestFlight against the production project (MVEE §1.4 as locked), or reopen §B1.4 for a separate staging project after #811?
3. **Sole-owner deletion:** must a sole business owner transfer ownership or close the business before deleting their account?
4. **Gmail import** (§B4.1): keep, park or drop. Plaid is kept, per Lucas (Oct 4). OpenRouter is Keep for the chat models and vision extraction, per Lucas's Oct 4 2:20 PM CT lock.
5. **Bundle id and name:** confirm `ai.cuadrao.app` and "Cuadrao" (availability unverified). Enroll the Apple team as an organization *before* the first external build (Iris F3, Guideline 5.1.1(ix)). Changing teams later forces a Sign in with Apple migration (#803).

#### Not verified in this draft
- Whether any 20260928+ migration exists in hosted production (no DB access). Hosted Supabase Auth settings, Render dashboard state and `WEB_CONCURRENCY`.
- The App Store Connect record and the availability of the name "Cuadrao". D-U-N-S timing.
- Paddle's availability for a DR entity. Current Render, Supabase and Resend prices (none are quoted on purpose).
- The cuadrao.ai DNS check was a single DNS-over-HTTPS read and one HTTPS attempt, around 12:30 PM CT.
- Size estimates are judgment, not measured.
- Aviso 06-26 / Nov 15 and the DGII process steps come from Iris's refs and the Blueprint. I didn't re-fetch DGII.
