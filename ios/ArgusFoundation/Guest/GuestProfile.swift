import SwiftUI
import CuadraoBook

enum GuestProfileRoute: Hashable {
    case preferences, privacy, receipts

    func title(_ es: Bool) -> String {
        switch self {
        case .preferences: CuadraoCopy.text("copy.guestProfile.7f8139b9a4", spanish: es)
        case .privacy: CuadraoCopy.text("copy.guestProfile.2c59cb5dad", spanish: es)
        case .receipts: CuadraoCopy.text("copy.guestProfile.44feb0dd16", spanish: es)
        }
    }

    var symbol: String {
        switch self {
        case .preferences: "slider.horizontal.3"
        case .privacy: "hand.raised"
        case .receipts: "doc.text.viewfinder"
        }
    }
}

/// Profile for the on-device book: no identity, no server settings. It offers the way to a real account, the
/// two settings that work offline, the legal pages and the one destructive action the book owns.
struct GuestProfile: View {
    @ObservedObject var model: GuestBookModel
    @Binding var appearance: AppearancePreference
    @Binding var path: [GuestProfileRoute]
    let leave: () -> Void
    let deleteData: () async -> Bool
    @Environment(\.locale) private var locale
    @Environment(\.guestReceipts) private var receipts

    private var spanish: Bool { CuadraoCopy.isSpanish() }

