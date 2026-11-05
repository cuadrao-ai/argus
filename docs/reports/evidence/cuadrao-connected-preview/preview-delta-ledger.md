# Preview delta ledger

Branch `codex/cuadrao-preview-delta-20261006`, built on the recovery candidate
`codex/cuadrao-recovery-r1-20261006` at `779c22f56`. Checkpoint: the approved Preview at
`5753b5d7cb3e4a13b4bac58a87fa32127b6fcf37`.

Founder instruction: go back to the application that had the checkpoint, see where the delta is,
and rewire accordingly. The Preview view layer is the base. Every line that still differs from the
checkpoint under `ios/ArgusFoundation/Cuadrao/**` and `ios/ArgusFoundation/ReleaseUI/**` is listed
here with its class and reason. A reviewer reads this file beside
`git diff 5753b5d7 HEAD -- ios/ArgusFoundation/Cuadrao ios/ArgusFoundation/ReleaseUI`.

Classes:

- SEAM: an opt-in parameter, protocol or extracted component that lets connected data feed the
  same Preview view. The Preview, with its defaults and fixtures, renders what it rendered at the
  checkpoint.
- FIX: a defect fix the Preview itself needed, or one the connected app needs that leaves the
  Preview's default-size rendering unchanged.
- NEW: a file added since the checkpoint, holding code extracted from a canvas.

## Method

1. `preview-delta/hunk_inventory.py` split the checkpoint-to-candidate diff into one file per
   changed source file (55 files, 2,799 insertions, 1,362 deletions).
2. Four read-only reviewers classified every hunk against
   `preview-delta/CLASSIFY-CONTRACT.md`, comparing the checkpoint tree with the candidate tree and
   naming the connected caller of each seam. Their hunk-level reports are kept verbatim under
   `preview-delta/classify-*.md`; this ledger is the per-file summary.
3. Every hunk classed DRIFT was restored to the checkpoint behavior (section "Restored"). Where the
   connected app needed the changed behavior, it became an opt-in whose default is the checkpoint.
4. Connected hosts that still used an Argus-styled view for a surface the Preview owns were rewired
   to the Preview component (section "Rewired").

## Restored

| Commit | File | What the checkpoint had and what came back |
| --- | --- | --- |
| `66ef4b1e6` | `Cuadrao/CuadraoHomeCanvas.swift` | `.environment(\.cuadraoChat, chat)` on the canvas root above its sheets and the receipt flow. Without it, Ask from a receipt review and from an account inside Novedades did nothing in the Preview. |
| `a8c48fde9` | `Cuadrao/CuadraoBalanceBreakdown.swift` | Row amount `row.change ?? row.closing ?? "—"` and the checkpoint caption rule. The connected overview opts into `missingCoverage: true` to keep "Sin datos" and "Sin inicio registrado" for periods without a recorded opening (PARITY-COMMON: known zero only with confirmed coverage). |
| `0353f232f` | `Cuadrao/CuadraoAppShell.swift` | No `.font(.body)` on the shell root. The modifier only undid the Argus root font; the Argus chrome now sits on the sample shell and the auth flow (`Connected/ConnectedCuadraoRoot.swift`), so the signed-in shell inherits nothing, like the Preview. |
| `13480d9a0` | `Cuadrao/CuadraoHomePresentation.swift` | No `.accessibilityLabel(currency + amount)` on the hero amount; VoiceOver reads the amount as at the checkpoint. |
| `5fa79433b` | `Cuadrao/Planning/CuadraoPlanDetailPresentation.swift`, `CuadraoPlanComposition.swift` | No `plan-detail-amount` or `plan-first-create` identifiers in the Preview tree (neither had a reader); connected hosts pass their own amount identifiers. |
| `bd952b7e0` | `Cuadrao/CuadraoProfilePage.swift` | Security footer "Las sesiones reales se mostrarán al conectar tu cuenta." and Usage description "Verás tu disponibilidad y cuándo se renueva al conectar tu cuenta." with their English. |
| `65cecadbb` | `Cuadrao/CuadraoSearchPresentation.swift` | `LazyVStack` results container (the checkpoint perf fix) and the rail's default bounce. The connected host opts into `eagerRows: true` for scroll restoration; the size-based bounce rule applies only with the connected refresh attached. |
| `4c553e7f3` | `Cuadrao/Planning/CuadraoPlanDisplay.swift`, `CuadraoPlanCanvas.swift` | The hold-to-reset menu on the "Lo que viene" title only, not on the whole header row and its "+" button. |
| `fb006a79a` | `Cuadrao/Planning/CuadraoPlanWhatIf.swift`, `CuadraoPlanDetail.swift` | The what-if draft resets on any plan change (`resetsOn: plan`), not only when the scenario moves. |

