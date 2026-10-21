#if DEBUG
import SwiftUI
import ArgusSession

struct ReleaseInvitationsGallery: View {
    @Environment(\.locale) private var locale
    private var spanish: Bool { CuadraoCopy.isSpanish() }

    var body: some View {
        List {
            Section {
                Text(CuadraoCopy.text("copy.releaseInvitationsGallery.2a39b56bcd", spanish: spanish))
            }
            Section(CuadraoCopy.text("copy.releaseInvitationsGallery.faf72f6575", spanish: spanish)) {
                ForEach(ReleaseInviteGateState.allCases, id: \.rawValue) { state in
                    NavigationLink(state.title(spanish: spanish)) {
                        ReleaseInviteGateFixture(initialState: state, spanish: spanish)
                    }.accessibilityIdentifier("release.invites.gallery.gate." + state.rawValue)
                }
            }
            Section(CuadraoCopy.text("copy.releaseInvitationsGallery.48a1e769ec", spanish: spanish)) {
                NavigationLink(CuadraoCopy.text("copy.releaseInvitationsGallery.a027f19e14", spanish: spanish)) {
                    ReleasePersonalInvitationFixture(spanish: spanish)
                }.accessibilityIdentifier("release.invites.gallery.personal")
                NavigationLink(CuadraoCopy.text("copy.releaseInvitationsGallery.e7ff74dc02", spanish: spanish)) {
                    ReleasePersonalInvitationFixture(spanish: spanish, initialRemaining: 0)
                }
                NavigationLink(CuadraoCopy.text("copy.releaseInvitationsGallery.3350acd647", spanish: spanish)) {
                    ReleasePersonalInvitationFixture(spanish: spanish, unavailable: true)
                }
            }
            Section(CuadraoCopy.text("copy.releaseInvitationsGallery.a81dad5195", spanish: spanish)) {
                NavigationLink(CuadraoCopy.text("copy.releaseInvitationsGallery.146a1f810b", spanish: spanish)) {
                    Form {
                        Text(CuadraoCopy.text("copy.releaseInvitationsGallery.b7b164756d", spanish: spanish))
                        if let invitation = householdFixture {
                            HouseholdInvitationShareView(invitation: invitation, spanish: spanish)
                        }
                    }
                }.accessibilityIdentifier("release.invites.gallery.household")
            }
            Section(CuadraoCopy.text("copy.releaseInvitationsGallery.5fcfa2448d", spanish: spanish)) {
                NavigationLink(CuadraoCopy.text("copy.releaseInvitationsGallery.20ed08d57a", spanish: spanish)) {
                    ReleaseGroupInvitationFixture(spanish: spanish)
                }.accessibilityIdentifier("release.invites.gallery.group.create")
                NavigationLink(CuadraoCopy.text("copy.releaseInvitationsGallery.fadf046ebd", spanish: spanish)) {
                    ReleaseGroupInvitationFixture(spanish: spanish, prepared: true)
                }.accessibilityIdentifier("release.invites.gallery.group.ready")
                NavigationLink(CuadraoCopy.text("copy.releaseInvitationsGallery.dd17dcf59e", spanish: spanish)) {
                    ReleaseGroupInvitationFixture(spanish: spanish, isFounder: false)
                }
            }
        }
        .navigationTitle(CuadraoCopy.text("copy.releaseInvitationsGallery.a30249c514", spanish: spanish))
    }

    private var householdFixture: HouseholdInvitation? {
        let json = """
        {"id":"00000000-0000-0000-0000-000000000001","expires_at":"2026-10-08T00:00:00Z","state":"pending","token":"DEBUG-NOT-A-VALID-INVITATION"}
        """
        return try? JSONDecoder().decode(HouseholdInvitation.self, from: Data(json.utf8))
    }

}

private enum ReleaseInvitationFixtures {
    static func share(expiry: Date = Date(timeIntervalSince1970: 1791417600)) -> ReleaseInvitationShare {
        ReleaseInvitationShare(url: URL(string: "https://cuadrao.ai/invite#DEBUG-NOT-A-VALID-INVITATION")!,
                               code: "DEMO-ONLY", expiresAt: expiry)
    }
}

private struct ReleaseInvitationFixtureNotice: View {
    let spanish: Bool
    var body: some View {
        Text(CuadraoCopy.text("copy.releaseInvitationsGallery.b9513fe8fe", spanish: spanish))
            .font(CuadraoTypography.caption).foregroundStyle(.secondary)
            .padding(12).frame(maxWidth: .infinity)
            .background(WelcomePalette.surface)
            .accessibilityIdentifier("release.invites.fixture.notice")
    }
}

private struct ReleaseInviteGateFixture: View {
    let spanish: Bool
    @Environment(\.openURL) private var openURL
    @State private var state: ReleaseInviteGateState
    @State private var code = ""
    @State private var accepted = false

    init(initialState: ReleaseInviteGateState, spanish: Bool) {
        self.spanish = spanish
        _state = State(initialValue: initialState)
    }

