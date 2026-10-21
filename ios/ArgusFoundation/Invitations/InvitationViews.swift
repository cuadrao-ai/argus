import SwiftUI
import ArgusSession

private extension Locale {
    var spanish: Bool { CuadraoCopy.isSpanish() }
}

/// Shows the beta gate only when the server says this person still needs an invitation.
struct InvitationGateHost<Content: View>: View {
    @ObservedObject var model: InvitationsModel
    var household: HouseholdModel?
    var signOut: (() -> Void)?
    @ViewBuilder let content: () -> Content
    @Environment(\.locale) private var locale
    @Environment(\.openURL) private var openURL
    @Environment(\.scenePhase) private var phase
    @State private var keyboardUp = false

    var body: some View {
        Group {
            switch model.admission {
            case .checking:
                ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
                    .accessibilityIdentifier("invites.access.checking")
            case .unanswered:
                unanswered
            case .required(let destinations):
                gate(destinations)
            case .admitted, .off:
                content()
            }
        }
        .task(id: model.identity?.revision) { await model.refreshAccess() }
        .onChange(of: phase) { _, value in if value == .active { Task { await model.refreshAccess() } } }
        .invitationNotices(model)
    }

    private var unanswered: some View {
        VStack(spacing: 16) {
            Text(CuadraoCopy.text("copy.invitationViews.afc302d2ff", spanish: locale.spanish))
                .font(CuadraoTypography.supporting).multilineTextAlignment(.center)
            Button { Task { await model.retryAccess() } } label: {
                Text(CuadraoCopy.text("copy.connectedCuadraoAuth.ada77fc089", spanish: locale.spanish)).foregroundStyle(WelcomePalette.onAccent).frame(minHeight: 28)
            }
            .buttonStyle(.borderedProminent).accessibilityIdentifier("invites.access.retry")
            signOutButton
        }
        .padding(24).frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(WelcomePalette.background.ignoresSafeArea())
        .foregroundStyle(WelcomePalette.ink).tint(WelcomePalette.pine)
        .accessibilityElement(children: .contain).accessibilityIdentifier("invites.access.unanswered")
    }

    @ViewBuilder private var signOutButton: some View {
        if let signOut {
            Button(CuadraoCopy.text("copy.connectedCuadraoProfile.a47c0e9665", spanish: locale.spanish), action: signOut)
                .frame(minHeight: 44).accessibilityIdentifier("invites.gate.signOut")
        }
    }

    private func gate(_ destinations: InviteDestinations) -> some View {
        ReleaseInviteGate(state: InvitationCopy.gateState(model.gate), code: $model.gateCode, spanish: locale.spanish,
                          onSubmit: { code in Task { await model.submitCode(code) } },
                          onWaitlist: { if let url = destinations.waitlist { openURL(url) } },
                          showsWaitlist: destinations.waitlist != nil)
            .safeAreaInset(edge: .bottom) { if !keyboardUp { signOutButton } }
            .onReceive(NotificationCenter.default.publisher(for: UIResponder.keyboardWillShowNotification)) { _ in keyboardUp = true }
            .onReceive(NotificationCenter.default.publisher(for: UIResponder.keyboardWillHideNotification)) { _ in keyboardUp = false }
            .background {
                if let household {
                    HouseholdPresenter(model: household)
                    HouseholdAdmissionWatcher(household: household) { Task { await model.refreshAccess() } }
                }
            }
    }
}

/// Accepting a Household invitation also admits the person; the gate re-reads access instead of assuming it.
private struct HouseholdAdmissionWatcher: View {
    @ObservedObject var household: HouseholdModel
    let changed: () -> Void
    var body: some View {
        Color.clear.frame(width: 0, height: 0).onChange(of: household.selectedId) { _, _ in changed() }
    }
}

/// Signed out with a link in hand: the intent waits for sign-in, and cancelling sign-in keeps it.
struct InvitationPendingNotice: View {
    @ObservedObject var model: InvitationsModel
    @Environment(\.locale) private var locale

