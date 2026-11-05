# Hunk classification: Home and Balance files

Diff base: 5753b5d7cb3e4a13b4bac58a87fa32127b6fcf37 (approved Preview). Candidate: cuadrao-delta HEAD.
Checkpoint tree read at the checkpoint worktree.
Candidate tree read at the candidate worktree.
Connected caller paths below are relative to `ios/ArgusFoundation/`.

Reading conventions:
- "Preview" means the design preview launch (`CuadraoDesignPreview.isActive == true`, i.e. `--cuadrao-design` or the `CUADRAO_DESIGN_PREVIEW` plist key).
- Additive accessibility identifiers (an id placed where the checkpoint had none) are recorded inside SEAM items; they do not change rendering. A changed or removed id would be DRIFT; none was found in these files.
- Where a classification depends on a fact I could not observe without a build (a rendering at accessibility sizes, an inherited-font effect), the item says UNSURE and names both classes.

## ios/ArgusFoundation/Cuadrao/CuadraoHomeCanvas.swift
Base lines: 386. Status: M.

### Hunk 1: @@ -7,7 +7,6 @@ (+0/-1)
Class: SEAM
Used by: Cuadrao/CuadraoAppShell.swift:18 (the `reduceMotion` environment moved there)
Reason: `@Environment(\.accessibilityReduceMotion)` is deleted because the only reader (the navigation-bar fade animation) moved into `CuadraoAppShell`.

### Hunk 2: @@ -25,7 +24,6 @@ (+0/-1)
Class: SEAM
Used by: Cuadrao/CuadraoAppShell.swift:17 (`pendingTab` state moved there)
Reason: `pendingTab` is the temporary-chat leave dialog state; it moved with the dialog into the shell. Same semantics.

### Hunk 3: @@ -34,7 +32,6 @@ (+0/-1)
Class: SEAM
Used by: Cuadrao/CuadraoAppShell.swift:4 (`CuadraoAppShellMetrics.navigationHeight = 72`)
Reason: `navigationBarHeight: CGFloat = 72` became `CuadraoAppShellMetrics.navigationHeight` with the same value; the one reader (Profile `bottomSpace`, Hunk 11) was updated.

### Hunk 4: @@ -44,39 +41,29 @@ (+19/-29)
Class: SEAM
Used by: Connected/ConnectedCuadraoShell.swift:43 (`CuadraoAppShell(`), Connected/ConnectedCuadraoHome.swift:53 (`CuadraoHomeLayout(`), Household/ConnectedHouseholdHome.swift (greeting/updates only)
Reason: `TabView(selection: tabSelection)` became `CuadraoAppShell(selection:chat:spanish:showsNavigation:compact:avatar:profileName:showProposal:)`; the `showsNavigation` and `compact` expressions are the checkpoint's inline conditions verbatim, and `showProposal: { voiceProposal = .proposed }` is passed, so the shell appends `selection = .plan; chat.voice.presentation = .compact` exactly as the checkpoint closure did. The `ScrollView { VStack(spacing: 36) { VStack(spacing: 18) { header; selector; household } ; sections; customize } .padding(.horizontal, 24).padding(.top, 28).padding(.bottom, 32) }.safeAreaPadding(.bottom, 80).background(WelcomePalette.background)` block became `CuadraoHomeLayout` with the same constants (see CuadraoHomePresentation.swift). The `notice: { EmptyView() }` slot contributes no spacing inside the VStack. `CuadraoNavigationScrollObserver` is now applied after `.safeAreaPadding`/`.background` instead of before; it uses `onScrollGeometryChange`, which reaches the ScrollView through wrapping modifiers, so behavior is unchanged. "Ordenar Inicio" button, `customize-home` id and `home-household-members` id are unchanged.

### Hunk 5: @@ -93,54 +80,12 @@ (+1/-43)
Split:

#### Hunk 5a: `destination(tab)` becomes `destination(tab, selection: selection)` (+1/-1)
Class: SEAM
Used by: none outside this file
Reason: The per-tab destination now receives the shell's gated `tabSelection` binding (used by the "Volver a Buscar" button, Hunk 11), which is the same binding the checkpoint's private `tabSelection` produced.

#### Hunk 5b: `.cuadraoScrollBar`, `.cuadraoSoftScrollEdges`, `.cuadraoVoicePresentation`, `.confirmationDialog`, `.tint`, `.foregroundStyle` removed (-37)
Class: SEAM
Used by: Cuadrao/CuadraoAppShell.swift:21-66 (the same modifiers, same strings, same order)
Reason: Moved verbatim into `CuadraoAppShell`. Spanish strings "¿Terminar el chat temporal?", "Terminar y salir", "Seguir aquí", "Se descartará el contenido temporal. Tu chat anterior quedará intacto." are byte-identical in the shell. One addition inside the shell (`.font(.body)`) is classified under CuadraoAppShell.swift below.

