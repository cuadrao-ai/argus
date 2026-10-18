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
    var sharePercent: Int {
        guard sharingCustom, case .success(let value?) = PercentInput.parse(customShare, .wholeShare) else { return share }
        return NSDecimalNumber(decimal: value).intValue
    }
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
    private static let amountAnchor = "account-entry-amount"

    private var hint: String? {
        if entry.kind?.isAsset == true && entry.sharingCustom && PercentInput.problem(entry.customShare, .wholeShare) != nil {
            return CuadraoCopy.text("copy.cuadraoFirstAccountSheet.d99eaf19c2", spanish: spanish)
        }
        if entry.kind == nil { return CuadraoCopy.text("copy.cuadraoFirstAccountSheet.57ca98595b", spanish: spanish) }
        if !error.isEmpty || (!entry.amount.isEmpty && Decimal(string: entry.amount) == nil) {
            return CuadraoCopy.text("copy.cuadraoFirstAccountSheet.94500b74b1", spanish: spanish)
        }
        return nil
    }
    private var message: String? { hint ?? status }
    var body: some View {
        NavigationStack {
            ScrollViewReader { proxy in
            ScrollView {
                VStack(alignment: .leading, spacing: 28) {
                    Text(spaceTitle).font(.subheadline).foregroundStyle(.secondary)
                    typePicker
                    VStack(alignment: .leading, spacing: 10) {
                        fieldLabel(CuadraoCopy.text("copy.cuadraoAccountManagement.9d191b79fb", spanish: spanish))
                        TextField(CuadraoCopy.text("copy.cuadraoFirstAccountSheet.8f5c63b1b7", spanish: spanish), text: $entry.name)
                            .autocorrectionDisabled().focused($nameFocused).submitLabel(.done)
                            .onSubmit { nameFocused = false }
                            .modifier(RegistrationField(focused: nameFocused))
                            .accessibilityIdentifier(ids.name)
                            .onChange(of: entry.name) { _, value in if value.count > 60 { entry.name = String(value.prefix(60)) } }
                    }
                    VStack(alignment: .leading, spacing: 10) {
                        fieldLabel(entry.kind?.isDebt == true ? (CuadraoCopy.text("copy.cuadraoFirstAccountSheet.3bf64e270f", spanish: spanish))
                            : entry.kind?.isAsset == true ? (CuadraoCopy.text("copy.cuadraoFirstAccountSheet.b93b8ff301", spanish: spanish))
                            : (CuadraoCopy.text("copy.cuadraoFirstAccountSheet.8e47b1cc18", spanish: spanish)))
                        CuadraoAmountField(raw: $entry.amount, currency: $entry.currency, error: $error,
                            spanish: spanish, allowNegative: entry.kind?.isDebt != true && entry.kind?.isAsset != true,
                            currencySelectable: currencySelectable, identifier: ids.amount, currencyIdentifier: ids.currency)
                        if let lockNote {
                            Text(lockNote).font(.footnote).foregroundStyle(.secondary).accessibilityIdentifier("account-lock-note")
                        }
                    }.id(Self.amountAnchor)
                    if entry.kind?.isAsset == true {
                        VStack(alignment: .leading, spacing: 12) {
                            HStack {
                                Text(CuadraoCopy.text("copy.cuadraoFirstAccountSheet.15732a4703", spanish: spanish))
                                Spacer()
                                Menu {
                                    Button(CuadraoCopy.text("copy.cuadraoFirstAccountSheet.21bfe8c3dc", spanish: spanish)) { entry.share = 100; entry.sharingCustom = false }
                                    Button(CuadraoCopy.text("copy.cuadraoFirstAccountSheet.9438fa2d7e", spanish: spanish)) { entry.share = 50; entry.sharingCustom = false }
                                    Button(CuadraoCopy.text("copy.cuadraoFirstAccountSheet.1bff0bb3fc", spanish: spanish)) { entry.sharingCustom = true }
                                } label: {
                                    Text(entry.sharingCustom ? (CuadraoCopy.text("copy.cuadraoFirstAccountSheet.1bff0bb3fc", spanish: spanish)) : "\(entry.share)%")
                                        .frame(minHeight: 44)
                                }.accessibilityIdentifier(ids.share)
                            }
                            if entry.sharingCustom {
                                PercentField(title: CuadraoCopy.text("copy.cuadraoFirstAccountSheet.1f4c965f11", spanish: spanish), text: $entry.customShare, bounds: .wholeShare,
                                             spanish: spanish, identifier: ids.share + ".percent")
                            }
                        }
                    }
                }.padding(24).disabled(locked)
            }
            .scrollDismissesKeyboard(.interactively)
            // The sheet's button rides above the keyboard, so the balance under Name would sit behind it.
            .onReceive(NotificationCenter.default.publisher(for: UIResponder.keyboardDidShowNotification)) { _ in
                guard nameFocused else { return }
                withAnimation(reduceMotion ? nil : .easeOut(duration: 0.2)) { proxy.scrollTo(Self.amountAnchor, anchor: .bottom) }
            }
            }
            .background(WelcomePalette.background)
            .navigationTitle(editing ? (CuadraoCopy.text("copy.cuadraoFirstAccountSheet.4df1187ce2", spanish: spanish)) : (CuadraoCopy.text("copy.connectedCuadraoHome.10d1d9ce3f", spanish: spanish)))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                CuadraoCancelToolbar(title: CuadraoCopy.text("copy.connectedCuadraoProfile.62a128b722", spanish: spanish), disabled: busy, identifier: ids.cancel, action: cancel)
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
                    RegistrationButton(title: primaryTitle ?? (editing ? (CuadraoCopy.text("copy.cuadraoAccountManagement.553ab1bf1a", spanish: spanish)) : (CuadraoCopy.text("copy.cuadraoFirstAccountSheet.aae0895459", spanish: spanish))),
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
            Text(CuadraoCopy.text("copy.cuadraoFirstAccountSheet.714b4a6fb3", spanish: spanish)).foregroundStyle(.secondary)
        }.font(.subheadline)
    }
    private var typePicker: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text(CuadraoCopy.text("copy.cuadraoFirstAccountSheet.94ce9d10da", spanish: spanish)).font(.subheadline)
            if let kind = entry.kind, !pickingType {
                Button { withAnimation(reduceMotion ? nil : .easeInOut(duration: 0.2)) { pickingType = true } } label: {
                    HStack(spacing: 14) {
                        CanvasAccountIcon(kind: kind)
                        Text(kind.title(spanish)).foregroundStyle(.primary)
                        Spacer()
                        if !kindLocked { Image(systemName: "chevron.down").font(.caption).foregroundStyle(.secondary) }
                    }.padding(18).background(WelcomePalette.sage.opacity(0.65), in: RoundedRectangle(cornerRadius: 16))
                }.buttonStyle(.plain).disabled(kindLocked).accessibilityLabel(kindLocked ? (CuadraoCopy.text("copy.cuadraoFirstAccountSheet.f2f5a5b366", spanish: spanish, String(describing: kind.title(spanish))))
                        : (CuadraoCopy.text("copy.cuadraoFirstAccountSheet.2767912ee7", spanish: spanish, String(describing: kind.title(spanish)))))
                    .accessibilityIdentifier(ids.typeChange)
            } else {
                typeGrid(CanvasAccountKind.allCases.filter { !$0.isAsset })
                DisclosureGroup(isExpanded: $assetsExpanded) {
                    typeGrid(CanvasAccountKind.allCases.filter(\.isAsset)).padding(.top, 12)
                } label: {
                    HStack(spacing: 12) {
                        CanvasAccountIcon(kind: .asset, size: 21)
                        Text(CuadraoCopy.text("copy.cuadraoFirstAccountSheet.4350bed6e7", spanish: spanish)).foregroundStyle(.primary)
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
                        error = CuadraoCopy.text("copy.cuadraoFirstAccountSheet.9cd9638ceb", spanish: spanish)
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
