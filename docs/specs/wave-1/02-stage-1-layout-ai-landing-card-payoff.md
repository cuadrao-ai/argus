# SPEC 1. Stage 1: layout, AI landing, card payoff

> **September 26, 2026 reconciliation:** Read
> [documentation authority](../../DOCUMENTATION_AUTHORITY.md) and the approved
> [MVEE](../argus-minimum-viable-ecosystem-experience.md) before using this spec.
> These Wave 1 package bodies and existing stage/review gates remain preserved
> for assigned work. Conflicting experience requirements need explicit package
> reconciliation; they are not permanent limits on the pivot. This notice does
> not cancel work, unlock stages, change technical contracts, or authorize
> exposing unfinished features. The original product/source text below remains
> a dated specification, not the final definition of the whole ecosystem.

Shared rules: `00-shared-rules.md` (Iris's R1 to R7, engineering rules E1 to
E7, reuse map RM-1 to RM-19). Integration tip used for this spec:
`5fb0f079b92ed5391da770cb9a7b89c1c4807684`.

Unlock: stage 1 work starts only after every SPEC 0 package is merged and has
passed review (E3).

---

## Product half (Iris, verbatim)

Source: Iris, "Wave 1 specs: product halves", Revision 2 (Sep 25 2026).

## SPEC 1: Layout, AI landing, and card payoff (pesos and dollars)

**Who it's for.** Two kinds of real users living in the DR (locked: residents, not the diaspora).
- **Everyday:** someone in Santo Domingo or Santiago with one or two credit cards, often one card carrying a peso balance and a dollar balance at the same time. They want to know how long their debt will take to pay off and what it costs, in plain Spanish. They don't know terms like "amortización".
- **Practitioner:** someone who knows finance (an accountant, analyst, advisor, or finance student) and wants fast, correct numbers on bonds, certificates, valuations and comparisons.

**Why.** Today a new visitor lands and doesn't know what Argus is for. Wave 1 turns the first screen into "ask a money question, get a grounded answer." The card payoff calculator is the missing everyday tool. Credit card debt is the most common money pain we can serve without any bank data.

### 1A. Layout
**Outcome.** A new visitor understands within five seconds that Argus answers money questions with real calculations, and can ask one with a single tap.
- The default screen for new visitors and signed-out users is the AI landing (1B). Signed-in users also land there until stage 2 ships Home, and then Home becomes their default.
- **Stage 1 has no Tools page.** Chips and chat only. Tools and Search come after the core.
- Wave 1 navigation shows only: Chat (the landing and conversations), Home (the slot is reserved and appears in stage 2), and account/settings.
- Everything in R6 is hidden from navigation. Following an old link to a hidden page lands on the AI landing, with no error screen.
- The new navigation ships behind a flag: on for integration and staging, off in production until rollout.
- Mobile first: works one-handed on a mid-range Android phone at 360px width, the common device in the DR. Desktop is secondary but must not break.
- Keep what already works: chat, receipts, sharing, sign-in, guest mode with its 7-day reset, and language switching.

### 1B. AI landing
Top to bottom:

1. **Headline and one line under it.**
   - ES: "Pregunta sobre tu dinero. Argus hace los cálculos." Sub: "Respuestas con números reales, en pesos o dólares."
   - EN: "Ask about your money. Argus does the math." Sub: "Answers with real numbers, in pesos or dollars."
2. **Chat input**, focused but without opening the keyboard automatically on mobile.
   - ES placeholder: "Ej.: ¿En cuánto tiempo pago mi tarjeta?" EN: "E.g., How long until my card is paid off?"
3. **Two rows of question chips.** Tapping a chip puts its text in the input so the user can edit the numbers before sending; it does not send. Every chip must lead to an existing calculator, or the new card payoff calculator, and produce a real receipt. A chip that can't produce a grounded answer doesn't ship.
   - Everyday row, labeled "Para tu día a día" / "For everyday money":
     - "¿En cuánto tiempo pago mi tarjeta si abono RD$5,000 al mes?" (card payoff)
     - "Si ahorro RD$3,000 al mes, ¿cuánto tendré en 2 años?" (time value)
     - "¿Qué parte de mi sueldo se va en deudas?" (debt-to-income)
   - Practitioner row, labeled "Para profesionales" / "For professionals":
     - "Compara dos certificados: 8% a 1 año vs 9% a 2 años" (ranked comparison or effective rate)
     - "¿Cuál es el rendimiento de un bono con cupón de 10% comprado a 95?" (bond)
     - "Valora una empresa con flujos de RD$10 millones creciendo 5%" (DCF)
   - The numbers in chips are examples, not market rates, and no chip names a bank. The English versions translate the same questions and keep the `RD$` amounts.
4. **One trust line under the chips.**
   - ES: "No vemos tus cuentas bancarias. Tú decides qué números compartir."
   - EN: "We don't see your bank accounts. You choose which numbers to share."
   - This is true today, since we have no institutional access. If that ever changes, this line changes with it.

**Not on the landing:** feature tours, pricing, sign-up walls before the first answer, and sponsored or partner content (sponsored placement is an open decision and stays out of wave 1).
Guests get their first answer without signing in. Sign-in is asked for only at save or goal time, per the locked setup checklist.

**App manifest (installed app name and description) changes in stage 1:**
- Name: "Argus" (both languages).
- es-419 description: "Pregunta sobre tu dinero. Argus hace los cálculos, en pesos o dólares."
- EN description: "Ask about your money. Argus does the math, in pesos or dollars."
- This replaces "Test investing ideas in plain language." If the manifest supports only one language, use es-419.

### 1C. Card payoff calculator, pesos and dollars (money math; R7 applies)
**It answers:** "If I pay X a month, when is this card paid off and how much interest will I pay?" and "What if I paid more?"