#### Hunk 5c: `.environment(\.cuadraoChat, chat)` removed from after `.sheet` / `.receiptPresentation` (-1)
Class: DRIFT
Used by: Cuadrao/CuadraoChatContext.swift:69 (`CuadraoContextPresentation` reads `@Environment(\.cuadraoChat)` and `guard let value, let chat else { return }`)
Reason: At the checkpoint the environment was set at line 143, after `.sheet(item:)` (140) and `.receiptPresentation` (141), so every Home sheet and the receipt flow inherited the chat. The candidate sets it only inside `CuadraoAppShell` on the `TabView`; the canvas's `.sheet` and `.receiptPresentation` are attached outside the shell and no longer carry it. Readers that lose it in the Preview: `Receipts/CuadraoReceiptReview.swift:188` ("Ask" from a receipt review) and `CuadraoUpdatesCanvas.swift:59` which hosts `CuadraoAccountCanvas` (`CuadraoAccountCanvas.swift:59`, "Preguntar a Cuadrao" from an account opened inside the Novedades sheet). With `chat == nil` the `onChange` guard returns and the tap does nothing. Views inside the tabs (chart Ask, account detail reached by navigation) still get it.
Restore: Re-add `.environment(\.cuadraoChat, chat)` on the canvas root after `.environment(\.receiptWorkspace, receiptWorkspace)` in `CuadraoHomeCanvas.body`, as at checkpoint line 143. The copy inside the shell can stay.

### Hunk 6: @@ -158,31 +103,13 @@ (+4/-22)
Split:

#### Hunk 6a: archived toast inline HStack becomes `CuadraoArchivedAccountToast` (+4/-12)
Class: SEAM
Used by: Connected/ConnectedCuadraoHome.swift:139; definition Cuadrao/CuadraoAccountManagement.swift:20-36
Reason: The extracted view is the checkpoint HStack verbatim ("Cuenta archivada", "Deshacer", xmark 44x44 with "Cerrar" label, `.font(.subheadline)`, leading 20 / trailing 6, `.regularMaterial` in radius 18, horizontal 20, bottom 90). Additive ids `accounts.archived.undo` and `accounts.archived.close` where the checkpoint had none.

#### Hunk 6b: private `tabSelection` binding removed (-10)
Class: SEAM
Used by: Cuadrao/CuadraoAppShell.swift:70-79
Reason: Same gating logic (temporary chat content asks before leaving; plain temporary chat leaves on `.returnToRegular`) moved into the shell.

### Hunk 7: @@ -198,11 +125,7 @@ (+1/-5)
Class: SEAM
Used by: Connected/ConnectedCuadraoHome.swift:213, Household/ConnectedHouseholdHome.swift:56
Reason: `CuadraoHomeGreeting(name:spanish:)` reproduces `VStack(alignment: .leading, spacing: 5) { Text("Hola" + ", name") .font(.title2.weight(.semibold)) .accessibilityIdentifier("home-greeting") }` with the same trimming. `.contextMenu` still attaches to the same node.

### Hunk 8: @@ -221,19 +144,7 @@ (+1/-13)
Class: SEAM
Used by: Connected/ConnectedCuadraoHome.swift:215, Household/ConnectedHouseholdHome.swift:58
Reason: `CuadraoUpdatesButton(spanish:unread:action:)` is the checkpoint button verbatim (image `CuadraoNotifications` 44x44, caption2 medium badge on pine circle, "Novedades", "N sin leer", id `cuadrao.updates.open`). `unread` is `Int?` so connected can omit it; the canvas passes `unreadUpdates`, so the badge and value are unchanged.

### Hunk 9: @@ -291,27 +202,13 @@ (+3/-17)
Class: SEAM
Used by: Plan/FinancialComingUpView.swift:13,20; Household/ConnectedHouseholdHome.swift:86; Connected/ConnectedCuadraoMovementRow.swift:10; Household/HouseholdPlanViews.swift:159
Reason: `CuadraoUpcomingSection` keeps `VStack(spacing: 18) { HStack { title; Spacer; "Ver plan" .font(.subheadline).frame(minHeight: 44) } ; rows }` and the title keeps `CuadraoTypography.section` + `.isHeader` from the checkpoint `sectionTitle` helper. Additive ids `home.comingUp` and `home.viewPlan`. The row "Internet / Mañana · Previsto / 1,500.00 / wifi" is unchanged. `CuadraoFeedRow` at default type size renders the checkpoint HStack; its accessibility-size branch is classified under CuadraoHomePresentation.swift.

### Hunk 10: @@ -323,7 +220,7 @@ (+1/-1)
Class: SEAM
Used by: none outside this file
Reason: Signature change only (Hunk 5a).

### Hunk 11: @@ -333,7 +230,7 @@ and @@ -342,7 +239,7 @@ (+2/-2)
Class: SEAM
Used by: none outside this file
Reason: "Volver a Buscar" now writes `selection.wrappedValue = .search` through the shell's binding (same binding as before). Profile `bottomSpace` reads `CuadraoAppShellMetrics.navigationHeight + 8 + (voice ? 64 : 0)`, same 72-based value.

## ios/ArgusFoundation/Cuadrao/CuadraoHomePresentation.swift
Base lines: 0. Status: A.

### Hunk 1: @@ -0,0 +1,161 @@ (+161/-0)
Class: NEW
Used by: Connected/ConnectedCuadraoHome.swift:53,213,215; Connected/ConnectedCuadraoBalanceOverview.swift:99; Household/ConnectedHouseholdHome.swift:56,58,86,124; Plan/FinancialComingUpView.swift:13,20; Connected/ConnectedCuadraoMovementRow.swift:10; Household/HouseholdPlanViews.swift:159
Reason: Extractions from the checkpoint `CuadraoHomeCanvas.swift`. Per struct:

