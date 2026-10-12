import SwiftUI

/// What the account sheet collects; the canvas stores it as a sample, the connected app sends it as one create request.
struct CanvasAccountEntry: Equatable {
    var kind: CanvasAccountKind?
    var name = ""
    var amount = ""
    var currency = "DOP"
    var share = 100
    var customShare = ""
    var sharingCustom = false

    var trimmedName: String { name.trimmingCharacters(in: .whitespacesAndNewlines) }
    var sharePercent: Int { sharingCustom ? (Int(customShare) ?? 100) : share }
}

/// The canvas keeps its own identifiers; the connected app keeps the ones its UI tests drive.
struct CanvasAccountEntryIDs {
    var type: (CanvasAccountKind) -> String = { "account-type-" + $0.rawValue }
    var typeChange = "account-type-change"
    var otherAssets = "account-other-assets"
    var name = "account-name"
    var amount = "cuadrao-amount"
    var currency = "account-edit-currency"
    var share = "account-share"
    var save = "account-save"
    var cancel = "account-cancel"
}

struct CuadraoFirstAccountSheet: View {
    let data: CuadraoAccountsPreview
    let spanish: Bool
    var existing: CanvasAccount?
    @Environment(\.dismiss) private var dismiss
    @State private var entry = CanvasAccountEntry()

    var body: some View {
        CuadraoAccountEntryForm(entry: $entry, spaceTitle: data.selectedSpace.title(spanish), spanish: spanish,
            editing: existing != nil, cancel: { dismiss() }) {
            guard let kind = entry.kind else { return }
            var account = existing ?? CanvasAccount(name: "", kind: kind)
            if existing == nil {
                account.spaceID = data.selectedSpaceID
                account.sharedWithHousehold = data.selectedSpace.kind == .household
            }
            account.name = entry.trimmedName
            account.kind = kind; account.currency = entry.currency
            account.balance = Decimal(string: entry.amount); account.share = entry.sharePercent
            data.replace(account); dismiss()
        }
        .onAppear {
            guard let existing else { return }
            entry.kind = existing.kind; entry.name = existing.name
            entry.amount = existing.balance.map(CanvasMoney.raw) ?? ""
            entry.currency = existing.currency; entry.share = existing.share
        }
    }
}

struct CuadraoAccountEntryForm: View {
    @Binding var entry: CanvasAccountEntry
    let spaceTitle: String
    let spanish: Bool
    var editing = false
    var ids = CanvasAccountEntryIDs()
    /// A connected save reports progress or a server answer in the hint slot.
    var status: String? = nil
    var statusIdentifier = "account-status"
    var primaryTitle: String? = nil
    /// Inputs freeze while a save is in flight or a create waits for its exact retry.
    var locked = false
    var busy = false
    /// A host that keeps the currency or the type fixed once a balance is recorded says so here.
    var currencySelectable = true
    var kindLocked = false
    var lockNote: String? = nil
    let cancel: () -> Void
    let save: () -> Void
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var pickingType = true
    @State private var assetsExpanded = false
    @State private var error = ""
    @FocusState private var nameFocused: Bool

