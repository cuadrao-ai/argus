import SwiftUI

public struct ReleaseSocialSignInView: View {
    public let state: ReleaseSocialSignInState
    public let pendingInvite: ReleasePendingInvite?
    public let onSignIn: (ReleaseSocialProvider, ReleasePendingInvite?) -> Void
    public let onSaveName: (String, ReleasePendingInvite?) -> Void
    public let onContinue: (ReleasePendingInvite?) -> Void
    @Environment(\.locale) private var locale
    @State private var name = ""

    public init(state: ReleaseSocialSignInState, pendingInvite: ReleasePendingInvite? = nil,
                onSignIn: @escaping (ReleaseSocialProvider, ReleasePendingInvite?) -> Void,
                onSaveName: @escaping (String, ReleasePendingInvite?) -> Void,
                onContinue: @escaping (ReleasePendingInvite?) -> Void) {
        self.state = state; self.pendingInvite = pendingInvite
        self.onSignIn = onSignIn; self.onSaveName = onSaveName; self.onContinue = onContinue
    }

    private var spanish: Bool { locale.language.languageCode?.identifier == "es" }
    private func text(_ es: String, _ en: String) -> String { spanish ? es : en }

    public var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                Text(text("Entra a Cuadrao", "Sign in to Cuadrao"))
                    .font(CuadraoTypography.screen).accessibilityAddTraits(.isHeader)
                if let pendingInvite {
                    Label {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(pendingInvite.title).font(CuadraoTypography.action)
                            Text(text("Tu invitación te espera al entrar.", "Your invitation will be waiting after sign-in."))
                                .font(CuadraoTypography.supporting).foregroundStyle(.secondary)
                        }
                    } icon: { Image(systemName: "envelope") }
                    .accessibilityIdentifier("identity.social.pendingInvite")
                }
                if state == .missingName || state == .savingName || state == .nameFailed {
                    nameForm
                } else if state == .complete {
                    Label(text("Ya estás dentro", "You're signed in"), systemImage: "checkmark.circle")
                    Button(text("Continuar", "Continue")) { onContinue(pendingInvite) }
                        .buttonStyle(.borderedProminent)
                        .accessibilityIdentifier("identity.social.complete")
                } else {
                    providerButtons
                    status
                }
                if CuadraoLegalURLs.current.hasPages {
                    ReleaseIdentityLegalLinks()
                }
            }.padding(24).frame(maxWidth: 560, alignment: .leading).frame(maxWidth: .infinity)
        }
        .background(Color(uiColor: .systemBackground))
        .font(CuadraoTypography.body)
        .tint(WelcomePalette.pine)
        .navigationTitle(text("Iniciar sesión", "Sign in"))
        .navigationBarTitleDisplayMode(.inline)
        .accessibilityIdentifier("identity.social.screen")
    }

    private var providerButtons: some View {
        VStack(spacing: 12) {
            ForEach(ReleaseSocialProvider.allCases) { provider in
                Button { onSignIn(provider, pendingInvite) } label: {
                    HStack(spacing: 10) {
                        if provider == .apple { Image(systemName: "apple.logo").accessibilityHidden(true) }
                        Text(text("Continuar con \(provider.title)", "Continue with \(provider.title)"))
                            .multilineTextAlignment(.center)
                    }
                    .font(CuadraoTypography.action)
                    .padding(.horizontal, 16).padding(.vertical, 14)
                    .frame(maxWidth: .infinity, minHeight: 52)
                    .foregroundStyle(provider == .apple ? Color(uiColor: .systemBackground) : Color.primary)
                    .background(provider == .apple ? Color.primary : Color(uiColor: .secondarySystemBackground),
                                in: RoundedRectangle(cornerRadius: 14))
                    .overlay { RoundedRectangle(cornerRadius: 14).stroke(Color(uiColor: .separator), lineWidth: 0.5) }
                }
                .buttonStyle(.plain).disabled(state.isBusy)
                .accessibilityIdentifier("identity.social.\(provider.rawValue)")
            }
        }
    }

    @ViewBuilder private var status: some View {
        switch state {
        case .loading(let provider):
            ProgressView(text("Conectando con \(provider.title)…", "Connecting with \(provider.title)…"))
                .accessibilityIdentifier("identity.social.loading")
        case .cancelled:
            Text(text("Cancelaste el inicio de sesión. Puedes intentarlo otra vez.",
                      "Sign-in was cancelled. You can try again."))
                .foregroundStyle(.secondary).accessibilityIdentifier("identity.social.cancelled")
        case .failed:
            Label(text("No pudimos iniciar sesión. Inténtalo otra vez.", "We couldn't sign you in. Try again."),
                  systemImage: "exclamationmark.circle")
                .accessibilityIdentifier("identity.social.error")
        default: EmptyView()
        }
    }

    private var nameForm: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text(text("¿Cómo te llamas?", "What should we call you?")).font(CuadraoTypography.section)
            TextField(text("Tu nombre", "Your name"), text: $name)
                .textContentType(.givenName).textInputAutocapitalization(.words)
                .textFieldStyle(.roundedBorder).disabled(state.isBusy)
                .accessibilityIdentifier("identity.social.name")
            if state == .nameFailed {
                Text(text("No pudimos guardar tu nombre. Inténtalo otra vez.", "We couldn't save your name. Try again."))
                    .foregroundStyle(.secondary)
            }
            if state == .savingName { ProgressView(text("Guardando…", "Saving…")) }
            Button(text("Continuar", "Continue")) {
                onSaveName(name.trimmingCharacters(in: .whitespacesAndNewlines), pendingInvite)
            }
            .buttonStyle(.borderedProminent)
            .disabled(state.isBusy || name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            .accessibilityIdentifier("identity.social.saveName")
        }
    }
}

struct ReleaseIdentityLegalLinks: View {
    let legal: CuadraoLegalURLs
    @Environment(\.locale) private var locale
    init(legal: CuadraoLegalURLs = .current) { self.legal = legal }

    var body: some View {
        let spanish = locale.language.languageCode?.identifier == "es"
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 24) { links(spanish) }
            VStack(alignment: .leading, spacing: 4) { links(spanish) }
        }.font(CuadraoTypography.supporting)
    }

    @ViewBuilder private func links(_ spanish: Bool) -> some View {
        if let terms = legal.terms {
            Link(spanish ? "Términos" : "Terms", destination: terms)
                .frame(minHeight: 44).accessibilityIdentifier("identity.legal.terms")
        }
        if let privacy = legal.privacy {
            Link(spanish ? "Privacidad" : "Privacy", destination: privacy)
                .frame(minHeight: 44).accessibilityIdentifier("identity.legal.privacy")
        }
    }
}