- `CuadraoHomeLayout` (lines 3-30) extracted from CuadraoHomeCanvas.swift checkpoint lines 47-82 (ScrollView body). Rendering unchanged (spacing 36/18, padding 24/28/32, safe-area 80, background, "Ordenar Inicio" with `slider.horizontal.3`, id `customize-home`). SEAM.
- `CuadraoHomeGreeting` (32-42) extracted from checkpoint lines 201-205. Unchanged. SEAM.
- `CuadraoUpdatesButton` (44-63) extracted from checkpoint lines 224-236. Unchanged for a non-nil `unread`. SEAM.
- `CuadraoFeedRow` (65-83) extracted from checkpoint lines 304-313 (`feedRow`). Default type size unchanged. New: at `dynamicTypeSize.isAccessibilitySize` the amount moves under the detail line instead of trailing. Class for that branch: UNSURE FIX/DRIFT. FIX if the checkpoint row clipped or pushed the amount off-screen at AX sizes (plausible: body title plus `rowAmount` on one line); DRIFT if it did not. Introduced in 9746bb602 ("bind connected Home"), which does not name a Preview defect. Default-size rendering is byte-identical either way.
- `CuadraoUpcomingSection` (85-102) extracted from checkpoint lines 293-302 plus `sectionTitle` 317-319. Unchanged apart from additive ids `home.comingUp`, `home.viewPlan`. SEAM.
- `CuadraoBalanceAmount` (104-161) extracted from CuadraoHomeBalanceChart.swift checkpoint lines 154-173 (`amountRow`). Two differences inside the extracted copy:
  - (i) `.accessibilityLabel(currency + " " + amount)` on the amount text (9746bb602). VoiceOver reads "DOP 1,500.00" where the checkpoint read "1,500.00". No visual change. Class: DRIFT (accessibility behavior, low impact). Restore: delete the `.accessibilityLabel` line in `amountLabel`.
  - (ii) At `isAccessibilitySize` the layout becomes `VStack { HStack { currency; Spacer; expand }; amount }` (eddb7da97 "keep balance readable at accessibility sizes"). Default size keeps the checkpoint `HStack(alignment: .firstTextBaseline, spacing: 8)` with the same `Spacer(minLength: 0)` only when not expanded. Class: UNSURE FIX/DRIFT. The checkpoint amount had `lineLimit(1).minimumScaleFactor(0.5)` beside a 44pt button, so at AX5 the amount would shrink to half size; that reads as a Preview defect, which makes FIX the likelier class, but the commit only touches this file and names no reproduction. Default-size rendering is unchanged.

## ios/ArgusFoundation/Cuadrao/CuadraoHomeInsights.swift
Base lines: 125. Status: M.

### Hunk 1: @@ -14,29 +14,10 @@ (+0/-19)
Class: SEAM
Used by: Cuadrao/CuadraoHomeInsightsLayout.swift:14-25 (same helpers)
Reason: `dismiss`, `periodLabel`, `metricChoice`, `controls`, `oldest`, `oldestOffset` moved into `CuadraoHomeInsightsLayout` / `CuadraoHomeInsightsChrome`. Strings "Vista", "Actividad", "Balance", id `home-insight-metric`, id `home-insight-period` unchanged.

### Hunk 2: @@ -48,7 +29,6 @@ (+0/-1)
Class: SEAM
Used by: Cuadrao/CuadraoHomeInsightsLayout.swift:15-17
Reason: `movePeriod` moved with the page accessibility actions.

### Hunk 3: @@ -72,44 +52,19 @@ (+8/-33)
Class: SEAM
Used by: Connected/ConnectedCuadraoBalanceOverview.swift:166,178
Reason: The `VStack(spacing: 8) { VStack(spacing: 4) { metric; controls }.padding(.horizontal, 24); TabView(.page) ... }.background(...)` block became `CuadraoHomeInsightsLayout` plus `CuadraoHomeInsightsChrome` (background, inline title `space`, leading xmark "Cerrar" with id `home-history-done`). The `oldestOffset` closure reproduces the checkpoint's `activity ? CanvasSpendingHistory.oldestOffset(expenses, range:) : range.oldestOffset(built?.points ?? history)`. The layout's `distributionOnPastPeriods` keeps its default `true`, so `distributionEnabled` is always `true` for the Preview and the distribution icon stays enabled on past pages. `historical: offset < 0` in `periodContent` (candidate line 43) is byte-identical to checkpoint line 63; the "historical" suspect is not in this file's diff.

### Hunk 4: @@ -119,7 +74,6 @@ (+1/-2)
Class: SEAM
Used by: Cuadrao/CuadraoHomeInsightsLayout.swift:57
Reason: `.onChange(of: oldest) { periodOffset = max(value, periodOffset) }` moved into the layout; `.tint(pine).foregroundStyle(ink)` stays on the canvas root.

## ios/ArgusFoundation/Cuadrao/CuadraoHomeInsightsLayout.swift
Base lines: 0. Status: A.

