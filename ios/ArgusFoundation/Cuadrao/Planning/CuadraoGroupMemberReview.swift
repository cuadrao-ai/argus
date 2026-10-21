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
                    Text(spanish ? "¿Quitar a \(member.name)?" : "Remove \(member.name)?").font(CuadraoTypography.screen)
                    Text(spanish ? "Los gastos y aportes anteriores permanecen en la historia del grupo." : "Past expenses and contributions remain in the group's history.")
                        .font(.body).foregroundStyle(.secondary)
                    if !group.canRemove(member.id) {
                        Text(spanish ? "Primero hay que cuadrar su saldo pendiente de \(PlanFormat.amount(Double(abs(group.balance(member.id))) / 100, currency: group.currency))." : "First settle their outstanding balance of \(PlanFormat.amount(Double(abs(group.balance(member.id))) / 100, currency: group.currency)).")
                            .font(.callout)
                    }
                    Button(spanish ? "Quitar del grupo" : "Remove from group", role: .destructive) {
                        store.removeMember(member.id, from: groupID); dismiss()
                    }.buttonStyle(.borderedProminent).disabled(!store.canManage || !group.canRemove(member.id))
                        .accessibilityIdentifier("group-remove-confirm")
                    Spacer(minLength: 0)
                }.padding(24).toolbar {
                    CuadraoCancelToolbar(title: spanish ? "Cancelar" : "Cancel") { dismiss() }
                }
            }
        }.presentationDetents([.medium, .large])
    }
}
