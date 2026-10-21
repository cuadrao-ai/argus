import SwiftUI

struct CuadraoGroupMemberReview: View {
    let store: CuadraoGroupPreview
    let groupID: UUID
    let member: PlanMember
    let spanish: Bool
    @Environment(\.dismiss) private var dismiss
    var body: some View {
        NavigationStack {
            if let group = store.group(groupID) {
                VStack(alignment: .leading, spacing: 24) {
                    Text(CuadraoCopy.text("copy.cuadraoGroupMemberReview.d531cf1640", spanish: spanish, String(describing: member.name))).font(CuadraoTypography.screen)
                    Text(CuadraoCopy.text("copy.cuadraoGroupMemberReview.b740e9c775", spanish: spanish))
                        .font(.body).foregroundStyle(.secondary)
                    if !group.canRemove(member.id) {
                        Text(CuadraoCopy.text("copy.cuadraoGroupMemberReview.f5f5bdaf51", spanish: spanish, String(describing: PlanFormat.amount(Double(abs(group.balance(member.id))) / 100, currency: group.currency))))
                            .font(.callout)
                    }
                    Button(CuadraoCopy.text("copy.cuadraoGroupMemberReview.87b7d81989", spanish: spanish), role: .destructive) {
                        store.removeMember(member.id, from: groupID); dismiss()
                    }.buttonStyle(.borderedProminent).disabled(!store.canManage || !group.canRemove(member.id))
                        .accessibilityIdentifier("group-remove-confirm")
                    Spacer(minLength: 0)
                }.padding(24).toolbar {
                    CuadraoCancelToolbar(title: CuadraoCopy.text("copy.connectedCuadraoProfile.62a128b722", spanish: spanish)) { dismiss() }
                }
            }
        }.presentationDetents([.medium, .large])
    }
}
