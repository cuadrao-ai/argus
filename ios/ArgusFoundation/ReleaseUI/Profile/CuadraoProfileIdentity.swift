import SwiftUI
import PhotosUI

enum CuadraoAvatarSelection: Equatable {
    case none
    case initials
    case theme(CuadraoAvatarTheme)
    case photo(CanvasAvatarPhoto)
}

enum CuadraoAvatarTheme: String, CaseIterable, Identifiable {
    case sun, leaf, moon, star
    var id: Self { self }
    var symbol: String {
        switch self { case .sun: "sun.max"; case .leaf: "leaf"; case .moon: "moon.fill"; case .star: "sparkle" }
    }
    var color: Color {
        switch self { case .sun: WelcomePalette.pine; case .leaf: WelcomePalette.sunshine; case .moon: WelcomePalette.bloom; case .star: WelcomePalette.clay }
    }
    func title(_ spanish: Bool) -> String {
        switch self { case .sun: CuadraoCopy.text("copy.cuadraoProfileIdentity.d7d3325840", spanish: spanish); case .leaf: CuadraoCopy.text("copy.cuadraoProfileIdentity.de90a8165d", spanish: spanish); case .moon: CuadraoCopy.text("copy.cuadraoProfileIdentity.c41d8b1763", spanish: spanish); case .star: CuadraoCopy.text("copy.cuadraoProfileIdentity.74811abcf9", spanish: spanish) }
    }
}

enum CuadraoAvatarPresentation { case profile, navigation }

struct CuadraoIdentityAvatar: View {
    let selection: CuadraoAvatarSelection
    let name: String
    var size: CGFloat = 32
    var presentation: CuadraoAvatarPresentation = .profile

    var body: some View {
        Group {
            switch selection {
            case .none:
                // The camera invites a photo, so it shows only where avatar editing exists.
                if presentation == .profile, CuadraoFirstRelease.editsAvatar {
                    Image(systemName: "camera.fill")
                        .font(.system(size: size * 0.32, weight: .medium))
                        .overlay(alignment: .topTrailing) {
                            Image(systemName: "plus.circle.fill")
                                .font(.system(size: size * 0.16, weight: .semibold))
                                .symbolRenderingMode(.palette)
                                .foregroundStyle(WelcomePalette.pine, Color(uiColor: .systemBackground))
                                .offset(x: size * 0.07, y: -size * 0.05)
                        }
                        .foregroundStyle(WelcomePalette.pine)
                        .frame(width: size, height: size)
                        .background(Color(uiColor: .tertiarySystemFill))
                } else {
                    Image("CuadraoProfile").resizable().scaledToFit().padding(size * 0.13)
                }
            case .initials:
                Text(name.split(whereSeparator: \.isWhitespace).prefix(2).compactMap(\.first).map(String.init).joined().uppercased())
                    .font(.system(size: size * 0.36, weight: .medium, design: .rounded))
                    .frame(width: size, height: size)
                    .background(presentation == .profile ? WelcomePalette.sage : .clear)
            case .theme(let theme):
                Image(systemName: theme.symbol).font(.system(size: size * 0.48))
                    .frame(width: size, height: size).foregroundStyle(theme.color)
                    .background(presentation == .profile ? theme.color.opacity(0.12) : .clear)
            case .photo(let photo):
                if let image = UIImage(data: photo.thumbnail) {
                    Image(uiImage: image).resizable().scaledToFill()
                }
            }
        }.frame(width: size, height: size).clipShape(Circle())
            .overlay {
                if presentation == .profile {
                    Circle().strokeBorder(.primary.opacity(0.1), lineWidth: 1)
                }
            }
            .accessibilityHidden(true)
    }
}

struct CuadraoIdentityEditor: View {
    let name: String
    @Binding var selection: CuadraoAvatarSelection
    @Environment(\.locale) private var locale
    @Environment(\.dismiss) private var dismiss
    @State private var draft: CuadraoAvatarSelection
    @State private var photo: PhotosPickerItem?
    @State private var crop: CanvasAvatarCropRequest?
    @State private var loading = false
    @State private var failed = false
    @State private var generation = UUID()
    private var spanish: Bool { CuadraoCopy.isSpanish() }

