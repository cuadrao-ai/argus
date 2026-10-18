import SwiftUI

enum ReleasePersonalInvitationState {
    case loading
    case unavailable
    case ready(remaining: Int, total: Int, invitation: ReleaseInvitationShare?)
}

struct ReleasePersonalInvitationsView: View {
    let state: ReleasePersonalInvitationState
    let spanish: Bool
    let onCreate: () -> Void

    var body: some View {
        ReleaseInvitationPage(title: CuadraoCopy.text("copy.releaseInvitationSenders.8460396eb5", spanish: spanish),
                              subtitle: CuadraoCopy.text("copy.releaseInvitationSenders.3ba0fda620", spanish: spanish)) {
            switch state {
            case .loading:
                ProgressView(CuadraoCopy.text("copy.releaseInvitationSenders.9278ec16c0", spanish: spanish))
                    .accessibilityIdentifier("release.personalInvites.loading")
            case .unavailable:
                Text(CuadraoCopy.text("copy.releaseInvitationSenders.2667e9b067", spanish: spanish))
                    .accessibilityIdentifier("release.personalInvites.unavailable")
            case let .ready(remaining, total, invitation):
                VStack(alignment: .leading, spacing: 20) {
                    Text(CuadraoCopy.text("copy.releaseInvitationSenders.b74d30e6da", spanish: spanish, String(describing: remaining), String(describing: total)))
                        .font(CuadraoTypography.section)
                        .accessibilityIdentifier("release.personalInvites.remaining")
                    Text(CuadraoCopy.text("copy.releaseInvitationSenders.6d44d35608", spanish: spanish))
                        .font(CuadraoTypography.supporting).foregroundStyle(.secondary)
                    if let invitation {
                        ReleaseInvitationShareCard(invitation: invitation, spanish: spanish,
                                                   identifier: "release.personalInvites")
                    }
                    Button(action: onCreate) {
                        Text(CuadraoCopy.text("copy.releaseInvitationSenders.abbc0c3edc", spanish: spanish))
                            .frame(maxWidth: .infinity, minHeight: 48).modifier(ReleaseProminentLabel())
                    }
                    .buttonStyle(.borderedProminent).disabled(remaining <= 0)
                    .accessibilityIdentifier("release.personalInvites.create")
                    if remaining <= 0 {
                        Text(CuadraoCopy.text("copy.invitationViews.1badc7ec88", spanish: spanish))
                            .font(CuadraoTypography.supporting)
                    }
                }
            }
        }
    }
}

enum ReleaseGroupInvitationState {
    case unavailable
    case draft
    case creating
    case ready(cap: Int, used: Int, invitation: ReleaseInvitationShare)
}

struct ReleaseFounderGroupInvitationView: View {
    let isFounder: Bool
    let state: ReleaseGroupInvitationState
    let spanish: Bool
    let onCreate: (String, Int, Date) -> Void
    @State private var label = ""
    @State private var cap = ""
    @State private var expiry = Date().addingTimeInterval(7 * 86_400)

    var body: some View {
        ReleaseInvitationPage(title: CuadraoCopy.text("copy.releaseInvitationSenders.aff13faf1f", spanish: spanish),
                              subtitle: CuadraoCopy.text("copy.releaseInvitationSenders.5c435a993b", spanish: spanish)) {
            if !isFounder {
                Text(CuadraoCopy.text("copy.invitationViews.cfc6ca56db", spanish: spanish))
                    .accessibilityIdentifier("release.groupInvite.founderOnly")
            } else {
                VStack(alignment: .leading, spacing: 20) {
                    Text(CuadraoCopy.text("copy.releaseInvitationSenders.768c6a35cf", spanish: spanish))
                        .font(CuadraoTypography.supporting).foregroundStyle(.secondary)
                    switch state {
                    case .unavailable:
                        Text(CuadraoCopy.text("copy.releaseInvitationSenders.f8962edf61", spanish: spanish))
                            .accessibilityIdentifier("release.groupInvite.unavailable")
                    case .draft, .creating:
                        groupForm
                    case let .ready(cap, used, invitation):
                        Text(CuadraoCopy.text("copy.invitationViews.8a54c66d27", spanish: spanish, String(describing: used), String(describing: cap)))
                            .font(CuadraoTypography.section)
                            .accessibilityIdentifier("release.groupInvite.usage")
                        ReleaseInvitationShareCard(invitation: invitation, spanish: spanish,
                                                   identifier: "release.groupInvite")
                        Text(CuadraoCopy.text("copy.releaseInvitationSenders.e013aaadbb", spanish: spanish))
                            .font(CuadraoTypography.caption).foregroundStyle(.secondary)
                    }
                }
            }
        }
    }

    private var creating: Bool {
        if case .creating = state { return true }; return false
    }

    private var groupForm: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text(CuadraoCopy.text("copy.releaseInvitationSenders.7b1869477d", spanish: spanish)).font(CuadraoTypography.supporting)
            TextField(CuadraoCopy.text("copy.releaseInvitationSenders.1d5bc9d75a", spanish: spanish), text: $label)
                .padding(16)
                .background(WelcomePalette.surface, in: RoundedRectangle(cornerRadius: 16))
                .accessibilityIdentifier("release.groupInvite.label")
            Text(CuadraoCopy.text("copy.releaseInvitationSenders.8508d12bce", spanish: spanish)).font(CuadraoTypography.supporting)
            TextField(CuadraoCopy.text("copy.releaseInvitationSenders.d1d28eb899", spanish: spanish), text: $cap)
                .keyboardType(.numberPad).padding(16)
                .background(WelcomePalette.surface, in: RoundedRectangle(cornerRadius: 16))
                .accessibilityIdentifier("release.groupInvite.cap")
            DatePicker(CuadraoCopy.text("copy.releaseInvitationSenders.293c8ffcef", spanish: spanish), selection: $expiry, in: Date()...,
                       displayedComponents: [.date, .hourAndMinute])
                .accessibilityIdentifier("release.groupInvite.expiry")
            Button {
                let name = label.trimmingCharacters(in: .whitespacesAndNewlines)
                guard !name.isEmpty, let value = Int(cap), value > 0, expiry > Date(), !creating else { return }
                onCreate(name, value, expiry)
            } label: {
                HStack {
                    if creating { ProgressView() }
                    Text(creating ? (CuadraoCopy.text("copy.releaseInvitationSenders.6e46294bca", spanish: spanish)) : (CuadraoCopy.text("copy.releaseInvitationSenders.d1e62c3d08", spanish: spanish)))
                }.frame(maxWidth: .infinity, minHeight: 48).modifier(ReleaseProminentLabel())
            }
            .buttonStyle(.borderedProminent)
            .disabled(label.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || (Int(cap) ?? 0) <= 0 || expiry <= Date() || creating)
            .accessibilityIdentifier("release.groupInvite.create")
        }.disabled(creating)
    }
}
