# Hunk classification: accounts, receipts, release identity

Checkpoint: 5753b5d7 (checkpoint worktree).
Candidate: HEAD of the candidate worktree.
Ref line numbers below are checkpoint lines; "cand" lines are candidate lines.
Commits that produced these hunks (from `git log` on the files): 46e2f7eca reuse preview account and movement presentation; 9746bb602 bind connected Home to approved Cuadrao views; 3c5f40ac2 review before archiving an account and offer Undo; 5417e9186 use the approved Cuadrao sheets to create and rename accounts; 25daad2c6 harden the archive toast and account sheet dismissal; b12813b39 restore receipt drafts behind a posting gate; f02ad86c9 hide unavailable receipt location action; bfc9b0176 remove one owner's connected drafts on confirmed deletion; d18070101 present the session owner's deletion results without inferring deletion.

Method: every Spanish and English string in each hunk was compared against the checkpoint copy; every new parameter's default was compared against the literal the checkpoint used; every extracted view was compared modifier by modifier with the code it replaced.

## ios/ArgusFoundation/Cuadrao/CanvasAccountPresentation.swift
Base lines: 0. Status: A (165 lines).

### Hunk 1: @@ -0,0 +1,165 @@ (+165/-0)
Class: NEW (extraction, rendering unchanged, so SEAM)
Used by: Connected/ConnectedAccountPresentation.swift:10 (`CanvasAccountRowContent`), Household/ConnectedHouseholdAccounts.swift:46, :109 (`CanvasAccountDetailHeader`), :134; Accounts/AccountDetailView.swift:27 (`CanvasAccountDetailContent` with `recordEnabled`/`checkEnabled` at :29-30); Accounts/AccountActivityView.swift:105 (`CanvasAccountActivityRowContent` with `status` at :110); Connected/ConnectedAccountPresentation.swift:88-89 (`notes`, `amountIdentifier`, `amountAccessibilityLabel`).
Reason: four value+content pairs extracted so connected hosts can feed the same rows and header. Sources at the checkpoint:
- `CanvasAccountRowContent` + `CanvasAccountRowValue` from CuadraoAccountsPreview.swift:169-197 (`CanvasAccountRow` body and `balance`). Same `HStack(alignment: typeSize.isAccessibilitySize ? .top : .center, spacing: 12)`, 42x42 sage 0.65 rounded 13 artwork, `CuadraoTypography.action` title, caption subtitle, `rowAmount` amount with `minimumScaleFactor(0.6)`, caption amountCaption, `.padding(.vertical, 12).contentShape(Rectangle())`. Additions are defaulted off: `note: String? = nil` (extra caption line) and `CanvasAccountArtwork` which renders `CanvasAccountIcon(kind:size:)` with the same default size 23 (CuadraoAccountsPreview.swift:147) when kind is non-nil, and a `square.stack` placeholder only for a nil kind the Preview never passes.
- `CanvasAccountDetailHeader` + `CanvasAccountDetailValue` from CuadraoAccountCanvas.swift:17-36 (header VStack spacing 18, 58x58 sage rounded 18 icon at size 30, `screen` title with id `account-detail-title`, spacing-9 balance block, `amount` font monospacedDigit lineLimit 1 scale 0.6, footnote freshness). Additions defaulted off: `notes: [String] = []` footnote lines; amount Text gains `.accessibilityLabel(amountAccessibilityLabel ?? amount)` (same spoken text) and `.accessibilityIdentifier("account-detail-amount")` (checkpoint had no id here).
- `CanvasAccountDetailContent` from CuadraoAccountCanvas.swift:16-43 (`LazyVStack(alignment: .leading, spacing: 30)`, header, `VStack(spacing: 12)` with `RegistrationButton("Añadir movimiento")` id `account-detail-record` and the capsule-stroked `Comprobar balance` button, then the history slot). Additions defaulted off: `recordEnabled = true` (RegistrationButton's own default, CuadraoRegistrationStyle.swift:25), `checkEnabled = true` rendered as `.disabled(false)`, new id `account-detail-check` on the check button (checkpoint had none).
- `CanvasAccountActivityRowContent` + value from CuadraoAccountCanvas.swift:57-69 (HStack spacing 14, 38x38 surface circle symbol hidden from accessibility, VStack spacing 5 body title + caption detail, Spacer, `rowAmount`, `.padding(.vertical, 10).contentShape(Rectangle())`). Addition defaulted off: `status: String? = nil` caption with id `activity.moved`.
No DRIFT items found inside the extracted copies.

## ios/ArgusFoundation/Cuadrao/CanvasActivityPresentation.swift
Base lines: 0. Status: A (63 lines).

### Hunk 1: @@ -0,0 +1,63 @@ (+63/-0)
Class: NEW (extraction, rendering unchanged, so SEAM)
Used by: Accounts/FinancialActivityDetailView.swift:23 (`CanvasActivityDetailContent`), :73 (`CanvasActivityAccountRowContent` with `amount`).
Reason: extracted from CuadraoActivityDetail.swift.
- `CanvasActivityDetailContent` from ref :17-34: same `VStack(alignment: .leading, spacing: 28)`, `feature` title id `activity-detail-title`, `amount` font monospacedDigit id `activity-detail-amount`, `LabeledContent("Tipo", value:)`, category `LabeledContent` with `HStack { CuadraoExpenseCategoryIcon; Text }`, then `Fecha`. Difference in mechanism, not output: the date arrives as a pre-formatted `String` through `LabeledContent(_:value:)` instead of `Text(date, format:)` inside the closure; the caller formats with the environment locale (see CuadraoActivityDetail hunk 2), so the rendered string is the same. Category became optional (`CanvasActivityCategoryValue?`, artwork optional) so the connected app can show a category without an icon; the Preview passes both.
- `CanvasActivityAccountRowContent` from ref :45-53: same HStack spacing 16, icon (via `CanvasAccountArtwork`, default size 23), `action` title, caption detail, Spacer, tertiary `chevron.right` hidden from accessibility, `.frame(minHeight: 62).contentShape(Rectangle())`. Additions defaulted to the checkpoint look: `showsDisclosure = true`, `amount: String? = nil`.
No DRIFT items found.

## ios/ArgusFoundation/Cuadrao/CuadraoAccountCanvas.swift
Base lines: 180. Status: M (cand 152).

### Hunk 1: @@ -8,38 +8,18 @@ (+8/-28)
Class: SEAM
Used by: the extracted `CanvasAccountDetailContent` is used by Accounts/AccountDetailView.swift:27; this hunk itself is the Preview caller.
Reason: header and the two buttons replaced by `CanvasAccountDetailContent(value: CanvasAccountDetailValue(...))` with the same title (`account.displayName(spanish)`), `balanceLabel`, currency, `CanvasMoney.format` amount or `—`, and the same freshness copy (`"Sin balance registrado"` / `"Actualizado hoy"`). `record` and `check` closures are the checkpoint's `record(accountID)` and `showingBalanceInfo = true`. Adds `@Environment(\.locale)` for hunk 2. The history `LazyVStack(spacing: 16)` with `"Movimientos"` stays in place.

### Hunk 2: @@ -54,19 +34,11 @@ (+5/-13)
Class: SEAM
Used by: `CanvasAccountActivityRowContent` used by Accounts/AccountActivityView.swift:105 and Household/ConnectedHouseholdAccounts.swift:134.
Reason: the inline row became `CanvasAccountActivityRowContent` with the same title, symbol (`arrow.down.left` / `arrow.up.right`), signed amount (`+` / `−` U+2212) and the date formatted `.dateTime.day().month(.abbreviated)`. The date is now formatted with `.locale(locale)` from the environment instead of letting `Text(_:format:)` read the environment; the Preview sets no custom locale (no `.environment(\.locale` under Cuadrao/), so both read the system locale and print the same string. The NavigationLink, `.buttonStyle(.plain)`, id `account-detail-activity.<id>` and `Divider()` are unchanged.

Unchanged in this file (not in the diff): the actions menu `moreButton` (cand :68-84) with `"Preguntar a Cuadrao"` / `"Cambiar nombre"` / `"Añadir movimiento"` / `"Archivar"` and id `account-detail-options`; the `"Comprobar balance"` alert; `CuadraoTransactionCanvas` (ref :116-180, cand :88-152) byte for byte.

## ios/ArgusFoundation/Cuadrao/CuadraoAccountManagement.swift
Base lines: 77. Status: M (cand 125).

### Hunk 1a: @@ -1,22 +1,40 @@ `CuadraoArchiveAccountReview` (+6/-4 of the hunk)
Class: SEAM
Used by: Connected/ConnectedCuadraoHome.swift:379, Accounts/AccountDetailView.swift:57; Preview caller CuadraoAccountModal.swift:18.
Reason: `data`/`id` dropped and `archived` renamed to `archive: () -> Void`; the Preview caller now passes `{ data.archive(id, true); archived(id) }`, which is the same two calls in the same order before `dismiss()`. Copy unchanged: `"¿Archivar esta cuenta?"`, `"El historial se conserva. Puedes recuperarla en Cuentas archivadas."`, `"Archivar"`, `"Cancelar"`. Adds ids `accounts.archive.confirm` and `accounts.archive.cancel` where the checkpoint had none.

### Hunk 1b: @@ -1,22 +1,40 @@ `CuadraoArchivedAccountToast` (+17/-0 of the hunk)
Class: NEW (extraction, rendering unchanged, so SEAM)
Used by: Connected/ConnectedCuadraoHome.swift:139; Preview caller Cuadrao/CuadraoHomeCanvas.swift:106.
Reason: extracted from the checkpoint's inline overlay in CuadraoHomeCanvas.swift:160-171. Same `HStack { Text("Cuenta archivada"); Spacer(); Button("Deshacer"); xmark 44x44 button with accessibilityLabel "Cerrar" }`, `.font(.subheadline).padding(.leading, 20).padding(.trailing, 6)`, `.regularMaterial` rounded 18, `.padding(.horizontal, 20).padding(.bottom, 90)`. The Preview's undo closure keeps `data.archive(archivedID, false); self.archivedID = nil`. Adds ids `accounts.archived.undo` and `accounts.archived.close` where the checkpoint had none.

### Hunk 2: @@ -53,25 +71,55 @@ (+36/-8)
Class: SEAM
Used by: Connected/ConnectedAccountSheet.swift:59 (`CuadraoRenameAccountForm` with `status` :61, `primaryTitle`/`busy` :62).
Reason: `CuadraoRenameAccount` keeps `data`/`account`, owns `name`, and delegates to the new `CuadraoRenameAccountForm`. Save logic is the checkpoint's (`updated.name = trimmed; data.replace(updated); dismiss()`), and `onAppear { name = account.displayName(spanish) }` moved from the inner `NavigationStack` chain to the wrapper, which fires at the same moment. New parameters all default to the checkpoint look: `status: nil` (no extra line), `primaryTitle: nil` (`"Guardar"`), `busy = false` (`.disabled(false)` on field and Cancel, `enabled: !busy && !empty` reduces to the old `enabled: !empty`). Copy unchanged: `"Nombre"`, `"Guardar"`, `"Cambiar nombre"`, `"Cancelar"`, placeholder `account.kind.title(spanish)`. Adds ids `account-rename-name`, `account-rename-save`, `account-rename-cancel` where the checkpoint had none.

## ios/ArgusFoundation/Cuadrao/CuadraoAccountModal.swift
Base lines: 29. Status: M (cand 29).

### Hunk 1: @@ -15,7 +15,7 @@ (+1/-1)
Class: SEAM
Used by: Preview only (connected hosts call `CuadraoArchiveAccountReview` directly, see above).
Reason: caller adaptation for hunk 1a of CuadraoAccountManagement; `data.archive(id, true)` then `archived(id)` as before.

## ios/ArgusFoundation/Cuadrao/CuadraoAccountsPreview.swift
Base lines: 197. Status: M (cand 180).

### Hunk 1: @@ -169,29 +169,12 @@ (+6/-23)
Class: SEAM
Used by: `CanvasAccountRowContent` used by Connected/ConnectedAccountPresentation.swift:10 and Household/ConnectedHouseholdAccounts.swift:46.
Reason: `CanvasAccountRow` body and `balance` moved to `CanvasAccountRowContent` (see CanvasAccountPresentation). The Preview passes the same strings: title `displayName(spanish)`, subtitle `kind.title(spanish) + " · Conjunta"/" · Joint"` when shared, amount `CanvasMoney.format` or `—`, caption `currency + " · pendiente"/" · owed"` for debt. `@Environment(\.dynamicTypeSize)` moved with the body. The `CanvasActivity` model (ref :41-49) is untouched.

## ios/ArgusFoundation/Cuadrao/CuadraoActivityDetail.swift
Base lines: 64. Status: M (cand 46).

### Hunk 1: @@ -7,6 +7,7 @@ (+1/-0)
Class: SEAM
Used by: hunk 2.
Reason: `@Environment(\.locale)` read so the date string can be formatted with the environment locale.

### Hunk 2: @@ -14,36 +15,17 @@ (+8/-27)
Class: SEAM
Used by: `CanvasActivityDetailContent` / `CanvasActivityAccountRowContent` used by Accounts/FinancialActivityDetailView.swift:23, :73.
Reason: body became `CanvasActivityDetailContent(value:)` with the same title, amount string (`currency + " " + sign + CanvasMoney.format`), kind copy (`"Ingreso"` / `"Gasto"`), category only when `!entry.income` (with icon and `entry.category.title(spanish)`), and the date formatted `.dateTime.day().month(.wide).year()` with the environment locale (equivalent to the old `Text(date, format:)`, see CuadraoAccountCanvas hunk 2). The account NavigationLink keeps `.buttonStyle(.plain)` and id `activity-detail-account`; its label is `CanvasActivityAccountRowContent(title:detail:artwork:)` with the same name, currency and chevron. The `"Preguntar a Cuadrao"` button that follows is unchanged.

## ios/ArgusFoundation/Cuadrao/CuadraoAmountField.swift
Base lines: 79. Status: M (cand 81).

### Hunk 1: @@ -8,6 +8,8 @@ (+2/-0)
Class: SEAM
Used by: CuadraoFirstAccountSheet passes `ids.amount` / `ids.currency`; the connected sheet substitutes ids through `CanvasAccountEntryIDs.connected` (Connected/ConnectedAccountSheet.swift:91-93). No other connected caller passes these parameters.
Reason: `identifier = "cuadrao-amount"` and `currencyIdentifier = "account-edit-currency"` default to the literals the checkpoint hard-coded (`CanvasDecimalInput.identifier` default at CanvasDecimalInput.swift:11 is also `"cuadrao-amount"`).

### Hunk 2: @@ -17,13 +19,13 @@ (+2/-2)
Class: SEAM
Used by: same as hunk 1.
Reason: the two literals replaced by the defaulted parameters; `CuadraoTransactionCanvas` and other callers that omit them render the same ids.

## ios/ArgusFoundation/Cuadrao/CuadraoFirstAccountSheet.swift
Base lines: 171. Status: M (cand 223).

Spanish copy audit for the whole file: `"Introduce tu parte, de 1 a 100%."`, `"Elige un tipo de cuenta"`, `"Revisa el monto"`, `"Nombre"`, `"Ej. Gastos del día"`, `"Monto pendiente"`, `"Valor total estimado"`, `"Balance actual"`, `"Tu parte"`, `"Todo · 100%"`, `"La mitad · 50%"`, `"Otra parte"`, `"Porcentaje"`, `"Añadir cuenta"`, `"Editar cuenta"`, `"Cancelar"`, `"Añadir"`, `"Guardar"`, `"Tipo de cuenta"`, `"Cambiar tipo, …"`, `"Otros activos"`, `"Introduce un monto positivo."` are all present unchanged, and no string was added that the Preview renders.

### Hunk 1a: @@ -1,120 +1,171 @@ `CanvasAccountEntry`, `CanvasAccountEntryIDs` (+26 of the hunk)
Class: SEAM
Used by: Connected/ConnectedAccountSheet.swift:29 (entry binding), :91-93 (`CanvasAccountEntryIDs.connected` remaps ids to `accounts.type.<type>` and friends).
Reason: the seven `@State` fields (`kind`, `name`, `amount`, `currency = "DOP"`, `share = 100`, `customShare`, `sharingCustom`) became one `Equatable` struct with the same defaults; `trimmedName` and `sharePercent` reproduce the checkpoint's inline `trimmingCharacters` and `sharingCustom ? (Int(customShare) ?? 100) : share`. `CanvasAccountEntryIDs` defaults are the checkpoint literals: `"account-type-" + rawValue`, `"account-name"`, `"cuadrao-amount"`, `"account-edit-currency"`, `"account-save"`. Three ids in it had no checkpoint counterpart and are additive: `"account-type-change"`, `"account-other-assets"`, `"account-share"`, `"account-cancel"`.

### Hunk 1b: @@ -1,120 +1,171 @@ `CuadraoFirstAccountSheet` wrapper (+28 of the hunk)
Class: SEAM
Used by: Preview only (CuadraoAccountModal and the Home canvas).
Reason: the sheet keeps `data`, `spanish`, `existing`, `dismiss` and now hosts `CuadraoAccountEntryForm(entry:spaceTitle:spanish:editing:cancel:save:)` with `spaceTitle = data.selectedSpace.title(spanish)`, `editing = existing != nil`, `cancel = dismiss`. The save closure is the checkpoint's body moved verbatim (`guard let kind`, `existing ?? CanvasAccount(name: "", kind:)`, `spaceID` / `sharedWithHousehold` for a new account, name, kind, currency, balance, share, `data.replace`, `dismiss`). The `onAppear` population of kind/name/amount/currency/share for an existing account moved here; `pickingType = false` moved to the form (hunk 1h).

### Hunk 1c: @@ -1,120 +1,171 @@ `CuadraoAccountEntryForm` parameters (+15 of the hunk)
Class: SEAM
Used by: Connected/ConnectedAccountSheet.swift:29-33 (`status`, `statusIdentifier`, `primaryTitle`, `locked`, `busy`).
Reason: parameters added with defaults that reproduce the Preview sheet: `editing = false`, `ids = CanvasAccountEntryIDs()`, `status: String? = nil`, `statusIdentifier = "account-status"`, `primaryTitle: String? = nil`, `locked = false`, `busy = false`. `cancel` and `save` are required closures the Preview wrapper supplies.

### Hunk 1d: @@ -1,120 +1,171 @@ hint slot (`message = hint ?? status`, identifier) (+4/-3 of the hunk)
Class: SEAM
Used by: Connected/ConnectedAccountSheet.swift:31 (`status` + `statusIdentifier: "accounts.status"` / `"accounts.form.error"`).
Reason: with `status == nil`, `message == hint`, so the same text shows and hides, and `.animation(..., value: message)` animates on the same changes as `value: hint`. The hint `Text` gains `.accessibilityIdentifier(hint == nil ? statusIdentifier : "account-hint")`, which is `"account-hint"` whenever the Preview shows it; the checkpoint hint had no id. Padding, icon, font, transition unchanged.

### Hunk 1e: @@ -1,120 +1,171 @@ lock and busy gating (+3/-2 of the hunk)
Class: SEAM
Used by: Connected/ConnectedAccountSheet.swift:33.
Reason: `.padding(24).disabled(locked)` with `locked = false`, Cancel `.disabled(busy)` with `busy = false`, and `enabled: hint == nil && !busy` all reduce to the checkpoint behavior.

### Hunk 1f: @@ -1,120 +1,171 @@ share menu and Cancel identifiers (+2 of the hunk)
Class: SEAM
Used by: connected ids via `CanvasAccountEntryIDs.connected`.
Reason: `.accessibilityIdentifier(ids.share)` on the share `Menu` and `.accessibilityIdentifier(ids.cancel)` on Cancel are additive; no checkpoint id existed on either.

### Hunk 1g: @@ -1,120 +1,171 @@ title and primary button condition (+2/-2 of the hunk)
Class: SEAM
Used by: Preview and connected.
Reason: `existing == nil ? "Añadir cuenta" : "Editar cuenta"` became `editing ? "Editar cuenta" : "Añadir cuenta"`; the primary title became `primaryTitle ?? (editing ? "Guardar" : "Añadir")`. Same strings in the same states.

### Hunk 1h: @@ -1,120 +1,171 @@ `onAppear` split (+1/-6 of the hunk)
Class: SEAM
Used by: both.
Reason: the form sets `pickingType = false` when `editing || entry.kind != nil`; the wrapper populates `entry` for an existing account. The checkpoint did both in one `onAppear` after the first frame, so the first frame is the same (type grid visible until `onAppear` collapses it for an existing account).

### Hunk 2: @@ -125,7 +176,7 @@ (+1/-1)
Class: SEAM
Reason: `if let kind, !pickingType` reads `entry.kind`.

### Hunk 3: @@ -134,6 +185,7 @@ (+1/-0)
Class: SEAM
Reason: adds `.accessibilityIdentifier(ids.typeChange)` (`"account-type-change"`) to the collapsed type button; additive, label `"Cambiar tipo, …"` unchanged.

### Hunk 4: @@ -142,7 +194,7 @@ (+1/-1)
Class: SEAM
Reason: adds `.accessibilityIdentifier(ids.otherAssets)` (`"account-other-assets"`) to the `"Otros activos"` disclosure label; additive.

### Hunk 5: @@ -153,9 +205,9 @@ (+2/-2)
Class: SEAM
Reason: `entry.kind = item` and `Decimal(string: entry.amount)` replace the local state; same `"Introduce un monto positivo."` rule.

### Hunk 6: @@ -163,8 +215,8 @@ (+2/-2)
Class: SEAM
Reason: selection background compares `entry.kind == item`; id `ids.type(item)` defaults to the checkpoint's `"account-type-" + item.rawValue`.

Answer to the parent's question: six new parameters (`editing`, `ids`, `status`, `statusIdentifier`, `primaryTitle`, `locked`, `busy`) plus `cancel`/`save` closures; every default reproduces the checkpoint sheet; no copy changed; four accessibility ids were added where none existed and none were changed.

## ios/ArgusFoundation/Cuadrao/Receipts/CuadraoReceiptCapture.swift
Base lines: 249. Status: M (cand 250).

### Hunk 1: @@ -11,6 +11,7 @@ (+1/-0)
Class: SEAM
Used by: CuadraoReceiptReview.swift (`workspace.postingCapability`); the connected store is built by Connected/ConnectedReceiptDrafts.swift:31.
Reason: `ReceiptWorkspace.postingCapability` forwards `receipts.postingCapability`.

## ios/ArgusFoundation/Cuadrao/Receipts/CuadraoReceiptReview.swift
Base lines: 356. Status: M (cand 366).

### Hunk 1: @@ -44,6 +44,10 @@ (+4/-0)
Class: SEAM
Used by: connected drafts (`.draftOnly` from Connected/ConnectedReceiptDrafts.swift:31).
Reason: a caption `"Este recibo se queda en este dispositivo y no crea un gasto."` with id `receipt-local-draft-notice` renders only when `!allowsPosting`; the Preview store defaults to `.preview`, so the Preview never shows it. New Spanish copy exists, but it is connected-only.

### Hunk 2: @@ -130,13 +134,15 @@ (+6/-4)
Class: SEAM
Used by: connected drafts.
Reason: the `destination` / `"Guardado en"` section and `splitSection(group)` are wrapped in `if workspace.postingCapability.allowsPosting`; always true in the Preview, so the same sections render in the same order.

### Hunk 3a: @@ -145,21 +151,25 @@ location button gated on `location.isAvailable` (+1/-1 of the hunk)
Class: FIX
Used by: connected receipt review (commit f02ad86c9 "hide unavailable receipt location action").
Reason: `else if draft.prepared && location.isAvailable`. `isAvailable` is `CuadraoDesignPreview.isActive` (CuadraoReceiptSupport.swift:73), the same guard `request()` already used, so in the Preview the `"Añadir ubicación actual"` button and `"Opcional. No es la dirección del comercio."` caption still show. Defect fixed: outside the Preview the button was offered and every tap could only set `unavailable` and print `"No pudimos obtener tu ubicación…"`.

### Hunk 3b: @@ -145,21 +151,25 @@ confirm section gated (+12/-8 of the hunk)
Class: SEAM
Used by: connected drafts.
Reason: the confirm `Section` renders when `allowsPosting || !error.isEmpty`; inside, the `"Confirmar gasto"` button (id `receipt-confirm`, `.disabled(!valid)`), `"Hasta confirmar, este recibo no cambia ningún balance."`, and the `"Gasto guardado"` label (id `receipt-confirmed`) are unchanged and always present in the Preview. The `receipt-error` text keeps its position.

## ios/ArgusFoundation/Cuadrao/Receipts/CuadraoReceiptStore.swift
Base lines: 137. Status: M (cand 165).

### Hunk 1: @@ -1,13 +1,24 @@ (+11/-1)
Class: SEAM
Used by: Connected/ConnectedReceiptDrafts.swift:31 via `connectedDrafts`.
Reason: `ReceiptPostingCapability { preview, draftOnly }` with `allowsPosting` and `requirePosting()`; `init(... postingCapability: = .preview)` keeps every existing caller posting.

### Hunk 2: @@ -18,6 +29,20 @@ (+14/-0)
Class: SEAM
Used by: Connected/ConnectedReceiptDrafts.swift:31 (`connectedDrafts(userID:)`), Auth/ProfileAuthModel.swift:55 (`removeConnectedDrafts(userID:)` as the confirmed-deletion cleanup, commit bfc9b0176).
Reason: static constructors for the per-user `CuadraoConnectedReceiptDrafts/<uuid>` directory; `removeConnectedDrafts` swallows `.fileNoSuchFile` so a retry converges. Preview path untouched.

### Hunk 3: @@ -77,6 +102,7 @@ (+1/-0)
Class: SEAM
Reason: `confirm` starts with `try postingCapability.requirePosting()`, a no-op for `.preview`.

### Hunk 4: @@ -97,6 +123,7 @@ (+1/-0)
Class: SEAM
Reason: `reconcile` starts with the same guard.

### Hunk 5: @@ -109,6 +136,7 @@ (+1/-0)
Class: SEAM
Reason: `projectPersonal` returns early unless `allowsPosting`; the Preview still projects into `CuadraoAccountsPreview`.

## ios/ArgusFoundation/Cuadrao/Receipts/CuadraoReceiptSupport.swift
Base lines: 171. Status: M (cand 171).

### Hunk 1: @@ -70,12 +70,12 @@ (+2/-2)
Class: SEAM
Used by: CuadraoReceiptReview.swift hunk 3a.
Reason: `var isAvailable: Bool { CuadraoDesignPreview.isActive }` names the guard `request()` already applied; the explanatory comment was dropped and the guard reads `isAvailable`. Behavior identical.

## ios/ArgusFoundation/ReleaseUI/Identity/ReleaseDeleteAccountView.swift
Base lines: 187. Status: M (cand 220).

### Hunk 1: @@ -8,6 +8,7 @@ (+1/-0)
Class: SEAM
Used by: Connected/ConnectedAccountDeletion.swift:16 (`appleAuthorization: auth.providers.apple ? AnyView(appleAuthorization) : nil`).
Reason: stored `appleAuthorization: AnyView?` slot for the Sign in with Apple re-authorization button.

### Hunk 2: @@ -16,10 +17,10 @@ (+2/-2)
Class: SEAM
Used by: same.
Reason: `init` gains `appleAuthorization: AnyView? = nil`; every existing call compiles and renders as before.

### Hunk 3: @@ -62,6 +63,38 @@ (+32/-0)
Class: SEAM
Used by: Auth/AccountDeletionModel.swift:80-112 produces `.uncertain(canRetry:)`, `.appleAuthorizationRequired`, `.supportRequested`, `.supportUnavailable`.
Reason: four new `switch state` cases required by the new enum cases (the switch has no `default`). Existing cases (`.ready`, `.submitting`, `.pending`, `.failed`, `.completed`) are untouched, so the gallery renders them as at the checkpoint. The new sections draw copy from `Localizable.strings` keys (`auth.deletion.uncertain`, `.checkAgain`, `.uncertain.support`, `.apple`, `.support.requested`, `.support.unavailable`; both `en.lproj` and `es-419.lproj` have them at Resources/*/Localizable.strings:842ff) while the rest of the view uses the inline `text(es, en)` helper keyed on `locale.language.languageCode == "es"` (line 27). Not DRIFT (no checkpoint state changed), but a copy-source split worth a note: on a Spanish locale that does not fall back to `es-419`, the new sections would be English beside Spanish siblings. UNSURE whether the parent wants that filed as FIX-needed; it is not a Preview regression.

## ios/ArgusFoundation/ReleaseUI/Identity/ReleaseIdentityGallery.swift
Base lines: 190. Status: M (cand 195).

### Hunk 1: @@ -66,6 +66,11 @@ (+5/-0)
Class: SEAM
Used by: gallery fixture only.
Reason: the deletion fixture's state menu gains five buttons (`"Sin confirmar"`, `"Sin confirmar, soporte"`, `"Apple"`, `"Solicitud enviada"`, `"Solicitud no enviada"`) so the new states can be exercised. Existing buttons and their order are unchanged; this is additive fixture detail visible only inside that menu.

## ios/ArgusFoundation/ReleaseUI/Identity/ReleaseIdentityModels.swift
Base lines: 102. Status: M (cand 104).

### Hunk 1: @@ -29,11 +29,13 @@ (+5/-3)
Class: SEAM
Used by: Auth/AccountDeletionModel.swift:36, :83, :94-95, :107, :112.
Reason: `ReleaseDeletionState` gains `appleAuthorizationRequired`, `uncertain(canRetry: Bool)`, `supportRequested`, `supportUnavailable`; the doc comment moves the 503 `account_deletion_incomplete` outcome from `pending` to `uncertain`. `allowsVerificationInput` keeps its `default: false`. Existing cases and their meaning are unchanged, so no gallery fixture changes.

## Summary

| file | SEAM | FIX | DRIFT | NEW |
|---|---|---|---|---|
| Cuadrao/CanvasAccountPresentation.swift | 0 | 0 | 0 | 1 (SEAM extraction) |
| Cuadrao/CanvasActivityPresentation.swift | 0 | 0 | 0 | 1 (SEAM extraction) |
| Cuadrao/CuadraoAccountCanvas.swift | 2 | 0 | 0 | 0 |
| Cuadrao/CuadraoAccountManagement.swift | 2 (1a, 2) | 0 | 0 | 1 (1b toast, SEAM extraction) |
| Cuadrao/CuadraoAccountModal.swift | 1 | 0 | 0 | 0 |
| Cuadrao/CuadraoAccountsPreview.swift | 1 | 0 | 0 | 0 |
| Cuadrao/CuadraoActivityDetail.swift | 2 | 0 | 0 | 0 |
| Cuadrao/CuadraoAmountField.swift | 2 | 0 | 0 | 0 |
| Cuadrao/CuadraoFirstAccountSheet.swift | 13 (1a-1h, 2-6) | 0 | 0 | 0 |
| Cuadrao/Receipts/CuadraoReceiptCapture.swift | 1 | 0 | 0 | 0 |
| Cuadrao/Receipts/CuadraoReceiptReview.swift | 3 (1, 2, 3b) | 1 (3a) | 0 | 0 |
| Cuadrao/Receipts/CuadraoReceiptStore.swift | 5 | 0 | 0 | 0 |
| Cuadrao/Receipts/CuadraoReceiptSupport.swift | 1 | 0 | 0 | 0 |
| ReleaseUI/Identity/ReleaseDeleteAccountView.swift | 3 | 0 | 0 | 0 |
| ReleaseUI/Identity/ReleaseIdentityGallery.swift | 1 | 0 | 0 | 0 |
| ReleaseUI/Identity/ReleaseIdentityModels.swift | 1 | 0 | 0 | 0 |
| **Total** | **39** | **1** | **0** | **3** |

### Highest-impact DRIFT

None found in these sixteen files. Every Spanish string the Preview renders is unchanged, every new parameter defaults to the checkpoint literal or to "off", no accessibility identifier was changed (fourteen were added where none existed, all default to the Preview's new literals and are invisible), no layout container changed (`LazyVStack` stays `LazyVStack`), and the three extractions reproduce their source modifier for modifier.

Things a user could still notice, none of them Preview regressions:
- Connected receipt review shows a new caption `"Este recibo se queda en este dispositivo y no crea un gasto."` and hides the destination, split and confirm sections while drafts are `.draftOnly` (CuadraoReceiptReview hunks 1, 2, 3b). Preview unaffected.
- Outside the Preview the `"Añadir ubicación actual"` button no longer appears (hunk 3a, FIX). Preview unaffected.
- The identity gallery's deletion state menu lists five more states (ReleaseIdentityGallery hunk 1).
- The four new deletion sections read copy from `Localizable.strings` while their siblings use inline `text(es, en)`; a locale that does not resolve to `es-419` would mix languages (ReleaseDeleteAccountView hunk 3, flagged UNSURE).

## CuadraoTransactionCanvas capability inventory

Source: checkpoint `ios/ArgusFoundation/Cuadrao/CuadraoAccountCanvas.swift:116-180` (candidate :88-152, byte-identical). Entry point: `CuadraoAccountModal.swift:26` on `.record(id)` passes `CuadraoTransactionCanvas(data:account:spanish:)`. The doc comment at :115 says saving stages a sample row, never a financial command.

Collected:
- Account: fixed, injected as `let account: CanvasAccount` (:118) and shown as icon + `displayName` header (:133-136). No account picker.
- Kind: `@State income: Bool = false` (:125), segmented `Picker` `"Gasto"` / `"Ingreso"` (:145-148). Two kinds only.
- Amount: `@State amount = ""` (:121) through `CuadraoAmountField(raw:currency:error:spanish:currencySelectable: false)` (:149); `@State error` (:123); `valid` is `error.isEmpty && amount > 0` (:128).
- Currency: `@State currency = ""` (:122) set to `account.currency` on appear (:178) and not selectable (`currencySelectable: false`, :149).
- Note: `@State title = ""` (:124), `TextField("Concepto (opcional)")` with `RegistrationField` (:150-151); on save an empty title becomes `"Ingreso"` / `"Gasto"` (:169).
- Date: `@State date = Date.now` (:126), `DatePicker("Fecha", in: ...Date.now, displayedComponents: .date)` (:152). Past or today only, no time.
- Review step: `@State reviewing` (:127) flips the body to a summary (signed amount :138, `"Moneda"` :140, `"Tipo"` :141, `"Concepto"` if present :142, `"Fecha"` :143); toolbar `"Atrás"` / `"Cancelar"` (:159-163); bottom `RegistrationButton` `"Revisar"` then `"Guardar"` gated on `valid` (:165-176).
- Save: `data.activity.insert(CanvasActivity(accountID:title:amount:date:income:), at: 0)` then `dismiss()` (:168-171).

Not collected: category (`CanvasActivity.category` defaults to `.other`, CuadraoAccountsPreview.swift:48, so every recorded movement renders as "other" in `CuadraoActivityDetail`), account picker, transfer or counter-account, refund flag, currency choice, attachments or receipt link, time of day, future dates.
