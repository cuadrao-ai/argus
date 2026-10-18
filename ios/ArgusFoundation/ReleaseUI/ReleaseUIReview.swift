#if DEBUG
import SwiftUI

private enum ReleaseReviewRoute: Hashable { case identity, invites, updates, legal }

struct ReleaseUIReview: View {
    @Environment(\.locale) private var locale
    @State private var avatar: CuadraoAvatarSelection = .none
    @State private var tab: CuadraoTab = .profile
    @State private var editing = false
    @State private var path = NavigationPath()
    private var spanish: Bool { CuadraoCopy.isSpanish() }

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
                Section(CuadraoCopy.text("copy.connectedAccountPresentation.f9d32ca2e5", spanish: spanish)) {
                    NavigationLink(value: ReleaseReviewRoute.identity) {
                        Label(CuadraoCopy.text("copy.releaseIdentityGallery.ba2eba4b9a", spanish: spanish), systemImage: "person.crop.circle")
                    }.accessibilityIdentifier("release.review.identity")
                    NavigationLink(value: ReleaseReviewRoute.invites) {
                        Label(CuadraoCopy.text("copy.invitationViews.4970c3efc4", spanish: spanish), systemImage: "person.badge.plus")
                    }.accessibilityIdentifier("release.review.invites")
                    NavigationLink(value: ReleaseReviewRoute.updates) {
                        Label(CuadraoCopy.text("copy.cuadraoHomePresentation.41483aed95", spanish: spanish), systemImage: "bell")
                    }.accessibilityIdentifier("release.review.updates")
                    NavigationLink(value: ReleaseReviewRoute.legal) {
                        Label(CuadraoCopy.text("copy.connectedCuadraoProfile.7081fb1e80", spanish: spanish), systemImage: "hand.raised")
                    }.accessibilityIdentifier("release.review.legal")
                }
            }
            .navigationTitle(CuadraoCopy.text("copy.releaseUIReview.2f5585913a", spanish: spanish))
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
                if editable { Text(CuadraoCopy.text("copy.releaseUIReview.0f597966d4", spanish: spanish)).font(.subheadline) }
            }
            Spacer()
        }.padding(.vertical, 8)
    }
}
#endif
