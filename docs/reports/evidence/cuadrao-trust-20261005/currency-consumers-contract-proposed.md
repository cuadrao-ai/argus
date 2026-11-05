# #820 native currency consumers: bounded contract and PR sequence

Read-only design, 2026-10-05. No implementation, build, simulator, provider call, hosted mutation, or runtime acceptance performed.

Inspected integration: `26c0692d634953bd542a6cca6504138e6e420e6c` at `/private/tmp/cuadrao-trust-20261005`. Inspected pending #853: `869931e28b221c62593c261edc607badb2a884e9` at `/private/tmp/cuadrao-primary-currency-20261005`. GitHub #820 and #818 were read live. #853 must land and its current final interface must be checked before consumer implementation. Existing untracked captain evidence in the integration worktree was left untouched.

## Outcome

Three small native PRs can finish the already-approved reachable consumer portion: order Home totals from the canonical profile; offer and persist the same preference during connected entry; show one connected Plan forecast currency at a time. No rate, conversion, blended amount, new financial projection, or onboarding persistence column is needed.

**Chart disposition:** the polished Home balance/history/spending/comparison designs are preview-only, not connected launch journeys. Keep them parked for this bounded assignment. The connected Plan forecast is reachable now and belongs in this currency slice. This distinction does not retire the broader approved chart experience or close #820 by itself; #818 owns release inclusion and the canonical chart-series work needs a separate assignment.

## Authority and settled facts

- `AGENTS.md`, `docs/DOCUMENTATION_AUTHORITY.md`, PRODUCT, ARCHITECTURE, API_CONTRACT, DATA_MODEL and both design guides were consulted within their declared scopes. The current repository authority supersedes older chat-primary/PWA-only framing.
- MVEE currency rule lines 265–275; master-plan currency lock line 216; decision-log currency section lines 418 onward: never convert/blend; Home keeps separate totals, primary first; choose at onboarding and change later; charts/comparisons show one currency; Plan currency stays fixed.
- `docs/API_CONTRACT.md:1057`: server `User.currency` is resolved from `currency_override`, otherwise declared country, otherwise null. It is read-only. `profiles.currency_override` is the only stored preference. The legacy `onboarding` JSON is inert and must remain so (`DATA_MODEL.md:219`, `API_CONTRACT.md:1066`).
- `docs/specs/argus-minimum-viable-ecosystem-experience.md:885`: confirmed complete zero spending is zero; missing coverage is no data; a known-zero comparison baseline uses an amount difference, not a percentage.
- #820 requires these connected consumer journeys and depends on #818 for completion. #818 permits useful bounded preparation while its finite release matrix is resolved.
- #854 remains a separate default-off financial-write lane. No mixed-currency Plan contribution, shared credit, obligation, FX ratio or payment posting semantics are designed here.

## Traced runtime and current owners

All repository paths below are relative to the integration root above unless marked #853.