    var body: some View {
        NavigationStack(path: $path) {
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    modeNotice
                    header
                    group(CuadraoCopy.text("copy.connectedAccountPresentation.f9d32ca2e5", spanish: spanish)) {
                        action(symbol: "arrow.right.circle", title: CuadraoCopy.text("copy.connectedCuadraoAuth.99024c1d78", spanish: spanish),
                               identifier: "guest.profile.signin", perform: leave)
                    }
                    Text(GuestCopy.bookStays(spanish)).font(.footnote).foregroundStyle(.secondary)
                        .padding(.horizontal, 4).accessibilityIdentifier("guest.profile.notice")
                    group(CuadraoCopy.text("copy.guestProfile.b67b6e77f6", spanish: CuadraoCopy.isSpanish())) {
                        link(.preferences, identifier: "guest.profile.preferences")
                        separator
                        link(.privacy, identifier: "guest.profile.privacy")
                        if receipts != nil {
                            separator
                            link(.receipts, identifier: "guest.profile.receipts")
                        }
                    }
                    legal
                }
                .padding(.horizontal, 24).padding(.top, 24).padding(.bottom, 112)
            }
            .background(WelcomePalette.background)
            .accessibilityIdentifier("guest.profile")
            .toolbar(.hidden, for: .navigationBar)
            .navigationDestination(for: GuestProfileRoute.self) { route in
                switch route {
                case .preferences: GuestPreferences(model: model, appearance: $appearance, spanish: spanish)
                case .privacy: GuestPrivacy(spanish: spanish, deleteData: deleteData)
                case .receipts:
                    if let receipts { GuestReceiptsList(store: receipts, model: model, spanish: spanish) }
                }
            }
        }
        .toolbar(.hidden, for: .tabBar)
    }

    /// The line the book says once on first open, kept here for good, with the way to a real account.
    private var modeNotice: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text(GuestNoticeCopy(spanish: spanish).modeLine).font(.subheadline.weight(.medium))
                .accessibilityIdentifier("guest.profile.mode")
            RegistrationButton(title: GuestNoticeCopy(spanish: spanish).createAccount, action: leave)
                .accessibilityIdentifier("guest.profile.signup")
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(CuadraoCopy.text("copy.guestProfile.9d28a6edfd", spanish: spanish))
                .font(.system(.title2, design: .default, weight: .semibold))
            Text(CuadraoCopy.text("copy.guestProfile.3febded68a", spanish: spanish))
                .font(.subheadline).foregroundStyle(.secondary)
        }.accessibilityElement(children: .combine).accessibilityIdentifier("guest.profile.header")
    }

    private var separator: some View {
        Rectangle().fill(CanvasSettingsStyle.separator).frame(height: 0.5)
            .padding(.leading, 54).padding(.trailing, 18).accessibilityHidden(true)
    }

    private func group<Rows: View>(_ title: String, @ViewBuilder rows: () -> Rows) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title).font(.subheadline).foregroundStyle(.secondary).accessibilityAddTraits(.isHeader)
            VStack(spacing: 0, content: rows)
                .background(CanvasSettingsStyle.surface, in: RoundedRectangle(cornerRadius: 22))
        }
    }

    private func rowLabel(symbol: String, title: String, chevron: Bool) -> some View {
        HStack(spacing: 14) {
            Image(systemName: symbol).font(.system(size: 19)).environment(\.symbolVariants, .none)
                .frame(width: 22, height: 22).foregroundStyle(.secondary).accessibilityHidden(true)
            Text(title).font(.body).multilineTextAlignment(.leading)
            Spacer(minLength: 8)
            if chevron {
                Image(systemName: "chevron.right").font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(.tertiary).accessibilityHidden(true)
            }
        }.padding(.horizontal, 18).padding(.vertical, 16).frame(minHeight: 56).contentShape(Rectangle())
    }

    private func action(symbol: String, title: String, identifier: String, perform: @escaping () -> Void) -> some View {
        Button(action: perform) { rowLabel(symbol: symbol, title: title, chevron: true) }
            .buttonStyle(.plain).accessibilityIdentifier(identifier)
    }

    private func link(_ route: GuestProfileRoute, identifier: String) -> some View {
        NavigationLink(value: route) { rowLabel(symbol: route.symbol, title: route.title(spanish), chevron: true) }
            .buttonStyle(.plain).accessibilityIdentifier(identifier)
    }

    @ViewBuilder private var legal: some View {
        let legal = CuadraoLegalURLs.current
        if legal.hasPages {
            group(CuadraoCopy.text("copy.cuadraoProfilePage.e9a2ff8d1a", spanish: spanish)) {
                if let terms = legal.terms {
                    Link(destination: terms) {
                        rowLabel(symbol: "doc.text", title: CuadraoCopy.text("copy.connectedCuadraoProfile.2fe6836750", spanish: spanish), chevron: false)
                    }.buttonStyle(.plain).accessibilityIdentifier("guest.profile.terms")
                }
                if legal.terms != nil, legal.privacy != nil { separator }
                if let privacy = legal.privacy {
                    Link(destination: privacy) {
                        rowLabel(symbol: "hand.raised", title: CuadraoCopy.text("copy.cuadraoProfilePage.3a2527a0ac", spanish: spanish), chevron: false)
                    }.buttonStyle(.plain).accessibilityIdentifier("guest.profile.legal")
                }
            }
        }
    }
}

/// The words the book uses for itself, Spanish first. One place, so the same sentence is never retyped.
enum GuestCopy {
    static func bookStays(_ es: Bool) -> String {
        CuadraoCopy.text("copy.guestProfile.8bc6e5a42e", spanish: es)
    }
}

private struct GuestPreferences: View {
    @ObservedObject var model: GuestBookModel
    @Binding var appearance: AppearancePreference
    let spanish: Bool
    @State private var choosingCurrency = false

    private var currency: String? { model.book.settings.primaryCurrency }

