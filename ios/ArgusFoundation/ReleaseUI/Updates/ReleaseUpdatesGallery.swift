#if DEBUG
import SwiftUI

struct ReleaseUpdatesGallery: View {
    var spanish: Bool = true
    @State private var selectedState = "data"
    @State private var permission: ReleasePushPermission = .notDetermined
    @State private var readIDs: Set<String> = []
    @State private var more: ReleaseUpdatesMore = .failure
    @State private var previewPermission = false
    @State private var openedSource = false
    @State private var openedSettings = false
    private let kinds: [ReleaseUpdateKind] = [
        .bill(name: "Electricidad", reminder: .threeDaysBefore),
        .bill(name: "Internet", reminder: .dueToday), .draftReady,
        .invitationAccepted(member: "Alex"), .householdAdminHandoff, .householdClosed,
        .movedAccountHistory(account: "Cuenta del hogar"), .ownerHistoryRemoved,
        .formerMember(plan: "Casa", closedBalance: ReleaseClosedBalance(amount: 1250, currency: "DOP")),
        .formerMember(plan: "Viaje", closedBalance: nil), .reassignResponsibilities(plan: "Casa"), .newPlanOwner(plan: "Casa")
    ]
    private var state: ReleaseUpdatesState {
        switch selectedState {
        case "unavailable": .unavailable
        case "loading": .loading
        case "empty": .empty
        case "error": .failure
        default: .loaded(kinds.enumerated().map { index, kind in
            ReleaseUpdateItem(id: String(index), kind: kind, occurredAt: Date(timeIntervalSince1970: 1_791_000_000),
                              isRead: readIDs.contains(String(index)), source: source(kind))
        }, more: more)
        }
    }
    private func source(_ kind: ReleaseUpdateKind) -> ReleaseUpdateSource {
        switch kind {
        case .bill: .available(.bill("preview"))
        case .draftReady: .available(.document("preview"))
        case .invitationAccepted, .householdAdminHandoff: .available(.household("preview"))
        case .householdClosed, .ownerHistoryRemoved: .unavailable
        case .movedAccountHistory: .available(.account("preview"))
        case .formerMember, .newPlanOwner, .reassignResponsibilities: .available(.plan("preview"))
        }
    }
    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Menu(CuadraoCopy.text("copy.releaseIdentityGallery.3f0dd2f033", spanish: spanish)) {
                    ForEach(["data", "empty", "loading", "error", "unavailable"], id: \.self) { value in
                        Button(stateLabel(value)) { selectedState = value }
                    }
                }.accessibilityIdentifier("updates-gallery-state")
                Spacer()
                Menu(CuadraoCopy.text("copy.releaseUpdatesGallery.55516bd01a", spanish: spanish)) {
                    ForEach(ReleasePushPermission.allCases, id: \.self) { value in
                        Button(permissionLabel(value)) { permission = value }
                    }
                }.accessibilityIdentifier("updates-gallery-permission")
                Spacer()
                NavigationLink(CuadraoCopy.text("copy.releaseUpdatesGallery.e66a6214e0", spanish: spanish)) { truthSamples }
                    .accessibilityIdentifier("updates-gallery-truth")
            }.font(CuadraoTypography.supporting).padding(.horizontal, 24).frame(minHeight: 44)
            ReleaseUpdatesInbox(state: state, spanish: spanish, permission: permission,
                retry: { selectedState = "data" }, loadMore: { more = .none },
                markRead: { readIDs.insert($0) }, openSource: { _ in openedSource = true },
                requestPermission: { previewPermission = true }, openSettings: { openedSettings = true })
        }
        .confirmationDialog(CuadraoCopy.text("copy.releaseUpdatesGallery.4c80b55600", spanish: spanish), isPresented: $previewPermission, titleVisibility: .visible) {
            Button(CuadraoCopy.text("copy.releaseUpdatesGallery.d0caba307b", spanish: spanish)) { permission = .authorized }
            Button(CuadraoCopy.text("copy.releaseUpdatesGallery.5f84e848cd", spanish: spanish)) { permission = .denied }
        }
        .alert(CuadraoCopy.text("copy.releaseUpdatesGallery.9aa76857c2", spanish: spanish), isPresented: $openedSource) {
            Button(CuadraoCopy.text("copy.cuadraoAccountsCollection.f296f2cba3", spanish: spanish), role: .cancel) {}
        } message: { Text(CuadraoCopy.text("copy.releaseUpdatesGallery.b232733306", spanish: spanish)) }
        .alert(CuadraoCopy.text("copy.releaseUpdatesGallery.19428a785f", spanish: spanish), isPresented: $openedSettings) {
            Button(CuadraoCopy.text("copy.releaseUpdatesGallery.d0caba307b", spanish: spanish)) { permission = .authorized }
            Button(CuadraoCopy.text("copy.releaseUpdatesGallery.66eac06e29", spanish: spanish)) { permission = .denied }
            Button(CuadraoCopy.text("copy.connectedCuadraoProfile.62a128b722", spanish: spanish), role: .cancel) {}
        }
    }
    private func stateLabel(_ value: String) -> String {
        switch value {
        case "empty": CuadraoCopy.text("copy.releaseUpdatesGallery.2ac18eba67", spanish: spanish)
        case "loading": CuadraoCopy.text("copy.releaseUpdatesGallery.73aa47ea83", spanish: spanish)
        case "error": CuadraoCopy.text("copy.releaseIdentityGallery.9160f189de", spanish: spanish)
        case "unavailable": CuadraoCopy.text("copy.releaseInvitationsGallery.3350acd647", spanish: spanish)
        default: CuadraoCopy.text("copy.releaseUpdatesGallery.bc2072fa4d", spanish: spanish)
        }
    }
    private func permissionLabel(_ value: ReleasePushPermission) -> String {
        switch value {
        case .unavailable: CuadraoCopy.text("copy.releaseInvitationsGallery.3350acd647", spanish: spanish)
        case .notDetermined: CuadraoCopy.text("copy.releaseUpdatesGallery.5462b2e59a", spanish: spanish)
        case .requesting: CuadraoCopy.text("copy.releaseUpdatesGallery.781395cda0", spanish: spanish)
        case .authorized: CuadraoCopy.text("copy.releaseUpdatesGallery.3fc759a54d", spanish: spanish)
        case .denied: CuadraoCopy.text("copy.releaseUpdatesGallery.be6e310e5a", spanish: spanish)
        }
    }
    private var truthSamples: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 28) {
                Text(CuadraoCopy.text("copy.cuadraoDesignGallery.08c8c7d7cc", spanish: spanish)).font(CuadraoTypography.section)
                ReleaseMonthComparison(current: .missingCoverage, previous: .recorded(100), currency: "DOP", spanish: spanish)
                Divider()
                Text(CuadraoCopy.text("copy.releaseUpdatesGallery.318d21b019", spanish: spanish)).font(CuadraoTypography.section)
                ReleaseMonthComparison(current: .recorded(250), previous: .recorded(0), currency: "DOP", spanish: spanish)
                ReleaseMonthComparison(current: .recorded(0), previous: .recorded(0), currency: "DOP", spanish: spanish)
                Divider()
                ReleaseHistoryAccessNote(access: .readOnly, spanish: spanish)
                ReleaseHistoryRecordRow(title: CuadraoCopy.text("copy.releaseUpdatesGallery.5aa1f7c5f1", spanish: spanish), amount: 400, currency: "DOP",
                    date: Date(timeIntervalSince1970: 1_791_000_000), access: .movedOutOfHousehold, spanish: spanish)
            }.padding(24)
        }.background(WelcomePalette.background).navigationTitle(CuadraoCopy.text("copy.releaseUpdatesGallery.22d7bd46d5", spanish: spanish))
    }
}
#endif