Hunk classes the reviewers left UNSURE and how they were decided:

- `CuadraoCanvas.swift` palette gate (always adaptive): SEAM. The flagged Preview launch resolved
  every token through the adaptive path already; the change affects the connected app and Xcode
  `#Preview` macros only. Owner: `9746bb602`, dark appearance for the connected app.
- `CuadraoHomePresentation.swift` accessibility-size layouts of `CuadraoFeedRow` and
  `CuadraoBalanceAmount`: FIX. Default size is byte-identical; the stacked layout at accessibility
  sizes is the documented decision "Stack the balance header for accessibility text sizes" in
  `../decisions.md` (`eddb7da97`).
- `CuadraoSearchPresentation.swift` rail bounce: restored for the Preview (see above).

## Rewired

| Commit | Surface | Change |
| --- | --- | --- |
| `d1b603f7c` | Record movement sheet (Preview side) | `Cuadrao/CuadraoTransactionSheet.swift` extracts the sheet chrome from `CuadraoTransactionCanvas`: account header, "Añadir movimiento" / "Revisar movimiento" titles, Cancel / Atrás, bottom "Revisar" / "Guardar". Every optional defaults to the Preview's words; the canvas keeps its fields and sample save. |
| `3ace1ce80` | Record movement sheet (connected) | `Accounts/ConnectedTransactionSheet.swift` hosts `FinancialActivityEditor` in that sheet. Kinds, account choices, loan split, source, purchase, category, note, correction reason, server review with coverage answers, goal and debt previews, uncertain and conflict phases, and every `loop.*` identifier the UI journeys use are kept. `FinancialActivityEditorView.swift` (29 `ArgusStyle` uses) is deleted; it had no other caller. |
| `af1274aa3` | Updates | The "Todas / Sin leer" picker and "Marcar todas como leídas" hide while updates are `.unavailable` (a connected-only state; the Preview never reaches it). |

Extensions to Preview components for connected fields, all opt-in with Preview defaults:

- `CuadraoTransactionSheet`: `title`, `primaryTitle`, `primaryEnabled`, `primaryBusy`,
  `primaryIdentifier`, `cancelDisabled`, `dismissDisabled`, `scrollTarget`, and an artwork-less
  account header (`CuadraoTransactionAccount.symbol`) for account types without Preview artwork.
  The connected entry renders the kind choice as the Preview plan editor's chips (the two-way
  segmented "Tipo" control cannot hold seven kinds), account, source, purchase and category choices
  as `CuadraoChoiceMenu` rows, and the review as the Preview's rows plus per-account impact cards.
- `CuadraoBalanceBreakdown.missingCoverage`, `CuadraoSearchContent.eagerRows`,
  `CuadraoPlanHeader.titleMenu`, `CuadraoPlanWhatIf.resetsOn` (this lane).

## Surviving deviations under Cuadrao/** and ReleaseUI/**

Owner `#877` is the connected-interface recovery unless another issue or commit is named.
"Extraction" means code moved out of a canvas into a shared component with the same strings,
fonts, spacing, identifiers and modifiers; the canvas calls it with its fixtures.