    var body: some View {
        Form {
            Section {
                CuadraoAppearanceChoices(spanish: spanish, selection: $appearance)
            } header: { Text(CuadraoCopy.text("copy.cuadraoProfilePage.6d3e76f91f", spanish: spanish)) }
              footer: { Text(CuadraoCopy.text("copy.cuadraoProfilePage.b894f61cc1", spanish: spanish)) }
                .listRowBackground(CanvasSettingsStyle.surface)
            Section {
                LabeledContent(CuadraoCopy.text("copy.cuadraoProfilePage.98633ea3c0", spanish: spanish)) { Text(CuadraoCopy.text("copy.cuadraoProfilePage.244f0f8d3d", spanish: spanish)).foregroundStyle(.secondary) }
                    .accessibilityIdentifier("guest.profile.language")
            }
            .listRowBackground(CanvasSettingsStyle.surface)
            Section {
                Button { choosingCurrency = true } label: {
                    HStack {
                        Text(CuadraoCopy.text("copy.connectedProfileCurrencyRow.8ceb934024", spanish: spanish)).foregroundStyle(.primary)
                        Spacer()
                        Text(currency ?? (CuadraoCopy.text("copy.connectedProfileCurrencyRow.8f6645049d", spanish: spanish))).foregroundStyle(.secondary)
                        Image(systemName: "chevron.down").font(.caption).foregroundStyle(.secondary)
                    }.frame(minHeight: 44).contentShape(Rectangle())
                }
                .accessibilityIdentifier("guest.profile.currency")
                .accessibilityValue(currency ?? "")
            } header: { Text(CuadraoCopy.text("copy.connectedTransactionSheet.9b96ad5816", spanish: spanish)) }
              footer: { Text(CuadraoCopy.text("copy.cuadraoProfilePage.854936f059", spanish: spanish)) }
                .listRowBackground(CanvasSettingsStyle.surface)
        }
        .environment(\.defaultMinListRowHeight, 52)
        .scrollContentBackground(.hidden).background(WelcomePalette.background)
        .navigationTitle(GuestProfileRoute.preferences.title(spanish)).navigationBarTitleDisplayMode(.large)
        .toolbar(.visible, for: .navigationBar)
        .sheet(isPresented: $choosingCurrency) {
            GuestCurrencyPicker(selection: currency, spanish: spanish) { code in
                _ = try? model.apply { try $0.settingPrimaryCurrency(code) }
            }
        }
    }
}

private struct GuestPrivacy: View {
    let spanish: Bool
    let deleteData: () async -> Bool
    @State private var confirmingDelete = false
    @State private var deleteFailed = false

    var body: some View {
        Form {
            Section {
                Text(CuadraoCopy.text("copy.guestProfile.7593f664ee", spanish: spanish))
                    .font(.subheadline).foregroundStyle(.secondary)
            }.listRowBackground(Color.clear)
            Section {
                Button(CuadraoCopy.text("copy.guestProfile.77303954dc", spanish: spanish), role: .destructive) { confirmingDelete = true }
                    .foregroundStyle(.red).frame(minHeight: 44).accessibilityIdentifier("guest.profile.delete")
            } footer: {
                Text(CuadraoCopy.text("copy.guestProfile.845e26f349", spanish: spanish))
            }.listRowBackground(CanvasSettingsStyle.surface)
        }
        .environment(\.defaultMinListRowHeight, 52)
        .scrollContentBackground(.hidden).background(WelcomePalette.background)
        .navigationTitle(GuestProfileRoute.privacy.title(spanish)).navigationBarTitleDisplayMode(.large)
        .toolbar(.visible, for: .navigationBar)
        .alert(GuestDeleteCopy.title(spanish), isPresented: $confirmingDelete) {
            Button(CuadraoCopy.text("copy.connectedCuadraoProfile.62a128b722", spanish: spanish), role: .cancel) {}
            Button(GuestDeleteCopy.confirm(spanish), role: .destructive) {
                Task { if await !deleteData() { deleteFailed = true } }
            }.accessibilityIdentifier("guest.delete.confirm")
        } message: { Text(GuestDeleteCopy.message(spanish)) }
        .alert(GuestDeleteCopy.failed(spanish), isPresented: $deleteFailed) {
            Button(CuadraoCopy.text("copy.cuadraoAccountCanvas.43385c465a", spanish: spanish), role: .cancel) {}
        }
    }
}