### Hunk 1: @@ -0,0 +1,77 @@ (+77/-0)
Class: NEW
Used by: Connected/ConnectedCuadraoBalanceOverview.swift:166 (`CuadraoHomeInsightsLayout(... distributionOnPastPeriods: false ...)`), :178 (`CuadraoHomeInsightsChrome`)
Reason: `CuadraoHomeInsightsLayout` (3-59) extracted from CuadraoHomeInsights.swift checkpoint lines 18-36 (helpers) and 75-97 (body) and 122 (`onChange`). `CuadraoHomeInsightsChrome` (61-77) extracted from checkpoint lines 17 (`dismiss`) and 98, 103-110 (background, title, toolbar). Rendering unchanged: same `TabView(.page(indexDisplayMode: .never))`, same `.id(range.rawValue + String(activity))`, same window of `abs(offset - periodOffset) <= 1`, same padding 24/16/32, same accessibility actions "Período anterior" / "Período siguiente" on page and TabView, same ids. The only new parameter, `distributionOnPastPeriods`, defaults to `true`, which makes `distributionEnabled` constant `true` (SEAM). The doc comment on line 9 is new text, not rendering.

## ios/ArgusFoundation/Cuadrao/CuadraoHomeBalanceChart.swift
Base lines: 267. Status: M.

### Hunk 1: @@ -15,15 +15,20 @@ (+7/-2)
Class: SEAM
Used by: Connected/ConnectedCuadraoBalanceOverview.swift:82-85 (`partial:`, `amountIdentifier:`)
Reason: Two defaulted parameters, `partial: Bool? = nil` and `amountIdentifier = "home-chart-amount"`. The Preview callers (`CuadraoHomeOverview.swift:11`, `CuadraoHomeInsights.swift:46`) pass neither.

### Hunk 2: @@ -31,7 +36,7 @@ (+1/-1)
Class: SEAM
Used by: as Hunk 1
Reason: Pass-through of the two new parameters to the private content view.

### Hunk 3: @@ -47,6 +52,8 @@ (+2/-0)
Class: SEAM
Used by: as Hunk 1
Reason: Stored fields for the two parameters.

### Hunk 4: @@ -93,7 +100,7 @@ (+1/-1)
Class: SEAM
Used by: as Hunk 1
Reason: `partial` becomes `partialOverride ?? accounts.contains { $0.balance == nil }`; with `nil` the checkpoint expression runs.

### Hunk 5: @@ -127,7 +134,7 @@ (+1/-1)
Class: SEAM
Used by: Connected/ConnectedCuadraoBalanceOverview.swift:82 (passes `accounts: []` with a server-built history)
Reason: `, !period.changes.isEmpty` added to the breakdown gate. In the Preview `CanvasBalancePeriod.changes` is `zip(starting, closingAccounts)` over the same `accounts` the history was built from (CuadraoBalancePeriod.swift checkpoint line 50), so `changes` is empty only when `accounts` is empty, and then `history` is empty and `period.closing` is already `nil`. The added condition never flips the Preview; it only hides the breakdown for the connected `accounts: []` call. This refutes the earlier audit's suspicion for the Preview.

### Hunk 6: @@ -152,25 +159,9 @@ (+3/-19)
Class: SEAM
Used by: Connected/ConnectedCuadraoBalanceOverview.swift:99, Household/ConnectedHouseholdHome.swift:124
Reason: `amountRow` delegates to `CuadraoBalanceAmount` with the checkpoint's "—" placeholder, `CanvasMoney.format`, `selectedDate = nil` before `chooseCurrency`, and `expanded`/`expand`. Default-size rendering is the checkpoint HStack. The two in-copy differences (VoiceOver label, AX-size layout) are recorded under CuadraoHomePresentation.swift `CuadraoBalanceAmount`.

## ios/ArgusFoundation/Cuadrao/CuadraoBalanceBreakdown.swift
Base lines: 91. Status: M.

### Hunk 1: @@ -4,6 +4,8 @@ (+2/-0)
Class: SEAM
Used by: Connected/ConnectedCuadraoBalanceOverview.swift:94 (`linksToAccounts: false`)
Reason: Defaulted `linksToAccounts = true`; Preview caller (`CuadraoHomeBalanceChart.swift:138`) does not pass it.

### Hunk 2: @@ -32,22 +34,13 @@ (+7/-16)
Class: SEAM
Used by: as Hunk 1
Reason: With `linksToAccounts == true` the row is `NavigationLink(value: row.id) { rowContent(row) }.buttonStyle(.plain).accessibilityIdentifier("home-balance-change-" + id)`, the checkpoint tree. The `else` branch (plain row, `.accessibilityElement(children: .combine)`, no chevron) is connected-only.

### Hunk 3: @@ -71,6 +64,22 @@ (+16/-0)
Class: SEAM
Used by: as Hunk 1
Reason: `rowContent` is the checkpoint HStack (spacing 12, AX-size VStack variant, `Spacer(minLength: 8)`, chevron `.caption2 .tertiary`, vertical padding 14). The chevron is gated on `linksToAccounts`, `true` in the Preview.