    var body: some View {
        if model.pendingLink != nil {
            HStack(alignment: .firstTextBaseline, spacing: 12) {
                Image(systemName: "envelope.open").accessibilityHidden(true)
                Text(CuadraoCopy.text("copy.invitationViews.833224248b", spanish: locale.spanish))
                    .font(CuadraoTypography.supporting).fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 0)
                Button(CuadraoCopy.text("copy.guestClaimModel.adac3a9868", spanish: locale.spanish)) { model.discardPendingLink() }
                    .frame(minHeight: 44).accessibilityIdentifier("invites.pending.discard")
            }
            .padding(.horizontal, 20).padding(.vertical, 8)
            .background(WelcomePalette.surface)
            .foregroundStyle(WelcomePalette.ink).tint(WelcomePalette.pine)
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier("invites.pending")
        }
    }
}

struct InvitationsProfileRow: View {
    @ObservedObject var model: InvitationsModel
    @Environment(\.locale) private var locale

    var body: some View {
        if model.showsInvitations {
            Divider()
            NavigationLink { InvitationsHub(model: model) } label: {
                HStack(spacing: 12) {
                    Image(systemName: "person.badge.plus").frame(width: 24)
                    Text(CuadraoCopy.text("copy.invitationViews.4970c3efc4", spanish: locale.spanish)).foregroundStyle(.primary)
                    Spacer()
                    Image(systemName: "chevron.right").font(.caption).foregroundStyle(.secondary)
                }.frame(minHeight: 58).contentShape(Rectangle())
            }.accessibilityIdentifier("invites.profile")
        }
    }
}

struct InvitationsHub: View {
    @ObservedObject var model: InvitationsModel
    @Environment(\.locale) private var locale
    private var spanish: Bool { locale.spanish }

    var body: some View {
        List {
            Section {
                NavigationLink { PersonalInvitationsScreen(model: model) } label: {
                    Label(CuadraoCopy.text("copy.invitationViews.6e55b9229e", spanish: spanish), systemImage: "person.badge.plus")
                }.accessibilityIdentifier("invites.personal")
            } footer: {
                Text(CuadraoCopy.text("copy.invitationViews.319b2d2fd2", spanish: spanish))
            }
            Section(CuadraoCopy.text("copy.invitationViews.27f96b1911", spanish: spanish)) {
                switch model.personal {
                case .loading:
                    ProgressView().accessibilityIdentifier("invites.sent.loading")
                case .failed:
                    Text(CuadraoCopy.text("copy.invitationViews.d1056ac1bb", spanish: spanish))
                        .foregroundStyle(.secondary).accessibilityIdentifier("invites.sent.failed")
                case .ready(let sent):
                    if sent.invitations.isEmpty {
                        Text(CuadraoCopy.text("copy.invitationViews.3e71bd2c6a", spanish: spanish))
                            .foregroundStyle(.secondary).accessibilityIdentifier("invites.sent.empty")
                    }
                    ForEach(sent.invitations) { SentInvitationRow(invite: $0) }
                }
            }
            if case .ready(.links(let links)) = model.groupLinks {
                Section(CuadraoCopy.text("copy.invitationViews.5885b421fe", spanish: spanish)) {
                    ForEach(links) { link in
                        GroupLinkRow(link: link) { Task { await model.revokeGroupLink(link.id) } }
                    }
                    NavigationLink { GroupLinkScreen(model: model) } label: {
                        Label(CuadraoCopy.text("copy.invitationViews.3d96033517", spanish: spanish), systemImage: "link.badge.plus")
                    }.accessibilityIdentifier("invites.group.new")
                }
            }
        }
        .navigationTitle(CuadraoCopy.text("copy.invitationViews.4970c3efc4", spanish: spanish))
        .navigationBarTitleDisplayMode(.inline).toolbar(.visible, for: .navigationBar)
        .refreshable { await reload() }
        .task { await reload() }
    }

    private func reload() async {
        await model.loadPersonal()
        await model.loadGroupLinks()
    }
}

private struct SentInvitationRow: View {
    let invite: SentInvite
    @Environment(\.locale) private var locale

    var body: some View {
        let spanish = locale.spanish
        VStack(alignment: .leading, spacing: 4) {
            Text(invite.kind == .household ? (CuadraoCopy.text("copy.cuadraoHouseholdSheet.b845d91db6", spanish: spanish)) : (CuadraoCopy.text("copy.invitationViews.fe268c6dcf", spanish: spanish)))
                .font(CuadraoTypography.supporting)
            Text(state(spanish)).font(CuadraoTypography.caption).foregroundStyle(.secondary)
        }
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("invites.sent." + invite.state.rawValue)
    }

