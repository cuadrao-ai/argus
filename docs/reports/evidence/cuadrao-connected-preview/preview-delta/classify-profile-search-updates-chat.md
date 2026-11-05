# Hunk classification: Profile, Search, Updates, Chat

Base: 5753b5d7cb3e4a13b4bac58a87fa32127b6fcf37 (checkpoint). Head: cuadrao-delta HEAD.
Diffs read from the hunk_inventory.py output (Cuadrao__*.diff). Callers grepped in the candidate tree
(Connected/, Search/, Household/, Accounts/). Commit attribution from `git log -S` on the candidate worktree.

Commits that touched these files after the checkpoint:
3d108de85 (restore connected profile), 051e41732 (share search presentation), e6b7cf325 (restore
connected shell), c6210f681 (account deletion), 9796eb1f9 (search refresh/bounce), d66f3227e
(name editing + quiet sign out), 2808ae2c1 (merge: currency persistence).

## ios/ArgusFoundation/Cuadrao/CuadraoProfileCanvas.swift
Base lines: 286. Status: M.

### Hunk 1: @@ -4,8 +4,12 @@ (+5/-1)
Class: SEAM
Used by: Connected/ConnectedCuadraoProfile.swift:12,51 (`CuadraoProfileSettingsDraft()`)
Reason: Splits `CanvasProfileDraft` into identity fields plus a nested `settings: CuadraoProfileSettingsDraft`. `currency` moves into the settings struct with the same default `"DOP"`; every other default is untouched. Data shape only, no rendering.

### Hunk 2: @@ -21,9 +25,15 @@ (+7/-1)
Class: SEAM
Used by: `CuadraoProfileIdentityValue` is built only inside this file (line 118) and consumed by `CuadraoProfileBody`; `.invitations` is used by Connected/ConnectedCuadraoProfile.swift:26,81
Reason: Adds the `CuadraoProfileIdentityValue` carrier (name, optional email, avatar) and a new `.invitations` route case. The Preview's group route lists (`[.preferences, .personalization, .notifications]`, `[.security, .privacy, .usage]`, `[.help]`) never include `.invitations`, so no Preview row appears.

### Hunk 3: @@ -42,6 +52,7 @@ (+1/-0)
Class: SEAM
Used by: Connected/ConnectedCuadraoProfile.swift:82 (`CanvasProfileRow(route: .invitations, ...)`)
Reason: Title `"Invitaciones"` / `"Invitations"` for the new route. Not rendered by the Preview.

### Hunk 4: @@ -62,6 +73,7 @@ (+1/-0)
Class: SEAM
Used by: same as Hunk 3
Reason: Symbol `"person.badge.plus"` for the new route. Not rendered by the Preview.

### Hunk 5: @@ -97,31 +109,29 @@ (+13/-15)
Class: SEAM
Used by: Connected/ConnectedCuadraoProfile.swift:18 (`CuadraoProfileBody(`), :35 (`CuadraoProfileEditor(name:`)
Reason: The canvas body now delegates to `CuadraoProfileBody`, passing `EmptyView()` as `accountRows` and the unchanged sign-out button (same font `.subheadline`, `.secondary`, `minHeight: 44`, id `"cuadrao.profile.signout"`) as `accountActions`. The editor sheet switches to the new field-binding init with `saveNames` left nil. `@Environment(\.dynamicTypeSize)` moves into the body struct. The sign-out alert copy ("Esta vista previa no tiene una sesión conectada. Tu sesión de Argus sigue abierta.") is unchanged. The checkpoint's `.background(WelcomePalette.background).toolbar(.hidden, for: .navigationBar)` move into `CuadraoProfileBody.body` (Hunk 6).