    init(name: String, selection: Binding<CuadraoAvatarSelection>) {
        self.name = name; _selection = selection; _draft = State(initialValue: selection.wrappedValue)
    }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    CuadraoIdentityAvatar(selection: draft, name: name, size: 96)
                        .frame(maxWidth: .infinity).padding(.vertical, 16)
                    PhotosPicker(selection: $photo, matching: .images) {
                        Label(CuadraoCopy.text("copy.cuadraoProfileIdentity.3d62df090b", spanish: spanish), systemImage: "photo")
                    }.accessibilityIdentifier("release.avatar.photo")
                    if case .photo(let value) = draft {
                        Button(CuadraoCopy.text("copy.cuadraoProfileAvatar.7e0ac1d51c", spanish: spanish)) {
                            crop = CanvasAvatarCropRequest(source: value.source, crop: value.crop)
                        }
                    }
                    if loading { ProgressView(CuadraoCopy.text("copy.cuadraoProfileAvatar.7415241987", spanish: spanish)) }
                    if failed { Text(CuadraoCopy.text("copy.cuadraoProfileIdentity.b7f2512242", spanish: spanish)).foregroundStyle(.secondary) }
                }
                Section(CuadraoCopy.text("copy.cuadraoProfileIdentity.236b6c6848", spanish: spanish)) {
                    choice(.none, title: CuadraoCopy.text("copy.cuadraoProfileIdentity.5c22b309d1", spanish: spanish), id: "none")
                    choice(.initials, title: CuadraoCopy.text("copy.cuadraoProfileAvatar.29387500ba", spanish: spanish), id: "initials")
                    ForEach(CuadraoAvatarTheme.allCases) { theme in
                        choice(.theme(theme), title: theme.title(spanish), id: theme.rawValue)
                    }
                }
            }
            .navigationTitle(CuadraoCopy.text("copy.connectedCuadraoProfile.95d374b19b", spanish: spanish))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                CuadraoCancelToolbar(title: CuadraoCopy.text("copy.connectedCuadraoProfile.62a128b722", spanish: spanish), identifier: "release.avatar.cancel") { dismiss() }
                CuadraoConfirmToolbar(title: CuadraoCopy.text("copy.cuadraoAccountManagement.553ab1bf1a", spanish: spanish), disabled: loading, identifier: "release.avatar.save") { selection = draft; dismiss() }
            }
            .sheet(item: $crop) { request in
                CanvasAvatarCropSheet(request: request, spanish: spanish) { draft = .photo($0) }
            }
            .task(id: photo) {
                guard let photo else { return }
                let request = UUID(); generation = request; loading = true; failed = false
                do {
                    guard let source = try await photo.loadTransferable(type: CanvasAvatarSource.self) else { throw CanvasAvatarPhotoError.unreadable }
                    guard !Task.isCancelled, generation == request else { return }
                    crop = CanvasAvatarCropRequest(source: source, crop: source.geometry.centered)
                    loading = false; self.photo = nil
                } catch {
                    guard !Task.isCancelled, generation == request else { return }
                    loading = false; failed = true; self.photo = nil
                }
            }
            .onDisappear { generation = UUID(); loading = false; photo = nil }
        }.tint(WelcomePalette.pine)
    }

    private func choice(_ value: CuadraoAvatarSelection, title: String, id: String) -> some View {
        Button {
            generation = UUID(); photo = nil; loading = false; failed = false; draft = value
        } label: {
            HStack(spacing: 14) {
                CuadraoIdentityAvatar(selection: value, name: name, presentation: .navigation)
                Text(title).foregroundStyle(.primary)
                Spacer()
                if draft == value { Image(systemName: "checkmark").foregroundStyle(WelcomePalette.pine) }
            }.frame(minHeight: 44).contentShape(Rectangle())
        }.buttonStyle(.plain).accessibilityIdentifier("release.avatar." + id)
            .accessibilityAddTraits(draft == value ? .isSelected : [])
    }
}