| File | Class | Reason | Owner |
| --- | --- | --- | --- |
| `Cuadrao/CanvasAccountPresentation.swift` | NEW, SEAM | Extraction of `CanvasAccountRow` body, account detail header and activity row from `CuadraoAccountsPreview.swift` and `CuadraoAccountCanvas.swift`; defaulted `amountIdentifier`, `amountAccessibilityLabel`, `notes`. | #877 |
| `Cuadrao/CanvasActivityPresentation.swift` | NEW, SEAM | Extraction of the activity detail body from `CuadraoActivityDetail.swift`. | #877 |
| `Cuadrao/CuadraoAccountCanvas.swift` | SEAM | Detail content via `CanvasAccountDetailContent`; transaction sheet via `CuadraoTransactionSheet` (this lane). | #877 |
| `Cuadrao/CuadraoAccountManagement.swift` | SEAM, NEW | `archive` closure instead of `data`/`id`; `CuadraoArchivedAccountToast` extracted from the Home canvas overlay; `CuadraoRenameAccountForm` extracted so the connected rename sheet shares it. | #877 |
| `Cuadrao/CuadraoAccountModal.swift` | SEAM | Caller adaptation for the archive closure. | #877 |
| `Cuadrao/CuadraoAccountsPreview.swift` | SEAM | Row body moved to `CanvasAccountRowContent`. | #877 |
| `Cuadrao/CuadraoActivityDetail.swift` | SEAM | Body via `CanvasActivityDetailContent`; locale read for the date. | #877 |
| `Cuadrao/CuadraoAmountField.swift` | SEAM | Defaulted `identifier` and `currencyIdentifier` (checkpoint literals). | #877 |
| `Cuadrao/CuadraoAppShell.swift` | NEW, SEAM | Extraction of the tab shell, bottom bar, voice presentation and temporary-chat dialog from `CuadraoHomeCanvas.swift`; `showProposal` optional so the connected shell hides the example proposal. | #877 |
| `Cuadrao/CuadraoAppearancePicker.swift` | SEAM | `CuadraoAppearanceChoices` takes a binding; the Preview still binds its AppStorage. | #877 |
| `Cuadrao/CuadraoBalanceBreakdown.swift` | SEAM | `linksToAccounts` and `missingCoverage` opt-ins; `rowContent` extracted unchanged. | #877 |
| `Cuadrao/CuadraoBalanceHistory.swift` | SEAM | Second initializer for pre-totalled points. | #877 |
| `Cuadrao/CuadraoBalancePeriod.swift` | SEAM | Fixture initializers moved to an extension so the memberwise initializer exists. | #877 |
| `Cuadrao/CuadraoCanvas.swift` | SEAM | Palette always adaptive (see UNSURE decisions). | `9746bb602` |
| `Cuadrao/CuadraoChartControls.swift` | SEAM | Defaulted `distributionEnabled` (past connected periods disable the distribution icon). | #877, `3e46feb40` |
| `Cuadrao/CuadraoChatCanvas.swift` | SEAM | `showsPreviewNotice` default false; the notice renders only for the connected host. | #826 |
| `Cuadrao/CuadraoDistributionContent.swift` | NEW, SEAM | Extraction of the distribution body from `CuadraoHomeDistribution.swift`. | #877 |
| `Cuadrao/CuadraoFirstAccountSheet.swift` | SEAM | `CanvasAccountEntry` state and `CuadraoAccountEntryForm` extracted; `editing`, `ids`, `status`, `primaryTitle`, `locked`, `busy` default to the Preview sheet. | #877 |
| `Cuadrao/CuadraoHomeBalanceChart.swift` | SEAM | `partial` override and `amountIdentifier` defaults; amount row via `CuadraoBalanceAmount`; `!period.changes.isEmpty` never flips in the Preview. | #877 |
| `Cuadrao/CuadraoHomeCanvas.swift` | SEAM | Hosts through `CuadraoAppShell` and `CuadraoHomeLayout`; toast and empty states extracted. Chat environment restored (this lane). | #877 |
| `Cuadrao/CuadraoHomeDistribution.swift` | SEAM | Body via `CuadraoDistributionContent`; unused `typeSize` dropped. | #877 |
| `Cuadrao/CuadraoHomeEmptyState.swift` | SEAM | `if shared` hoisted; identical branches. | #877 |
| `Cuadrao/CuadraoHomeInsights.swift` | SEAM | Controls, period paging and accessibility actions moved to `CuadraoHomeInsightsLayout`. | #877 |
| `Cuadrao/CuadraoHomeInsightsLayout.swift` | NEW, SEAM | Extraction of the expanded Balance layout. | #877 |
| `Cuadrao/CuadraoHomePresentation.swift` | NEW, SEAM, FIX | Extraction of the Home layout, greeting, feed rows and hero amount; accessibility-size stacking is the documented fix. VoiceOver label restored (this lane). | #877, `eddb7da97` |
| `Cuadrao/CuadraoProfileCanvas.swift` | SEAM | `CuadraoProfileBody` extracted with empty account rows for the Preview; editor takes bindings, optional email and `saveNames`. | #877 |
| `Cuadrao/CuadraoProfilePage.swift` | SEAM | `includeExamples`, currency binding row, development notice sections and legal link fallback for the connected host; approved footers restored (this lane). | #877 |
| `Cuadrao/CuadraoSearchCanvas.swift` | SEAM | Field, rail, filters and empty states moved to `CuadraoSearchPresentation`. | #877 |
| `Cuadrao/CuadraoSearchPresentation.swift` | NEW, SEAM | Extraction; `accessibility` prefixes, `showsFilters`, `loading`, `refresh`, `eagerRows` default to the Preview. | #877 |
| `Cuadrao/CuadraoSpaceSelector.swift` | SEAM | `CuadraoSpaceSelectorLayout` and `CuadraoSpaceLabel` extracted for `ConnectedCuadraoSpaces`. | #877, #819 |
| `Cuadrao/CuadraoSpendingChart.swift` | SEAM | Header via `CuadraoSpendingReading`; `CuadraoMissingCoverage` strings shared. | #877, #824 |
| `Cuadrao/CuadraoTransactionSheet.swift` | NEW, SEAM | This lane: the record-movement chrome extracted from `CuadraoTransactionCanvas`. | #877 |
| `Cuadrao/CuadraoUpdatesCanvas.swift` | SEAM | List, picker and empty state moved to `CuadraoUpdatesLayout`. | #877, #825 |
| `Cuadrao/CuadraoUpdatesLayout.swift` | NEW, SEAM | Extraction; `.unavailable` state and copy exist only for the connected host; its filter now hides (this lane). | #877, #825 |
| `Cuadrao/Planning/CuadraoForecastPlayground.swift` | SEAM | `isolatedExample` default false keeps the approved copy. | #877 |
| `Cuadrao/Planning/CuadraoPlanCanvas.swift` | SEAM | Header, cards and collection via `CuadraoPlanDisplay` and `CuadraoPlanComposition`; title menu scoped (this lane). | #877 |
| `Cuadrao/Planning/CuadraoPlanComposition.swift` | NEW, SEAM | Extraction of the plan page, cold start and collection. | #877 |
| `Cuadrao/Planning/CuadraoPlanDetail.swift` | SEAM | Heading, facts, options and what-if moved to `CuadraoPlanDetailPresentation` and `CuadraoPlanWhatIf`. | #877 |
| `Cuadrao/Planning/CuadraoPlanDetailPresentation.swift` | NEW, SEAM | Extraction; `amountIdentifier` optional (this lane); `scroll` restoration opt-in. | #877 |
| `Cuadrao/Planning/CuadraoPlanDisplay.swift` | NEW, SEAM | Extraction of the plan header and card; `titleMenu` opt-in (this lane). | #877 |
| `Cuadrao/Planning/CuadraoPlanEditor.swift` | SEAM | Generic `host`, `details`, `footer`; every gate defaults to the checkpoint editor. | #877 |
| `Cuadrao/Planning/CuadraoPlanEditorHost.swift` | NEW, SEAM | Host parameters for the connected drafts. | #877 |
| `Cuadrao/Planning/CuadraoPlanForecastChart.swift` | NEW, SEAM | Extraction of the forecast chart; `stepped` projection default off. | #877 |
| `Cuadrao/Planning/CuadraoPlanPreview.swift` | SEAM | Math moved to `PlanScenario`; same preview day constants. | #877 |
| `Cuadrao/Planning/CuadraoPlanVisuals.swift` | SEAM | Card via `CuadraoPlanCard`; chart via `CuadraoPlanForecastChart`; `month(after:)` anchored on the preview day (verified equal for 0...600 months). | #877 |
| `Cuadrao/Planning/CuadraoPlanWhatIf.swift` | NEW, SEAM | Extraction of the what-if block and chart; `apply`, `showsDisclosure`, `resetsOn` opt-ins. | #877 |
| `Cuadrao/Planning/PlanAmountInput.swift` | SEAM | Defaulted `currencyIdentifier`. | #877 |
| `Cuadrao/Planning/PlanCurrencyChoice.swift` | SEAM | Defaulted `identifier`. | #877 |
| `Cuadrao/Planning/PlanScenario.swift` | NEW, SEAM | Extraction of the plan math from `CuadraoPlanPreview.swift`. | #877 |
| `Cuadrao/Receipts/CuadraoReceiptCapture.swift` | SEAM | `postingCapability` forwarded. | #823 |
| `Cuadrao/Receipts/CuadraoReceiptReview.swift` | SEAM, FIX | Draft-only caption and hidden destination, split and confirm when posting is off; location button hidden where the permission cannot be requested (FIX, `f02ad86c9`). | #823 |
| `Cuadrao/Receipts/CuadraoReceiptStore.swift` | SEAM | `ReceiptPostingCapability` with `.preview` default; per-user connected draft folders. | #823 |
| `Cuadrao/Receipts/CuadraoReceiptSupport.swift` | SEAM | `isAvailable` names the existing guard. | #823 |
| `ReleaseUI/Identity/ReleaseDeleteAccountView.swift` | SEAM | `appleAuthorization` slot and four new deletion states; existing states render as before. | `c6210f681`, `d18070101` |
| `ReleaseUI/Identity/ReleaseIdentityGallery.swift` | SEAM | Five more fixture states in the gallery menu. | `d18070101` |
| `ReleaseUI/Identity/ReleaseIdentityModels.swift` | SEAM | New `ReleaseDeletionState` cases. | `d18070101` |