### Hunk 6: @@ -131,43 +141,72 @@ (+58/-29)
Class: SEAM
Used by: Connected/ConnectedCuadraoProfile.swift:18-24
Reason: Extraction of the scroll body, identity row and `group` into `CuadraoProfileBody<AccountRows, AccountActions>`. Compared line by line against checkpoint lines 104-176: `ScrollView` / `VStack(spacing: 24)` / `identity.padding(.bottom, 4)` / three groups / trailing action / paddings 24 and `bottomSpace + 24` / background / hidden nav bar are identical. Identity row: same `AnyLayout` switch at accessibility sizes, avatar size 76, `.title2` semibold name, `.subheadline` secondary email, "Editar perfil" in pine, `.contentShape(Rectangle())`, `.buttonStyle(.plain)`, id `"cuadrao.profile.identity"`. Email is now `if let` but the Preview passes a non-nil `profile.emailAddress`. `group` gains `includesAccountRows`, which appends `accountRows()` (an `EmptyView` in the Preview) after the last row inside the rounded surface; separators, 0.5 height, `.padding(.leading, 54).padding(.trailing, 18)` and corner radius 22 unchanged. No rendering difference found.

### Hunk 7: @@ -206,28 +245,37 @@ (+20/-11)
Class: SEAM
Used by: Connected/ConnectedCuadraoProfile.swift:35-38 (`saveNames: { await auth.setNames(...) }`)
Reason: `CuadraoProfileEditor` takes `name`, `preferredName`, `avatar` bindings, an optional `emailAddress` and an optional async `saveNames` instead of the whole draft. Initial `@State` values, `valid` (non-empty trimmed name, name <= 60, preferred <= 40) and `changed` are the same predicates as the checkpoint. Adds `saving` / `saveFailed` state that stays false when `saveNames` is nil (the Preview).

### Hunk 8: @@ -239,25 +287,33 @@ (+16/-8)
Class: SEAM
Used by: same as Hunk 7
Reason: `.disabled(saving)` on both fields is `.disabled(false)` in the Preview. The email section is now `if let emailAddress` and the Preview passes `"alex@example.com"`, so it still renders with the same "Correo" / "Email" label. The `saveFailed` footnote ("No pudimos guardar tu nombre. Inténtalo de nuevo.") never shows in the Preview. Footer copy "Usaremos tu nombre preferido al conversar contigo." unchanged.

### Hunk 9: @@ -268,15 +324,24 @@ (+15/-6)
Class: SEAM
Used by: same as Hunk 7
Reason: Save moves to `save()`. With `saveNames == nil` it writes the trimmed name, trimmed preferred name and avatar to the bindings and dismisses, exactly the checkpoint's inline closure. Disabled predicate gains `|| saving` (false in the Preview). Ids `"cuadrao.profile.save"` / `"cuadrao.profile.cancel"` unchanged.

Suspects from the earlier audit not found at HEAD in this file: `allowsIdentityEdits` (absent from the whole candidate tree); "sign-out quiet button vs block" (the Preview sign-out is byte-identical; d66f3227e made the connected host adopt it); "avatar 'Your photo stays in this preview' copy" lives in Cuadrao/CuadraoProfileAvatar.swift:61-62, not an assigned file.

## ios/ArgusFoundation/Cuadrao/CuadraoProfilePage.swift
Base lines: 242. Status: M.

### Hunk 1: @@ -1,24 +1,48 @@ (+27/-3)
Class: SEAM
Used by: Connected/ConnectedCuadraoProfile.swift:29-30 (`CuadraoProfilePage(route:settings:spanish:includeExamples:connection: .connected(...))`)
Reason: Adds `CuadraoProfilePageConnection` (`.preview` / `.connected(appearance:profile:)`), a `settings` binding in place of the whole draft, and a compatibility init `init(route:profile:spanish:includeExamples:)` that forwards `profile.settings` with `.preview`; both Preview callers (CuadraoProfileCanvas.swift:128, CuadraoUpdatesCanvas.swift:50) still use it. `developmentNotice` is inserted first in the `Form` but is an `if case .connected` builder, so the Preview Form starts with `content` as before. `.navigationDestination(isPresented: $deletingAccount)` is inert in the Preview (`connectedDeletion` is nil). `.feedback` branch, `defaultMinListRowHeight` 52, backgrounds, large title and alert unchanged.