### Hunk 4: @@ -79,13 +88,22 @@ (+13/-4)
Class: DRIFT
Used by: Connected/ConnectedCuadraoBalanceOverview.swift:94 (motivating caller; commit 38ea181ee)
Reason: The row amount and caption copy changed for two account states that the Preview can reach:
  (a) An account with no balance at either end. Checkpoint amount: `"—"` (via `row.closing.map(money) ?? "—"`), caption "Sin balance" / "No balance". Candidate amount: `CuadraoMissingCoverage.amount(spanish)` = "Sin datos" / "No data", caption unchanged.
  (b) An account with a closing but no opening inside a period whose totals do have an opening (`period.change != nil`), e.g. an account added mid-period from the Preview's add-account sheet. Checkpoint: the closing balance as the amount, no caption. Candidate: "Sin datos" / "No data" with the new Spanish caption "Sin inicio registrado" / "No recorded opening".
  Fixture defaults do not hit either state (`CanvasBalanceHistory.examples` gives every account with a balance an observation on every example day, CuadraoBalanceHistory.swift checkpoint lines 70-90), so the first screen is unchanged; interaction reaches both. 38ea181ee records this as a deviation needed by connected data. Under this contract a new Spanish string on a Preview-reachable row is DRIFT; the data-honesty argument would make it FIX only if the founder accepts the new wording.
Restore: In `accountValue`, put back `Text(row.change.map(signed) ?? row.closing.map(money) ?? "—").font(CuadraoTypography.rowAmount)` and the checkpoint caption rule (caption only when `row.change != nil` or `row.closing == nil`); drop `startingBalance`, the "Sin inicio registrado" branch and the `CuadraoMissingCoverage.amount` fallback. If connected needs the new wording, thread it behind a defaulted flag so the Preview keeps "—".

## ios/ArgusFoundation/Cuadrao/CuadraoBalanceHistory.swift
Base lines: 193. Status: M.

### Hunk 1: @@ -98,6 +98,11 @@ (+5/-0)
Class: SEAM
Used by: Connected/ConnectedCuadraoBalanceOverview.swift:84 (`CanvasBuiltBalanceHistory(points: points, now: .now)`)
Reason: A second initializer that accepts pre-totalled points. The fixture initializer and `points(on:)` are untouched.

## ios/ArgusFoundation/Cuadrao/CuadraoBalancePeriod.swift
Base lines: 57. Status: M.

### Hunk 1: @@ -23,7 +23,10 @@ (+3/-0)
Class: SEAM
Used by: Connected/ConnectedCuadraoBalanceOverview.swift:136 (`CanvasBalancePeriod(interval:opening:closing:...)` memberwise)
Reason: The two fixture initializers move into an `extension`, which lets the synthesized memberwise initializer exist. No computation changed.

## ios/ArgusFoundation/Cuadrao/CuadraoChartControls.swift
Base lines: 70. Status: M.

### Hunk 1: @@ -4,6 +4,7 @@ (+1/-0)
Class: SEAM
Used by: Cuadrao/CuadraoHomeInsightsLayout.swift:33 (fed `true` in the Preview; `false` on past pages only via Connected/ConnectedCuadraoBalanceOverview.swift:167)
Reason: Defaulted `distributionEnabled = true` on `CuadraoChartViewChoice`.

### Hunk 2: @@ -25,7 +26,8 @@ (+2/-1)
Class: SEAM
Used by: as Hunk 1
Reason: `.opacity(breakdown && !distributionEnabled ? 0.35 : 1)` and `.disabled(breakdown && !distributionEnabled)` resolve to `.opacity(1)` / `.disabled(false)` in the Preview, a no-op on the 44pt sage-circle buttons; labels "Distribución" / "Evolución" and ids `home-view-distribution` / `home-view-history` unchanged.

### Hunk 3: @@ -59,6 +61,7 @@ (+1/-0)
Class: SEAM
Used by: as Hunk 1
Reason: Same defaulted flag on `CuadraoInsightControls`.

### Hunk 4: @@ -66,5 +69,7 @@ (+4/-1)
Class: SEAM
Used by: as Hunk 1
Reason: Pass-through to `CuadraoChartViewChoice`.

## ios/ArgusFoundation/Cuadrao/CuadraoHomeDistribution.swift
Base lines: 162. Status: M.

### Hunk 1: @@ -9,9 +9,7 @@ (+0/-2)
Class: SEAM
Used by: Cuadrao/CuadraoDistributionContent.swift:27 (`reduceMotion` moved there)
Reason: `typeSize` was declared but never read at the checkpoint (only lines 12 and 14 mention it; no use). `reduceMotion` moved with `select(_:)`.