Noted for the owner, not Preview drift: the four new deletion sections in
`ReleaseDeleteAccountView.swift` read `Localizable.strings` while their siblings use the inline
`text(es, en)` helper; a Spanish locale that does not resolve to `es-419` would mix languages.

## Connected hosts outside Cuadrao/** touched by this lane

- `ArgusFoundationApp.swift`, `Connected/ConnectedCuadraoRoot.swift`: Argus tint, ink and body
  font moved from the app root onto the sample shell and the auth flow.
- `Connected/ConnectedCuadraoBalanceOverview.swift`: `missingCoverage: true`.
- `Search/FinancialSearchView.swift`: `eagerRows: true`.
- `Accounts/AccountActivityView.swift`: the editor presenter shows `ConnectedTransactionSheet`.
- `Accounts/ConnectedTransactionSheet.swift` added; `Accounts/FinancialActivityEditorView.swift`
  deleted.

## Surfaces that still have no Preview component

These keep their connected views and are listed so nobody mistakes them for omissions:

- Account details and reviewed starting balance (`Accounts/AccountForm.swift`, reached from the
  connected account detail "Edit" and "Opening balance"): the Preview has only the first-account
  and rename sheets, which the connected app already uses.
- Check balance and expected-expense editor (`Accounts/FinancialEditorView.swift`): the Preview's
  "Comprobar balance" is an informational alert.
