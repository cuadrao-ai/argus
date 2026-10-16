import SwiftUI
import PhotosUI

struct CanvasProfileAvatar: View {
    let name: String
    let style: CuadraoAvatarSelection
    var size: CGFloat = 64

    var body: some View {
        CuadraoIdentityAvatar(selection: style, name: name, size: size)
    }
}

struct CuadraoProfileAvatarPicker: View {
    let name: String
    let spanish: Bool
    @Binding var avatar: CuadraoAvatarSelection
    @Binding var loading: Bool
    @Binding var cropRequest: CanvasAvatarCropRequest?
    @State private var selectedPhoto: PhotosPickerItem?
    @State private var generation = UUID()
    @State private var loadFailed = false

    private var hasPhoto: Bool {
        if case .photo = avatar { return true }
        return false
    }

    var body: some View {
        Section {
            PhotosPicker(selection: $selectedPhoto, matching: .images) {
                Label(spanish ? (hasPhoto ? "Cambiar foto" : "Elegir foto") : (hasPhoto ? "Change photo" : "Choose photo"),
                      systemImage: "photo")
            }.accessibilityIdentifier("cuadrao.profile.photo.choose")
            if loading {
                ProgressView(spanish ? "Preparando foto" : "Preparing photo")
                    .accessibilityIdentifier("cuadrao.profile.photo.loading")
            }
            if case .photo(let photo) = avatar {
                Button(spanish ? "Ajustar foto" : "Reposition photo") {
                    cropRequest = CanvasAvatarCropRequest(source: photo.source, crop: photo.crop)
                }.accessibilityIdentifier("cuadrao.profile.photo.edit")
                Button(spanish ? "Quitar foto" : "Remove photo", role: .destructive) { select(.none) }
                    .accessibilityIdentifier("cuadrao.profile.photo.remove")
            }
            if loadFailed {
                Text(spanish ? "No pudimos abrir esa foto. Intenta con otra." : "We couldn't open that photo. Try another.")
                    .font(.footnote).foregroundStyle(.secondary)
                    .accessibilityIdentifier("cuadrao.profile.photo.error")
            }
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 76))], spacing: 12) {
                choice(.none, title: spanish ? "Perfil" : "Profile", id: "none")
                choice(.initials, title: spanish ? "Iniciales" : "Initials", id: "initial")
                ForEach(CuadraoAvatarTheme.allCases) { theme in
                    choice(.theme(theme), title: theme.title(spanish), id: theme.rawValue)
                }
            }.padding(.vertical, 8)
        } header: {
            Text(spanish ? "Tu foto o avatar" : "Your photo or avatar")
        } footer: {
            Text(spanish ? "Tu foto se queda en esta vista previa. No se sube a tu cuenta."
                 : "Your photo stays in this preview. It isn't uploaded to your account.")
        }
            .listRowBackground(CanvasSettingsStyle.surface)
            .task(id: selectedPhoto) {
                guard let selectedPhoto else { return }
                let request = UUID()
                generation = request; loading = true; loadFailed = false
                do {
                    guard let source = try await selectedPhoto.loadTransferable(type: CanvasAvatarSource.self) else {
                        throw CanvasAvatarPhotoError.unreadable
                    }
                    guard !Task.isCancelled, generation == request else { return }
                    cropRequest = CanvasAvatarCropRequest(source: source, crop: source.geometry.centered)
                    loading = false; self.selectedPhoto = nil
                } catch {
                    guard !Task.isCancelled, generation == request else { return }
                    loading = false; loadFailed = true; self.selectedPhoto = nil
                }
            }
            .onDisappear { generation = UUID(); selectedPhoto = nil; loading = false }
    }

    private func select(_ style: CuadraoAvatarSelection) {
        generation = UUID(); selectedPhoto = nil; loading = false; loadFailed = false
        avatar = style
    }

    private func choice(_ style: CuadraoAvatarSelection, title: String, id: String) -> some View {
        return Button { select(style) } label: {
            VStack(spacing: 6) {
                CanvasProfileAvatar(name: name, style: style)
                    .overlay(alignment: .bottomTrailing) {
                        if avatar == style {
                            Image(systemName: "checkmark.circle.fill")
                                .foregroundStyle(WelcomePalette.pine, WelcomePalette.background)
                        }
                    }
                Text(title).font(.caption).foregroundStyle(.primary)
            }.frame(minHeight: 88).contentShape(Rectangle())
        }.buttonStyle(.plain).accessibilityLabel(title)
            .accessibilityAddTraits(avatar == style ? .isSelected : [])
            .accessibilityIdentifier("cuadrao.profile.avatar.\(id)")
    }
}