### Hunk 2: @@ -28,123 +26,42 @@ (+42/-100)
Class: SEAM
Used by: Connected/ConnectedCuadraoBalanceOverview.swift:207,213 (`CuadraoDistributionGroup`, `CuadraoDistributionContent`)
Reason: The body now builds a `balanceTitle` string (same three variants: "Balance neto · <date>", "Sin balances en este período", "Balance neto · Hoy"), `groups` (one per `kinds` entry with `accountCount = rows(kind).count`, always non-nil) and hands them to `CuadraoDistributionContent` with `balance`, `partial = accounts.count != known.count`, `assets`, `deductions` (nil when empty, as the checkpoint's `if !deductions.isEmpty`), `hasDeductionRows = !deductions.isEmpty` and the selection binding. `CanvasChartAsk` sits as the second child of an outer `VStack(spacing: 24)` whose first child is the content's own `VStack(spacing: 24)`; nesting two same-spacing leading VStacks yields the checkpoint's single-stack layout. Account rows and `accountRow` are untouched. `.sensoryFeedback(.selection, trigger:)` and the `onChange` that clears a vanished selection moved into the content with equivalent triggers (`selectedGroup` string, `groups.map(\.id)`).

## ios/ArgusFoundation/Cuadrao/CuadraoDistributionContent.swift
Base lines: 0. Status: A.

### Hunk 1: @@ -0,0 +1,142 @@ (+142/-0)
Class: NEW
Used by: Connected/ConnectedCuadraoBalanceOverview.swift:207,213
Reason: Extracted from CuadraoHomeDistribution.swift checkpoint lines 31-35 (`select`), 37-108 (body), 115-150 (`distributionBar`, `categoryRow`). Rendering unchanged for the Preview inputs: header (supporting secondary title, `currency` + amount with `home-distribution-total`, "Faltan balances por registrar"), controls slot, "Distribución de activos" row, `CuadraoAllocationBar` with id prefix `home-distribution-segment-`, "Todo" crumb with `home-distribution-all` and the chevron + tinted kind title, category rows (supporting title, chevron up/down, "N cuenta(s)" caption, percent + amount `rowAmount`, 3pt bar, vertical padding 18, id `home-distribution-<kind>`, value "Expandido" / "Contraído"), empty text "Tus balances positivos aparecerán aquí." with vertical padding 32, `Divider`, "Por descontar" `DisclosureGroup`, "Balance neto" row, spring/easeInOut selection animation. The `accountCount == nil` branches (no chevron, no count caption, value "Seleccionado") and the non-disclosure `deductionLabel` branch are connected-only and unreachable from `CuadraoHomeDistribution`. SEAM.

## ios/ArgusFoundation/Cuadrao/CuadraoSpendingChart.swift
Base lines: 247. Status: M.

### Hunk 1: @@ -4,6 +4,7 @@ (+1/-0)
Class: SEAM
Used by: Connected/ConnectedCuadraoBalanceOverview.swift:197
Reason: `CuadraoMissingCoverage.title` returns the same "Falta una parte de la historia" / "Part of the story is missing" that `emptyTitle` held inline.

### Hunk 2: @@ -61,20 +62,13 @@ (+7/-14)
Class: SEAM
Used by: Connected/ConnectedCuadraoBalanceOverview.swift:188,195
Reason: The header `VStack(spacing: 8)` became `CuadraoSpendingReading(currency:amount:caption:insight:)` with the same amount expression, the same caption expression (month-wide year for `.year`, `story.periodText`, "Gastos registrados" fallback) and `insight` passed only for `.populated` / `.emptyPeriod`, matching the checkpoint `if`.

### Hunk 3: @@ -110,7 +104,7 @@ (+1/-1)
Class: SEAM
Used by: as Hunk 1
Reason: `.unavailable` title reads from the shared helper; same string.

### Hunk 4: @@ -245,3 +239,25 @@ (+22/-0)
Class: SEAM
Used by: as Hunk 2
Reason: `CuadraoSpendingReading` is the checkpoint header verbatim (supporting secondary currency, `amount` font with `lineLimit(1).minimumScaleFactor(0.5)` and id `home-spending-total`, caption, optional insight with id `home-spending-insight`).

## ios/ArgusFoundation/Cuadrao/CuadraoHomeEmptyState.swift
Base lines: 46. Status: M.

### Hunk 1: @@ -13,34 +13,38 @@ (+24/-20)
Class: SEAM
Used by: Connected/ConnectedCuadraoHome.swift:334 (`CuadraoPersonalAccountsEmpty`)
Reason: The `if shared` moved from inside the `VStack(spacing: 28)` to the top of `body`; each branch now owns an identical `VStack(alignment: .leading, spacing: 28) { CuadraoChartState(title:detail:); buttons }.padding(.top, 16).frame(maxWidth: .infinity, alignment: .leading)`. Strings byte-identical: "Un lugar para\nlo de ustedes.", "Añade una cuenta que lleven juntos. Las cuentas personales siguen siendo privadas.", "Añadir cuenta conjunta", "Invitar a alguien", "Personas", "Empieza con una cuenta.", "Tu banco, tu efectivo o tus ahorros. Tú eliges por dónde empezar.", "Añadir cuenta". Additive id `accounts.add` on the personal Add button (`RegistrationButton` sets no identifier of its own, CuadraoRegistrationStyle.swift). The earlier audit's "rewrite" is a branch reorder with no rendering change.

## ios/ArgusFoundation/Cuadrao/CuadraoSpaceSelector.swift
Base lines: 31. Status: M.

### Hunk 1: @@ -4,28 +4,49 @@ (+41/-20)
Class: SEAM
Used by: Connected/ConnectedCuadraoSpaces.swift:10,14,25 (`CuadraoSpaceSelectorLayout`, `CuadraoSpaceLabel`)
Reason: `CuadraoSpaceSelectorLayout` is the checkpoint `HStack(spacing: 4) { ScrollViewReader { ScrollView(.horizontal) { HStack(spacing: 24) ... }.scrollIndicators(.hidden).onChange(of: selection) { proxy.scrollTo } }; CuadraoSectionAddButton }` with `addTitle` "Añadir o gestionar espacios" and id `cuadrao-spaces-add` supplied by the Preview wrapper. `CuadraoSpaceLabel` keeps `.subheadline` semibold/regular, primary/secondary, `minHeight: 44`, `contentShape`. Per-space `Button`, `.id(space.id)`, `.isSelected` trait and id `cuadrao-space-<id>` unchanged. The earlier audit's "rewrite" is an extraction with no rendering change.

## ios/ArgusFoundation/Cuadrao/CuadraoCanvas.swift
Base lines: 147. Status: M.

### Hunk 1: @@ -1,44 +1,35 @@ (+13/-22)
Class: UNSURE SEAM/DRIFT
Used by: no connected file reads `adaptsToAppearance`; every Cuadrao view reads the tokens (9746bb602)
Reason: `WelcomePalette.adaptsToAppearance` was `CuadraoDesignPreview.isActive` (DEBUG also `--cuadrao-release-ui`) and is now the constant `true`; the `fixed` light `Color` argument of each `adaptive` token is dropped. For the design-preview launch (`isActive == true`) every token already resolved through the `UIColor { trait }` path, and the light values of the dropped `fixed` colors equal the `light` UIColors (pine 0.16/0.29/0.25, moneyInput 0.18/0.47/0.40, sage 0.91/0.93/0.91, overlap 0.25/0.38/0.33, owedNegative 0.68/0.36/0.26, background white, surface 0.965, ink 0.08, onAccent white), so the Preview app renders byte-identical: SEAM. For any launch where `isActive` was `false` (the Xcode `#Preview("Home · First use") { CuadraoHomeCanvas().preferredColorScheme(.light) }` macros at the bottom of CuadraoHomeCanvas.swift, UI tests without the flag, and the connected app) the tokens were fixed and are now adaptive, which changes light mode for three tokens (`separator`: `Color(white: 0.85)` to `.separator` at 0.45 opacity; `border`: `Color(white: 0.80)` to `.separator`; `disabledInk`: `Color(white: 0.43)` to `Color.secondary`) and turns on the dark-appearance palette everywhere. The checkpoint comment "Every other launch, including Connected Cuadrao, keeps the shipped light tokens exactly" is deleted with it. If the founder counts the Xcode canvas previews as the Preview, this is DRIFT; if only the flagged app counts, SEAM with a connected-side rendering change the owner should accept explicitly.
Restore: Put back the `isActive`-gated `adaptsToAppearance` and the three-argument `adaptive(_ fixed:, _ light:, _ dark:)` with `guard adaptsToAppearance else { return fixed }`.

## ios/ArgusFoundation/Cuadrao/CuadraoAppShell.swift
Base lines: 0. Status: A.

### Hunk 1: @@ -0,0 +1,82 @@ (+82/-0)
Class: NEW
Used by: Connected/ConnectedCuadraoShell.swift:43
Reason: Extracted from CuadraoHomeCanvas.swift checkpoint lines 9 (`reduceMotion`), 28 (`pendingTab`), 37 (`navigationBarHeight`), 47 (`TabView(selection: tabSelection)`), 98-139 (`.cuadraoScrollBar` bottom bar with `CuadraoVoiceBar`, `CuadraoNavigationBar` in a 72pt ZStack with 64pt frame, horizontal 20, bottom 8, `.easeOut(0.18)` fade on recording; `.cuadraoSoftScrollEdges`; `.cuadraoVoicePresentation`; the temporary-chat `confirmationDialog`; `.tint(pine).foregroundStyle(ink)`), 143 (`.environment(\.cuadraoChat, chat)`) and 176-184 (`tabSelection`). Sub-items:

#### Hunk 1a: shell structure, bottom bar, voice presentation, dialog, tint
Class: SEAM
Reason: Verbatim, same strings and constants. `showsNavigation` and `compact` are computed by the caller from the checkpoint expressions.

#### Hunk 1b: `showProposal: (() -> Void)? = nil` (6f30bf2f9)
Class: SEAM
Reason: Optional so the connected shell can hide "Show example proposal"; the canvas passes `{ voiceProposal = .proposed }` and the shell wraps it with the checkpoint's `selection = .plan; chat.voice.presentation = .compact`. Preview behavior unchanged.

#### Hunk 1c: `.font(.body)` on the TabView (line 64, e6b7cf325 "restore the complete connected Cuadrao shell", no body text)
Class: UNSURE SEAM/DRIFT
Reason: The checkpoint root had no `.font` modifier (no `font(.body)` in CuadraoHomeCanvas.swift, CuadraoCanvas.swift or CuadraoDesignPreview.swift at the checkpoint). An explicit body font in the environment is a no-op for text that already defaults to body, but SwiftUI surfaces that pick a smaller default only when the environment carries no font (List section headers in the Profile and Search tab canvases, which use `Section`) can restyle. I could not render to confirm. If any such header or label changes, DRIFT; otherwise SEAM.
Restore: Delete the `.font(.body)` line; nothing in the Preview depended on it.

#### Hunk 1d: `.environment(\.cuadraoChat, chat)` scoped to the TabView (line 67)
Class: SEAM here, DRIFT in CuadraoHomeCanvas.swift Hunk 5c
Reason: Setting the environment inside the shell is fine for tab content; the drift is the canvas no longer setting it above its own `.sheet` / `.receiptPresentation`.

## Summary table

| file | SEAM | FIX | DRIFT | NEW | UNSURE |
|---|---|---|---|---|---|
| Cuadrao/CuadraoHomeCanvas.swift | 14 | 0 | 1 | 0 | 0 |
| Cuadrao/CuadraoHomePresentation.swift | 4 | 0 | 1 | 1 | 2 (FIX/DRIFT: FeedRow and BalanceAmount AX-size layouts) |
| Cuadrao/CuadraoHomeInsights.swift | 4 | 0 | 0 | 0 | 0 |
| Cuadrao/CuadraoHomeInsightsLayout.swift | 2 | 0 | 0 | 1 | 0 |
| Cuadrao/CuadraoHomeBalanceChart.swift | 6 | 0 | 0 | 0 | 0 |
| Cuadrao/CuadraoBalanceBreakdown.swift | 3 | 0 | 1 | 0 | 0 |
| Cuadrao/CuadraoBalanceHistory.swift | 1 | 0 | 0 | 0 | 0 |
| Cuadrao/CuadraoBalancePeriod.swift | 1 | 0 | 0 | 0 | 0 |
| Cuadrao/CuadraoChartControls.swift | 4 | 0 | 0 | 0 | 0 |
| Cuadrao/CuadraoHomeDistribution.swift | 2 | 0 | 0 | 0 | 0 |
| Cuadrao/CuadraoDistributionContent.swift | 1 | 0 | 0 | 1 | 0 |
| Cuadrao/CuadraoSpendingChart.swift | 4 | 0 | 0 | 0 | 0 |
| Cuadrao/CuadraoHomeEmptyState.swift | 1 | 0 | 0 | 0 | 0 |
| Cuadrao/CuadraoSpaceSelector.swift | 1 | 0 | 0 | 0 | 0 |
| Cuadrao/CuadraoCanvas.swift | 0 | 0 | 0 | 0 | 1 (SEAM/DRIFT: palette gate) |
| Cuadrao/CuadraoAppShell.swift | 3 | 0 | 0 | 1 | 1 (SEAM/DRIFT: `.font(.body)`) |
| **Total** | **51** | **0** | **3** | **4** | **4** |

The UNSURE column is added to the contract's four because four items hinge on a rendering I could not observe without a build; each names both candidate classes above.

## Highest-impact DRIFT

1. **CuadraoHomeCanvas.swift Hunk 5c.** "Preguntar a Cuadrao" from a receipt review and from an account opened inside the Novedades sheet now does nothing in the Preview: the `cuadraoChat` environment moved inside the shell and no longer reaches the canvas's `.sheet` / `.receiptPresentation`. Restore the `.environment(\.cuadraoChat, chat)` on the canvas root after `.environment(\.receiptWorkspace, ...)`.
2. **CuadraoBalanceBreakdown.swift Hunk 4.** Expanded Balance "What changed" rows: an account with no balance shows "Sin datos" instead of "—", and an account added mid-period shows "Sin datos" with the new caption "Sin inicio registrado" instead of its closing balance. Reachable by interaction, not by fixtures. Restore the checkpoint `accountValue` or gate the new wording behind a defaulted flag.
3. **CuadraoCanvas.swift Hunk 1 (UNSURE).** Palette always adapts. Flagged Preview launch is unchanged; Xcode `#Preview` canvases, unflagged UI-test launches and the connected app now get `.separator`-based separators and borders, `Color.secondary` disabled ink, and the dark palette in dark mode.
4. **CuadraoAppShell.swift Hunk 1c (UNSURE).** `.font(.body)` on the shell root was not at the checkpoint; it can restyle List section headers in the Profile and Search tabs. Delete it unless a rendering check shows nothing moved.
5. **CuadraoHomePresentation.swift, `CuadraoBalanceAmount` (i).** VoiceOver reads "DOP 1,500.00" for the hero amount instead of "1,500.00". No visual change. Delete the `.accessibilityLabel` on `amountLabel` to restore.
6. **CuadraoHomePresentation.swift, `CuadraoFeedRow` and `CuadraoBalanceAmount` (ii) (UNSURE FIX/DRIFT).** At accessibility type sizes the amount drops under the detail line (feed rows) and under the currency row (hero). Default size is byte-identical. FIX if the checkpoint truncated at AX sizes; verify at AX5 before keeping or reverting.

Suspects from the earlier audit that are not DRIFT in these files: `!period.changes.isEmpty` (never flips in the Preview; `changes` is empty only when `accounts` is empty, and then `closing` is already nil), `historical:` in CuadraoHomeInsights (untouched), `showProposal` default (canvas passes its closure), the voice proposal path (same three statements in the same order), `CuadraoHomeEmptyState` and `CuadraoSpaceSelector` (extractions with identical strings and modifiers).