- Recurring expectation form and occurrence sheet (`Plan/FinancialPlanForms.swift`): the Preview
  plan editor has goal, month and debt kinds only; the recurring journey depends on
  `plan.expectation.*`.
- Goal allocation and link sheets (`Plan/FinancialGoalActions.swift`), asset editor
  (`Accounts/FinancialAssetEditor.swift`): no Preview counterpart.
- Expanded Actividad categories, highlights and paging (#824), Updates inbox (#825), chat replies
  and Ask (#826, #827): need backend reads the API does not expose yet.

## Visual proof

See the "Visual proof" section below once the side-by-side captures are listed.

## Tests

Run on October 6 from this branch at the simulator 8AFB6084 (iPhone 18 Pro, iOS 27) against the local API
at 127.0.0.1:58900 (allocation `accounts-local-58900`, CAPTCHA bridge 58905).

| Check | Result |
| --- | --- |
| `python3 ios/FinancialModelTests/run.py` | 91 tests, 4 failing, the four known #842 failures only (`testEmptyPlanSelectionIsAnExplicitJournaledPut`, `testPlanConfirmationSurvivesRelaunchAndDifferentOwnerCannotReplay`, `testPostSaveHomeWinsOverEarlierRead`, `testSearchAccountNavigationAndAcceptedEditsPreserveAccountsSelection`). |
| `ios/DesignPreviewTests/run_plan_preview.py`, `run_home_balance.py`, `run_connected_balance.py`, `run_connected_swipe.py`, `run_currency_presentation.py` | all exit 0. |
| `python3 scripts/check_modularity_budget.py` | no budget violations. |
| Debug build (`ios/scripts/verify.sh build`) | succeeded. |
| Release build (`xcodebuild build -configuration Release -destination 'generic/platform=iOS Simulator'`) | succeeded. |
| UI tests build-for-testing (`ios/scripts/auth/run-ui.py`) | succeeded on every run below. |

The seven journeys that passed on the candidate this morning, each in its own result bundle under
`ios/.build/accounts-local-58900/` (one test per bundle; a zero-test bundle counts as a failure):

| Journey | This branch | Candidate `779c22f56`, re-run now in a separate worktree |
| --- | --- | --- |
| `testHomeMovementOpensDetailAndBackKeepsPosition` | passed 1, failed 0 (`ui-20261006T231915Z`) | not re-run |
| `testMovementRowSwipesOpenCorrectionAndCategory` | passed 1, failed 0 (`ui-20261006T232204Z`) | not re-run |
| `testAccountRowSwipesAddEditAndMoreArchive` | passed 1, failed 0 (`ui-20261006T232415Z`) | not re-run |
| `testRecurringSetupSpanishCopy` | passed 1, failed 0 (`ui-20261006T233036Z`) | not re-run |
| `testRecurringFromMovementShowsInHomeUpcomingAndFulfilsOnce` | failed at `ConnectedRecurringUITests.swift:46` ("Home keeps its own 30-day window": `homeUpcomingRows` returns 0 while the Plan tab is shown; the Home tab is no longer in the accessibility tree while Plan is selected) (`ui-20261006T232636Z`) | same failure, same line (base worktree `ui-20261006T234344Z`) |
| `testConnectedReceiptDraftSurvivesRelaunchWithoutPosting` | failed at `ConnectedChrome.swift:131`: the sign-out alert exposes two `auth.signOut.confirm` buttons (`ui-20261006T233315Z`) | same failure, same line (base worktree `ui-20261006T234304Z`) |
| `testConnectedProfileUsesRealIdentityAndApprovedDestinations` | failed at `ConnectedProfileRecoveryUITests.swift:14`: after tapping `header.profile` the Home tab stays selected (`ui-20261006T233402Z`, repeated `ui-20261006T233849Z`) | same failure, same line (base worktree `ui-20261006T234118Z`) |

The three failures reproduce identically on the untouched candidate commit under the same simulator and API,
and reverting this branch's root-font change (`0353f232f`) in the working tree did not change the Profile
result, so they are drift in the shared simulator or test user state since the morning runs, not this diff.
The first journey also failed once before commit `97e53e363`: the connected sheet exposed `loop.confirm`
while coverage questions were still open, which the journeys treat as "confirmable"; the fix keeps
`loop.review` until the review is confirmable, as the old editor did.

## Spaces row and sheet (candidate merge of `codex/cuadrao-spaces-sheet-20261007`)

| Item | Checkpoint | Candidate | Reason |
| --- | --- | --- | --- |
| Home row, no household | Personal, Hogar and a trailing plus (Hogar is a fixture space) | `Personal   + Hogar` with the plus and pine tint, no trailing plus in release | A grey label that opens a flow reads as locked. The plus names the action and the trailing plus would open a sheet with one real choice. Debug and `--cuadrao-design` keep the trailing plus so Espacios stays reviewable. |
| Home row, household exists | Personal and household labels | Same, household label opens the existing select, manage menu | Real household state. |
| `Espacios` sheet | Hogar, Negocio, Personalizado, Gestionar espacios | Same view, driven by `CuadraoSpacesSource`; Hogar works, Negocio and Personalizado show "Próximamente" and are hidden by `CuadraoFirstRelease.showsExtraSpaces` | No backend exists for business or custom spaces; they stay built and hidden. |
| Hogar flow | Preview introduction | Existing household management screen | Restyling that screen is a separate slice. |

## Final candidate run (2026-10-07)

On the merged candidate: modularity budget clean, ArgusSession tests pass, household runner 53 tests pass,
model runner 92 tests with only the four #842 failures, Debug and Release simulator builds succeed.
`run_linux.py` now compiles `PlanScenario.swift` for its plan slice. Its avatar-crop slice, `run_tap_targets`,
`run_group_preview` and `run_receipt_preview` still fail; the last three fail identically on the base commit.

All eight journeys pass, each in its own bundle: the seven above plus
`testSpacesSheetLeadsHogarAndKeepsBusinessAndCustomDisabled`. Three journeys needed test fixes, not product fixes:
the recurring journey brings Home forward before counting its rows, the sign-out helper takes the first matching
confirm button, and the spaces journey checks the "Próximamente" caption instead of tapping a row that is not a
button. A first batch failed because the simulator had a hardware-keyboard flag
(`HardwareKeyboardLastSeen`) that hid the software keyboard; resetting it fixed that.

## Home account reorder (2026-10-07)

| Item | Checkpoint | Candidate | Reason |
| --- | --- | --- | --- |
| Hold on a Home account row | Preview Home reorders accounts with hold and drag through `CuadraoOrderedCollection`; no hold menu | The connected Home uses the same collection. The hold menu is gone (swipes already cover Rename, Add movement and Archive through More). Order is stored per person on the device | The hold menu duplicated the swipe actions and blocked the Preview's drag. The server keeps no account order. |
| `CuadraoOrderedCollection` | `Edit` and `Archive` swipes | Same, plus optional `leadingSwipes` and `trailingSwipes` so a connected host supplies its own sets. Preview callers pass none and are unchanged | SEAM. The swipe modifiers stay direct in the ForEach element: wrapping them in a conditional `ViewModifier` made every lift crash with "Unexpected identifier type. Expected UUID, got UUID". |
| Swipe container on Home | One container on the whole Home scroll | One on the Activity rows; the accounts collection brings its own | Keeps swipes for Activity while accounts reorder. |

Checks: `CuadraoCollectionUITests/testGroupNativeReorderPersistenceAndRecovery` passes, the new
`testAccountRowHoldAndDragReordersAndKeepsTheOrderAfterRelaunch` passes, and the account and movement swipe journeys,
the Home movement journey, the spaces journey and the Profile journey still pass.
