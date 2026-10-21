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
                            Text(CuadraoCopy.text("copy.cuadraoGroupInvitation.d0fdbe557e", spanish: spanish))
                                .font(.subheadline).foregroundStyle(.secondary)
                            PlanPrimaryButton(title: joined ? (CuadraoCopy.text("copy.cuadraoGroupInvitation.0b4287b35f", spanish: spanish)) : (CuadraoCopy.text("copy.cuadraoGroupInvitation.fa4a2449bf", spanish: spanish)), symbol: joined ? "checkmark" : "person.badge.plus") {
                                var updated = group
                                if let existing = updated.members.first(where: { $0.name == "Mar" }) {
                                    updated.removedMemberIDs.removeAll { $0 == existing.id }
                                } else { updated.members.append(.init(name: "Mar", symbol: "sparkles")) }
                                store.save(updated)
                                joined = true
                            }.disabled(joined).accessibilityIdentifier("group-invite-accept")
                            Text(CuadraoCopy.text("copy.cuadraoGroupInvitation.eb8543b7f9", spanish: spanish)).font(.caption).foregroundStyle(.secondary)
                        } else {
                            PlanLookPicker(look: $look, spanish: spanish)
                            PhotosPicker(selection: $photo, matching: .images) { Label(CuadraoCopy.text("copy.cuadraoGroupInvitation.16a54b6b51", spanish: spanish), systemImage: "photo").frame(minHeight: 44) }
                            if cover != nil { Button(CuadraoCopy.text("copy.cuadraoGroupInvitation.7fc87fa16f", spanish: spanish)) { cover = nil; photo = nil } }
                            if photoError { Text(CuadraoCopy.text("copy.cuadraoGroupInvitation.e116044f04", spanish: spanish)).font(.caption).foregroundStyle(.red) }
                            PlanPrimaryButton(title: CuadraoCopy.text("copy.cuadraoGroupInvitation.af2c931451", spanish: spanish), symbol: "arrow.right") { guest = true }
                                .accessibilityIdentifier("group-invite-preview")
                            Button { code = true } label: { Label(CuadraoCopy.text("copy.cuadraoGroupInvitation.1a036f5a95", spanish: spanish), systemImage: "qrcode").frame(minHeight: 44) }
                                .accessibilityIdentifier("group-invite-code")
                        }
                        Text(CuadraoCopy.text("copy.cuadraoGroupInvitation.871fcac72c", spanish: spanish)).font(.caption2).foregroundStyle(.secondary)
                    }.padding(24)
                }.background(WelcomePalette.background)
                    .navigationTitle(guest ? (CuadraoCopy.text("copy.cuadraoGroupInvitation.1347a0f20e", spanish: spanish)) : (CuadraoCopy.text("copy.cuadraoGroupInvitation.b37dcc9870", spanish: spanish)))
                    .navigationBarTitleDisplayMode(.inline)
                    .toolbar {
                        CuadraoCancelToolbar(title: CuadraoCopy.text("copy.cuadraoAccountsCollection.f296f2cba3", spanish: spanish)) { dismiss() }
                        if guest { ToolbarItem(placement: .topBarTrailing) { Button(CuadraoCopy.text("copy.connectedCuadraoHome.2ddd4a589f", spanish: spanish)) { guest = false } } }
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
                Text(CuadraoCopy.text("copy.cuadraoGroupInvitation.9417346f11", spanish: spanish)).font(.system(size: 10, weight: .semibold)).tracking(1.8).foregroundStyle(look.color)
                Text(group.name).font(.system(size: 32, weight: .regular, design: .serif))
                Text(group.kind == .trip ? (CuadraoCopy.text("copy.cuadraoGroupInvitation.a2de5fc954", spanish: spanish)) : (CuadraoCopy.text("copy.cuadraoGroupInvitation.0c3d65b110", spanish: spanish))).font(.subheadline).foregroundStyle(.secondary)
                Divider()
                Label(CuadraoCopy.text("copy.cuadraoGroupInvitation.bf8e91a9ed", spanish: spanish, String(describing: group.activeMembers.count)), systemImage: "person.2").font(.subheadline)
                Text(CuadraoCopy.text("copy.cuadraoGroupInvitation.48e4871dfd", spanish: spanish)).font(.caption).foregroundStyle(.secondary)
            }.padding(24).frame(maxWidth: .infinity, alignment: .leading)
        }.background(look.color.opacity(0.065), in: RoundedRectangle(cornerRadius: 30)).clipShape(RoundedRectangle(cornerRadius: 30))
    }
}