**Inputs**, gathered in chat. Ask only for what's missing, one question at a time, in plain words:
- **Balance with its currency** (RD$ or US$). A card can carry both. When the user gives both balances, calculate each separately and show two results side by side. **No combined total in wave 1** (R2). If the user asks for one, say: ES "Por ahora mostramos pesos y dólares por separado; todavía no convertimos entre monedas." / EN "For now we show pesos and dollars separately; we don't convert between currencies yet."
- **Interest rate.** DR statements often show a monthly rate, not only an annual one. Ask "¿Esa tasa es mensual o anual?" / "Is that rate monthly or yearly?" whenever the user doesn't say. Never assume, whatever the size of the number. Keep the rate as the user stated it, and convert internally.
- **Monthly payment.** The user gives the fixed amount they plan to pay. We don't compute the bank's minimum payment, because each bank uses its own formula and we don't have them. If the user says "the minimum", ask them to type the minimum payment from their statement.
- **Optional: new monthly spending on the card.** The default is none, and the receipt states it: "Supone que no haces compras nuevas con la tarjeta" / "Assumes no new purchases on the card."

**Math** (Yelena and Marcus to specify precisely in the engineering half): monthly compounding on the balance, the payment applied after that month's interest, and a final partial payment. No fees, insurance or late charges unless the user gives them. The receipt lists these assumptions.

**Outputs (receipt):**
- Months to payoff, also shown as a date ("Terminas de pagar en marzo de 2028" / "Paid off by March 2028").
- Total interest paid, in the balance's currency.
- Total paid.
- A comparison row for the same balance paying 25% more a month, with the months and interest saved. Label: "Si pagas RD$X más al mes" / "If you pay RD$X more a month" (US$ for dollar balances). It's always calculated, even if the layout collapses it.
- The assumptions list and "Antes de impuestos" / "Before taxes".

**Edge cases (each needs a test):**
- **A payment at or below the first month's interest never pays the debt off.** Say so plainly, with no months:
  - ES: "Con ese pago la deuda no baja: los intereses del mes son mayores. Necesitas pagar más de {interés mensual} al mes para avanzar."
  - EN: "At that payment the debt won't go down: the monthly interest is larger. You need to pay more than {monthly interest} a month to make progress."
  - This amount is shown in the app only, so R4 isn't affected.
- **A payment above the balance** pays it off in 1 month, with only that month's interest.
- **A zero or negative balance, rate or payment:** ask again politely and don't calculate.
- **An annual rate above 100% or a monthly rate above 10%:** calculate, but flag it: "Esa tasa es muy alta, revísala en tu estado de cuenta" / "That rate is very high, check your statement."
- **Payoff longer than 50 years:** say it won't realistically be paid off at this payment, and show the comparison with a higher payment.
- **Two currencies but a payment given in only one:** ask how the payment splits between the peso and dollar balances. Don't guess, and don't convert.

**Out of scope:** bank-specific minimum payment formulas, fees, balance transfers, cash advances, promotional rates, any bank data pull, comparing card offers across banks (we don't have every bank's rates), naming banks in answers, and currency conversion.

**How we'll know stage 1 worked:**
- Leading indicator during the pilot: the share of new visitors who get a first answer in their first session, which is `first_answer_shown` divided by landing views. Yelena confirms whether a landing-view event exists or is cheap to add; otherwise use session start.
- Correctness: the card payoff eval set passes 100% against a reference spreadsheet calculation, including every edge case above.

**Acceptance checks:**
- **B1.** At 360px width, the landing shows the headline, input and the first chip row without scrolling, with screenshots in es-419 and EN.
- **B2.** Each of the 6 chips, sent unedited, returns a grounded answer with a receipt from the named calculator (Playwright or eval).
- **B3.** Every R6 item is absent from navigation, there's no Tools page, and an old link lands on the AI landing with no error.
- **B4.** A guest gets an answer without signing in, and sign-in appears only at save.
- **B5.** Card payoff matches the reference calculation for at least: RD$50,000 at 60% annual paying RD$3,000; US$2,000 at 3.5% monthly paying US$150; a dual-currency card with both balances; a payment below the interest; a payment above the balance; a very high rate; and the monthly-or-yearly question being asked whenever the period is missing.
- **B6.** No receipt ever shows a combined peso-plus-dollar total. A request for one gets the "separately" reply above.
- **B7.** Every receipt shows "Antes de impuestos" / "Before taxes" and the assumptions list.
- **B8.** The card payoff PR has Priya's eval check plus a Codex review.
- **B9.** The installed app shows the new manifest name and description.

### Iris's round 2 answers that apply to SPEC 1 (verbatim)

Source: "Answers to Yelena, round 2" in Iris's product halves. Where these
answers change an item above, the answer wins (the chips, B2, and the
leading indicator).

**1. Chips: I'm rewriting them to carry every number the calculator needs, so one unedited tap gives a receipt.**
The stage 1 leading indicator is "first answer in the first session." Every follow-up question before a first answer is a place a new visitor can drop off, and the summer users left after one day. The grounded follow-up still shows up whenever someone types their own question. B2 now reads: *each of the 6 chips, sent unedited, returns a grounded answer with a receipt from the named calculator, with no follow-up question.* If a calculator still asks for something with the text below, tell me what's missing and I'll add it. Don't loosen B2.

Everyday row ("Para tu día a día" / "For everyday money"):
- ES: "Debo RD$60,000 en mi tarjeta al 4% mensual. Si pago RD$5,000 al mes, ¿cuándo termino de pagar?"
  EN: "I owe RD$60,000 on my card at 4% a month. If I pay RD$5,000 a month, when will it be paid off?" (card payoff)
- ES: "Si ahorro RD$3,000 al mes al 7% anual, ¿cuánto tendré en 2 años?"
  EN: "If I save RD$3,000 a month at 7% a year, how much will I have in 2 years?" (time value)
- ES: "Gano RD$45,000 al mes y pago RD$15,000 en deudas. ¿Qué parte de mi sueldo se va en deudas?"
  EN: "I earn RD$45,000 a month and pay RD$15,000 in debts. How much of my income goes to debt?" (debt-to-income)

Practitioner row ("Para profesionales" / "For professionals"):
- ES: "Compara dos certificados: 8% anual a 1 año vs 9% anual a 2 años."
  EN: "Compare two certificates: 8% a year for 1 year vs 9% a year for 2 years." (ranked comparison or effective rate)