### Hunk 2: @@ -27,6 +51,34 @@ (+28/-0)
Class: SEAM
Used by: rendered only when `connection` is `.connected` (Connected/ConnectedCuadraoProfile.swift:30)
Reason: `developmentNotice` section ("Vista de desarrollo" / "Development preview" plus a per-route `developmentDetail`) with id `"cuadrao.profile.development"`. Never rendered by the Preview. Note for the ledger: this is new connected-only copy with no checkpoint counterpart (3d108de85, c6210f681 edited the privacy sentence).

### Hunk 3: @@ -37,7 +89,7 @@ (+1/-1)
Class: DRIFT
Used by: both Preview and connected (the `.usage` page is shared)
Reason: The Usage empty-state description changed wording in both languages (3d108de85). Title "Tu uso, aquí" and symbol `chart.bar` unchanged.
Restore: Spanish `"Verás tu disponibilidad y cuándo se renueva al conectar tu cuenta."`, English `"Your allowance and reset time will appear when your account is connected."`. HEAD has `"Esta vista previa no consulta tu disponibilidad ni cuándo se renueva."` / `"This preview does not load your allowance or reset time."`.

### Hunk 4: @@ -64,14 +116,17 @@ (+5/-2)
Class: SEAM
Used by: Connected/ConnectedCuadraoProfile.swift:26 (`route == .invitations`), :30 (`.connected(appearance: $appearance, ...)`)
Reason: Two edits. `.personal, .invitations: EmptyView()`; `.invitations` is never pushed in the Preview. The Appearance section switches on `connection`; `.preview` renders `CuadraoAppearancePicker(spanish:)` as before, header "Apariencia" and footer "Sistema sigue la apariencia de tu iPhone." unchanged.

### Hunk 5: @@ -79,10 +134,15 @@ (+9/-4)
Class: SEAM
Used by: Connected/ConnectedCuadraoProfile.swift:30 (`.connected(_, profile)` branch renders `ConnectedProfileCurrencyRow`)
Reason: Region row unchanged. Currency row switches on `connection`; `.preview` keeps the `LabeledContent` + `CuadraoChoiceMenu` on `$settings.currency` with id `"cuadrao.profile.currency"`, header "Región y moneda" and footer "Elegir una moneda no convierte ni combina tus balances." unchanged.

### Hunk 6: @@ -95,19 +155,19 @@ (+3/-3)
Class: SEAM
Used by: n/a (binding rename)
Reason: Personalization pickers ("Extensión", "Tono") and the instructions `TextField` rebound from `$profile.*` to `$settings.*`. Tags, labels, `lineLimit(4...8)`, headers and the "Son preferencias que tú eliges..." footer unchanged.

### Hunk 7: @@ -119,22 +179,22 @@ (+10/-10)
Class: SEAM
Used by: n/a (binding rename)
Reason: Notifications toggles and quiet-hours pickers rebound from `$profile.*` to `$settings.*`. Labels, ids `"cuadrao.quiet.start"` / `"cuadrao.quiet.end"`, headers and footers unchanged.

### Hunk 8: @@ -149,7 +209,7 @@ (+1/-1)
Class: DRIFT
Used by: both Preview and connected (the `.security` page is shared)
Reason: Sessions footer wording changed in both languages (3d108de85). The two `previewAction` rows and the "Sesiones" header are unchanged.
Restore: Spanish `"Las sesiones reales se mostrarán al conectar tu cuenta."`, English `"Real sessions will appear when your account is connected."`. HEAD has `"Estos ejemplos no consultan ni cierran sesiones reales."` / `"These examples do not load or sign out real sessions."`.