    var body: some View {
        Group {
            if accepted {
                ReleaseInvitationPage(title: CuadraoCopy.text("copy.releaseInvitationsGallery.461de6a3b6", spanish: spanish),
                                      subtitle: CuadraoCopy.text("copy.releaseInvitationsGallery.681593dcd5", spanish: spanish)) {
                    NavigationLink(CuadraoCopy.text("copy.releaseInvitationsGallery.d62438ffc8", spanish: spanish)) {
                        ReleasePersonalInvitationFixture(spanish: spanish)
                    }.buttonStyle(.borderedProminent).modifier(ReleaseProminentLabel())
                        .accessibilityIdentifier("release.invites.fixture.accepted.continue")
                    Button(CuadraoCopy.text("copy.releaseInvitationsGallery.14202e8693", spanish: spanish)) {
                        accepted = false; state = .ready
                    }.frame(minHeight: 44)
                }.accessibilityIdentifier("release.invites.fixture.accepted")
            } else {
                ReleaseInviteGate(state: state, code: $code, spanish: spanish,
                                  onSubmit: { _ in state = .checking },
                                  onWaitlist: { openURL(URL(string: "https://cuadrao.ai")!) })
            }
        }
        .safeAreaInset(edge: .top) { ReleaseInvitationFixtureNotice(spanish: spanish) }
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Menu(CuadraoCopy.text("copy.releaseInvitationsGallery.6421b20f7a", spanish: spanish)) {
                    Button(CuadraoCopy.text("copy.releaseInvitationsGallery.5c2a07b862", spanish: spanish)) { accepted = true }
                        .accessibilityIdentifier("release.invites.fixture.result.accepted")
                    ForEach([ReleaseInviteGateState.invalid, .expired, .full, .consumed, .revoked, .unavailable], id: \.rawValue) { outcome in
                        Button(outcome.title(spanish: spanish)) { state = outcome }
                            .accessibilityIdentifier("release.invites.fixture.result." + outcome.rawValue)
                    }
                }.disabled(state != .checking || accepted)
                    .accessibilityIdentifier("release.invites.fixture.result")
            }
        }
    }
}

private struct ReleasePersonalInvitationFixture: View {
    let spanish: Bool
    @State private var remaining: Int
    @State private var state: ReleasePersonalInvitationState
    @State private var pending = false
    @State private var invitation: ReleaseInvitationShare?

    init(spanish: Bool, initialRemaining: Int = 7, unavailable: Bool = false) {
        self.spanish = spanish
        let share = initialRemaining > 0 ? ReleaseInvitationFixtures.share() : nil
        _remaining = State(initialValue: initialRemaining)
        _invitation = State(initialValue: share)
        _state = State(initialValue: unavailable ? .unavailable : .ready(remaining: initialRemaining, total: 10, invitation: share))
    }

    var body: some View {
        ReleasePersonalInvitationsView(state: state, spanish: spanish) {
            pending = true
            state = .loading
        }
        .safeAreaInset(edge: .top) { ReleaseInvitationFixtureNotice(spanish: spanish) }
        .toolbar {
            ToolbarItem(placement: .topBarTrailing) {
                Menu(CuadraoCopy.text("copy.releaseInvitationsGallery.6421b20f7a", spanish: spanish)) {
                    Button(CuadraoCopy.text("copy.invitationViews.3b2351f33d", spanish: spanish)) {
                        guard pending, remaining > 0 else { return }
                        remaining -= 1
                        invitation = ReleaseInvitationFixtures.share()
                        pending = false
                        showReady()
                    }.disabled(!pending)
                        .accessibilityIdentifier("release.invites.fixture.personal.complete")
                    Button(CuadraoCopy.text("copy.releaseInvitationsGallery.3350acd647", spanish: spanish)) {
                        pending = false; state = .unavailable
                    }.disabled(!pending)
                    Button(CuadraoCopy.text("copy.releaseInvitationsGallery.e4bd371375", spanish: spanish)) {
                        pending = false; showReady()
                    }.accessibilityIdentifier("release.invites.fixture.personal.retry")
                }.accessibilityIdentifier("release.invites.fixture.result")
            }
        }
    }

    private func showReady() {
        state = .ready(remaining: remaining, total: 10, invitation: invitation)
    }
}

private struct ReleaseGroupInvitationFixture: View {
    let spanish: Bool
    let isFounder: Bool
    @State private var state: ReleaseGroupInvitationState
    @State private var pending: (cap: Int, expiry: Date)?

    init(spanish: Bool, isFounder: Bool = true, prepared: Bool = false) {
        self.spanish = spanish
        self.isFounder = isFounder
        _state = State(initialValue: prepared ? .ready(cap: 25, used: 8, invitation: ReleaseInvitationFixtures.share()) : .draft)
    }

    var body: some View {
        ReleaseFounderGroupInvitationView(isFounder: isFounder, state: state, spanish: spanish) { _, cap, expiry in
            pending = (cap, expiry)
            state = .creating
        }
        .safeAreaInset(edge: .top) { ReleaseInvitationFixtureNotice(spanish: spanish) }
        .toolbar {
            if isFounder {
                ToolbarItem(placement: .topBarTrailing) {
                    Menu(CuadraoCopy.text("copy.releaseInvitationsGallery.6421b20f7a", spanish: spanish)) {
                        Button(CuadraoCopy.text("copy.releaseInvitationsGallery.0e49ae7f72", spanish: spanish)) {
                            guard let values = pending else { return }
                            state = .ready(cap: values.cap, used: 0,
                                           invitation: ReleaseInvitationFixtures.share(expiry: values.expiry))
                            pending = nil
                        }.disabled(pending == nil)
                            .accessibilityIdentifier("release.invites.fixture.group.complete")
                        Button(CuadraoCopy.text("copy.releaseInvitationsGallery.3350acd647", spanish: spanish)) {
                            pending = nil; state = .unavailable
                        }.disabled(pending == nil)
                        Button(CuadraoCopy.text("copy.releaseInvitationsGallery.7ebef64246", spanish: spanish)) {
                            pending = nil; state = .draft
                        }.accessibilityIdentifier("release.invites.fixture.group.edit")
                    }.accessibilityIdentifier("release.invites.fixture.result")
                }
            }
        }
    }
}
#endif
