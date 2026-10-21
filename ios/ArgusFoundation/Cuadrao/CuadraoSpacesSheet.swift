import SwiftUI

/// What a row in the Spaces sheet does. The shared sheet draws every row; a host decides the outcome.
enum CuadraoSpaceChoice {
    /// Pushes a page inside the sheet.
    case page(AnyView)
    /// Runs the host's action, then closes the sheet.
    case act(() -> Void)
    /// Designed but has no backend yet: shown disabled with a caption.
    case soon
}

protocol CuadraoSpacesSource {
    /// Business and custom rows appear only when true.
    var showsExtraSpaces: Bool { get }
    /// The outcome for Household, Business and Custom. Personal is never offered.
    func choice(_ kind: CanvasSpaceKind, finish: @escaping () -> Void) -> CuadraoSpaceChoice
    func manage(finish: @escaping () -> Void) -> CuadraoSpaceChoice
}

/// The design preview: every row works on the fixture in `CuadraoAccountsPreview`.
struct CuadraoPreviewSpacesSource: CuadraoSpacesSource {
    let data: CuadraoAccountsPreview
    let spanish: Bool
    var showsExtraSpaces: Bool { CuadraoFirstRelease.showsExtraSpaces }
    func choice(_ kind: CanvasSpaceKind, finish: @escaping () -> Void) -> CuadraoSpaceChoice {
        switch kind {
        case .household: .page(AnyView(CuadraoHouseholdIntroduction(data: data, spanish: spanish, finished: finish)))
        case .business, .custom: .page(AnyView(CuadraoSpaceNameForm(data: data, kind: kind, spanish: spanish, finished: finish)))
        case .personal: .soon
        }
    }
    func manage(finish: @escaping () -> Void) -> CuadraoSpaceChoice {
        .page(AnyView(CuadraoManageSpaces(data: data, spanish: spanish, open: finish)))
    }
}

struct CuadraoSpacesSheet: View {
    let source: any CuadraoSpacesSource
    let spanish: Bool
    @Environment(\.dismiss) private var dismiss

    init(source: any CuadraoSpacesSource, spanish: Bool) {
        self.source = source; self.spanish = spanish
    }
    init(data: CuadraoAccountsPreview, spanish: Bool) {
        self.init(source: CuadraoPreviewSpacesSource(data: data, spanish: spanish), spanish: spanish)
    }

    var body: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: 8) {
                choiceRow(.household, subtitle: spanish ? "Lo que comparten en casa" : "What you share at home")
                Divider()
                if source.showsExtraSpaces {
                    ForEach([CanvasSpaceKind.business, .custom]) { kind in
                        choiceRow(kind, subtitle: kind == .business
                            ? (spanish ? "Tus finanzas del negocio" : "Your business finances")
                            : (spanish ? "Un espacio a tu manera" : "A space of your own"))
                        Divider()
                    }
                }
                manageRow
                Spacer(minLength: 0)
            }.padding(.horizontal, 24).padding(.top, 12)
                .navigationTitle(spanish ? "Espacios" : "Spaces").navigationBarTitleDisplayMode(.inline)
                .toolbar { CuadraoDoneToolbar(title: spanish ? "Listo" : "Done") { dismiss() } }
        }.tint(WelcomePalette.pine).presentationDetents([.medium, .large]).presentationDragIndicator(.visible)
    }

    @ViewBuilder private func choiceRow(_ kind: CanvasSpaceKind, subtitle: String) -> some View {
        let choice = source.choice(kind, finish: { dismiss() })
        let content = spaceChoice(kind, subtitle: subtitle, caption: caption(for: choice))
        switch choice {
        case .page(let destination):
            NavigationLink { destination } label: { content.contentShape(Rectangle()) }.buttonStyle(.plain)
                .accessibilityIdentifier("spaces.choice." + kind.rawValue)
        case .act(let run):
            Button { run(); dismiss() } label: { content.contentShape(Rectangle()) }.buttonStyle(.plain)
                .accessibilityIdentifier("spaces.choice." + kind.rawValue)
        case .soon:
            content.opacity(0.55).accessibilityElement(children: .combine)
                .accessibilityIdentifier("spaces.choice." + kind.rawValue)
        }
    }

    @ViewBuilder private var manageRow: some View {
        let label = Label(spanish ? "Gestionar espacios" : "Manage spaces", systemImage: "slider.horizontal.3")
            .font(.subheadline).foregroundStyle(.secondary).frame(maxWidth: .infinity, minHeight: 52, alignment: .leading).contentShape(Rectangle())
        switch source.manage(finish: { dismiss() }) {
        case .page(let destination):
            NavigationLink { destination } label: { label.contentShape(Rectangle()) }.buttonStyle(.plain).accessibilityIdentifier("spaces.manage")
        case .act(let run):
            Button { run(); dismiss() } label: { label.contentShape(Rectangle()) }.buttonStyle(.plain).accessibilityIdentifier("spaces.manage")
        case .soon:
            label.opacity(0.55).accessibilityIdentifier("spaces.manage")
        }
    }

    private func caption(for choice: CuadraoSpaceChoice) -> String? {
        if case .soon = choice { return spanish ? "Próximamente" : "Coming soon" }
        return nil
    }

    private func spaceChoice(_ kind: CanvasSpaceKind, subtitle: String, caption: String?) -> some View {
        HStack(spacing: 16) {
            Image(systemName: kind.symbol).font(.title3).frame(width: 28).foregroundStyle(WelcomePalette.pine)
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 5) {
                Text(kind.title(spanish)).font(CuadraoTypography.action)
                Text(subtitle).font(.subheadline).foregroundStyle(.secondary)
                if let caption { Text(caption).font(.caption.weight(.medium)).foregroundStyle(.secondary) }
            }
            Spacer()
            if caption == nil {
                Image(systemName: "chevron.right").font(.caption).foregroundStyle(.tertiary).accessibilityHidden(true)
            }
        }.padding(.vertical, 14).contentShape(Rectangle())
    }
}

