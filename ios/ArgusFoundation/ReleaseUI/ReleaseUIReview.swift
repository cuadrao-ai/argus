#if DEBUG
import SwiftUI

private enum ReleaseReviewRoute: Hashable { case identity, invites, updates, legal }

struct ReleaseUIReview: View {
    @Environment(\.locale) private var locale
    @State private var avatar: CuadraoAvatarSelection = .none
    @State private var tab: CuadraoTab = .profile
    @State private var editing = false
    @State private var path = NavigationPath()
    private var spanish: Bool { locale.language.languageCode?.identifier == "es" }

    var body: some View {
        NavigationStack(path: $path) {
            List {
                Section {
                    if CuadraoFirstRelease.editsAvatar {
                        Button { editing = true } label: { identity(editable: true) }
                            .accessibilityIdentifier("release.profile.avatar")
                    } else {
                        identity(editable: false).accessibilityElement(children: .combine)
                            .accessibilityIdentifier("release.profile.display")
                    }
                }
                Section(spanish ? "Cuenta" : "Account") {
                    NavigationLink(value: ReleaseReviewRoute.identity) {
                        Label(spanish ? "Identidad y datos" : "Identity and data", systemImage: "person.crop.circle")
                    }.accessibilityIdentifier("release.review.identity")
                    NavigationLink(value: ReleaseReviewRoute.invites) {
                        Label(spanish ? "Invitaciones" : "Invitations", systemImage: "person.badge.plus")
                    }.accessibilityIdentifier("release.review.invites")
                    NavigationLink(value: ReleaseReviewRoute.updates) {
                        Label(spanish ? "Novedades" : "Updates", systemImage: "bell")
                    }.accessibilityIdentifier("release.review.updates")
                    NavigationLink(value: ReleaseReviewRoute.legal) {
                        Label(spanish ? "Privacidad y términos" : "Privacy and terms", systemImage: "hand.raised")
                    }.accessibilityIdentifier("release.review.legal")
                }
            }
            .navigationTitle(spanish ? "Revisión de interfaz" : "UI review")
            .navigationBarTitleDisplayMode(.inline)
            .safeAreaInset(edge: .bottom) {
                if path.isEmpty {
                    CuadraoNavigationBar(selection: $tab, compact: false, spanish: spanish, avatar: avatar, profileName: "Alex", add: {})
                        .padding(.horizontal, 20).padding(.bottom, 8)
                }
            }
            .navigationDestination(for: ReleaseReviewRoute.self) { route in
                switch route {
                case .identity: ReleaseIdentityGallery()
                case .invites: ReleaseInvitationsGallery()
                case .updates: ReleaseUpdatesGallery(spanish: spanish)
                case .legal: CuadraoLegalLinks()
                }
            }
            .sheet(isPresented: $editing) { CuadraoIdentityEditor(name: "Alex", selection: $avatar) }
        }.tint(WelcomePalette.pine)
            .preferredColorScheme(ProcessInfo.processInfo.arguments.contains("--release-dark") ? .dark : nil)
    }

    private func identity(editable: Bool) -> some View {
        HStack(spacing: 18) {
            CuadraoIdentityAvatar(selection: avatar, name: "Alex", size: 64)
            VStack(alignment: .leading, spacing: 5) {
                Text("Alex").font(.title2.weight(.semibold)).foregroundStyle(.primary)
                if editable { Text(spanish ? "Editar avatar" : "Edit avatar").font(.subheadline) }
            }
            Spacer()
        }.padding(.vertical, 8)
    }
}
#endif
