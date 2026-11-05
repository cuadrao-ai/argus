# Planning hunk classification (checkpoint 5753b5d7 -> HEAD)

Scope: `ios/ArgusFoundation/Cuadrao/Planning/` (15 files). Read-only. Line numbers for the checkpoint come from the hunk headers in the inventory diffs and were spot-checked against the checkpoint tree.

Evidence used beyond the diffs:
- Checkpoint `CuadraoHomeCanvas.swift:139` applied `.tint(WelcomePalette.pine).foregroundStyle(WelcomePalette.ink)` above the Plan canvas. Candidate Preview Home is hosted by `CuadraoAppShell.swift:65-66`, which applies the same two modifiers above the Plan canvas. So `CuadraoPlanPage`'s own copy of those modifiers inherits identical values in the Preview.
- `PlanFormat.space` (checkpoint `CuadraoPlanVisuals.swift:25-27`) already falls back to "Espacio archivado" / "Archived space", the same fallback the editor now uses through `host.spaces`.
- A Foundation script (`classify/datecheck.swift`, run with `swift`, no project build) confirmed: `.long` date in `es_DO` for 2026-10-12 prints "12 de octubre de 2026" and in `en_US` "October 12, 2026"; `budgetEdges` prints "1 oct." / "31 oct." and "Oct 1" / "Oct 31"; `PlanFormat.month(after:)` old vs new formulas agree for every count 0...600 in both locales.
- `CuadraoPlanPreview.save` is synchronous in both trees (`CuadraoPlanPreview.swift:136` candidate, `:161` checkpoint).
- `Cuadrao/CuadraoOrderedCollection.swift` (card swipe edit/archive and reorder) is byte-identical between trees. `CuadraoArchivedPlans` (inline "Retomar"/"Restore") lives in the unchanged tail of `CuadraoPlanCanvas.swift` and is not in any hunk.
- Commit reasons: faa7475fe "restore the shared Plan presentation" (Composition/Display, `plan-first-create`, `isolatedExample`); ba8c9e4f1 "restore approved connected plan details" (DetailPresentation, `plan-detail-amount`); 3f3b01273 (`scroll:` FinancialScrollContext); 4adaa8e45 (`stepped`); 9ada86f07 (PlanScenario); 22802377c (CuadraoPlanWhatIf); ac331ab07 (CuadraoPlanEditorHost); 91db621f4 (ConnectedPlanEditor host).

Class key: SEAM = Preview renders the same with defaults; FIX = defect fix; DRIFT = Preview look/behavior/copy/id changed; NEW = added file.

---

## ios/ArgusFoundation/Cuadrao/Planning/CuadraoForecastPlayground.swift
Base lines: 156. Status: M.

### Hunk 1: @@ -6,6 +6,7 @@ (+1/-0)
Class: SEAM
Used by: Plan/FinancialPlanForecast.swift:109-111 (`isolatedExample: true`)
Reason: Adds the stored `let isolatedExample: Bool`; no rendering on its own.

### Hunk 2: @@ -18,13 +19,21 @@ (+9/-1)
Class: SEAM
Used by: Plan/FinancialPlanForecast.swift:111
Reason: `init` gains `isolatedExample: Bool = false`; the Preview caller (`CuadraoPlanCanvas` via `CuadraoPlanExploreLink`) passes nothing, so the "Escenario de ejemplo" notice block (`forecast-example-notice`) is never inserted and the VStack(spacing: 28) starts with the same "Octubre · scope" block as the checkpoint.

### Hunk 3: @@ -79,16 +88,24 @@ (+12/-4)
Class: SEAM
Used by: Plan/FinancialPlanForecast.swift:111
Reason: Four copy sites switch on `isolatedExample`; the `false` branch keeps the approved strings verbatim: "Guardar este ritmo", "Volver a mi plan", "Ritmo guardado", "Solo cambia tu previsión. No mueve dinero.". Ids `forecast-apply` / `forecast-reset` unchanged. "Explorar escenarios" itself lives in `CuadraoPlanExploreLink` (see Composition) and is unchanged for the Preview.

---

## ios/ArgusFoundation/Cuadrao/Planning/CuadraoPlanCanvas.swift
Base lines: 206. Status: M.

### Hunk 1: @@ -25,26 +25,19 @@ (+12/-19)
Class: SEAM
Used by: Plan/FinancialPlanView.swift:44, Household/ConnectedHouseholdPlan.swift:14 (`CuadraoPlanPage`)
Reason: `ScrollView { VStack(spacing: 24) { header; Picker; content; footnote }.padding(.horizontal, 24).padding(.top, 20).padding(.bottom, bottomSpace) }.scrollIndicators(.hidden).background(WelcomePalette.background).cuadraoSoftScrollEdges()` moves verbatim into `CuadraoPlanPage` (Composition). The audience `Picker` (`plan-audience`, "Para ti"/"En grupo") becomes `CuadraoPlanAudiencePicker` with the same copy and style. `.toolbar(.hidden, ...)` stays here; its order relative to `cuadraoSoftScrollEdges()` does not affect rendering. The one addition inside `CuadraoPlanPage` (`.foregroundStyle(ink).tint(pine)`) is classified under Composition hunk 1b.

### Hunk 2a: @@ -71,21 +64,14 @@ (+8/-15) header extraction
Class: SEAM
Used by: Plan/FinancialPlanView.swift:45, Household/ConnectedHouseholdPlan.swift:17 (`CuadraoPlanHeader`)
Reason: `HStack(alignment: .top) { VStack(spacing: 6) { Text("Lo que viene").font(screen).accessibilityIdentifier("plan-heading") }; Spacer(); Button(plus, 44x44, sage Circle).accessibilityLabel(createTitle).accessibilityIdentifier("plan-create") }` moves verbatim into `CuadraoPlanHeader`; `createTitle` and the action are the same expressions; `canCreate` defaults to `true` so `.disabled(false)` adds nothing.

