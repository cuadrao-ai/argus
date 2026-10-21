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

    private var spanish: Bool { CuadraoCopy.isSpanish() }

    public var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                Text(CuadraoCopy.text("copy.releaseSocialSignInView.1b2acf5dfd", spanish: spanish))
                    .font(CuadraoTypography.screen).accessibilityAddTraits(.isHeader)
                if let pendingInvite {
                    Label {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(pendingInvite.title).font(CuadraoTypography.action)
                            Text(CuadraoCopy.text("copy.releaseSocialSignInView.d1ffc4095d", spanish: spanish))
                                .font(CuadraoTypography.supporting).foregroundStyle(.secondary)
                        }
                    } icon: { Image(systemName: "envelope") }
                    .accessibilityIdentifier("identity.social.pendingInvite")
                }
                if state == .missingName || state == .savingName || state == .nameFailed {
                    nameForm
                } else if state == .complete {
                    Label(CuadraoCopy.text("copy.releaseSocialSignInView.0e746f0a2a", spanish: spanish), systemImage: "checkmark.circle")
                    Button(CuadraoCopy.text("copy.releaseSocialSignInView.c27a4762b9", spanish: spanish)) { onContinue(pendingInvite) }
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
        .navigationTitle(CuadraoCopy.text("copy.releaseSocialSignInView.99024c1d78", spanish: spanish))
        .navigationBarTitleDisplayMode(.inline)
        .accessibilityIdentifier("identity.social.screen")
    }

    private var providerButtons: some View {
        VStack(spacing: 12) {
            ForEach(ReleaseSocialProvider.allCases) { provider in
                Button { onSignIn(provider, pendingInvite) } label: {
                    HStack(spacing: 10) {
                        if provider == .apple { Image(systemName: "apple.logo").accessibilityHidden(true) }
                        Text(CuadraoCopy.text("copy.releaseSocialSignInView.08580b4d44", spanish: spanish, String(describing: provider.title)))
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
            ProgressView(CuadraoCopy.text("copy.releaseSocialSignInView.55beef0fe5", spanish: spanish, String(describing: provider.title)))
                .accessibilityIdentifier("identity.social.loading")
        case .cancelled:
            Text(CuadraoCopy.text("copy.releaseSocialSignInView.2bd47177f5", spanish: spanish))
                .foregroundStyle(.secondary).accessibilityIdentifier("identity.social.cancelled")
        case .failed:
            Label(CuadraoCopy.text("copy.releaseSocialSignInView.bd6090d050", spanish: spanish),
                  systemImage: "exclamationmark.circle")
                .accessibilityIdentifier("identity.social.error")
        default: EmptyView()
        }
    }

    private var nameForm: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text(CuadraoCopy.text("copy.releaseSocialSignInView.47ff37592a", spanish: spanish)).font(CuadraoTypography.section)
            TextField(CuadraoCopy.text("copy.releaseSocialSignInView.ef3db0bd59", spanish: spanish), text: $name)
                .textContentType(.givenName).textInputAutocapitalization(.words)
                .textFieldStyle(.roundedBorder).disabled(state.isBusy)
                .accessibilityIdentifier("identity.social.name")
            if state == .nameFailed {
                Text(CuadraoCopy.text("copy.releaseSocialSignInView.5bfb080c11", spanish: spanish))
                    .foregroundStyle(.secondary)
            }
            if state == .savingName { ProgressView(CuadraoCopy.text("copy.releaseSocialSignInView.5f4c79aff9", spanish: spanish)) }
            Button(CuadraoCopy.text("copy.releaseSocialSignInView.c27a4762b9", spanish: spanish)) {
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
        let spanish = CuadraoCopy.isSpanish()
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 24) { links(spanish) }
            VStack(alignment: .leading, spacing: 4) { links(spanish) }
        }.font(CuadraoTypography.supporting)
    }

    @ViewBuilder private func links(_ spanish: Bool) -> some View {
        if let terms = legal.terms {
            Link(CuadraoCopy.text("copy.releaseSocialSignInView.e6e8e0f79a", spanish: spanish), destination: terms)
                .frame(minHeight: 44).accessibilityIdentifier("identity.legal.terms")
        }
        if let privacy = legal.privacy {
            Link(CuadraoCopy.text("copy.connectedCuadraoProfile.a405422e66", spanish: spanish), destination: privacy)
                .frame(minHeight: 44).accessibilityIdentifier("identity.legal.privacy")
        }
    }
}