    private func state(_ spanish: Bool) -> String {
        switch invite.state {
        case .accepted:
            let day = invite.acceptedAt?.formatted(date: .abbreviated, time: .omitted) ?? ""
            return CuadraoCopy.text("copy.invitationViews.beb1fc5836", spanish: spanish, String(describing: day))
        case .pending:
            let day = invite.expiresAt?.formatted(date: .abbreviated, time: .omitted) ?? ""
            return CuadraoCopy.text("copy.invitationViews.0dd4dc5fea", spanish: spanish, String(describing: day))
        case .expired: return CuadraoCopy.text("copy.invitationViews.b871a58957", spanish: spanish)
        case .revoked: return CuadraoCopy.text("copy.invitationViews.a6a58738bc", spanish: spanish)
        }
    }
}

private struct GroupLinkRow: View {
    let link: GroupLink
    let revoke: () -> Void
    @Environment(\.locale) private var locale

    var body: some View {
        let spanish = locale.spanish
        VStack(alignment: .leading, spacing: 4) {
            Text(link.sourceLabel).font(CuadraoTypography.supporting)
            Text(CuadraoCopy.text("copy.invitationViews.8a54c66d27", spanish: spanish, String(describing: link.redeemed), String(describing: link.cap)))
                .font(CuadraoTypography.caption)
            Text(stateText(spanish)).font(CuadraoTypography.caption).foregroundStyle(.secondary)
        }
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("invites.group." + link.state.rawValue)
        .swipeActions {
            if link.state == .open {
                Button(CuadraoCopy.text("copy.invitationViews.21a7c4e053", spanish: spanish), role: .destructive, action: revoke)
            }
        }
    }

    private func stateText(_ spanish: Bool) -> String {
        let day = link.expiresAt.formatted(date: .abbreviated, time: .shortened)
        switch link.state {
        case .open: return CuadraoCopy.text("copy.invitationViews.c4b180bbee", spanish: spanish, String(describing: day))
        case .full:
            return CuadraoCopy.text("copy.invitationViews.84d38c546a", spanish: spanish, String(describing: link.overflow))
        case .expired: return CuadraoCopy.text("copy.invitationViews.38a9285a2d", spanish: spanish)
        case .revoked: return CuadraoCopy.text("copy.invitationViews.5fb7aa6ccc", spanish: spanish)
        }
    }
}

private struct PersonalInvitationsScreen: View {
    @ObservedObject var model: InvitationsModel
    @Environment(\.locale) private var locale

    var body: some View {
        ReleasePersonalInvitationsView(state: state, spanish: locale.spanish) {
            Task { await model.createPersonal() }
        }
        .toolbar(.visible, for: .navigationBar)
        .task { await model.loadPersonal() }
    }

    private var state: ReleasePersonalInvitationState {
        if model.creatingPersonal { return .loading }
        switch model.personal {
        case .loading: return .loading
        case .failed: return .unavailable
        case .ready(let sent):
            let share = model.createdPersonal.map { InvitationCopy.share($0, testFlight: model.admission.destinations?.testFlight) }
            return .ready(remaining: sent.quota.remaining, total: sent.quota.limit, invitation: share)
        }
    }
}

private struct GroupLinkScreen: View {
    @ObservedObject var model: InvitationsModel
    @Environment(\.locale) private var locale

    var body: some View {
        ReleaseFounderGroupInvitationView(isFounder: model.groupLinks != .ready(.notFounder), state: state, spanish: locale.spanish) { label, cap, expiry in
            Task { await model.createGroupLink(label: label, cap: cap, expiresAt: expiry) }
        }
        .toolbar(.visible, for: .navigationBar)
        .onAppear { model.startGroupLink() }
    }

    private var state: ReleaseGroupInvitationState {
        switch model.group {
        case .draft: .draft
        case .creating: .creating
        case .created(let invite, let used):
            .ready(cap: invite.cap ?? 0, used: used, invitation: InvitationCopy.share(invite, testFlight: model.admission.destinations?.testFlight))
        }
    }
}

