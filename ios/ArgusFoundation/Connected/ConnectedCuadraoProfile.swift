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
    private var spanish: Bool { CuadraoCopy.isSpanish() }
    private var displayName: String { auth.profile?.displayName ?? (CuadraoCopy.text("copy.connectedCuadraoProfile.95d374b19b", spanish: spanish)) }

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
            .alert(CuadraoCopy.text("copy.connectedCuadraoProfile.acc5cbf2ec", spanish: spanish), isPresented: $confirmingSignOut) {
                Button(CuadraoCopy.text("copy.connectedCuadraoProfile.62a128b722", spanish: spanish), role: .cancel) {}
                Button(CuadraoCopy.text("copy.connectedCuadraoProfile.a47c0e9665", spanish: spanish), role: .destructive) { Task { await auth.signOut() } }
                    .accessibilityIdentifier("auth.signOut.confirm")
            } message: {
                Text(CuadraoCopy.text("copy.connectedCuadraoProfile.43803ec665", spanish: spanish))
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
            Button(CuadraoCopy.text("copy.connectedCuadraoProfile.a47c0e9665", spanish: spanish)) { confirmingSignOut = true }
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
                CanvasProfileRow(route: .invitations, spanish: CuadraoCopy.isSpanish())
            }.buttonStyle(.plain).accessibilityIdentifier("invites.profile")
        }
    }
}

struct CuadraoLegalLinks: View {
    var legal: CuadraoLegalURLs = .current
    @Environment(\.locale) private var locale
    private var spanish: Bool { CuadraoCopy.isSpanish() }

    var body: some View {
        List {
            if legal.hasPages {
                if let privacy = legal.privacy {
                    Link(destination: privacy) {
                        Label(CuadraoCopy.text("copy.connectedCuadraoProfile.a405422e66", spanish: spanish), systemImage: "hand.raised")
                    }.accessibilityIdentifier("release.legal.privacy")
                }
                if let terms = legal.terms {
                    Link(destination: terms) {
                        Label(CuadraoCopy.text("copy.connectedCuadraoProfile.2fe6836750", spanish: spanish), systemImage: "doc.text")
                    }.accessibilityIdentifier("release.legal.terms")
                }
            } else {
                Text(CuadraoCopy.text("copy.connectedCuadraoProfile.7cc578247d", spanish: spanish))
            }
        }.navigationTitle(CuadraoCopy.text("copy.connectedCuadraoProfile.7081fb1e80", spanish: spanish))
            .navigationBarTitleDisplayMode(.inline).toolbar(.visible, for: .navigationBar)
    }
}