- ES: "Un bono con cupón de 10% anual, precio 95, vence en 5 años. ¿Cuál es su rendimiento?"
  EN: "A bond with a 10% annual coupon, priced at 95, matures in 5 years. What's its yield?" (bond)
- ES: "Valora una empresa con flujos de RD$10 millones al año, creciendo 5% anual, con tasa de descuento de 12%."
  EN: "Value a company with RD$10 million a year in cash flow, growing 5% a year, at a 12% discount rate." (DCF)

The numbers are examples, not market rates, and no chip names a bank. On a 360px screen, chips can wrap to two lines. If a chip still doesn't fit, shorten the wording, never the numbers.

**2. `landing_viewed`: yes.** It's the 9th event, for guests and signed-in users, with language as its only property. It fires once per landing view (not on every re-render). The stage 1 leading indicator becomes `first_answer_shown` divided by `landing_viewed`, among first-session visitors.

**Noted:** the payoff date uses the user's local date. Agreed.

### Iris's round 3 answer that applies to SPEC 1 (verbatim)

Source: "Answers to Yelena, round 3" in Iris's product halves. The six
chips that ship are: card payoff, debt-to-income, and certificates from
round 2, plus time value, bond, and DCF from round 3.

These three chips replace their round 2 versions. The other three (card payoff, debt-to-income, certificates) stay as written in round 2.

- **Time value (everyday row)**
  ES: "Si ahorro RD$3,000 al mes al 7% anual, empezando desde cero, ¿cuánto tendré en 2 años?"
  EN: "If I save RD$3,000 a month at 7% a year, starting from zero, how much will I have in 2 years?"
- **Bond (practitioner row)**
  ES: "Un bono con valor nominal 100, cupón de 10% pagado una vez al año, precio 95, vence en 5 años. ¿Cuál es su rendimiento?"
  EN: "A bond with a face value of 100 and a 10% coupon paid once a year, priced at 95, matures in 5 years. What's its yield?"
- **DCF (practitioner row)**
  ES: "Valora una empresa con flujos de RD$10 millones al año, creciendo 5% anual durante 5 años, con tasa de descuento de 12%."
  EN: "Value a company with RD$10 million a year in cash flow, growing 5% a year for 5 years, at a 12% discount rate."
  The 2% terminal growth stays a default and is shown in the receipt's assumptions list, as it already is.

The code check 1C-4 is agreed. Every chip must pass it, now and later.

---

## Engineering half

### 1.1 What exists and is reused

| Need | Reuse | Map |
| --- | --- | --- |
| Breakpoints | `web/lib/responsive-layout.ts`, `useResponsiveLayout.ts`, `docs/BREAKPOINTS.md`, breakpoint Playwright baselines | RM-12 |
| Navigation today | `ChatSidebar.tsx` (New chat, Search, Recents, Settings), `SidebarDrawer.tsx`, `SidebarNavButton.tsx`, `useMobileShell.ts`, `ProfileMenu.tsx`, `ProfileSettingsPanels.tsx` | RM-12 |
| AI landing surface | `/` bootstraps guests through `GuestEntry.tsx` and sends signed-in users to `currentChatPath()`; the empty chat is `EmptyChatSurface.tsx`, `EmptyChatGreeting.tsx`, `EmptyChatHeading.tsx`, `ChatInput.tsx` | RM-12 |
| Chip text into the input without sending | landing-starter prefill: `useLandingStarterPrefill.ts`, `noteLandingStarterComposerMatch()` in `web/lib/landing-intent.ts` | RM-12 |
| Guest answers without sign-in; sign-in at save | guest mode plus the `can_save_decision` capability gate (conversion reason `save_decision`) | RM-11 |
| Calculation card rendering and editing | `ToolResultCard.tsx`, `ToolCardPresentation.tsx`, `ToolInputEditor.tsx` (each input carries its own unit, so an RD$ field and a US$ field can sit on one card), `web/lib/tool-result-card.ts`, recompute route in `src/argus/api/routers/tool_results.py` | RM-6, RM-10 |
| Missing-input questions | `src/argus/agent_runtime/calculated_answer.py` (`missing_inputs`), web `tools.calc.missing_inputs.ask` in `web/lib/chat-recovery-display.ts` near line 826 | RM-6 |
| Calculator framework | `ToolDeclaration`, `free_policy`, `ExactlyOneUnknown` and other rules, `_shared.py` helpers (`money_input`, `percent_input`, `note`, `no_solution`, `dated_path`), `get_calculation_declarations()`, fixture script | RM-6 |
| Payoff math | `calculate_payoff()` in `money-view/server/platform/credit.py` at `026be6d3` (port, do not import) | RM-8, RM-15 |
| Currency precision | babel (already used by `src/argus/domain/home_country.py`) | RM-9 |
| Notes on cards and receipts | presenter notes render on the card, in copy text, and as the receipt's assumptions list | RM-10 |
| Backtest results | `StrategyResultCard.tsx`, receipt `receipt.fine_print` keys | RM-10 |
| Manifest | `web/public/manifest.json` | RM-14 |
| Flags | `web/lib/private-alpha-flags.ts`, `web/.env.example`, `render.yaml`, release profile | RM-12, RM-19 |
| Analytics | `first_answer_shown` (0C-3) and `landing_viewed` (0C-5) from SPEC 0; the leading indicator query from 0C-6 | RM-1 |

### 1.2 What is genuinely new

1. A navigation model with one owner (`web/lib/app-navigation.ts`) listing
   only Chat, Home (reserved, hidden until stage 2), and Account/Settings,
   rendered as a bottom bar under 720 px and in the sidebar at 720 px and up,
   behind `[removed obsolete setting]`.
2. A not-found route that sends any unknown or hidden path to the AI landing.
3. The 1B landing content on the empty chat surface: headline, sub line,
   placeholder, two labeled chip rows that prefill, and the trust line.
4. The chip audience carried on the chat request so `first_answer_shown`
   gets `chip_audience`.
5. The manifest name and description.
6. The `card_payoff` calculation with a pure Decimal engine, one side per
   currency, the 25% comparison row, and the edge cases.
