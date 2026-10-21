import SwiftUI
import PhotosUI

struct CuadraoGroupInvitation: View {
    let store: CuadraoGroupPreview
    let groupID: UUID
    let spanish: Bool
    @State private var guest = false
    @State private var code = false
    @State private var look: CanvasPlanLook = .coast
    @State private var joined = false
    @State private var photo: PhotosPickerItem?
    @State private var cover: Data?
    @State private var photoError = false
    @Environment(\.dismiss) private var dismiss
    private var group: PlanGroup? { store.group(groupID) }
    var body: some View {
        NavigationStack {
            if let group {
                ScrollView {
                    VStack(spacing: 22) {
                        invitation(group)
                        if guest {
                            Text(spanish ? "Verás las personas, los gastos y los aportes de este grupo. Aceptar no crea una deuda ni comparte tus cuentas." : "You'll see this group's people, expenses and contributions. Accepting doesn't create a debt or share your accounts.")
                                .font(.subheadline).foregroundStyle(.secondary)
                            PlanPrimaryButton(title: joined ? (spanish ? "Ya estás en el plan" : "You're in") : (spanish ? "Probar aceptación" : "Preview joining"), symbol: joined ? "checkmark" : "person.badge.plus") {
                                var updated = group
                                if let existing = updated.members.first(where: { $0.name == "Mar" }) {
                                    updated.removedMemberIDs.removeAll { $0 == existing.id }
                                } else { updated.members.append(.init(name: "Mar", symbol: "sparkles")) }
                                store.save(updated)
                                joined = true
                            }.disabled(joined).accessibilityIdentifier("group-invite-accept")
                            Text(spanish ? "Mar es una persona ficticia de esta vista previa." : "Mar is a fictional person in this preview.").font(.caption).foregroundStyle(.secondary)
                        } else {
                            PlanLookPicker(look: $look, spanish: spanish)
                            PhotosPicker(selection: $photo, matching: .images) { Label(spanish ? "Usar una foto" : "Use a photo", systemImage: "photo").frame(minHeight: 44) }
                            if cover != nil { Button(spanish ? "Volver a la ilustración" : "Use illustration") { cover = nil; photo = nil } }
                            if photoError { Text(spanish ? "No pudimos abrir esa foto." : "Couldn't open that photo.").font(.caption).foregroundStyle(.red) }
                            PlanPrimaryButton(title: spanish ? "Ver como invitado" : "Preview as a guest", symbol: "arrow.right") { guest = true }
                                .accessibilityIdentifier("group-invite-preview")
                            Button { code = true } label: { Label(spanish ? "Ver tarjeta con código" : "View code card", systemImage: "qrcode").frame(minHeight: 44) }
                                .accessibilityIdentifier("group-invite-code")
                        }
                        Text(spanish ? "Vista previa · la invitación no se envía" : "Preview · invitation is not sent").font(.caption2).foregroundStyle(.secondary)
                    }.padding(24)
                }.background(WelcomePalette.background)
                    .navigationTitle(guest ? (spanish ? "Te invitaron" : "You're invited") : (spanish ? "Así empieza el plan" : "It starts with an invitation"))
                    .navigationBarTitleDisplayMode(.inline)
                    .toolbar {
                        CuadraoCancelToolbar(title: spanish ? "Cerrar" : "Close") { dismiss() }
                        if guest { ToolbarItem(placement: .topBarTrailing) { Button(spanish ? "Editar" : "Edit") { guest = false } } }
                    }
                    .sheet(isPresented: $code) { CuadraoGroupCodeCard(group: group, look: look, cover: cover, spanish: spanish) }
                    .onAppear { look = group.look; cover = group.cover; joined = group.activeMembers.contains { $0.name == "Mar" } }
                    .onChange(of: look) { _, value in var updated = group; updated.look = value; store.save(updated) }
                    .onChange(of: cover) { _, value in var updated = store.group(groupID) ?? group; updated.cover = value; store.save(updated) }
            }
        }.presentationDragIndicator(.visible)
            .task(id: photo) {
                guard let photo else { return }; photoError = false
                if let data = try? await photo.loadTransferable(type: Data.self), let source = UIImage(data: data) {
                    let scale = min(1, 1400 / max(source.size.width, source.size.height))
                    let size = CGSize(width: source.size.width * scale, height: source.size.height * scale)
                    cover = UIGraphicsImageRenderer(size: size).image { _ in source.draw(in: CGRect(origin: .zero, size: size)) }.jpegData(compressionQuality: 0.7)
                } else { photoError = true }
            }
    }
    private func invitation(_ group: PlanGroup) -> some View {
        VStack(spacing: 0) {
            ZStack(alignment: .bottomLeading) {
                PlanGroupArtwork(look: look, cover: cover).frame(height: 230)
                PlanAvatarStack(members: group.activeMembers).padding(20)
            }
            VStack(alignment: .leading, spacing: 14) {
                Text(spanish ? "HAY UN PLAN CONTIGO" : "YOU'RE PART OF THE PLAN").font(.system(size: 10, weight: .semibold)).tracking(1.8).foregroundStyle(look.color)
                Text(group.name).font(.system(size: 32, weight: .regular, design: .serif))
                Text(group.kind == .trip ? (spanish ? "Un buen rato. Las cuentas, claras." : "Good times. Clear shares.") : (spanish ? "Algo bonito que construir juntos." : "Something worth building together.")).font(.subheadline).foregroundStyle(.secondary)
                Divider()
                Label(spanish ? "\(group.activeMembers.count) personas en el plan" : "\(group.activeMembers.count) people in the plan", systemImage: "person.2").font(.subheadline)
                Text(spanish ? "Los montos se revisan dentro del grupo." : "Review amounts inside the group.").font(.caption).foregroundStyle(.secondary)
            }.padding(24).frame(maxWidth: .infinity, alignment: .leading)
        }.background(look.color.opacity(0.065), in: RoundedRectangle(cornerRadius: 30)).clipShape(RoundedRectangle(cornerRadius: 30))
    }
}