### Hunk 9: @@ -164,10 +224,15 @@ (+7/-2)
Class: SEAM
Used by: Connected/ConnectedCuadraoProfile.swift (via `ProfileAuthModel.deletion`, c6210f681)
Reason: Delete account button keeps the Preview path (`notice = "Eliminar cuenta"`) when `connectedDeletion` is nil; the connected path pushes `ConnectedAccountDeletion`. Adds the identifier `"cuadrao.profile.deleteAccount"` where the checkpoint had none (additive, not visible). Drops the `// Entry point only ...` comment (no rendering).

### Hunk 10: @@ -178,6 +243,10 @@ (+4/-0)
Class: SEAM
Used by: Hunks 1 and 9
Reason: `connectedDeletion` accessor; nil for `.preview`.

### Hunk 11: @@ -217,8 +286,20 @@ (+14/-2)
Class: SEAM
Used by: Connected/ConnectedCuadraoProfile.swift:30 (`.connected(_, profile)` reads `profile.configuration?.webURL`)
Reason: Legal rows switch on `connection`; `.preview` keeps the two `previewAction` rows "Términos de uso" / "Política de privacidad" under the "Acerca de Cuadrao" header. The connected `Link`s and the "Los enlaces no están disponibles en este momento." fallback never render in the Preview.

## ios/ArgusFoundation/Cuadrao/CuadraoAppearancePicker.swift
Base lines: 93. Status: M.

### Hunk 1: @@ -5,6 +5,15 @@ (+9/-0)
Class: SEAM
Used by: Cuadrao/CuadraoProfilePage.swift:128 (`.connected` branch: `CuadraoAppearanceChoices(spanish:selection: appearance)`), driven by Connected/ConnectedCuadraoProfile.swift:30
Reason: The `@AppStorage("cuadrao.design.appearance")` picker now wraps `CuadraoAppearanceChoices`, which takes a `Binding<AppearancePreference>`. The layout body (accessibility `AnyLayout`, 76pt preview, radius 11/15, pine stroke 2, checkmark overlay, `.subheadline` title) moved verbatim; only `@Environment(\.dynamicTypeSize)` moved with it. Preview storage key and default `.light` unchanged.

## ios/ArgusFoundation/Cuadrao/CuadraoSearchCanvas.swift
Base lines: 337. Status: M.

### Hunk 1: @@ -15,7 +15,6 @@ (+0/-1)
Class: SEAM
Used by: n/a
Reason: `@State filters` moves into `CuadraoSearchContent.showingFilters`. Same open/close behavior (set on the filters button, cleared by "Listo").

### Hunk 2: @@ -80,104 +79,76 @@ (+59/-87)
Class: SEAM (the container change inside the extracted copy is classified under CuadraoSearchPresentation Hunk 1b)
Used by: Search/FinancialSearchView.swift:83, Household/ConnectedHouseholdSearch.swift:15 (`CuadraoSearchContent(`)
Reason: The results `ScrollView`, kind rail, filter summary and search field move to `CuadraoSearchContent`; the canvas now supplies the results closure, `filterSummary` (same `" · "` join of scope title and currency), `clearFilters` (`scope = .all; currency = ""`) and `filterControls`. Each row call maps 1:1: `heading(...)` to `CuadraoSearchHeading(title:count:)`, `resultRow(...)` to `CuadraoSearchResultRow(title:detail:spanish:...)` with the same `symbol` / `accountKind` / `category` / `date` arguments, same `Divider()`s, same ids `cuadrao.search.activity.*`, `cuadrao.search.plan.*`, `cuadrao.search.group.*`, same `emptyState.padding(.top, 36)`. `Text(title(value))` became `Text(value.title(spanish))`; `title(_:)` is `kind.title(spanish)` at checkpoint line 329, so identical.

### Hunk 3: @@ -205,117 +176,25 @@ (+11/-103)
Class: SEAM
Used by: n/a (moved code, see CuadraoSearchPresentation)
Reason: Removes `emptyState`, `emptyTitle`, `emptyDetail`, `searchField`, `filterSheet`, `heading`, `resultRow` (checkpoint lines 212-317) and the `.sheet(isPresented: $filters)`; keeps the sheet's two `Picker`s and the "Restablecer filtros" section with its footer as `filterControls`, passed into the shared `Form`. Strings byte-identical to the checkpoint, including the long "Solo yo incluye lo que no has compartido..." footer.