7. "Antes de impuestos" / "Before taxes" on every calculated result.
8. Field-specific missing-input questions, asked one at a time for card
   payoff.
9. The user's local date on the chat and recompute requests
   (`client_local_date`), used for the payoff month.
10. One chip fixture that owns the six chips and a deterministic check
    that each chip states every input its calculator needs (1C-4).

There is no Tools page and no Tools API in stage 1.

### 1.3 Data and schema changes

- No migration.
- `docs/API_CONTRACT.md`: optional `starter_audience` (`everyday` or
  `practitioner`) on the chat stream request (1B-2).
- `docs/API_CONTRACT.md`: optional `client_local_date` (`YYYY-MM-DD`, a
  Pydantic `date`, closed model) on the chat stream request and on the
  tool-result recompute request (1C-2). It is the user's local calendar date
  from the browser (`Intl`/`Date` local fields, never `toISOString()`, which is
  UTC). The server accepts it only within one day of the server's UTC date;
  outside that window, or when absent, the server's UTC date is used. It is
  not stored and not sent to analytics.
- Register the new calculation in `get_calculation_declarations()` only.
  `docs/ARCHITECTURE.md` already points at that runtime owner; do not add or
  grow a hand-maintained registered-calculations table.
- `.agent/designs/argus/DESIGN.md` navigation and landing sections;
  `docs/BREAKPOINTS.md` gains the 360 px check.

### 1.4 Card payoff: precise specification (the math Iris asked Yelena and Marcus to specify)

Arguments (`CardPayoffArguments(CalculationArguments)`), flat fields so the
generic editor works with no new component:

| Field | Type | Rule |
| --- | --- | --- |
| `currency` | ISO code | the first balance's currency, `DOP` or `USD` |
| `balance` | Decimal > 0 | first balance |
| `rate_pct` | Decimal > 0 | the rate exactly as the user stated it |
| `rate_period` | `monthly` or `annual`, no default | required; never inferred from the size of the number |
| `monthly_payment` | Decimal > 0 | the fixed amount the user plans to pay |
| `monthly_new_spending` | Decimal >= 0, default 0 | optional |
| `second_currency` | ISO code, optional | must differ from `currency` |
| `second_balance`, `second_rate_pct`, `second_rate_period`, `second_monthly_payment`, `second_monthly_new_spending` | same rules | all required once `second_balance` is given |

A rule class (new, in `src/argus/domain/tool_declaration.py` next to
`ExactlyOneUnknown`) makes "second balance given without its payment, rate,
or period" a missing input, which produces Iris's "ask how the payment
splits" behavior. Zero or negative values fail validation and become a
re-ask, never a calculation.

Math per side, in that side's currency only (never added, never converted):

1. `r` = `rate_pct / 100` if monthly, `rate_pct / 100 / 12` if annual
   (nominal annual rate divided by 12, the same convention as
   `calculate_payoff()` and `time_value`).
2. Month `m` = 1, 2, ...: `interest_m = round_half_up(balance * r)` to the
   currency's minor unit (2 for DOP and USD, from babel);
   `balance = balance + interest_m + new_spending`;
   `paid_m = min(monthly_payment, balance)`; `balance = balance - paid_m`.
   Stop when `balance` is 0 (the last payment is the partial one).
3. Non-amortizing: if `monthly_payment <= interest_1 + new_spending`, do not
   iterate; return status `non_amortizing` with `min_payment_to_progress =
   interest_1 + new_spending`.
4. Over 50 years: if month 600 is reached with a balance left, stop; return
   status `beyond_50_years`.
5. Outputs: `months`, `payoff_month` (calendar month of the user's local
   date plus `months`, via `dated_path()` with `start` =
   `client_local_date` from the request; see 1.3), `total_interest`,
   `total_paid`. The user's local date is a request input, not an editable
   card field, and it is recorded on the receipt so a reopened receipt shows
   the same month.
6. Comparison row, always computed: `extra = round_half_up(0.25 *
   monthly_payment)`; rerun with `monthly_payment + extra`; outputs `extra`,
   `months_saved`, `interest_saved` (or its own status if it is also
   non-amortizing or beyond 50 years).
7. High-rate flag: annual rate above 100% or monthly rate above 10%, judged
   on the stated period. Calculate and add the note.

Presentation (all keys under `tools.calc.card_payoff.*`, exact Iris copy in
both languages; RD$ and US$ via the existing currency unit):