### Hunk 2b: @@ -71,21 +64,14 @@ context menu scope
Class: DRIFT (low)
Used by: none found (Preview-only dev affordance)
Reason: Checkpoint line 76-79 attached `.contextMenu { "Ver primer uso" / "Restablecer ejemplos" }` to the title `Text("Lo que viene")` only. Candidate attaches it to the whole `CuadraoPlanHeader` row, so a long-press on the "+" create button (and on the empty space between title and button) now also opens the menu, and the context-menu preview snapshot is the full row instead of the title.
Restore: Expose the title `Text` from `CuadraoPlanHeader` (for example a `title` ViewBuilder slot, or apply `.contextMenu` to the `Text("Lo que viene")` inside `CuadraoPlanHeader` through an optional parameter) and drop the `.contextMenu` from the call site in `CuadraoPlanCanvas.header`.

### Hunk 3a: @@ -95,78 +81,49 @@ forecastOverview
Class: SEAM
Used by: Plan/FinancialPlanForecast.swift:22 (`CuadraoPlanForecastSection`), :135 (`CuadraoPlanForecastValue`), :61 (`CuadraoPlanExploreLink`)
Reason: `VStack(spacing: 8) { HStack(spacing: 8) { "Tu mes" supporting/secondary; Spacer; scope menu or label }; VStack(spacing: 5) { title; amount }; chart; NavigationLink }` becomes `CuadraoPlanForecastSection(period:scope:content:explore:)`, whose body is the same `VStack(spacing: 8)` with `CuadraoPlanForecastHeading` (same HStack), then the `content` tuple (`CuadraoPlanForecastValue` with identical fonts/modifiers and `plan-month-ending`, then `PlanForecastChart` with the same arguments), then `CuadraoPlanExploreLink` ("Explorar escenarios", chevron, supporting/secondary, minHeight 44, `.buttonStyle(.plain)`, `plan-explore`). The scope `CuadraoChoiceMenu` / `CuadraoChoiceLabel` and their labels and ids are unchanged.

### Hunk 3b: @@ -95,78 +81,49 @@ forecastColdStart
Class: SEAM
Used by: Plan/FinancialPlanForecast.swift:53
Reason: `CuadraoPlanColdStart(spanish:detail:action:)` renders the same `VStack(spacing: 18)`: `PlanLandscape(.sunshine).frame(height: 135)`, "Lo que viene empieza aquí." feature, the detail subheadline/secondary (same Spanish string passed in), then the action with `.font(.subheadline.weight(.medium)).frame(minHeight: 44)` applied to the single Button, which is the same as applying them inline. Button copy "Explorar un mes de ejemplo" unchanged.

### Hunk 3c: @@ -95,78 +81,49 @@ plans
Class: SEAM (one additive id, see Composition hunk 4b)
Used by: Plan/FinancialPlanCards.swift:16, :28
Reason: `CuadraoPlanCollection(spanish:isEmpty:create:rows:archives:)` keeps the order Text("Tus planes" section) -> `CuadraoOrderedCollection` (same identifier closure, open/edit/archive/reorder, `PlanCard`) -> `CuadraoPlanArchiveLink` ("Archivados", archivebox, supporting/secondary, minHeight 44, `plan-archives`) -> empty-state card (same copy "¿Qué tienes en mente?", "Un viaje, un respiro, llegar a fin de mes con más espacio.", `PlanPrimaryButton("Crear mi primer plan", symbol: "plus")`, padding 24, surface, radius 26). `canCreate` defaults to `true`.

Unchanged and verified present: `CuadraoArchivedPlans` with inline `Button("Retomar" / "Restore").buttonStyle(.bordered)`, "Nada archivado" empty state, sheets, the reset confirmation dialog, and the `CuadraoPlanEditor` creation sheet with its `onSave { if store.plan(route.plan.id) != nil { path.append(id) } }`.

---

## ios/ArgusFoundation/Cuadrao/Planning/CuadraoPlanComposition.swift
Base lines: 0. Status: A (113 lines).

### Hunk 1a: @@ -0,0 +1,113 @@ `CuadraoPlanPage`
Class: NEW / SEAM
Used by: Plan/FinancialPlanView.swift:44, Household/ConnectedHouseholdPlan.swift:14
Reason: Extracted from checkpoint `CuadraoPlanCanvas.swift:28-48` (ScrollView, VStack(spacing: 24), Picker 31-34, paddings 43, `.scrollIndicators(.hidden)` 45, `.background` 46, `.cuadraoSoftScrollEdges()` 48). Optional `audience` binding; the Preview passes `$together`, so the picker renders in the same slot. `bottomSpace` default 90 matches the checkpoint default.