Note on the "All empty text changed" suspect: `emptyTitle` / `emptyDetail` for `.all` are unchanged ("Tu información, aquí" / "Busca cuentas, movimientos, planes y conversaciones."). The connected host overrides `title:` / `detail:` on `CuadraoSearchEmptyState` (Search/FinancialSearchView.swift:143,158), outside the assigned files.

## ios/ArgusFoundation/Cuadrao/CuadraoSearchPresentation.swift
Base lines: 0. Status: A.

### Hunk 1: @@ -0,0 +1,249 @@ (+249/-0)
Class: NEW. Extracted from checkpoint CuadraoSearchCanvas.swift lines 82-183 (`ScrollView`, `LazyVStack`, `.cuadraoScrollBar` bar with `searchField`, kind rail and filter summary, soft edges, background, hidden nav bar), 212-253 (`emptyState`, `emptyTitle`, `emptyDetail`), 255-273 (`searchField`), 275-294 (`filterSheet`), 296-317 (`heading`, `resultRow`). Split below.

#### Hunk 1a: `CuadraoSearchAccessibility` (lines 3-22)
Class: SEAM
Used by: Search/FinancialSearchView.swift:86,143,158 (`.connected`), Household/ConnectedHouseholdSearch.swift:17,24 (`.household`)
Reason: Prefix table. For `.preview` every id resolves to the checkpoint string: `"cuadrao.search.query"`, `"cuadrao.search.filters"`, `"cuadrao.search.kind.<kind>"`, `"cuadrao.search.clear"`, `"cuadrao.search.reset"`, `"cuadrao.search.everything"`.

#### Hunk 1b: results container (line 43: `VStack(alignment: .leading, spacing: 0, content: results)`)
Class: DRIFT
Used by: Search/FinancialSearchView.swift:170 (`.financialScrollAnchor(hit.id, in: "search.viewport")` needs eagerly measured rows)
Reason: Checkpoint line 84 was `LazyVStack(alignment: .leading, spacing: 0)`. 051e41732 made it an eager `VStack` so the connected host can restore a partially visible row; e6b7cf325 removed the comment that said so. Rendering is the same pixels, but every Preview result row is now built up front, which reverses the lazy container the Preview had. The contract names this container change as DRIFT.
Restore: `LazyVStack(alignment: .leading, spacing: 0, content: results)` for the Preview; if the connected anchor restore needs eager rows, add an opt-in (for example `var eagerRows = false`) that `FinancialSearchView` sets, so the Preview default stays lazy.

#### Hunk 1c: `.coordinateSpace(name: "search.viewport")`, `.modifier(CuadraoSearchRefresh(action: refresh))`, `.accessibilityIdentifier(prefix + ".results")`, loading overlay (lines 45-55)
Class: SEAM
Used by: Search/FinancialSearchView.swift:87 (`refresh:`), :86 (`loading:`), :170 (coordinate space)
Reason: `refresh` defaults nil so no `.refreshable` is attached; `loading` defaults false so the `ProgressView("accounts.loading")` overlay never renders; the named coordinate space draws nothing. `"cuadrao.search.results"` is an added identifier where the checkpoint had none (additive, not visible).