- One result block per side, side by side (stacked at 360 px).
- Notes (the assumptions list): no new purchases (Iris's copy) when
  `monthly_new_spending` is 0; no fees, insurance, or late charges; fixed
  payment; "Antes de impuestos" / "Before taxes" (from 1F-1); on two-currency
  cards, Iris's "Por ahora mostramos pesos y dólares por separado; todavía no
  convertimos entre monedas." / "For now we show pesos and dollars
  separately; we don't convert between currencies yet."; the high-rate
  warning when flagged.
- `non_amortizing` shows Iris's message with `{interés mensual}` / `{monthly
  interest}` = `min_payment_to_progress`, and no months.
- `beyond_50_years` shows that it will not realistically be paid off at this
  payment, plus the comparison row.
- The result has no field for a combined total, so none can be rendered
  (B6).

Candidate reference values (computed with the algorithm above; Priya must
confirm each against her reference spreadsheet before 1C-1 merges):

| Case | Months | Total interest | Total paid | Last payment |
| --- | --- | --- | --- | --- |
| RD$50,000, 60% annual, RD$3,000/month | 37 | RD$60,185.94 | RD$110,185.94 | RD$2,185.94 |
| same, 25% more (RD$3,750) | 23 | RD$34,461.95 | RD$84,461.95 | RD$1,961.95 |
| RD$60,000, 4% monthly, RD$5,000/month (the landing chip) | 17 | RD$23,386.47 | RD$83,386.47 | RD$3,386.47 |
| same, 25% more (RD$6,250) | 13 | RD$17,236.67 | RD$77,236.67 | RD$2,236.67 |
| US$2,000, 3.5% monthly, US$150/month | 19 | US$741.42 | US$2,741.42 | US$41.42 |
| same, 25% more (US$187.50) | 14 | US$547.98 | US$2,547.98 | US$110.48 |
| RD$50,000, 60% annual, RD$2,500/month | non-amortizing, needs more than RD$2,500.00 | | | |
| RD$50,000, 60% annual, RD$60,000/month | 1 | RD$2,500.00 | RD$52,500.00 | RD$52,500.00 |
| RD$50,000, 180% annual (high-rate flag), RD$8,000/month | 20 | RD$108,778.17 | RD$158,778.17 | RD$6,778.17 |

### 1.5 Flag

`[removed obsolete setting]` gates 1A and 1B. Code default: off (`=== "true"`,
like `researchRailEnabled`). Integration and staging environments set it to
`true`; production stays `false` until rollout. The variable goes into
`web/.env.example` (true), `render.yaml` for `argus-app` (false, production),
and the release profile (RM-19). The internal team sets hosted values. Flag
off must be byte-identical to today.

### 1.6 Work packages

Merge order: 1C-1, 1F-1, 1C-2, 1C-4, 1A-1, 1A-2, 1B-1, 1B-3, 1B-2, then
internal 1C-3. 1C-1 and 1A-1 can be built in parallel. 1B-1 cannot merge
until 1C-4 has merged (the chips must pass B2 strict first).

Done when, for every package unless it lists more: the Outcome holds,
every named test passes in CI on the PR head (local runs attached where a
test is not in CI), the gate is met (E6, plus the extra gate where named),
the docs it names are updated in the same PR, and the PR is squash-merged
into `codex/private-alpha-next`.

#### 1A-1. Navigation model and bottom bar

- Outcome: with the flag on, navigation shows only Chat and Account/Settings
  (Home reserved and hidden until stage 2). Under 720 px a bottom bar;
  at 720 px and up the same entries in the sidebar. New chat, Recents, and
  conversation Search stay inside the Chat area (see Clashes resolved C3).
  With the flag off, nothing changes.
- Files (new): `web/lib/app-navigation.ts` (the only list: id, route,
  locale key, icon, `visible`), `web/components/navigation/BottomNav.tsx`.
  (changed): `web/lib/private-alpha-flags.ts` (`appNavigationEnabled`),
  `web/components/sidebar/ChatSidebar.tsx`, `web/app/chat/page.tsx`, both
  locale files (new area `navigation.*`), `web/.env.example`, `render.yaml`,
  `.github/private-alpha-release-profile.json`, `docs/BREAKPOINTS.md`,
  `.agent/designs/argus/DESIGN.md`.
- Behavior: `nav` landmark with `aria-label`; `aria-current` on the active
  entry; 44 px minimum targets reachable one-handed at 360 px;
  `env(safe-area-inset-bottom)` padding; the composer is never covered; the
  bar hides while the on-screen keyboard is open.
- Tests: new `web/__tests__/app-navigation.test.ts` (visible entries are
  exactly Chat and Account/Settings; Home present but hidden; flag off
  returns the current sidebar; every label in both languages); new
  `web/__tests__/bottom-nav.test.tsx`; `mobile-shell-layout.test.tsx`,
  `responsive-layout-store.test.ts`, `sidebar-nav-button.test.tsx` green;
  new `web/e2e/app-navigation.spec.ts` at 360, 720, 1024 px;
  `tests/test_private_alpha_release_profile.py` green; screenshots per E4.
- Depends on: SPEC 0 complete. Gate: E6.

#### 1A-2. Hidden and old links land on the AI landing

- Outcome: any unknown path, and any path of an R6 item, lands on the AI
  landing with no error screen (B3).
- Files (new): `web/app/not-found.tsx` (client redirect to `/` with
  `router.replace`, no 404 UI when the flag is on; the current default when
  off). Note: the `/dev/*` playgrounds call `notFound()` in production, so
  they also redirect; that is intended.
- Tests: new `web/e2e/old-links.spec.ts` (`/networth`, `/accounts`,
  `/discover`, `/budgets`, `/tools`, `/rewards`, a random path: each ends on
  the landing with HTTP navigation success and no error text); new unit
  test that no navigation entry or visible link names an R6 item or Tools.
- Depends on: 1A-1. Gate: E6.

#### 1B-1. AI landing content

- Outcome: the empty chat surface shows, top to bottom, Iris's headline and
  sub line, the input with her placeholder, the two labeled chip rows, and
  the trust line, in es-419 and EN, with the flag on. The six chips are card
  payoff, debt-to-income, and certificates from Iris's round 2 answer 1,
  and time value, bond, and DCF from her round 3 answer, word for word
  (they replace the SPEC 1 chip list). The chip data and copy come from
  1C-4; 1B-1 only renders them. Tapping a chip puts its text in the input and does not send.
  At 360 px a chip may wrap to two lines; if one still does not fit, the
  wording is shortened with Iris's approval, never the numbers. The input
  is focused without opening the mobile keyboard. Guests reach it without
  signing in. The surface fires `landing_viewed` once per landing view
  through the SPEC 0 0C-5 hook; 1B-1 must not add a second call or move it
  into a render path.
- Files: `web/components/chat/EmptyChatSurface.tsx`,
  `EmptyChatHeading.tsx`, `EmptyChatGreeting.tsx` (flag-on branch), new
  `web/components/chat/LandingChips.tsx` (reuses the landing-starter prefill
  path; does not reuse `StarterActions`' send-on-tap; reads the chips from
  `web/lib/landing-chips.ts`, created in 1C-4), `ChatInput.tsx` (placeholder key; focus with
  `preventScroll` and no programmatic keyboard open on touch devices), both
  locale files (`landing_ai.*` headline, sub line, placeholder, row
  labels, and trust line in Iris's exact copy; the chip strings
  `landing_ai.chips.*` already exist from 1C-4).
- Tests: new
  `web/e2e/ai-landing.spec.ts`: at 360 x 640 the headline, input, and first
  chip row are visible without scrolling in es-419 and EN (B1, screenshots),
  no chip is clipped or wraps past two lines at 360 px;
  `landing_viewed` fires exactly once per landing view (reuses the 0C-5
  assertion);
  tapping a chip fills the input and sends nothing (no chat request
  observed); a guest can send and get an answer, and the sign-in prompt
  appears only when saving (B4). Existing `guest-entry.spec.ts` and
  `chat-boot.spec.ts` green.
- Depends on: 1A-1, 1C-2 (the card payoff chip needs the calculator), 1C-4
  (B2 strict passes for all six chips), SPEC 0 0C-5 (`landing_viewed`).
  Gate: E6.

#### 1B-2. Chip audience on `first_answer_shown`

- Outcome: when the sent text came from a chip (edited or not), the chat
  request carries `starter_audience`, and `first_answer_shown` sets
  `chip_audience` from it; otherwise `none`.
- Files: chat stream request schema in `src/argus/api/schemas.py` (optional
  literal field), the chat route, `emit_first_answer_event()` from 0C-3,
  `web/lib/argus-api.ts` request builder, `LandingChips.tsx` (remember the
  chip audience for the next send, consume once), `docs/API_CONTRACT.md`.
- Tests: `tests/test_guest_observability.py::test_first_answer_carries_chip_audience`,
  `::test_first_answer_without_chip_is_none`, unknown value is 422; web test
  that the audience is consumed once.
- Depends on: 1B-1, SPEC 0 0C-3. Gate: E6 plus Priya and Codex re-review
  (analytics, R7).

#### 1B-3. Manifest

- Outcome: `name` and `short_name` "Argus"; `description` Iris's es-419
  text; `lang` `"es-419"` (the manifest is one file, so Iris's es-419 rule
  applies); `start_url` stays `/` (it already opens the AI landing).
- Files: `web/public/manifest.json`.
- Tests: new `web/__tests__/manifest.test.ts` (exact name, description,
  lang; icons exist on disk; no U+2014). B9 also needs an internal
  install check on staging with a screenshot of the installed app (Android
  Chrome).
- Depends on: nothing. Gate: E6.

#### 1C-1. Card payoff engine

- Outcome: `src/argus/domain/finance/card_payoff.py`, pure Decimal
  functions implementing 1.4 steps 1 to 7 for one side, no web or API code,
  no import from `money-view/`.
- Tests (new) `tests/domain/finance/test_card_payoff_math.py`, one per row of
  the 1.4 table plus:
  - `test_monthly_and_annual_periods_convert_as_stated`
  - `test_payment_at_first_month_interest_is_non_amortizing`
  - `test_payment_above_balance_pays_off_in_one_month_with_one_months_interest`
  - `test_beyond_50_years_stops_at_600_months`
  - `test_new_spending_raises_the_progress_threshold`
  - `test_high_rate_flag_annual_over_100_and_monthly_over_10`
  - `test_interest_rounds_half_up_each_month`
  - `test_comparison_row_uses_25_percent_more_rounded_to_minor_unit`
  - `test_matches_money_view_calculate_payoff_when_no_new_spending`
    (literal vectors computed at `026be6d3`, SHA in a comment)
- Depends on: SPEC 0 complete. Gate: E6 plus Priya and Codex re-review
  (money math).

#### 1F-1. "Antes de impuestos" / "Before taxes" on every calculated result

- Outcome: every calculation card (all 12) and every backtest result shows
  the line, in the card's assumptions list and on its shared receipt (R3,
  B7).
- Files: `src/argus/domain/tool_declaration.py` (append
  `note("before_taxes")` once in `result_card()`, so no presenter can forget
  it), both locale files (`tools.calc.notes.before_taxes`), backtest:
  `web/components/chat/StrategyResultCard.tsx` and the backtest receipt fine
  print (`receipt.fine_print.*`), regenerate
  `web/__tests__/fixtures/calculation-cards.json`.
- Tests: `tests/domain/calculations/test_before_taxes_note.py::test_every_registered_calculation_card_has_before_taxes`
  (loops over `get_calculation_declarations()`); `test_web_fixture.py` green;
  a web test that the backtest result card and receipt render the line;
  `locales.test.ts` exact copy.
- Depends on: nothing. Gate: E6 plus Priya and Codex re-review (money copy).

#### 1C-2. `card_payoff` calculation, card, and questions

- Outcome: `card_payoff` is registered, reachable by asking in chat, renders
  through the generic card, asks for missing inputs one at a time with
  Iris's wording, and never shows a combined total.
- Files (new): `src/argus/domain/calculations/card_payoff.py`
  (`CardPayoffArguments`, `compute_card_payoff()`, `present_card_payoff()`,
  `get_card_payoff_declaration()` with `free_policy(...)`,
  `ToolProgressTemplate("tools.calc.card_payoff.progress")`,
  `ToolCardBinding(card_type="card_payoff", version=1, ...)`, the
  second-balance rule). Declaration domain lines state: never add or
  convert currencies; never infer the rate period; the minimum payment is
  typed by the user.
  (changed): `src/argus/domain/calculations/__init__.py` (register),
  `src/argus/agent_runtime/calculated_answer.py` (when a declaration sets an
  ask order, request only the first missing field), web
  `web/lib/chat-recovery-display.ts` (render a field-specific key such as
  `tools.calc.card_payoff.ask.rate_period` = Iris's "¿Esa tasa es mensual o
  anual?" / "Is that rate monthly or yearly?" when it exists, else the
  generic ask), both locale files, fixture regeneration, `docs/ARCHITECTURE.md`;
  for the local date: chat stream request and recompute request schemas in
  `src/argus/api/schemas.py` (`client_local_date`), the chat route and
  `src/argus/api/routers/tool_results.py` (pass it through to the
  calculation context), `web/lib/argus-api.ts` (send the browser's local
  date on both requests), `docs/API_CONTRACT.md`.
- Tests (new) `tests/domain/calculations/test_card_payoff.py`:
  `test_single_side_card`, `test_two_sides_are_separate_and_have_no_total_field`,
  `test_two_currency_card_shows_separately_note`,
  `test_missing_rate_period_is_a_missing_input_never_defaulted`,
  `test_second_balance_without_payment_is_missing_input`,
  `test_zero_or_negative_inputs_are_rejected`,
  `test_non_amortizing_presents_min_payment_message_without_months`,
  `test_beyond_50_years_presents_comparison`,
  `test_high_rate_note`, `test_no_new_purchases_note_when_spending_is_zero`,
  `test_card_payoff_is_free_calculation`,
  `test_payoff_month_uses_client_local_date` (server clock at 2026-10-01
  02:00 UTC, client date 2026-09-30: the month is counted from September),
  `test_client_local_date_outside_one_day_falls_back_to_server_utc`,
  `test_receipt_records_the_start_date`; plus
  new `tests/test_client_local_date.py` (optional on `ChatStreamRequest`
  and `ToolResultRecomputeRequest`; a bad format is 422); web test that `argus-api.ts`
  sends the local date, not the UTC date, near midnight; plus
  `tests/agent_runtime/test_calculated_answer.py::test_ask_order_requests_one_field_at_a_time`;
  web test for the field-specific ask key; `test_web_fixture.py`,
  `test_calculation_driving_inputs.py`, `test_calculation_kernels.py` green.
- Gate: E6 plus Priya's eval check and Codex re-review (money math, B8),
  AND model-facing text: the declaration description and domain lines are
  rendered into the list the interpreter reads
  (`answer_request.py` near line 197), and `calculated_answer.py` is in the
  frozen surface (`.agent/interpreter_prompt_fingerprint.json`). Live
  measurement eval, scorecard under `docs/reports/evidence/`, regenerated
  fingerprint (AGENTS.md Standard 12). Internal team runs the live eval.
- Depends on: 1C-1, 1F-1.

#### 1C-3. Card payoff and chip eval (internal, Priya)

- Outcome: the card payoff eval set passes 100% against the reference
  spreadsheet, including every edge case in 1C and every B5 case, in es-419
  and EN; each of the six chips, sent unedited, reaches its named
  calculator and returns a receipt with no follow-up question (B2 strict,
  run on every chip in es-419 and EN, several runs each; any missing-input
  question is a failure). The eval also compares the arguments the
  interpreter sent with the 1C-4 table: the bond call must carry
  `coupons_per_year` 1 (left out or 2 is a failure, because the default
  would silently answer 11.34% instead of 11.37%); the time value call must
  carry `periods` 24 with `periods_per_year` 12 and `present_value` 0; the
  certificates ranking must use `prefer` `higher`;
  a request for a combined total gets Iris's "separately" reply (B6); "the
  minimum" gets the "type the minimum from your statement" question.
- Files: eval cases under `tests/evals/`; no prompt edits unless the eval
  fails, and then only under Standard 12.
- Done when: Priya's scorecard is committed under `docs/reports/evidence/`
  and shows 100% on the card payoff set and on all six chips in both
  languages.
- Depends on: 1C-2, 1C-4, 1B-1. Gate: Priya's verdict (internal).

#### 1C-4. Landing chips: data, copy, and the input check

- Outcome: the six chips exist as data and copy, and a deterministic check
  proves that each chip states every input its calculator needs, so a tap
  sent unedited cannot get a missing-input question (the code half of B2;
  Iris: "Every chip must pass it, now and later"). No calculator, prompt,
  or declaration changes.
- Files (new): `web/__tests__/fixtures/landing-chips.json` (the one owner
  of the chip list: id, audience, locale key, calculator, and the expected
  arguments below), `web/lib/landing-chips.ts` (typed import of the JSON),
  both locale files (`landing_ai.chips.<id>` in Iris's exact round 2 and
  round 3 copy; the English keeps the RD$ amounts),
  `tests/domain/calculations/test_landing_chip_inputs.py`.
- Expected arguments (every value is stated in the chip; nothing invented;
  currency is `DOP` from the RD$ amounts, or from the profile when the chip
  has no amount in a currency, which is never a question), checked at
  `5fb0f079`:

| Chip | Calculator | Arguments the chip states | Unknown solved | Result at `5fb0f079` |
| --- | --- | --- | --- | --- |
| Card payoff | `card_payoff` | `balance` 60000, `rate_pct` 4, `rate_period` `monthly`, `monthly_payment` 5000 (`monthly_new_spending` default 0, shown as a note) | months | 17 months, RD$23,386.47 interest (1.4 algorithm; Priya confirms) |
| Time value | `time_value` | `direction` `save`, `present_value` 0 ("empezando desde cero"), `payment` 3000, `annual_rate_pct` 7, `periods` 24, `periods_per_year` 12 | `future_value` | RD$77,043.09 |
| Debt-to-income | `debt_to_income` | `monthly_debt_payments` 15000, `monthly_income` 45000 | `ratio_pct` | 33.33% |
| Certificates | `effective_rate` (once per certificate); the live eval also accepts `ranked_comparison` | `nominal_rate_pct` 8, then 9 (`compounding_per_year` default 12, shown on the card). A `ranked_comparison` call must carry items 8 and 9 with `prefer` `higher` (checked in 1C-3; not in the fixture, because "higher" is not a stated input) | effective rate | 8.30% and 9.38% |
| Bond | `bond_value` | `face_value` 100, `coupon_rate_pct` 10, `coupons_per_year` 1 ("pagado una vez al año"), `years` 5, `price` 95 | `yield_to_maturity_pct` | 11.37% (with the default of 2 it would be 11.34%) |
| DCF | `discounted_cash_flow` | `cash_flow` 10000000, `growth_rate_pct` 5, `years` 5 ("durante 5 años"), `discount_rate_pct` 12 (`terminal_growth_rate_pct` default 2.0, shown in the assumptions list as Iris asked) | `value` | RD$115,238,571.17 |

- Tests (`test_landing_chip_inputs.py`), one case per chip, read from the
  JSON fixture:
  - `test_chip_arguments_validate_with_no_missing_input`: the expected
    arguments build the calculator's arguments model and pass every rule
    (`ExactlyOneUnknown` counts a stated 0 as given).
  - `test_chip_arguments_are_stated_in_the_copy`: every amount, rate,
    price, and term in the expected arguments appears in the es-419 chip
    text. Each derived value carries, in the fixture, the phrase it comes
    from, and that phrase must appear too: `periods` 24 and
    `periods_per_year` 12 from "al mes" and "2 años"; `present_value` 0
    from "empezando desde cero"; `coupons_per_year` 1 from "una vez al
    año"; `rate_period` `monthly` from "mensual"; `direction` `save` from
    "ahorro".
  - `test_bond_chip_sets_coupons_per_year_explicitly`: the bond fixture
    contains `coupons_per_year: 1`, so the default of 2 can never be
    relied on.
  - `test_chip_result_matches_expected`: the handler returns the result
    column above (card payoff added once 1C-2 is merged, which 1C-4
    depends on).
  - Web: new `web/__tests__/landing-chips.test.ts` (six chips, three per
    audience, each maps to a registered calculator or `card_payoff`, exact
    copy in both languages, every number in the ES chip also appears in the
    EN chip, no bank names, no U+2014).
- Done when: both test files pass in CI, and a future chip cannot be added
  without a fixture row (the web test fails on a chip with no row).
- Depends on: 1C-2. Gate: E6 (no money math is changed; the calculators
  are only called).

### 1.7 Acceptance checks mapped to packages

| Check | Evidence | Package |
| --- | --- | --- |
| B1 | `ai-landing.spec.ts` at 360 x 640, screenshots es-419 and EN | 1B-1 |
| B2 | strict: each chip, sent unedited, returns a receipt from its named calculator with no follow-up question; deterministic input check plus live chip eval in es-419 and EN | 1C-4, 1C-3, 1B-1 |
| B3 | `app-navigation.test.ts`, `old-links.spec.ts`, no Tools route | 1A-1, 1A-2 |
| B4 | `ai-landing.spec.ts` guest case | 1B-1 |
| B5 | `test_card_payoff_math.py` table rows, `test_card_payoff.py` two-currency and missing-period tests, eval | 1C-1, 1C-2, 1C-3 |
| B6 | `test_two_sides_are_separate_and_have_no_total_field`, separately note, eval reply | 1C-2, 1C-3 |
| B7 | `test_every_registered_calculation_card_has_before_taxes`, backtest card test, card payoff notes tests | 1F-1, 1C-2 |
| B8 | Priya's eval check and Codex re-review written on the 1C-2 PR | 1C-2 |
| B9 | `manifest.test.ts` plus the internal staging install screenshot | 1B-3 |

### 1.8 Review summary

| Package | CI + Codex + threads | Priya + Codex re-review | Measurement eval |
| --- | --- | --- | --- |
| 1A-1, 1A-2, 1B-1, 1B-3, 1C-4 | yes | no | no |
| 1B-2 | yes | yes (analytics) | no |
| 1C-1 | yes | yes (money math) | no |
| 1F-1 | yes | yes (money copy) | no |
| 1C-2 | yes | yes (money math) | yes |
| 1C-3 | internal | Priya verdict | yes |

### 1.9 Clashes resolved

| # | Iris's text | What the code does at `5fb0f079` | Resolution |
| --- | --- | --- | --- |
| C1 | Tapping a chip fills the input and does not send | `StarterActions` sends on tap | Iris wins: new `LandingChips` on the landing-starter prefill path |
| C2 | No combined total | `Money` refuses cross-currency sums; no FX source | Consistent; the result has no total field |
| C3 | Navigation shows only Chat, Home (stage 2), account/settings; keep what already works | The sidebar also has New chat, Search (conversation search), Recents | Both hold: New chat, Recents, and conversation Search live inside Chat, not as top-level entries. Iris to confirm on the 1A-1 PR |
| C4 | R6 items hidden from navigation | None of them exist in this web app (only in the unmerged `money-view/` pilot) | Already true; 1A-2 adds the redirect and a test so they cannot appear |
| C5 | Old links land on the AI landing | No `not-found.tsx`; unknown paths show the default 404 | Iris wins: 1A-2 |
| C6 | Manifest in es-419 if only one language is supported | `manifest.json` is one file with `lang: "en"` | Iris wins: es-419 (1B-3) |
| C7 | Ask "one question at a time" | The missing-input ask lists every missing field in one sentence | Iris wins for card payoff (ask order); other calculators unchanged |
| C8 | "¿Esa tasa es mensual o anual?" exactly | The ask copy is generic ("tell me {inputs}") | Iris wins: field-specific ask key |
| C9 | Every receipt says "Before taxes" | No such line anywhere | Iris wins: 1F-1, once in `result_card()` plus backtest results |
| C10 | Every receipt shows the assumptions list | Several calculators produce no notes | The before-taxes line is part of the notes, so every list is non-empty |
| C11 | The 360 px phone is the target | Breakpoint baselines use 390 px | 1B-1 and 1A-1 add 360 px checks |
| C12 | The payoff date uses the user's local date | `dated_path()` takes a start date; the calculation context has only the server's UTC clock | Iris wins: `client_local_date` on the chat and recompute requests (1.3, 1C-2) |
| C13 | Leading indicator: `first_answer_shown` divided by `landing_viewed`, first-session visitors | No landing-view event exists | Resolved by SPEC 0: `landing_viewed` (0C-5) and the saved query (0C-6) |
| C14 | Certificates chip: "8% a year for 1 year vs 9% a year for 2 years" | `effective_rate` silently assumes monthly compounding (12) when not stated; `ranked_comparison` defaults to "lower is better" | No question is asked, so B2 holds. The receipt's assumptions list shows the compounding; the interpreter must rank "higher is better", checked in 1C-3 |
| C15 | Bond chip: "a 10% coupon paid once a year" | `bond_value.coupons_per_year` defaults to 2 when the interpreter leaves it out, which gives a wrong yield with no question | The chip states the frequency; 1C-4 pins `coupons_per_year` 1 in the fixture and 1C-3 fails any call without it. No calculator change |

Resolved in round 3:

- All six chips now state every required input at `5fb0f079` (table in
  1C-4). Time value gained "empezando desde cero" (`present_value` 0), bond
  gained face value 100 and "pagado una vez al año" (`coupons_per_year` 1),
  and DCF gained "durante 5 años" (`years` 5).

Not resolved: none.