### Hunk 1b: `CuadraoPlanPage` line 22 `.foregroundStyle(WelcomePalette.ink).tint(WelcomePalette.pine)`
Class: SEAM (UNSURE between SEAM and DRIFT only in principle; in practice identical)
Used by: Plan/FinancialPlanView.swift:44 (connected host needs it because it is not under `CuadraoAppShell`'s modifiers in every presentation)
Reason: Not in the checkpoint canvas, but the checkpoint inherited the same two values from `CuadraoHomeCanvas.swift:139`, and the candidate Preview inherits them from `CuadraoAppShell.swift:65-66` (candidate `CuadraoHomeCanvas.swift:44` hosts through `CuadraoAppShell`). Applying the same ink foreground and pine tint again on the ScrollView changes no color. Pushed destinations (`CuadraoPlanDetail`, playground, archived list) still get them from the shell, as before.

### Hunk 2: `CuadraoPlanForecastSection`
Class: NEW / SEAM
Used by: Plan/FinancialPlanForecast.swift:22
Reason: Structure of checkpoint `CuadraoPlanCanvas.swift:98-131` (VStack(spacing: 8) { heading; value; chart; link }). The heading moved to `CuadraoPlanForecastHeading` (Display). The ViewBuilder tuple flattens into the same VStack, so spacing is unchanged.

### Hunk 3: `CuadraoPlanExploreLink`
Class: NEW / SEAM
Used by: Plan/FinancialPlanForecast.swift:61 (`example: true`)
Reason: Checkpoint `CuadraoPlanCanvas.swift:122-129` verbatim. `example` defaults to `false`, so the Preview prints "Explorar escenarios"; "Explorar escenarios de ejemplo" only appears for the connected host.

### Hunk 4a: `CuadraoPlanColdStart`
Class: NEW / SEAM
Used by: Plan/FinancialPlanForecast.swift:53
Reason: Checkpoint `CuadraoPlanCanvas.swift:134-143`; title, landscape height 135, fonts identical; `detail` and the action are passed through by the Preview with the checkpoint strings.

### Hunk 4b: `CuadraoPlanCollection`
Class: NEW / SEAM, plus one DRIFT (low, additive id)
Used by: Plan/FinancialPlanCards.swift:16
Reason: Checkpoint `CuadraoPlanCanvas.swift:147-170` in the same order. Additive: `.accessibilityIdentifier("plan-first-create")` on the empty-state `PlanPrimaryButton` (checkpoint had no identifier) and `.disabled(!canCreate)` with `canCreate = true`. Not visible to a user, but it is a new id on the Preview tree.
Restore: Remove `.accessibilityIdentifier("plan-first-create")` from the empty-state button, or make it a parameter defaulting to `nil` so the Preview tree carries no id there.

### Hunk 5: `CuadraoPlanArchiveLink`
Class: NEW / SEAM
Used by: Plan/FinancialPlanCards.swift:28
Reason: Checkpoint `CuadraoPlanCanvas.swift:155-160` verbatim ("Archivados", `archivebox`, supporting/secondary, minHeight 44, `plan-archives`).

---

## ios/ArgusFoundation/Cuadrao/Planning/CuadraoPlanDetail.swift
Base lines: 241. Status: M.

### Hunk 1: @@ -1,5 +1,4 @@ (+0/-1)
Class: SEAM
Used by: n/a
Reason: Drops `import Charts`; the chart moved to `CuadraoPlanWhatIf`.

### Hunk 2a: @@ -8,60 +7,51 @@ state removal
Class: SEAM
Used by: n/a
Reason: `draftAmount`, `sliderCeiling`, `exact`, `saved` and the `baseline/amount/changed` helpers (checkpoint lines 11-12, 14, 17, 21-23) move into `CuadraoPlanWhatIf` as private state.

### Hunk 2b: @@ -8,60 +7,51 @@ `CuadraoPlanDetailPage` wrapper
Class: SEAM
Used by: Plan/FinancialGoalView.swift:125, FinancialBudgetView.swift:117, FinancialDebtView.swift:121 (all with `scroll:`)
Reason: Checkpoint lines 28-29, 47-49 (`ScrollView { VStack(.leading, spacing: 20) {...}.padding(24).padding(.bottom, bottomSpace) }.background(WelcomePalette.background).cuadraoSoftScrollEdges()`) now come from `CuadraoPlanDetailPage(bottomSpace:)` with `scroll == nil`, which takes the plain `ScrollView` branch. Children (`heading`, landscape states with the same strings and heights 135/100, what-if, "Actualizar progreso" button with `plus.circle`, minHeight 44, `plan-record-progress`, `facts`, `household`, `PlanPreviewFootnote`) are the same views in the same order. "Tu ritmo aparecerá con tus primeros movimientos." unchanged.

### Hunk 2c: @@ -8,60 +7,51 @@ `CuadraoPlanWhatIf` replaces `playground(plan)`
Class: SEAM (rendering); one behavior DRIFT listed under CuadraoPlanWhatIf hunk 1b
Used by: Plan/FinancialGoalView.swift:132, FinancialBudgetView.swift:128, FinancialDebtView.swift:129
Reason: Same visibility condition `plan.remaining > 0 || plan.kind == .budget`. `apply` performs the checkpoint's save (`target` for budget, `monthly` otherwise, `store.save(updated)`). `showsDisclosure` defaults to `false`, so no extra text under the block (the facts disclosure still shows it).

### Hunk 2d: @@ -8,60 +7,51 @@ `CuadraoPlanDetailOptions`
Class: SEAM
Used by: Plan/FinancialGoalView.swift:206, FinancialBudgetView.swift:191, FinancialDebtView.swift:199
Reason: Checkpoint lines 52, 57-58 (`Menu { ... } label: { Image("ellipsis").frame(44x44) }.accessibilityLabel("Opciones del plan").accessibilityIdentifier("plan-detail-options")`) extracted; the three menu items ("Preguntar a Cuadrao" with `plan-open-chat`, "Editar plan", "Archivar") stay at the call site unchanged.

### Hunk 2e: @@ -8,60 +7,51 @@ exact-amount sheet removed
Class: SEAM
Used by: n/a
Reason: Checkpoint lines 61-64 `.sheet(isPresented: $exact) { PlanExactAmount(...) }` now lives inside `CuadraoPlanWhatIf` with the same title "Mi margen mensual" / "Cada mes", minimum 1, maximum `CanvasMoney.maximumValue`. Presenting from a child view inside the ScrollView shows the same sheet. The `progressEntry` sheet and the archive dialog "¿Dejamos este plan en pausa?" / "Archivar plan" are untouched (candidate lines 60-61).

### Hunk 3a: @@ -79,111 +69,31 @@ `.onChange(of: plan)` and `.sensoryFeedback` removed
Class: SEAM (behavioral nuance recorded as DRIFT under WhatIf 1b)
Used by: n/a
Reason: Both move into `CuadraoPlanWhatIf` (`.onChange(of: scenario)`, `.sensoryFeedback(.success, trigger: saved)`); same haptic on the same event in the Preview because the store saves synchronously.

### Hunk 3b: @@ -79,111 +69,31 @@ heading -> `CuadraoPlanDetailHeading`
Class: SEAM, plus DRIFT (low, additive id) recorded under DetailPresentation hunk 2
Used by: Plan/FinancialGoalView.swift:236, FinancialBudgetView.swift:217, FinancialDebtView.swift:226
Reason: Checkpoint lines 88-98 (space caption, name feature + landscape 70x76, amount secondaryAmount + annotation caption) now come from `CuadraoPlanDetailDisplay`; the status slot carries the same "Lo hiciste. Un plan menos, más posibilidades." Label with `checkmark.seal` in `plan.look.color`. Amount and annotation strings ("por pagar" / `recordedTitle`) are built by the same expressions.

### Hunk 3c: @@ -79,111 +69,31 @@ playground + chart removed
Class: SEAM
Used by: n/a
Reason: Checkpoint lines 105-170 (`playground`) move to `CuadraoPlanWhatIf.body`; see that file for the line-by-line comparison.

### Hunk 3d: @@ -79,111 +69,31 @@ facts -> `CuadraoPlanDetailFacts` + `PlanScenario.disclosure`
Class: SEAM
Used by: Plan/FinancialGoalView.swift:263, FinancialBudgetView.swift:131, FinancialDebtView.swift:140
Reason: Checkpoint lines 173-185: `DisclosureGroup { VStack(.leading, spacing: 16) {...}.font(.subheadline).padding(.top, 16) } label: { "Los detalles, claros" subheadline medium }` extracted unchanged. The three `LabeledContent` rows and "Interés anual" are unchanged. The disclosure strings now come from `PlanScenario.disclosure(spanish:)`; for the Preview fixture (12 of 31 days, 2026-10-12) they print exactly "Proyección simple con 12 días registrados de un mes de 31 días. No es un gasto confirmado." and "Escenario al 12 de octubre de 2026. Aportes mensuales constantes. Sin rendimientos, compras nuevas ni comisiones. El plan no mueve dinero." (verified by script).

### Hunk 4: @@ -199,43 +109,3 @@ (+0/-40)
Class: SEAM
Used by: n/a
Reason: `private struct PlanDetailChart` (checkpoint 203-241) moves to `CuadraoPlanWhatIf.swift` as a private struct over `PlanScenario`; comparison under that file.

---

## ios/ArgusFoundation/Cuadrao/Planning/CuadraoPlanDetailPresentation.swift
Base lines: 0. Status: A (83 lines).

### Hunk 1: `CuadraoPlanDetailDisplay`, `CuadraoPlanDetailPage`
Class: NEW / SEAM
Used by: Plan/FinancialGoalView.swift:125, FinancialBudgetView.swift:117, FinancialDebtView.swift:121 (`scroll:`), Connected/ConnectedCuadraoHome.swift:77, Household/ConnectedHouseholdHome.swift:41
Reason: Page extracted from checkpoint `CuadraoPlanDetail.swift:28-29, 47-49`. `scroll: FinancialScrollContext?` defaults to `nil` (commit 3f3b01273, scroll restoration for the connected app); the Preview path is a plain `ScrollView` with the same `VStack(spacing: 20)`, `.padding(24).padding(.bottom, bottomSpace)`, background and soft edges.

### Hunk 2: `CuadraoPlanDetailHeading`
Class: NEW / SEAM, plus DRIFT (low, additive id)
Used by: Plan/FinancialGoalView.swift:236-239, FinancialBudgetView.swift:217-220, FinancialDebtView.swift:226-229 (`amountIdentifier`)
Reason: Extracted from checkpoint `CuadraoPlanDetail.swift:88-98`; same VStack(spacing: 12), caption space, feature name with `fixedSize`, `PlanLandscape` 70x76, secondaryAmount + caption annotation, then `status()` in the same position. Additive: `.accessibilityIdentifier(display.amountIdentifier)` defaulting to `"plan-detail-amount"` on the amount Text; the checkpoint amount had no identifier (commit ba8c9e4f1).
Restore: Make `amountIdentifier` optional (`String? = nil`) and apply the identifier only when set, so the Preview amount carries no id as at the checkpoint.

### Hunk 3: `CuadraoPlanDetailFacts`
Class: NEW / SEAM
Used by: Plan/FinancialGoalView.swift:263, FinancialBudgetView.swift:131, FinancialDebtView.swift:140
Reason: Checkpoint `CuadraoPlanDetail.swift:173-174, 184-185` verbatim (DisclosureGroup, VStack(.leading, 16), `.font(.subheadline).padding(.top, 16)`, label "Los detalles, claros").

### Hunk 4: `CuadraoPlanDetailOptions`
Class: NEW / SEAM
Used by: Plan/FinancialGoalView.swift:206, FinancialBudgetView.swift:191, FinancialDebtView.swift:199
Reason: Checkpoint `CuadraoPlanDetail.swift:52, 57-58` verbatim (ellipsis 44x44, "Opciones del plan", `plan-detail-options`).

---

## ios/ArgusFoundation/Cuadrao/Planning/CuadraoPlanDisplay.swift
Base lines: 0. Status: A (116 lines).

### Hunk 1: `CuadraoPlanHeader`
Class: NEW / SEAM (the context-menu scope change is the Canvas hunk 2b DRIFT)
Used by: Plan/FinancialPlanView.swift:45, Household/ConnectedHouseholdPlan.swift:17
Reason: Checkpoint `CuadraoPlanCanvas.swift:74-90` minus the `.contextMenu` (now applied by the caller to the whole header). `canCreate = true`, `createIdentifier = "plan-create"` reproduce the checkpoint.

### Hunk 2: `CuadraoPlanAudiencePicker`
Class: NEW / SEAM
Used by: none found outside Planning (only `CuadraoPlanPage`)
Reason: Checkpoint `CuadraoPlanCanvas.swift:31-34` verbatim.

### Hunk 3: `CuadraoPlanForecastHeading`, `CuadraoPlanForecastValue`
Class: NEW / SEAM
Used by: Plan/FinancialPlanForecast.swift:135 (`CuadraoPlanForecastValue`)
Reason: Checkpoint `CuadraoPlanCanvas.swift:99-110` (HStack(spacing: 8), supporting/secondary period, Spacer, scope) and `113-120` (VStack(spacing: 5), subheadline/secondary title, amount font, `monospacedDigit`, `numericText`, `minimumScaleFactor(0.65)`, `lineLimit(1)`, identifier) verbatim.

### Hunk 4: `CuadraoPlanCardDisplay`, `CuadraoPlanCard`
Class: NEW / SEAM
Used by: Plan/FinancialPlanCards.swift:22, :141, :154; Household/HouseholdPlanViews.swift:47; Household/ConnectedHouseholdPlan.swift:60, :84
Reason: Checkpoint `CuadraoPlanVisuals.swift:88-120` (`PlanCard.body`). `annotation` and `progress` are optional for connected hosts, but `PlanCard` always passes both, so the Preview card still draws the caption ("por pagar" for debt, "N%" otherwise) and the 4pt progress capsule for every kind, debt included (`plan.progress` = recorded/target). `notice` is `nil` from `PlanCard`, so no extra caption. Padding 22, radius 28, 0.065 tint, contentShape unchanged.

---

## ios/ArgusFoundation/Cuadrao/Planning/CuadraoPlanEditor.swift
Base lines: 155. Status: M.

Defaults check: the Preview constructs `CuadraoPlanEditorHost(store:accounts:initial:spanish:onSave:)` (EditorHost hunk 1), which yields `kindLocked=false`, `currencyLocked=false`, `showsTarget/Recorded/Rate/Look=true`, `monthlyRequired=true`, `monthlyTitle=nil`, default identifiers, `canSave` always true, `saving=false`, `dismissesOnSave=true`, `spaces` = `visibleSpaces` titled by `PlanFormat.space`. Every gate below collapses to the checkpoint.

### Hunk 1: @@ -1,11 +1,11 @@ (+5/-5)
Class: SEAM
Used by: Plan/ConnectedPlanEditor.swift:41 (`CuadraoPlanEditor(host:...)`)
Reason: Generic `<Details, Footer>` with `host`, `details`, `footer`; the checkpoint signature survives as the extension init in hunk 6, and both Preview callers (`CuadraoPlanCanvas.swift:49`, `CuadraoPlanDetail.swift:69` candidate) still use it.

### Hunk 2: @@ -13,44 +13,56 @@ (+30/-18)
Class: SEAM
Used by: Plan/ConnectedPlanEditor.swift:71-81 (identifiers, host flags)
Reason: `valid` adds `(!host.showsTarget && id == ids.target)` (false), `!host.showsTarget || target range` (same range), monthly lower bound `host.monthlyRequired ? 0.01 : 0` (0.01), `!host.showsTarget ||` on the debt check (same), `host.spaces.contains` over the same ids, `host.canSave` (true). Kind chips render when `!editing && !host.kindLocked` (same as `!editing`). Name field id `ids.name` = "plan-name". Amount card: `showsTarget` true takes the checkpoint branch (target primary row, Divider, "Cada mes" monthly row with `plan-target` / `plan-monthly`). `details($draft)` is `EmptyView`, which adds no spacing in the VStack. Space menu titles come from `host.spaces` built with `PlanFormat.space`; the fallback string "Espacio archivado" / "Archived space" is the same one `PlanFormat.space` returned.

### Hunk 3: @@ -61,28 +73,34 @@ (+24/-18)
Class: SEAM
Used by: Plan/ConnectedPlanEditor.swift:80-81 (`showsLook`, `showsRecorded`, `showsRate`, `showsTarget`)
Reason: Look picker DisclosureGroup "Darle mi estilo" shown when `showsLook` (true). "Punto de partida" shown when `showsRecorded || (debt && showsRate)` (true); inside, the recorded row and the debt rate row ("Interés anual (%)", `plan-rate`, assumption caption) are unchanged. Collapsed assumption line gated on `showsRate` (true). Estimate block ("Ya llegaste." / month) gated on `showsTarget && showsRecorded` (true).

### Hunk 4: @@ -96,7 +114,7 @@ (+1/-1)
Class: SEAM
Used by: Plan/ConnectedPlanEditor.swift:41 (footer slot)
Reason: `footer()` is `PlanPreviewFootnote(spanish:)` through the extension init, so "Vista previa · datos de ejemplo" renders in the same slot.

### Hunk 5: @@ -108,23 +126,25 @@ (+6/-4)
Class: SEAM
Used by: Plan/ConnectedPlanEditor.swift:80-81 (`save`, `saving`, `dismissesOnSave`)
Reason: Save button: `host.save(draft)` then `dismiss()`. The host closure is `store.save(plan); onSave?(plan.id)`, so the order becomes save -> onSave -> dismiss instead of save -> dismiss -> onSave; both run synchronously in one tap, and the only Preview `onSave` (`CuadraoPlanCanvas`: `path.append(id)`) commits in the same transaction either way. `.disabled(!valid || host.saving)` and the opacity use `saving=false`; Cancel `.disabled(false)`; `interactiveDismissDisabled(draft != initial || false)`. Title "Guardar cambios" / "Crear plan", `plan-save`, "Cancelar", "¿Descartar cambios?" / "Descartar" unchanged. `monthlyTitle` falls back to "Cada mes".

### Hunk 6: @@ -141,15 +161,22 @@ (+10/-3)
Class: SEAM
Used by: Plan/ConnectedPlanEditor.swift:71-72 (`CuadraoPlanEditorIdentifiers`)
Reason: Kind chip ids via `ids.kind(kind)` = "plan-kind-<raw>"; `amountRow` passes `currencyIdentifier: ids.currency` = "plan-edit-currency" and uses `currencyLocked` (= `editing` for the Preview) for `currencySelectable` / `showCurrencyLock`, identical to `editing`. The extension init rebuilds the checkpoint call with `EmptyView` details and `PlanPreviewFootnote` footer.

---

## ios/ArgusFoundation/Cuadrao/Planning/CuadraoPlanEditorHost.swift
Base lines: 0. Status: A (45 lines).

### Hunk 1: @@ -0,0 +1,45 @@
Class: NEW / SEAM (no rendering)
Used by: Plan/ConnectedPlanEditor.swift:71-72, :80-81
Reason: Values extracted from checkpoint `CuadraoPlanEditor.swift:16` (`editing`), `:52-53` (visible spaces and `PlanFormat.space` titles), `:111` (`store.save(draft); onSave?(draft.id)`). All flag defaults reproduce the checkpoint editor (see Editor defaults check).

---

## ios/ArgusFoundation/Cuadrao/Planning/CuadraoPlanForecastChart.swift
Base lines: 0. Status: A (88 lines).

### Hunk 1: @@ -0,0 +1,88 @@
Class: NEW / SEAM
Used by: Plan/FinancialPlanForecast.swift:184 (`CuadraoPlanChartPoint`), :201 (`CuadraoPlanChartTick`), :213-217 (`CuadraoPlanForecastChart`, `stepped: true`)
Reason: Extracted from checkpoint `CuadraoPlanVisuals.swift:136-182` (`PlanForecastChart.body`). Same mark sequence and styles: recorded `AreaMark` (pine 0.13 gradient) + `LineMark` 2.5 round linear; comparison dashed `[3,5]` 1.5 secondary 0.3 (empty array when `comparison == daily`, matching the `if let comparison, comparison != daily` guard); projected dashed `[5,5]` 2.5 pine; today `RuleMark` dashed `[2,4]`; zero rule when `detailed`; selected rule + `PointMark` 45. X values are `Double` instead of `Int`, domain `1.0...31.0`, ticks at 1/12/31 with the same titles ("Hoy, 12" / "Today, 12", "N oct.") and the same anchor rule (last -> topTrailing, first -> topLeading). Heights 95/170/150, `plan-forecast-chart`, accessibility label and value unchanged. Two opt-ins never fire in the Preview: `stepped` defaults false (`.linear`, the checkpoint default), and the single-point `PointMark` needs `projected.count == 1` (the Preview projection has 20 points). Selection binding rounds the `Double` to the nearest day, which is what `chartXSelection` on an `Int` binding did.

---

## ios/ArgusFoundation/Cuadrao/Planning/CuadraoPlanPreview.swift
Base lines: 202. Status: M.

### Hunk 1: @@ -55,39 +55,14 @@ (+8/-33)
Class: SEAM
Used by: Plan/ConnectedPlanScenario.swift:17, :27, :37 (`PlanScenario(...)`)
Reason: `remaining`, `progress`, `months(at:)`, `outstanding`, `projectedValue(at:monthly:)`, `monthlyAmount(finishingIn:)` (checkpoint 58-89) move to `PlanScenario`; `CanvasPlan` forwards through `scenario`, with `budgetDays = .preview` (elapsed 12) replacing the `CanvasForecast.today` constant (12). Codable shape unchanged.

### Hunk 2: @@ -106,8 +81,8 @@ (+2/-2)
Class: SEAM
Used by: none found outside Planning
Reason: `CanvasForecast.today = PlanScenarioDays.preview.elapsed` (12) and `lastDay = .total` (31), same values.

---

## ios/ArgusFoundation/Cuadrao/Planning/CuadraoPlanVisuals.swift
Base lines: 192. Status: M.

### Hunk 1: @@ -1,5 +1,4 @@ (+0/-1)
Class: SEAM
Used by: n/a
Reason: Drops `import Charts`; chart moved to `CuadraoPlanForecastChart.swift`.

### Hunk 2: @@ -17,8 +16,8 @@ (+2/-2)
Class: SEAM
Used by: none found outside Planning (`CuadraoPlanWhatIf` passes `from: scenario.today`)
Reason: `month(after:spanish:from:)` adds months to `PlanScenario.previewToday` (2026-10-12) instead of building `month: 10 + count, day: 12`; verified equal output for counts 0...600 in both locales.

### Hunk 3: @@ -85,38 +84,14 @@ (+8/-32)
Class: SEAM
Used by: Plan/FinancialPlanCards.swift:22, Household/HouseholdPlanViews.swift:47 (`CuadraoPlanCard`)
Reason: `PlanCard.body` becomes `CuadraoPlanCard(display:)` with every string built by the checkpoint expressions: amount (`remaining` for debt, `recorded` otherwise), annotation ("por pagar" / "to go" for debt, else percent), `progress: plan.progress` (so the debt card keeps its bar), detail ("de X este mes", "Deuda inicial: X", "Meta: X"). Layout constants are in Display hunk 4.

### Hunk 4: @@ -128,58 +103,24 @@ (+14/-48)
Class: SEAM
Used by: n/a (Preview callers `CuadraoPlanCanvas`, `CuadraoForecastPlayground` keep the `PlanForecastChart` API; `selected` becoming `private` has no external reader in the checkpoint)
Reason: Body delegates to `CuadraoPlanForecastChart` with the checkpoint domain, ticks, today, comparison guard, heights and accessibility strings ("Balance de octubre. Línea continua: registrado. Línea punteada: estimación."); see ForecastChart hunk 1.

---

## ios/ArgusFoundation/Cuadrao/Planning/CuadraoPlanWhatIf.swift
Base lines: 0. Status: A (136 lines).

### Hunk 1a: @@ -0,0 +1,136 @@ `CuadraoPlanWhatIf` body and sheet
Class: NEW / SEAM
Used by: Plan/FinancialGoalView.swift:132, FinancialBudgetView.swift:128, FinancialDebtView.swift:129 (`showsDisclosure: true`, `apply` nil or set)
Reason: Extracted from checkpoint `CuadraoPlanDetail.swift:105-170` (`playground`), `:61-64` (exact sheet), `:11-12, 14, 17, 21-23` (state and helpers), `:82, 84` (`onChange`, `sensoryFeedback`). Line-by-line the same: headline strings ("Dale aire a tu mes.", "Más cerca de soltarla.", "A tu ritmo, llegarías en"), budget pace line with `budgetDays.total` (31, same as `CanvasForecast.lastDay`), estimated month in `.title` rounded with `plan-estimated-date`, "N meses antes/después", chart, the slider card (padding 16, 0.065 tint, radius 24, `plan-detail-exact`, `plan-detail-slider`, range `1...max(1000, baseline*3, ceiling)`, "Probar otro monto"), "Llegar en N meses" chips with `plan-in-N-months`, "Aplicar a mi plan" (`plan-detail-apply`, rendered because the Preview passes `apply`), "Deshacer prueba" (`plan-detail-reset`), "Tu plan, a tu ritmo." in pine. `showsDisclosure` defaults false. The exact sheet keeps "Mi margen mensual" / "Cada mes".

### Hunk 1b: `.onChange(of: scenario)` and deferred `saved`
Class: DRIFT (low, behavior)
Used by: Plan/FinancialGoalView.swift:132 and siblings (needed because a connected write is asynchronous, per commit 22802377c)
Reason: Checkpoint `CuadraoPlanDetail.swift:82` reset `draftAmount` and `sliderCeiling` on any change of `plan` (including a rename or space move from the editor sheet). Candidate resets only when `scenario` changes (kind, currency, target, recorded, monthly, annualRate, look), so after editing the plan's name or space with a what-if draft pending, the slider now keeps the draft instead of snapping back. Also, "Tu plan, a tu ritmo." and the success haptic are set in `onChange` after the apply rather than inline; with the synchronous Preview store this fires in the same tap, so no visible difference there.
Restore: Give `CuadraoPlanWhatIf` an optional `resetToken: AnyHashable?` (or pass the whole `CanvasPlan` equality) and have `CuadraoPlanDetail` pass `plan`, so the draft resets on any plan change as at the checkpoint; keep the deferred `saved` since it is observably identical in the Preview.

### Hunk 1c: `private struct PlanDetailChart`
Class: NEW / SEAM
Used by: n/a (private)
Reason: Checkpoint `CuadraoPlanDetail.swift:203-241` over `PlanScenario`: same horizon rule (`budgetDays.total` = 31 for budget; `min(24, max(6, months ?? 12))`), same `upperBound`, same `RuleMark` + two `LineMark` series with the same styles, height 110, hidden axes, same accessibility label, edge labels from `budgetEdges` ("1 oct." / "31 oct.", "Oct 1" / "Oct 31", verified) or "Hoy" / "N meses", legend "Punteado: estimado · gris: plan guardado".

---

## ios/ArgusFoundation/Cuadrao/Planning/PlanAmountInput.swift
Base lines: 36. Status: M.

### Hunk 1: @@ -11,13 +11,14 @@ (+2/-1)
Class: SEAM
Used by: Plan/ConnectedPlanEditor.swift:71-72 via `CuadraoPlanEditorIdentifiers.currency`
Reason: `currencyIdentifier = "plan-edit-currency"` default passed through to `PlanCurrencyChoice`; same id as the checkpoint literal.

---

## ios/ArgusFoundation/Cuadrao/Planning/PlanCurrencyChoice.swift
Base lines: 23. Status: M.

### Hunk 1: @@ -5,6 +5,7 @@ (+1/-0)
Class: SEAM
Used by: PlanAmountInput (Planning) only
Reason: `identifier = "plan-edit-currency"` default.

### Hunk 2: @@ -17,7 +18,7 @@ (+1/-1)
Class: SEAM
Used by: same
Reason: `.accessibilityIdentifier(identifier)` resolves to the checkpoint literal.

---

## ios/ArgusFoundation/Cuadrao/Planning/PlanScenario.swift
Base lines: 0. Status: A (84 lines).

### Hunk 1: @@ -0,0 +1,84 @@ math
Class: NEW / SEAM
Used by: Plan/ConnectedPlanScenario.swift:17, :27, :37
Reason: `remaining`, `progress`, `months(at:)`, `outstanding`, `projectedValue`, `monthlyAmount` are the checkpoint `CuadraoPlanPreview.swift:58-89` bodies with `budgetDays.elapsed` (12) in place of `CanvasForecast.today` (12).

### Hunk 2: `disclosure(spanish:)`
Class: NEW / SEAM
Used by: Plan/FinancialGoalView.swift:132 and siblings through `showsDisclosure`, Accounts/FinancialActivityDetailView.swift:74
Reason: Reproduces checkpoint `CuadraoPlanDetail.swift:180-182` for the fixture: "Proyección simple con 12 días registrados de un mes de 31 días. No es un gasto confirmado." and "Escenario al 12 de octubre de 2026. Aportes mensuales constantes. Sin rendimientos, compras nuevas ni comisiones. El plan no mueve dinero." (script-verified). The singular "1 día registrado" branch cannot occur with the 12-day fixture.

### Hunk 3: `budgetEdges(spanish:)`, `dayLabel`
Class: NEW / SEAM
Used by: `CuadraoPlanWhatIf.PlanDetailChart` (Planning) only
Reason: Reproduces checkpoint `CuadraoPlanDetail.swift:233-237` literals for October: "1 oct." / "31 oct." and "Oct 1" / "Oct 31" (script-verified with `es_DO` "MMM" = "oct", period re-appended).

---

## Summary

| file | SEAM | FIX | DRIFT | NEW |
|---|---|---|---|---|
| CuadraoForecastPlayground.swift | 3 | 0 | 0 | 0 |
| CuadraoPlanCanvas.swift | 5 | 0 | 1 | 0 |
| CuadraoPlanComposition.swift | 5 (incl. 1b) | 0 | 1 (additive id) | 1 |
| CuadraoPlanDetail.swift | 10 | 0 | 0 (its DRIFTs are recorded in WhatIf 1b and DetailPresentation 2) | 0 |
| CuadraoPlanDetailPresentation.swift | 4 | 0 | 1 (additive id) | 1 |
| CuadraoPlanDisplay.swift | 4 | 0 | 0 | 1 |
| CuadraoPlanEditor.swift | 6 | 0 | 0 | 0 |
| CuadraoPlanEditorHost.swift | 1 | 0 | 0 | 1 |
| CuadraoPlanForecastChart.swift | 1 | 0 | 0 | 1 |
| CuadraoPlanPreview.swift | 2 | 0 | 0 | 0 |
| CuadraoPlanVisuals.swift | 4 | 0 | 0 | 0 |
| CuadraoPlanWhatIf.swift | 2 | 0 | 1 (behavior) | 1 |
| PlanAmountInput.swift | 1 | 0 | 0 | 0 |
| PlanCurrencyChoice.swift | 2 | 0 | 0 | 0 |
| PlanScenario.swift | 3 | 0 | 0 | 1 |
| **Total** | **53** | **0** | **4** | **7** |

No hunk earned FIX: nothing in this directory fixes a Preview defect; the `scroll:` restoration and `stepped` projection are connected-only opt-ins that default off.

### Highest-impact DRIFT (ordered by what a user would notice)

1. `CuadraoPlanCanvas.swift` hunk 2b: the "Ver primer uso" / "Restablecer ejemplos" context menu now covers the whole "Lo que viene" header row including the "+" button, instead of only the title text. Restore by scoping `.contextMenu` back to the title `Text` inside `CuadraoPlanHeader`.
2. `CuadraoPlanWhatIf.swift` hunk 1b: a pending what-if draft on the plan detail survives a name-only or space-only edit of the plan (checkpoint reset the slider on any plan change). Restore by resetting on the whole `CanvasPlan`, not only on `scenario`.
3. `CuadraoPlanDetailPresentation.swift` hunk 2: new accessibility identifier `plan-detail-amount` on the detail amount text (invisible to users; changes the Preview accessibility tree). Restore by making `amountIdentifier` optional and nil for the Preview.
4. `CuadraoPlanComposition.swift` hunk 4b: new accessibility identifier `plan-first-create` on the "Crear mi primer plan" button (invisible to users). Restore by dropping the id or defaulting it to nil.

Items the founder asked about that are unchanged: what-if slider, chart, insight line and "Llegar en N meses" chips (same strings, ids, fonts, heights); "Actualizar progreso" button and `plan-record-progress`; archive confirmation "¿Dejamos este plan en pausa?" / "Archivar plan"; footnote "Vista previa · datos de ejemplo" on canvas, detail, editor and playground; card swipe edit/archive and reorder (`CuadraoOrderedCollection.swift` byte-identical); archived list inline "Retomar" / "Restore"; editor kind chips, landscape, look picker, `PlanAmountInput` rows and the currency chip (all gates default to the checkpoint); debt card progress bar (`progress` always passed); "Explorar escenarios" (the `example` variant is off for the Preview).