struct CuadraoSpaceNameForm: View {
    let data: CuadraoAccountsPreview
    let kind: CanvasSpaceKind
    let spanish: Bool
    var existing: CanvasSpace?
    let finished: () -> Void
    @State private var name = ""
    @FocusState private var focused: Bool
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 22) {
                Text(spanish ? "Nombre" : "Name").font(.subheadline)
                TextField(kind == .business ? (spanish ? "Ej. Mi estudio" : "e.g. My studio")
                          : (spanish ? "Ej. Mi proyecto" : "e.g. My project"), text: $name)
                    .autocorrectionDisabled().focused($focused).submitLabel(.done)
                    .onSubmit { focused = false }.modifier(RegistrationField(focused: focused))
                    .onChange(of: name) { _, value in if value.count > 40 { name = String(value.prefix(40)) } }
                    .accessibilityIdentifier("space-name")
                if !name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !valid {
                    Text(spanish ? "Ya existe un espacio con ese nombre." : "A space already uses that name.")
                        .font(.footnote).foregroundStyle(.secondary)
                }
                Text(spanish ? "Solo tú tienes acceso a este espacio." : "Only you can access this space.")
                    .font(.subheadline).foregroundStyle(.secondary)
                RegistrationButton(title: existing == nil ? (spanish ? "Crear espacio" : "Create space")
                    : (spanish ? "Guardar" : "Save"), enabled: valid) {
                    data.saveSpace(kind: kind, name: name, existing: existing); finished()
                }
            }.padding(24)
        }.background(WelcomePalette.background)
            .navigationTitle(existing == nil ? kind.title(spanish) : (spanish ? "Cambiar nombre" : "Rename"))
            .navigationBarTitleDisplayMode(.inline)
            .onAppear { name = existing?.name ?? "" }
    }
    private var valid: Bool { data.spaceNameAvailable(name, except: existing?.id) }
}

struct CuadraoManageSpaces: View {
    let data: CuadraoAccountsPreview
    let spanish: Bool
    let open: () -> Void
    @State private var deletion: CanvasSpace?
    @State private var deletedID: String?
    var body: some View {
        List {
            Section {
                ForEach(data.visibleSpaces) { space in row(space) }
            }
            if data.spaces.contains(where: { $0.archived && !$0.deleted }) {
                Section(spanish ? "Archivados" : "Archived") {
                    ForEach(data.spaces.filter { $0.archived && !$0.deleted }) { space in row(space) }
                }
            }
            if data.spaces.contains(where: \.deleted) {
                Section(spanish ? "Eliminados recientemente" : "Recently deleted") {
                    ForEach(data.spaces.filter(\.deleted)) { space in row(space) }
                }
            }
            if let deletedID {
                Button(spanish ? "Deshacer eliminación" : "Undo deletion") {
                    data.restoreSpace(deletedID); self.deletedID = nil
                }
            }
        }.navigationTitle(spanish ? "Gestionar espacios" : "Manage spaces").navigationBarTitleDisplayMode(.inline)
            .confirmationDialog(spanish ? "¿Eliminar este espacio vacío?" : "Delete this empty space?",
                isPresented: Binding(get: { deletion != nil }, set: { if !$0 { deletion = nil } }), titleVisibility: .visible) {
                if let deletion {
                    Button(spanish ? "Eliminar espacio" : "Delete space", role: .destructive) {
                        data.deleteSpace(deletion); deletedID = deletion.id; self.deletion = nil
                    }
                }
                Button(spanish ? "Cancelar" : "Cancel", role: .cancel) { deletion = nil }
            } message: {
                Text(spanish ? "Puedes restaurarlo desde Eliminados recientemente." : "You can restore it from Recently deleted.")
            }
    }
    private func row(_ space: CanvasSpace) -> some View {
        HStack(spacing: 14) {
            Image(systemName: space.kind.symbol).frame(width: 24).foregroundStyle(WelcomePalette.pine).accessibilityHidden(true)
            Button {
                if space.deleted || space.archived { data.restoreSpace(space.id) }
                data.selectedSpaceID = space.id; open()
            } label: {
                VStack(alignment: .leading, spacing: 4) {
                    Text(space.title(spanish)).foregroundStyle(.primary)
                    Text(space.deleted || space.archived ? (spanish ? "Restaurar y abrir" : "Restore and open")
                         : space.kind.title(spanish)).font(.caption).foregroundStyle(.secondary)
                }.frame(maxWidth: .infinity, minHeight: 44, alignment: .leading).contentShape(Rectangle())
            }.buttonStyle(.plain)
            if space.isPrivate && !space.deleted {
                Menu {
                    NavigationLink(spanish ? "Cambiar nombre" : "Rename") {
                        CuadraoSpaceNameForm(data: data, kind: space.kind, spanish: spanish,
                            existing: space, finished: open)
                    }
                    Button(space.archived ? (spanish ? "Restaurar" : "Restore") : (spanish ? "Archivar" : "Archive"),
                        systemImage: space.archived ? "arrow.uturn.backward" : "archivebox") {
                        data.archiveSpace(space.id, archived: !space.archived)
                    }
                    if data.canDeleteSpace(space) {
                        Button(spanish ? "Eliminar espacio vacío" : "Delete empty space", systemImage: "trash", role: .destructive) { deletion = space }
                    }
                } label: {
                    Image(systemName: "ellipsis").frame(width: 44, height: 44)
                }.accessibilityLabel((spanish ? "Opciones de " : "Options for ") + space.title(spanish))
            }
        }
    }
}
