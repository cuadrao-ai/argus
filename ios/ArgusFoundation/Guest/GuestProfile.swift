import SwiftUI
import CuadraoBook

enum GuestProfileRoute: Hashable {
    case preferences, privacy

    func title(_ es: Bool) -> String {
        switch self {
        case .preferences: es ? "Preferencias" : "Preferences"
        case .privacy: es ? "Datos y privacidad" : "Data and privacy"
        }
    }

    var symbol: String {
        switch self {
        case .preferences: "slider.horizontal.3"
        case .privacy: "hand.raised"
        }
    }
}

/// Profile for the on-device book: no identity, no server settings. It offers the way to a real account, the
/// two settings that work offline, the legal pages and the one destructive action the book owns.
struct GuestProfile: View {
    @ObservedObject var model: GuestBookModel
    @Binding var appearance: AppearancePreference
    @Binding var path: [GuestProfileRoute]
    let webURL: URL?
    let leave: () -> Void
    let deleteData: () async -> Bool
    @Environment(\.locale) private var locale

    private var spanish: Bool { locale.language.languageCode?.identifier == "es" }

    var body: some View {
        NavigationStack(path: $path) {
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    header
                    group(spanish ? "Cuenta" : "Account") {
                        action(symbol: "person.badge.plus", title: spanish ? "Crear cuenta" : "Create account",
                               identifier: "guest.profile.signup", perform: leave)
                        separator
                        action(symbol: "arrow.right.circle", title: spanish ? "Iniciar sesión" : "Sign in",
                               identifier: "guest.profile.signin", perform: leave)
                    }
                    Text(GuestCopy.bookStays(spanish)).font(.footnote).foregroundStyle(.secondary)
                        .padding(.horizontal, 4).accessibilityIdentifier("guest.profile.notice")
                    group("App") {
                        link(.preferences, identifier: "guest.profile.preferences")
                        separator
                        link(.privacy, identifier: "guest.profile.privacy")
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
                }
            }
        }
        .toolbar(.hidden, for: .tabBar)
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(spanish ? "Tu libro en este iPhone" : "Your book on this iPhone")
                .font(.system(.title2, design: .default, weight: .semibold))
            Text(spanish ? "Solo vive aquí. No se sube a ningún lado." : "It lives only here. It isn't uploaded anywhere.")
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
        if let webURL {
            group(spanish ? "Acerca de Cuadrao" : "About Cuadrao") {
                Link(destination: webURL.appendingPathComponent("terms")) {
                    rowLabel(symbol: "doc.text", title: spanish ? "Términos de uso" : "Terms of use", chevron: false)
                }.buttonStyle(.plain).accessibilityIdentifier("guest.profile.terms")
                separator
                Link(destination: webURL.appendingPathComponent("privacy")) {
                    rowLabel(symbol: "hand.raised", title: spanish ? "Política de privacidad" : "Privacy policy", chevron: false)
                }.buttonStyle(.plain).accessibilityIdentifier("guest.profile.legal")
            }
        }
    }
}

/// The words the book uses for itself, Spanish first. One place, so the same sentence is never retyped.
enum GuestCopy {
    static func bookStays(_ es: Bool) -> String {
        es ? "Tu libro de este iPhone sigue aquí; no se subió." : "Your book on this iPhone is still here; it was not uploaded."
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
            } header: { Text(spanish ? "Apariencia" : "Appearance") }
              footer: { Text(spanish ? "Sistema sigue la apariencia de tu iPhone." : "System follows your iPhone’s appearance.") }
                .listRowBackground(CanvasSettingsStyle.surface)
            Section {
                Button { choosingCurrency = true } label: {
                    HStack {
                        Text(spanish ? "Moneda preferida" : "Preferred currency").foregroundStyle(.primary)
                        Spacer()
                        Text(currency ?? (spanish ? "Elegir" : "Choose")).foregroundStyle(.secondary)
                        Image(systemName: "chevron.down").font(.caption).foregroundStyle(.secondary)
                    }.frame(minHeight: 44).contentShape(Rectangle())
                }
                .accessibilityIdentifier("guest.profile.currency")
                .accessibilityValue(currency ?? "")
            } header: { Text(spanish ? "Moneda" : "Currency") }
              footer: { Text(spanish ? "Elegir una moneda no convierte ni combina tus balances." : "Choosing a currency does not convert or combine your balances.") }
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
                Text(spanish ? "Tus cuentas, movimientos, presupuestos y metas se guardan solo en este iPhone, sin cuenta ni conexión. Si borras la app, se borran con ella."
                     : "Your accounts, activity, budgets and goals are kept only on this iPhone, with no account and no connection. If you delete the app, they go with it.")
                    .font(.subheadline).foregroundStyle(.secondary)
            }.listRowBackground(Color.clear)
            Section {
                Button(spanish ? "Eliminar los datos de este iPhone" : "Delete this iPhone's data", role: .destructive) { confirmingDelete = true }
                    .frame(minHeight: 44).accessibilityIdentifier("guest.profile.delete")
            } footer: {
                Text(spanish ? "Quita tu libro de este iPhone. Si luego creas una cuenta, esto no la toca."
                     : "Removes your book from this iPhone. If you create an account later, this doesn't touch it.")
            }.listRowBackground(CanvasSettingsStyle.surface)
        }
        .environment(\.defaultMinListRowHeight, 52)
        .scrollContentBackground(.hidden).background(WelcomePalette.background)
        .navigationTitle(GuestProfileRoute.privacy.title(spanish)).navigationBarTitleDisplayMode(.large)
        .toolbar(.visible, for: .navigationBar)
        .alert(GuestDeleteCopy.title(spanish), isPresented: $confirmingDelete) {
            Button(spanish ? "Cancelar" : "Cancel", role: .cancel) {}
            Button(GuestDeleteCopy.confirm(spanish), role: .destructive) {
                Task { if await !deleteData() { deleteFailed = true } }
            }.accessibilityIdentifier("guest.delete.confirm")
        } message: { Text(GuestDeleteCopy.message(spanish)) }
        .alert(GuestDeleteCopy.failed(spanish), isPresented: $deleteFailed) {
            Button(spanish ? "Entendido" : "Got it", role: .cancel) {}
        }
    }
}
