import SwiftUI

struct ConnectedCuadraoProfile: View {
    @Binding var appearance: AppearancePreference
    @Binding var avatar: CuadraoAvatarSelection
    @Binding var path: [CanvasProfileRoute]
    var bottomSpace: CGFloat = 88
    @EnvironmentObject private var auth: ProfileAuthModel
    @Environment(\.locale) private var locale
    @State private var editing = false
    @State private var confirmingSignOut = false
    @State private var claim: GuestClaimModel?
    @Environment(\.cuadraoGuestClaim) private var guestClaim
    @State private var settingsExamples = CuadraoProfileSettingsDraft()
    private var spanish: Bool { locale.language.languageCode?.identifier == "es" }
    private var displayName: String { auth.profile?.displayName ?? (spanish ? "Tu perfil" : "Your profile") }

    var body: some View {
        NavigationStack(path: $path) {
            CuadraoProfileBody(spanish: spanish,
                identity: .init(name: displayName, emailAddress: auth.profile?.email, avatar: avatar),
                bottomSpace: bottomSpace, editProfile: { editing = true }) {
                if let invitations = auth.invitations { ConnectedProfileInvitationsRow(model: invitations) }
                if let guestClaim { GuestClaimRow(spanish: spanish) { openClaim(guestClaim) } }
            } accountActions: {
                signOut
            }
            .navigationDestination(for: CanvasProfileRoute.self) { route in
                if route == .invitations, let invitations = auth.invitations {
                    InvitationsHub(model: invitations).toolbar(.visible, for: .navigationBar)
                } else if route == .files, CuadraoFirstRelease.savedReceipts, let receipts = auth.savedReceipts {
                    SavedReceiptsScreen(model: receipts, spanish: spanish, review: { document in
                        Task { await auth.receiptJourney?.open(document.connectionID) }
                    }).toolbar(.visible, for: .navigationBar)
                } else {
                    CuadraoProfilePage(route: route, settings: $settingsExamples, spanish: spanish,
                        includeExamples: true, connection: .connected(appearance: $appearance, profile: auth))
                }
            }
            .sheet(isPresented: $editing) {
                NavigationStack {
                    CuadraoProfileEditor(name: .constant(auth.profile?.displayName ?? ""),
                        preferredName: .constant(auth.profile?.preferredName ?? ""),
                        emailAddress: auth.profile?.email, avatar: $avatar, spanish: spanish,
                        saveNames: { await auth.setNames(displayName: $0, preferredName: $1) })
                }.tint(WelcomePalette.pine).preferredColorScheme(appearance.colorScheme)
            }
            .sheet(item: $claim) { model in
                GuestClaimSheet(model: model, close: { claim = nil }).preferredColorScheme(appearance.colorScheme)
            }
            .alert(spanish ? "¿Cerrar sesión?" : "Sign out?", isPresented: $confirmingSignOut) {
                Button(spanish ? "Cancelar" : "Cancel", role: .cancel) {}
                Button(spanish ? "Cerrar sesión" : "Sign out", role: .destructive) { Task { await auth.signOut() } }
                    .accessibilityIdentifier("auth.signOut.confirm")
            } message: {
                Text(spanish ? "Volverás a la pantalla de inicio de sesión." : "You'll return to the sign-in screen.")
            }
        }
        .toolbar(.hidden, for: .tabBar)
        .onChange(of: auth.profile?.id) { _, _ in
            settingsExamples = CuadraoProfileSettingsDraft()
            editing = false
            confirmingSignOut = false
        }
    }

    private func openClaim(_ entry: GuestClaimEntry) {
        Task {
            guard let server = await auth.guestClaimServer() else { return }
            claim = GuestClaimModel(directory: entry.directory, server: server, spanish: spanish, discard: entry.discard)
        }
    }

    private var signOut: some View {
        VStack(spacing: 6) {
            Button(spanish ? "Cerrar sesión" : "Sign out") { confirmingSignOut = true }
                .font(.subheadline).foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, minHeight: 44)
                .disabled(auth.busy)
                .accessibilityIdentifier("auth.signOut")
            if let key = auth.errorKey {
                Text(LocalizedStringKey(key)).font(.footnote).foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity).multilineTextAlignment(.center)
                    .accessibilityIdentifier("auth.error")
            }
        }
    }
}

private struct ConnectedProfileInvitationsRow: View {
    @ObservedObject var model: InvitationsModel
    @Environment(\.locale) private var locale

    var body: some View {
        if model.showsInvitations {
            Rectangle().fill(CanvasSettingsStyle.separator).frame(height: 0.5)
                .padding(.leading, 54).padding(.trailing, 18).accessibilityHidden(true)
            NavigationLink(value: CanvasProfileRoute.invitations) {
                CanvasProfileRow(route: .invitations, spanish: locale.language.languageCode?.identifier == "es")
            }.buttonStyle(.plain).accessibilityIdentifier("invites.profile")
        }
    }
}

struct CuadraoLegalLinks: View {
    var legal: CuadraoLegalURLs = .current
    @Environment(\.locale) private var locale
    private var spanish: Bool { locale.language.languageCode?.identifier == "es" }

    var body: some View {
        List {
            if legal.hasPages {
                if let privacy = legal.privacy {
                    Link(destination: privacy) {
                        Label(spanish ? "Privacidad" : "Privacy", systemImage: "hand.raised")
                    }.accessibilityIdentifier("release.legal.privacy")
                }
                if let terms = legal.terms {
                    Link(destination: terms) {
                        Label(spanish ? "Términos de uso" : "Terms of use", systemImage: "doc.text")
                    }.accessibilityIdentifier("release.legal.terms")
                }
            } else {
                Text(spanish ? "Los enlaces no están disponibles en este momento." : "These links aren't available right now.")
            }
        }.navigationTitle(spanish ? "Privacidad y términos" : "Privacy and terms")
            .navigationBarTitleDisplayMode(.inline).toolbar(.visible, for: .navigationBar)
    }
}