    private var hint: String? {
        if entry.kind?.isAsset == true && entry.sharingCustom && !(1...100).contains(Int(entry.customShare) ?? 0) {
            return spanish ? "Introduce tu parte, de 1 a 100%." : "Enter your share, from 1 to 100%."
        }
        if entry.kind == nil { return spanish ? "Elige un tipo de cuenta" : "Choose an account type" }
        if !error.isEmpty || (!entry.amount.isEmpty && Decimal(string: entry.amount) == nil) {
            return spanish ? "Revisa el monto" : "Check the amount"
        }
        return nil
    }
    private var message: String? { hint ?? status }
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 28) {
                    Text(spaceTitle).font(.subheadline).foregroundStyle(.secondary)
                    typePicker
                    VStack(alignment: .leading, spacing: 10) {
                        fieldLabel(spanish ? "Nombre" : "Name")
                        TextField(spanish ? "Ej. Gastos del día" : "e.g. Everyday spending", text: $entry.name)
                            .autocorrectionDisabled().focused($nameFocused).submitLabel(.done)
                            .onSubmit { nameFocused = false }
                            .modifier(RegistrationField(focused: nameFocused))
                            .accessibilityIdentifier(ids.name)
                            .onChange(of: entry.name) { _, value in if value.count > 60 { entry.name = String(value.prefix(60)) } }
                    }
                    VStack(alignment: .leading, spacing: 10) {
                        fieldLabel(entry.kind?.isDebt == true ? (spanish ? "Monto pendiente" : "Amount owed")
                            : entry.kind?.isAsset == true ? (spanish ? "Valor total estimado" : "Estimated total value")
                            : (spanish ? "Balance actual" : "Current balance"))
                        CuadraoAmountField(raw: $entry.amount, currency: $entry.currency, error: $error,
                            spanish: spanish, allowNegative: entry.kind?.isDebt != true && entry.kind?.isAsset != true,
                            currencySelectable: currencySelectable, identifier: ids.amount, currencyIdentifier: ids.currency)
                        if let lockNote {
                            Text(lockNote).font(.footnote).foregroundStyle(.secondary).accessibilityIdentifier("account-lock-note")
                        }
                    }
                    if entry.kind?.isAsset == true {
                        VStack(alignment: .leading, spacing: 12) {
                            HStack {
                                Text(spanish ? "Tu parte" : "Your share")
                                Spacer()
                                Menu {
                                    Button(spanish ? "Todo · 100%" : "All · 100%") { entry.share = 100; entry.sharingCustom = false }
                                    Button(spanish ? "La mitad · 50%" : "Half · 50%") { entry.share = 50; entry.sharingCustom = false }
                                    Button(spanish ? "Otra parte" : "Another share") { entry.sharingCustom = true }
                                } label: {
                                    Text(entry.sharingCustom ? (spanish ? "Otra parte" : "Another share") : "\(entry.share)%")
                                        .frame(minHeight: 44)
                                }.accessibilityIdentifier(ids.share)
                            }
                            if entry.sharingCustom {
                                TextField(spanish ? "Porcentaje" : "Percentage", text: $entry.customShare)
                                    .keyboardType(.numberPad).modifier(RegistrationField())
                            }
                        }
                    }
                }.padding(24).disabled(locked)
            }
            .scrollDismissesKeyboard(.interactively)
            .background(WelcomePalette.background)
            .navigationTitle(editing ? (spanish ? "Editar cuenta" : "Edit account") : (spanish ? "Añadir cuenta" : "Add account"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                CuadraoCancelToolbar(title: spanish ? "Cancelar" : "Cancel", disabled: busy, identifier: ids.cancel, action: cancel)
            }
            .safeAreaInset(edge: .bottom, spacing: 0) {
                VStack(spacing: 0) {
                    if let message {
                        HStack(spacing: 8) {
                            Image(systemName: "info.circle").accessibilityHidden(true)
                            Text(message).font(.subheadline)
                                .accessibilityIdentifier(hint == nil ? statusIdentifier : "account-hint")
                        }.foregroundStyle(.secondary).padding(.top, 14).padding(.bottom, 12)
                            .frame(maxWidth: .infinity)
                            .transition(.move(edge: .bottom).combined(with: .opacity))
                    }
                    RegistrationButton(title: primaryTitle ?? (editing ? (spanish ? "Guardar" : "Save") : (spanish ? "Añadir" : "Add")),
                                       enabled: hint == nil && !busy, action: save)
                        .accessibilityIdentifier(ids.save)
                }
                .background(WelcomePalette.sage.opacity(0.65), in: RoundedRectangle(cornerRadius: 20))
                .clipped()
                .animation(reduceMotion ? nil : .easeInOut(duration: 0.22), value: message)
                .padding(.horizontal, 24).padding(.top, 12).padding(.bottom, 16)
                .background(WelcomePalette.background)
            }
        }.tint(WelcomePalette.pine)
        .onAppear { if editing || entry.kind != nil { pickingType = false } }
    }
    private func fieldLabel(_ label: String) -> some View {
        HStack(spacing: 8) {
            Text(label)
            Text(spanish ? "Opcional" : "Optional").foregroundStyle(.secondary)
        }.font(.subheadline)
    }
    private var typePicker: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text(spanish ? "Tipo de cuenta" : "Account type").font(.subheadline)
            if let kind = entry.kind, !pickingType {
                Button { withAnimation(reduceMotion ? nil : .easeInOut(duration: 0.2)) { pickingType = true } } label: {
                    HStack(spacing: 14) {
                        CanvasAccountIcon(kind: kind)
                        Text(kind.title(spanish)).foregroundStyle(.primary)
                        Spacer()
                        if !kindLocked { Image(systemName: "chevron.down").font(.caption).foregroundStyle(.secondary) }
                    }.padding(18).background(WelcomePalette.sage.opacity(0.65), in: RoundedRectangle(cornerRadius: 16))
                }.buttonStyle(.plain).disabled(kindLocked).accessibilityLabel(kindLocked ? (spanish ? "Tipo fijo, \(kind.title(spanish))" : "Fixed type, \(kind.title(spanish))")
                        : (spanish ? "Cambiar tipo, \(kind.title(spanish))" : "Change type, \(kind.title(spanish))"))
                    .accessibilityIdentifier(ids.typeChange)
            } else {
                typeGrid(CanvasAccountKind.allCases.filter { !$0.isAsset })
                DisclosureGroup(isExpanded: $assetsExpanded) {
                    typeGrid(CanvasAccountKind.allCases.filter(\.isAsset)).padding(.top, 12)
                } label: {
                    HStack(spacing: 12) {
                        CanvasAccountIcon(kind: .asset, size: 21)
                        Text(spanish ? "Otros activos" : "Other assets").foregroundStyle(.primary)
                    }.padding(.vertical, 10).accessibilityIdentifier(ids.otherAssets)
                }
            }
        }
    }
    private func typeGrid(_ kinds: [CanvasAccountKind]) -> some View {
        LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible()), GridItem(.flexible())], spacing: 10) {
            ForEach(kinds) { item in
                Button {
                    nameFocused = false
                    withAnimation(reduceMotion ? nil : .easeInOut(duration: 0.22)) {
                        entry.kind = item; pickingType = false
                    }
                    if (item.isDebt || item.isAsset), (Decimal(string: entry.amount) ?? 0) < 0 {
                        error = spanish ? "Introduce un monto positivo." : "Enter a positive amount."
                    }
                } label: {
                    VStack(spacing: 11) {
                        CanvasAccountIcon(kind: item, size: 26)
                        Text(item.title(spanish)).font(.caption).multilineTextAlignment(.center).foregroundStyle(.primary)
                    }.frame(maxWidth: .infinity, minHeight: 91)
                        .background(entry.kind == item ? WelcomePalette.sage : WelcomePalette.surface, in: RoundedRectangle(cornerRadius: 16))
                }.buttonStyle(.plain).accessibilityIdentifier(ids.type(item))
            }
        }
    }
}