/// Maps the model's answers onto the release screens' states and copy.
enum InvitationCopy {
    static func gateState(_ gate: InvitationGate) -> ReleaseInviteGateState {
        switch gate {
        case .ready: .ready
        case .checking: .checking
        case .problem(let problem): gateState(problem)
        }
    }

    static func gateState(_ problem: InvitationProblem) -> ReleaseInviteGateState {
        switch problem {
        case .invalid: .invalid
        case .expired: .expired
        case .revoked: .revoked
        case .used: .consumed
        case .full: .full
        case .rateLimited: .rateLimited
        default: .unavailable
        }
    }

    static func share(_ invite: CreatedInvite, testFlight: URL?) -> ReleaseInvitationShare {
        ReleaseInvitationShare(url: invite.link, code: invite.code, expiresAt: invite.expiresAt, testFlightURL: testFlight)
    }
}

extension View {
    func invitationNotices(_ model: InvitationsModel) -> some View { modifier(InvitationNoticeAlert(model: model)) }

    /// Universal links arrive as browsing activity; the legacy scheme arrives as an opened URL.
    func invitationLinks(_ model: InvitationsModel?) -> some View {
        onOpenURL { url in Task { await model?.open(url) } }
            .onContinueUserActivity(NSUserActivityTypeBrowsingWeb) { activity in
                if let url = activity.webpageURL { Task { await model?.open(url) } }
            }
    }
}

private struct InvitationNoticeAlert: ViewModifier {
    @ObservedObject var model: InvitationsModel
    @Environment(\.locale) private var locale

    func body(content: Content) -> some View {
        content.alert(title, isPresented: Binding(get: { model.notice != nil }, set: { if !$0 { model.notice = nil } })) {
            Button(CuadraoCopy.text("copy.invitationViews.2b2821ec48", spanish: CuadraoCopy.isSpanish())) { model.notice = nil }.accessibilityIdentifier("invites.notice.ok")
        } message: { Text(message) }
    }

    private var title: String {
        let spanish = locale.spanish
        switch model.notice {
        case .alreadyAdmitted: return CuadraoCopy.text("copy.invitationViews.cdf789e134", spanish: spanish)
        case .secretsShownOnce: return CuadraoCopy.text("copy.invitationViews.3b2351f33d", spanish: spanish)
        default: return CuadraoCopy.text("copy.invitationViews.b484b400d2", spanish: spanish)
        }
    }

    private var message: String {
        let spanish = locale.spanish
        switch model.notice {
        case .alreadyAdmitted:
            return CuadraoCopy.text("copy.invitationViews.d9972d83e7", spanish: spanish)
        case .secretsShownOnce:
            return CuadraoCopy.text("copy.invitationViews.5ae0c9d266", spanish: spanish)
        case .householdUnavailable:
            return CuadraoCopy.text("copy.invitationViews.637ed524fb", spanish: spanish)
        case .groupLink(let invalid):
            switch invalid {
            case .label: return CuadraoCopy.text("copy.invitationViews.01c90ceec0", spanish: spanish)
            case .cap: return CuadraoCopy.text("copy.invitationViews.c1dad79c4e", spanish: spanish)
            case .expiry: return CuadraoCopy.text("copy.invitationViews.bb29705401", spanish: spanish)
            }
        case .problem(let problem):
            switch problem {
            case .refused: return CuadraoCopy.text("copy.invitationViews.7f4a160e2d", spanish: spanish)
            case .quotaExhausted: return CuadraoCopy.text("copy.invitationViews.1badc7ec88", spanish: spanish)
            case .founderOnly: return CuadraoCopy.text("copy.invitationViews.cfc6ca56db", spanish: spanish)
            case .invitationRequired: return CuadraoCopy.text("copy.invitationViews.e8cc9956c8", spanish: spanish)
            case .rateLimited: return ReleaseInviteGateState.rateLimited.message(spanish: spanish) ?? ""
            case .invalid, .expired, .revoked, .used, .full:
                return InvitationCopy.gateState(problem).message(spanish: spanish) ?? ""
            default: return ReleaseInviteGateState.unavailable.message(spanish: spanish) ?? ""
            }
        case nil: return ""
        }
    }
}
