import SwiftUI

struct CuadraoHouseholdIntroduction: View {
    let data: CuadraoAccountsPreview
    let spanish: Bool
    let finished: () -> Void
    private var exists: Bool { data.spaces.contains { $0.kind == .household } }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 28) {
                RegistrationHeading(title: CuadraoCopy.text("copy.cuadraoHouseholdSheet.14942f12e7", spanish: spanish),
                    detail: CuadraoCopy.text("copy.cuadraoHouseholdSheet.0e509e222b", spanish: spanish))
                Label(CuadraoCopy.text("copy.cuadraoHouseholdSheet.be1916140e", spanish: spanish), systemImage: "person.badge.plus")
                Label(CuadraoCopy.text("copy.cuadraoHouseholdSheet.77a5a9f0f3", spanish: spanish), systemImage: "checkmark.shield")
                RegistrationButton(title: exists ? (CuadraoCopy.text("copy.cuadraoHouseholdSheet.fb267f8db8", spanish: spanish))
                    : (CuadraoCopy.text("copy.cuadraoHouseholdSheet.d70d6d9dc3", spanish: spanish))) {
                    data.openHousehold(); finished()
                }
            }.padding(24)
        }.navigationTitle(CuadraoCopy.text("copy.cuadraoHouseholdSheet.b845d91db6", spanish: spanish)).navigationBarTitleDisplayMode(.inline)
    }
}

struct CuadraoHouseholdSheet: View {
    let data: CuadraoAccountsPreview
    let spanish: Bool
    @Environment(\.dismiss) private var dismiss
    @State private var sharing: CanvasHouseholdInvitation?
    @State private var cancelInvitation = false

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    Label(CuadraoCopy.text("copy.cuadraoHouseholdSheet.df8578d82b", spanish: spanish), systemImage: "person.crop.circle")
                    Divider()
                    switch data.household {
                    case .alone:
                        RegistrationHeading(title: CuadraoCopy.text("copy.cuadraoHouseholdSheet.4d276a3600", spanish: spanish),
                            detail: CuadraoCopy.text("copy.cuadraoHouseholdSheet.9e06b2ce09", spanish: spanish))
                        RegistrationButton(title: CuadraoCopy.text("copy.cuadraoHouseholdSheet.3e59d3aca8", spanish: spanish)) {
                            let invitation = CanvasHouseholdInvitation()
                            data.household = .invitation(invitation)
                            sharing = invitation
                        }
                        previewNotice
                    case .invitation(let invitation):
                        RegistrationHeading(title: CuadraoCopy.text("copy.cuadraoHouseholdSheet.018d184830", spanish: spanish),
                            detail: CuadraoCopy.text("copy.cuadraoHouseholdSheet.d97c3003dc", spanish: spanish))
                        Label(CuadraoCopy.text("copy.cuadraoHouseholdSheet.49fb10f099", spanish: spanish), systemImage: "link")
                            .foregroundStyle(.secondary)
                        RegistrationButton(title: CuadraoCopy.text("copy.cuadraoHouseholdSheet.3e59d3aca8", spanish: spanish)) { sharing = invitation }
                        Button(CuadraoCopy.text("copy.cuadraoHouseholdSheet.6c85ce9f4e", spanish: spanish), role: .destructive) { cancelInvitation = true }
                            .frame(minHeight: 44)
                        Divider()
                        NavigationLink {
                            CuadraoInvitationRecipient(data: data, invitation: invitation, spanish: spanish)
                        } label: {
                            Label(CuadraoCopy.text("copy.cuadraoHouseholdSheet.0cbf3131b1", spanish: spanish), systemImage: "person.crop.rectangle")
                                .frame(minHeight: 44)
                        }.accessibilityIdentifier("household-recipient-preview")
                        previewNotice
                    case .joined(let name):
                        RegistrationHeading(title: CuadraoCopy.text("copy.cuadraoHouseholdSheet.7065040bc1", spanish: spanish),
                            detail: CuadraoCopy.text("copy.cuadraoHouseholdSheet.14e8fb1684", spanish: spanish))
                        Label(name, systemImage: "person.crop.circle")
                    }
                }.padding(24)
            }.background(WelcomePalette.background)
                .navigationTitle(CuadraoCopy.text("copy.cuadraoHomeEmptyState.bede691c92", spanish: spanish)).navigationBarTitleDisplayMode(.inline)
                .toolbar { CuadraoDoneToolbar(title: CuadraoCopy.text("copy.guestClaimModel.bd6b05a681", spanish: spanish)) { dismiss() } }
                .confirmationDialog(CuadraoCopy.text("copy.cuadraoHouseholdSheet.ad7a6f259b", spanish: spanish),
                    isPresented: $cancelInvitation, titleVisibility: .visible) {
                    Button(CuadraoCopy.text("copy.cuadraoHouseholdSheet.6c85ce9f4e", spanish: spanish), role: .destructive) { data.household = .alone }
                    Button(CuadraoCopy.text("copy.cuadraoHouseholdInvitation.48bff92372", spanish: spanish), role: .cancel) {}
                } message: {
                    Text(CuadraoCopy.text("copy.cuadraoHouseholdSheet.c416e66eaa", spanish: spanish))
                }
        }.tint(WelcomePalette.pine).presentationDetents([.large]).presentationDragIndicator(.visible)
            .sheet(item: $sharing) { invitation in
                CuadraoInvitationShareSheet(invitation: invitation, spanish: spanish)
            }
    }
    private var previewNotice: some View {
        Text(CuadraoCopy.text("copy.cuadraoHouseholdSheet.694a7713e1", spanish: spanish))
            .font(.footnote).foregroundStyle(.secondary)
    }
}

extension CuadraoAccountsPreview {
    func acceptedHouseholdMembers(spanish: Bool) -> [PlanMember] {
        var members = [PlanMember(id: UUID(uuidString: "00000000-0000-4000-8000-000000000001")!, name: CuadraoCopy.text("copy.cuadraoHouseholdSheet.df8578d82b", spanish: spanish), symbol: "sun.max.fill")]
        if case .joined(let name) = household {
            members.append(PlanMember(id: UUID(uuidString: "00000000-0000-4000-8000-000000000002")!, name: name, symbol: "leaf.fill"))
        }
        return members
    }
}
