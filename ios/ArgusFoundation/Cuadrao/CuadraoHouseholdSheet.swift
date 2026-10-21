import SwiftUI

struct CuadraoHouseholdIntroduction: View {
    let data: CuadraoAccountsPreview
    let spanish: Bool
    let finished: () -> Void
    private var exists: Bool { data.spaces.contains { $0.kind == .household } }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 28) {
                RegistrationHeading(title: spanish ? "Lo de ustedes,\nen un solo lugar." : "What you share,\nin one place.",
                    detail: spanish ? "Un espacio para las cuentas que llevan juntos. Cada persona conserva sus cuentas privadas."
                        : "A space for the accounts you manage together. Everyone keeps their personal accounts private.")
                Label(spanish ? "Invita cuando quieras" : "Invite when you're ready", systemImage: "person.badge.plus")
                Label(spanish ? "Elijan qué compartir" : "Choose what to share", systemImage: "checkmark.shield")
                RegistrationButton(title: exists ? (spanish ? "Abrir Hogar" : "Open Household")
                    : (spanish ? "Crear Hogar" : "Create Household")) {
                    data.openHousehold(); finished()
                }
            }.padding(24)
        }.navigationTitle(spanish ? "Hogar" : "Household").navigationBarTitleDisplayMode(.inline)
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
                    Label(spanish ? "Tú" : "You", systemImage: "person.crop.circle")
                    Divider()
                    switch data.household {
                    case .alone:
                        RegistrationHeading(title: spanish ? "Invita a quien\ncomparte contigo." : "Invite someone\nyou share with.",
                            detail: spanish ? "Envía un enlace por la app que prefieras. Tus cuentas personales siguen siendo privadas."
                                : "Send a link using the app you prefer. Your personal accounts stay private.")
                        RegistrationButton(title: spanish ? "Compartir invitación" : "Share invitation") {
                            let invitation = CanvasHouseholdInvitation()
                            data.household = .invitation(invitation)
                            sharing = invitation
                        }
                        previewNotice
                    case .invitation(let invitation):
                        RegistrationHeading(title: spanish ? "Tu invitación,\nlista para compartir." : "Your invitation,\nready to share.",
                            detail: spanish ? "Nadie se ha unido todavía. Compartir el enlace no da acceso hasta que se acepte la invitación."
                                : "No one has joined yet. Sharing the link doesn't grant access until the invitation is accepted.")
                        Label(spanish ? "Enlace disponible" : "Link available", systemImage: "link")
                            .foregroundStyle(.secondary)
                        RegistrationButton(title: spanish ? "Compartir invitación" : "Share invitation") { sharing = invitation }
                        Button(spanish ? "Cancelar invitación" : "Cancel invitation", role: .destructive) { cancelInvitation = true }
                            .frame(minHeight: 44)
                        Divider()
                        NavigationLink {
                            CuadraoInvitationRecipient(data: data, invitation: invitation, spanish: spanish)
                        } label: {
                            Label(spanish ? "Ver como invitado" : "Preview as recipient", systemImage: "person.crop.rectangle")
                                .frame(minHeight: 44)
                        }.accessibilityIdentifier("household-recipient-preview")
                        previewNotice
                    case .joined(let name):
                        RegistrationHeading(title: spanish ? "Su hogar." : "Your household.",
                            detail: spanish ? "Las cuentas personales siguen siendo privadas." : "Personal accounts remain private.")
                        Label(name, systemImage: "person.crop.circle")
                    }
                }.padding(24)
            }.background(WelcomePalette.background)
                .navigationTitle(spanish ? "Personas" : "People").navigationBarTitleDisplayMode(.inline)
                .toolbar { CuadraoDoneToolbar(title: spanish ? "Listo" : "Done") { dismiss() } }
                .confirmationDialog(spanish ? "¿Cancelar esta invitación?" : "Cancel this invitation?",
                    isPresented: $cancelInvitation, titleVisibility: .visible) {
                    Button(spanish ? "Cancelar invitación" : "Cancel invitation", role: .destructive) { data.household = .alone }
                    Button(spanish ? "Volver" : "Go back", role: .cancel) {}
                } message: {
                    Text(spanish ? "Este enlace dejará de servir para unirse al hogar." : "This link will no longer allow someone to join the household.")
                }
        }.tint(WelcomePalette.pine).presentationDetents([.large]).presentationDragIndicator(.visible)
            .sheet(item: $sharing) { invitation in
                CuadraoInvitationShareSheet(invitation: invitation, spanish: spanish)
            }
    }
    private var previewNotice: some View {
        Text(spanish ? "Vista previa · El enlace es de ejemplo y no permite acceder a ningún hogar."
             : "Design preview · This sample link doesn't grant access to any household.")
            .font(.footnote).foregroundStyle(.secondary)
    }
}

extension CuadraoAccountsPreview {
    func acceptedHouseholdMembers(spanish: Bool) -> [PlanMember] {
        var members = [PlanMember(id: UUID(uuidString: "00000000-0000-4000-8000-000000000001")!, name: spanish ? "Tú" : "You", symbol: "sun.max.fill")]
        if case .joined(let name) = household {
            members.append(PlanMember(id: UUID(uuidString: "00000000-0000-4000-8000-000000000002")!, name: name, symbol: "leaf.fill"))
        }
        return members
    }
}