| Surface/fact | Actual owner and caller | Current behavior and bounded implication |
| --- | --- | --- |
| Connected entry | `ios/ArgusFoundation/ArgusFoundationApp.swift:42` → `Connected/ConnectedCuadraoRoot.swift:4` | Ordinary connected launch uses Root. Auth-disabled FoundationShell and design preview are separate paths. |
| Authentication | `Connected/ConnectedCuadraoAuth.swift`; `Auth/ProfileAuthModel.swift`; `Packages/ArgusSession/.../SessionController.swift` | Existing email/provider/session owners; no connected currency setup currently. Do not rebuild auth or edit these owners in consumer PRs. |
| Admission | `ConnectedCuadraoRoot.swift:14` → `Invitations/InvitationViews.swift:9` (`InvitationGateHost`) | Only admitted/off content enters Shell. Currency setup belongs inside admitted content, not ahead of invitation checks. |
| Profile preference (#853) | `SessionTypes.swift` `SessionProfile.currency` / `currencyOverride`; `SessionController.swift:97` `setPrimaryCurrency(_:expectedIdentity:)`; `Auth/ProfileAuthModel.swift:132`; `ConnectedCuadraoProfile.swift:27` | PATCH `/api/v1/me` with `currency_override`, then canonical profile re-read. Session revision/identity checks remain authoritative. Profile renders resolved server currency or Choose. |
| Personal Home | `ConnectedCuadraoShell.swift:98` → `ConnectedCuadraoHome.swift:234` | `ForEach(home.currencies)` displays independent server `FinancialCurrencySummary` values. Does not contain the polished Home history chart. Order only; never recalculate totals. |
| Personal read model | `Accounts/FinancialLoopModel.swift`; `Packages/ArgusSession/.../FinancialLoopTypes.swift:222,265`; `src/argus/domain/recording/loop_reads.py:160` | Server groups financial position by account currency. Carries exact minor strings, fraction digits, known/unknown counts, source date. Nil/missing and known zero remain distinct. |
| Household Home | `ConnectedCuadraoShell.swift:88` → `Household/HouseholdViews.swift:51,65,93` | `HouseholdDestination` renders authorized `snapshot.positions`. Order using the viewing person's profile, not a household setting. Preserve server scope, unknownCount and known-subtotal disclosure. |
| Upcoming on Home | `ConnectedCuadraoHome.swift` → `Plan/FinancialComingUpView.swift:25` | All server-default `homeProjection.currencies` summaries remain separate. Order primary first here too; do not replace the existing independent Home horizon with Plan's explored horizon. |
| Connected Plan forecast | `ConnectedCuadraoShell.swift:105` → `Plan/FinancialPlanView.swift:80,89,176` | Overview loops over all `projection.currencies`; each known series gets `FinancialForecastChart`. These charts are real connected consumers. Replace the forecast block's multi-currency loop with one selected currency and a switcher. |
| Forecast data | `Plan/FinancialPlanModel.swift`; `Packages/ArgusSession/.../FinancialPlanTypes.swift`; `src/argus/domain/planning/responses.py` | Existing dated projection, selected accounts, unknown IDs, exact point balances and exponents. No new forecast owner needed. |
| Preview charts | `ArgusFoundationApp.swift:47` → `CuadraoCanvas` → `CuadraoHomeCanvas` → `CuadraoHomeOverview.swift:3` → `CuadraoHomeBalanceChart`, `CuadraoHomeInsights`, `CuadraoSpendingChart` | `CuadraoDesignPreview` gates them; they consume `CuadraoAccountsPreview` / Canvas records. Overview currently falls back to DOP and selects alphabetically. Do not import that fallback or its local preference store into connected code. |
| Shared native choice list | `Cuadrao/Planning/CuadraoPlanPreview.swift:42` `PlanCurrency.supported` | #853 reuses DOP/USD/EUR for Profile. New onboarding must reuse this existing list rather than create another. It is a UI subset, not backend currency acceptance truth. |
| Exact currency precision | `src/argus/domain/recording/currency.py`; `domain/home_country.py` | Server CLDR/tender acceptance and exponent. Connected payload exponents are authoritative. `Accounts/AccountsView.swift:188` exact decimal/string formatting underlies `PlanPresentation.money` and `HouseholdMoney`; use it, not CanvasMoney/Double for labels or any accounting. |

## Technical contract

### 1. Primary currency is profile-derived presentation input

Every consumer reads `auth.profile?.currency`. It must not independently resolve country, device locale, account order, USD, DOP or an AppStorage value into a primary currency. Missing remains missing. `currencyOverride` answers only whether the person explicitly saved a choice; it must not replace resolved `currency` as the ordering source.

One small Foundation-only presentation owner can express ordering and chart selection (proposed location `ios/ArgusFoundation/Currency/CurrencyPresentation.swift`). It owns no persisted state, currency whitelist, amounts or exponent logic. Sketch, not an extra API commitment:

```swift
static func orderedCodes(_ available: [String], primary: String?) -> [String]
static func selectedCode(_ explicit: String?, available: [String], primary: String?) -> String?
```

Ordering is primary first **only if present in the supplied authorized currencies**, then deterministic code order. Missing primary leaves normal deterministic ordering; the UI must not label the first code as the person's preference. An absent primary currency must not create a new zero-value row. No currencies means an empty state, not DOP.

Chart selection retains an explicit valid selection; otherwise uses primary only if available; otherwise a sole available currency is self-evident; otherwise remains unselected and asks which available currency to inspect. This avoids silently making alphabetical order a financial default. If the selected currency disappears on account/scope changes, resolve again and clear old chart inspection. Selection is transient, scoped to the current person and surface/context. No device-global chart preference store.

For a profile primary switch, Home reorders immediately from the new published profile. A chart with no explicit choice follows it. A deliberate current chart choice remains visible and labeled; changing the global preference does not pretend the user selected a different chart. A fresh chart entry/relaunch resolves from the latest profile. This is a presentation decision within the locked rule, not a currency conversion.

### 2. Connected onboarding reuses the profile mutation

Use a small currency-choice surface inside the admitted connected entry/Home flow. Show it when `currencyOverride == nil`; an existing country-resolved currency may be displayed as a suggestion, but only explicit confirmation saves an override. A null profile currency starts with no selection. Continue/Save is disabled until a displayed choice is selected.

Use `auth.setPrimaryCurrency(code)` from #853. Dismiss/complete the choice only when the canonical profile readback contains the saved override for the current identity. Do not set a local completed bit or resurrect legacy onboarding JSON. Disable repeat submission during `auth.busy`. Show retryable failure using existing auth error state, preserve the unsaved selection in the current view, and let relaunch re-read the canonical profile. A committed PATCH followed by a lost readback is resolved by profile refresh/relaunch; it must not require financial-write replay machinery.

The smallest assignment is a resumable onboarding prompt in connected Home, accessible to existing users without a saved choice as well as new users. This fulfills a persistent choice without introducing a new global auth gate or blocking existing registered users from their records. Exact screen layout remains with the founder's design owner. If the captain specifically chooses a mandatory fullscreen gate, settle existing-user/skip behavior with that owner first; it is not specified by the current currency lock. This does not block the Home or Plan PRs.

Preserve invitation precedence, pending household destinations and sign-out. Do not place the prompt in `ConnectedCuadraoAuth.swift`; authenticated success, email confirmation and provider sign-in already converge on Root/Shell. Identity change resets draft/selection; no preference write may cross to another person.

### 3. Connected Plan displays one forecast currency

Available choices come from `projection.currencies`, not from Profile's UI choice list or all device ISO codes. Include a currency with unknown amounts so the user can see its honest unknown state. Use the same presentation resolver as Home and an optional selection local to the Plan overview.

One selected `FinancialForecastCurrency` feeds the summary, chart, expected income/bills, transfer effect, net change, shortfall and included-account explanation. Show the currency explicitly and a switcher if multiple authorized currencies exist. Do not change global Plan account selection merely to switch the view. Existing due-date occurrences and management controls retain their currencies and existing scope; do not silently hide pending bills by applying a chart filter to the whole Plan.

Keep current eligibility: unknown balances do not become zero or a plotted line. Known zero is plotted and labeled zero. Empty points remain empty. On currency switch, remount/reset chart inspection (the same selected index must not turn into a different currency's retained observation). Exact label formatting uses the selected payload's exponent and locale; Double remains confined to existing plot coordinates.

There is no connected Home historical comparison to adjust in this PR. Do not wire `CanvasBalanceHistory` or example spending coverage into financial production facts. A future connection requires an approved authorized history/coverage/series adapter, including zero-baseline and no-data comparison semantics.

## Design alternatives considered

A. Store a new native primary preference and have each screen sort/filter independently. Rejected: creates a second durable fact, identity leakage risk and separate defaults.

B. Derive durable preference from #853's canonical profile, add one pure presentation resolver, pass existing server summaries through unchanged. Selected: no new financial rules or persistence, and the same known/unknown facts flow to every reader.

For onboarding, a new registration wizard plus completion column is disproportionate; a resumable admitted currency choice uses the already-available profile write and avoids touching session or invitation internals.

## Small PR briefs after #853 lands

### C1 — Primary-first Home summaries

Allowed: new pure `CurrencyPresentation.swift`; `ConnectedCuadraoHome.swift`; `FinancialComingUpView.swift`; `HouseholdViews.swift` presentation only; focused tests/resources. Consume published Profile without changing its owner. Use one helper for all three currency lists. Personal and household contexts retain server projections and permissions. Do not alter account order, horizon, money values, record writers, or household membership code.

Tests: primary USD reorders DOP/USD; missing primary does not invent one; primary EUR absent from rows adds no EUR row; empty rows; unknown-only and known-zero rows; actual 0/2/3-digit currency payloads; household viewer preference changes order without changing granted scope; Profile switch updates Home. Rollback is the native presentation commit.

### C2 — Persist the connected onboarding choice

Allowed: new currency-choice view; bounded Root/Shell/Home composition; localized resources; focused onboarding tests. Reuse #853's exact `setPrimaryCurrency` interface and `PlanCurrency.supported`; no copy of choices, no changed server/session contract. If the UI list is moved out of the preview file for module ownership, move the declaration unchanged and update imports/callers in one atomic change. Do not grow the catalog or rewrite money inputs as part of this slice.

Tests: admitted new person with null currency; country-resolved suggestion with nil override; already-confirmed override; save/refresh/relaunch; PATCH rejection; response loss; identity switch/sign-out while save is pending; invitation denied/unanswered prevents setup; guest/auth-disabled paths unchanged. Extend existing synthetic auth journey harness, not a second auth backend. Rollback removes the prompt; existing saved overrides remain valid Profile preferences.

### C3 — One connected Plan forecast currency

Allowed: `FinancialPlanView.swift` and a small extracted forecast view if its modularity budget requires it; common presentation helper; resources and focused tests. Reuse canonical `FinancialPlanProjection`. No modification of expectation/goal/budget/debt currency or financial transfer owner.

Tests: two known currencies produce exactly one chart; switch changes chart and matching readout together; primary missing/absent requires explicit choice when ambiguous; unknown currency stays selectable but plots no invented line; known zero plots zero; disappearing currency/account selection invalidates old inspection; locale/precision; no change in stored accounts, plan selection, expectations or actual money. Rollback is the forecast view commit.

C1 precedes C3's shared helper use. C2 can follow C1 or proceed after its exact composition files are reserved. Serialize edits to shared view/helpers and active binding-worker paths. Each PR gets its own reconciled branch and evidence; do not turn this into a multi-feature Profile/session rewrite.

## Synthetic connected acceptance, to be run later by the assigned worker

Reuse `ios/scripts/auth/local_stack.py`, `ios/scripts/auth/run-ui.py`, `AuthJourneyUITests.swift`, `FinancialLoopUITests.swift`, `ConnectedPlanUITests.swift`, Household tests and the existing FinancialModelTests runners. Prepare synthetic users and real local API records. Use a lane-owned stack/ports and the shared Mac/device scheduler. No hosted profile, provider, or real customer record is required.

| Journey | Required evidence |
| --- | --- |
| English new entry | Pass invitation admission, choose USD, verify PATCH/readback, reach Home; DOP/USD remain separate with USD first; relaunch repeats ordering without setup. |
| Spanish entry/change | Choose DOP in Spanish; change to USD in Profile; Home/Upcoming and household projection use primary-first order; labels and decimals follow locale without modifying money. |
| Missing primary | Null country/override/profile currency; visible Choose state, no inferred DOP/USD; mixed-currency chart asks for a choice; lone currency remains clearly identified. |
| Country suggestion | Resolved server currency with no override may order Home but is not mistaken for a user-confirmed onboarding choice; explicit save creates the override. |
| Zero versus missing | DOP confirmed zero, USD unknown, and another partial currency; compare API exact amounts/counts to Home and forecast state; unknown does not become zero; selected unknown has no fabricated chart. |
| Precision | Existing valid JPY zero-digit and KWD three-digit synthetic rows demonstrate server exponents pass unchanged; no new primary-menu catalog expansion is implied. |
| Chart switch | Switch DOP→USD after inspecting a point; exactly one currency's chart/readout appears; no stale point/currency, no changed Plan account selection or ledger write. |
| Recovery | Failed save stays retryable; committed save with lost response resolves by canonical refresh/relaunch; no local completion lie. |
| Isolation | Sign out A, sign in B; no draft/selection/preference leaks. Change household context/revoke access; unavailable currencies disappear with authorized data. |

Capture sanitized exact-head API/read-model comparisons and English/Spanish UI evidence durably in the eventual PR. Include interruption and relaunch. Simulator/local connected evidence is not physical-phone delivery or TestFlight enablement. No test was run in this planning task.

## Genuine gaps and stop conditions

1. **Home history/spending chart connection is still a separate gap.** Current design evidence cannot satisfy connected chart acceptance. Keep it out of these three PRs; #818 must record whether it is required for the named release. Do not close all of #820 from C1–C3.
2. **Native currency selection is not the full backend tender catalog.** #853's shared Profile choice list has DOP/USD/EUR, while account input exposes broader device ISO codes and the server accepts CLDR tender currencies. Do not make another list or pretend these lists match. The bounded onboarding consumer reuses the existing Profile list; if launch requires choosing any backend-supported currency as primary, assign a canonical catalog contract to the foundation owner before expanding this UI. This does not affect displaying/switching existing currencies from server projections.
3. **Onboarding visual policy:** the currency outcome is locked; a mandatory wizard or forced existing-user gate is not. The proposed resumable prompt needs design-owner placement, not a new currency product decision. Other consumer work proceeds independently.
4. Stop if #853 changes its interface or profile publication semantics, if active binding work reserves a required file, if a consumer needs new server history/coverage semantics, or if a change would mutate currency/amounts/permissions. Return the precise owner conflict to the captain.
5. No edits to SessionController, ProfileAuthModel, ConnectedCuadraoAuth, binding-worker files, API/data/migrations, #854 money/Plan posting, provider setup, web/chat/backtest, analytics, production flags, hosted state, signing, or deployment. Do not start simulator/build/service resources from this report.

## Handoff

Captain retains final sequencing and approved-contract activation. Apply `implemented`/`verified`/`enabled` only with their separate evidence. Before each READY claim, reconcile current integration, report semantic overlap and exact SHAs, run required focused checks and merged-tree modularity budget, finish review and unresolved threads, then write the terminal audit. This read-only task created only this report and owns no running processes or child agents.