#### Hunk 1d: kind rail `.scrollBounceBehavior(.basedOnSize, axes: .horizontal)` (line 74)
Class: UNSURE (FIX or DRIFT)
Used by: Search/FinancialSearchView.swift (9796eb1f9: the host's `.refreshable` made the rail inherit vertical bounce)
Reason: Added by 9796eb1f9 together with the results-only refresh. It is a behavior change on the Preview's rail: with `.basedOnSize` the rail bounces only when the chips overflow. On iPhone widths the six or seven chips ("Todo Cuentas Movimientos Planes Chats Archivos Memoria", spacing 24, horizontal padding 24) overflow, so the Preview feel is unchanged there; on a width where they fit the rail would stop bouncing. FIX if the founder accepts that the rail should not bounce when nothing is clipped, DRIFT if the checkpoint's always-bounce rail is part of the approved feel.
Restore: drop `.scrollBounceBehavior(.basedOnSize, axes: .horizontal)` and keep only `.accessibilityIdentifier(accessibility.prefix + ".kinds")`; the refresh scoping (`CuadraoSearchRefresh`) is independent and can stay.

#### Hunk 1e: added identifiers `".kinds"`, `".filter-summary"`, `".query.clear"`, `".filters.done"`, `".empty"` (lines 75, 78, 115, 98, 153)
Class: SEAM
Used by: UI tests in Search/ and Household/ via the `.connected` / `.household` prefixes
Reason: Additive identifiers on the rail, the filter summary text, the clear-query button, the sheet's "Listo" button and the empty-state title. No checkpoint identifier was renamed or removed. The empty-state `Label` becomes `Label { Text(...) } icon: { Image(systemName: "magnifyingglass") }` to carry the id; same glyph and text.

#### Hunk 1f: `showsFilters` (lines 34, 117-125)
Class: SEAM
Used by: Household/ConnectedHouseholdSearch.swift:17 (`showsFilters: false`)
Reason: Defaults true; the filters button, its `frame(minWidth: 44, minHeight: 48)`, badge and label "Filtros, N activos" are unchanged in the Preview.

#### Hunk 1g: filter sheet `Form(content: filters)` with "Filtros" inline title, "Listo", `[.medium, .large]` detents, drag indicator (lines 90-102)
Class: SEAM
Used by: Search/FinancialSearchView.swift (filters closure)
Reason: Same chrome as checkpoint lines 275-294; the Preview passes the same two pickers and reset section.

#### Hunk 1h: `CuadraoSearchEmptyState` with optional `title` / `detail` (lines 138-197)
Class: SEAM
Used by: Search/FinancialSearchView.swift:141-158, Household/ConnectedHouseholdSearch.swift:21-24
Reason: Overrides default nil; `emptyTitle` / `emptyDetail` strings and the three action buttons match checkpoint lines 212-253 exactly.

#### Hunk 1i: `CanvasExpenseCategory.fromRecordedCategory` (lines 199-210)
Class: SEAM
Used by: Search/FinancialSearchView.swift:310, Accounts/FinancialActivityDetailView.swift:59
Reason: Connected-only mapping from recorded category strings to Preview artwork. Not referenced by the Preview. Placement in a `*Presentation.swift` file is a modularity nit, not drift.

#### Hunk 1j: `CuadraoSearchHeading`, `CuadraoSearchResultRow` (lines 212-249)
Class: SEAM
Used by: Search/FinancialSearchView.swift:164,261, Household/ConnectedHouseholdSearch.swift:35
Reason: Byte-equivalent to checkpoint `heading` (lines 296-301) and `resultRow` (lines 302-317): `CuadraoTypography.section` + `.caption` count, paddings 20/10, icon frame 42 radius 13, `CuadraoTypography.action` title, `.caption` detail, `minHeight: 62`, `padding(.vertical, 8)`, chevron or `CuadraoChatDate`.

## ios/ArgusFoundation/Cuadrao/CuadraoUpdatesCanvas.swift
Base lines: 176. Status: M.

### Hunk 1: @@ -35,43 +35,22 @@ (+16/-37)
Class: SEAM
Used by: Cuadrao/CuadraoUpdatesLayout.swift:86 (`ConnectedCuadraoUpdates`), hosted by Connected/ConnectedCuadraoShell.swift:71
Reason: The `List`, segmented "Mostrar" picker, "Marcar todas como leídas", empty state and toolbar move to `CuadraoUpdatesLayout`. The canvas passes `hasUnread: !unread.isEmpty`, `emptyState: visible.isEmpty ? (items.isEmpty ? .empty : .read) : nil`, the same `readIDs.formUnion(visible)` action, the same two `updateSection`s, and the same preferences `NavigationLink` (label through `CuadraoUpdatesPreferencesLabel`, same `slider.horizontal.3` in a 44x44 frame, same label and id `"cuadrao.updates.preferences"`). The canvas keeps its own `@Environment(\.dismiss)` (now unused) while the layout reads its own; both resolve to the presenting sheet because the layout is the stack root.

### Hunk 2: @@ -144,21 +123,6 @@ (+0/-15)
Class: SEAM
Used by: n/a (moved code)
Reason: `emptyState` removed; its content lives in `CuadraoUpdatesLayout.empty(_:)` unchanged (see below).

Suspects not found at HEAD in this file: the Done button id is still `"cuadrao.updates.done"`; "picker inert in `.unavailable`" applies only to `ConnectedCuadraoUpdates` (connected host), the Preview canvas never passes `.unavailable`.

## ios/ArgusFoundation/Cuadrao/CuadraoUpdatesLayout.swift
Base lines: 0. Status: A.

### Hunk 1: @@ -0,0 +1,96 @@ (+96/-0)
Class: NEW. Extracted from checkpoint CuadraoUpdatesCanvas.swift lines 38-75 (`List`, `.listStyle(.plain)`, title "Novedades" inline, toolbar) and 147-161 (`emptyState`). Split below.

#### Hunk 1a: `CuadraoUpdatesLayout` (lines 3-71)
Class: SEAM
Used by: Cuadrao/CuadraoUpdatesCanvas.swift:38, Cuadrao/CuadraoUpdatesLayout.swift:86
Reason: Rendering matches the checkpoint item for item: segmented picker tags `false` "Todas" / `true` "Sin leer" with id `"cuadrao.updates.filter"`; "Marcar todas como leídas" `.subheadline` with id `"cuadrao.updates.read-all"` when `hasUnread`; clear row background and hidden separators; `.listStyle(.plain)`, hidden scroll background, `WelcomePalette.background`; "Novedades" / "Updates" inline; leading preferences item; trailing "Listo" / "Done" with id `"cuadrao.updates.done"`. Empty state: `PlanLandscape(look: .bloom)` 130x90, title "Todo tranquilo por aquí" for `.empty` and "Estás al día" for `.read` (the checkpoint's `items.isEmpty` split), details identical, "Ver todas" only for `.read` (checkpoint `!items.isEmpty`), `padding(.vertical, 36)`, id `"cuadrao.updates.empty"`. The `.unavailable` case and its copy ("Las novedades aún no están conectadas en esta versión. Tus movimientos y planes siguen disponibles.") are connected-only new copy, never reached by the Preview.

#### Hunk 1b: `CuadraoUpdatesPreferencesLabel` (lines 73-77)
Class: SEAM
Used by: both hosts
Reason: Same `Image(systemName: "slider.horizontal.3").frame(width: 44, height: 44)` as the checkpoint label.

#### Hunk 1c: `ConnectedCuadraoUpdates` (lines 79-96)
Class: SEAM
Used by: Connected/ConnectedCuadraoShell.swift:71
Reason: Connected host that renders the layout with `hasUnread: false`, `emptyState: .unavailable`, no rows, and a `Button` for preferences; tinted pine with `WelcomePalette.ink`. Not part of the Preview. Modularity nit: a `Connected*` host lives in the Cuadrao/ design directory.

## ios/ArgusFoundation/Cuadrao/CuadraoChatCanvas.swift
Base lines: 379. Status: M.

### Hunk 1: @@ -10,6 +10,7 @@ (+1/-0)
Class: SEAM
Used by: Connected/ConnectedCuadraoShell.swift:132 (`showsPreviewNotice: true`)
Reason: `var showsPreviewNotice = false`. The Preview callers (Cuadrao/CuadraoHomeCanvas.swift:230, Cuadrao/CuadraoChatContext.swift:105) do not pass it.

### Hunk 2: @@ -173,6 +174,7 @@ (+1/-0)
Class: SEAM
Used by: same
Reason: `if showsPreviewNotice { previewNotice }` under the empty-chat headline. Not rendered by the Preview.

### Hunk 3: @@ -184,6 +186,7 @@ (+1/-0)
Class: SEAM
Used by: same
Reason: Same guard at the top of the message `LazyVStack`. Not rendered by the Preview.

### Hunk 4: @@ -249,6 +252,13 @@ (+7/-0)
Class: SEAM
Used by: same
Reason: `previewNotice` text ("Vista previa del chat. Puedes probar ejemplos; no se envían mensajes ni se cambian tus cuentas.") with id `"chat.preview.notice"`, `CuadraoTypography.caption`, secondary, centered. Connected-only copy with no checkpoint counterpart (e6b7cf325).

## Summary

| file | SEAM | FIX | DRIFT | NEW |
|---|---|---|---|---|
| CuadraoProfileCanvas.swift | 9 | 0 | 0 | 0 |
| CuadraoProfilePage.swift | 9 | 0 | 2 | 0 |
| CuadraoAppearancePicker.swift | 1 | 0 | 0 | 0 |
| CuadraoSearchCanvas.swift | 3 | 0 | 0 | 0 |
| CuadraoSearchPresentation.swift | 8 sub-items | 0 | 1 (+1 UNSURE FIX/DRIFT) | 1 |
| CuadraoUpdatesCanvas.swift | 2 | 0 | 0 | 0 |
| CuadraoUpdatesLayout.swift | 3 sub-items | 0 | 0 | 1 |
| CuadraoChatCanvas.swift | 4 | 0 | 0 | 0 |

Highest-impact DRIFT (ordered by what a user would notice):

- CuadraoProfilePage.swift Hunk 8 (Security page footer). Restore `"Las sesiones reales se mostrarán al conectar tu cuenta."` / `"Real sessions will appear when your account is connected."`. Visible on every visit to Seguridad.
- CuadraoProfilePage.swift Hunk 3 (Usage page empty-state description). Restore `"Verás tu disponibilidad y cuándo se renueva al conectar tu cuenta."` / `"Your allowance and reset time will appear when your account is connected."`. Visible on every visit to Uso.
- CuadraoSearchPresentation.swift Hunk 1b (results container `LazyVStack` to `VStack`). Same pixels, but the Preview now builds every result row eagerly; noticeable as scroll cost on long fixture result lists. Restore `LazyVStack` and give the connected anchor restore an opt-in.
- CuadraoSearchPresentation.swift Hunk 1d (kind rail `.scrollBounceBehavior(.basedOnSize, axes: .horizontal)`), UNSURE FIX/DRIFT. Not observable at iPhone widths because the chips overflow; a feel change only where they fit.

Connected-only additions that are not Preview drift but have no checkpoint counterpart (for the ledger, not for restore): "Vista de desarrollo" notice sections on every connected Profile page (CuadraoProfilePage Hunk 2), the chat "Vista previa del chat..." notice (CuadraoChatCanvas Hunk 4), the Updates `.unavailable` copy (CuadraoUpdatesLayout Hunk 1a), the editor's "No pudimos guardar tu nombre." error (CuadraoProfileCanvas Hunk 8), and the "Los enlaces no están disponibles en este momento." legal fallback (CuadraoProfilePage Hunk 11).

Suspects from the earlier audit that are not in these files or not at HEAD: `allowsIdentityEdits` (absent from the candidate tree); Search "All" empty text (unchanged here; overridden only by Search/FinancialSearchView.swift:143,158); Updates "Listo" id (unchanged, `"cuadrao.updates.done"`); avatar "Your photo stays in this preview" copy (Cuadrao/CuadraoProfileAvatar.swift:61-62, not assigned); preferred-name `.constant` binding and the sign-out block (Connected/ConnectedCuadraoProfile.swift:35, connected host).
