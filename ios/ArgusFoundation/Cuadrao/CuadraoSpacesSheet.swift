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
                choiceRow(.household, subtitle: CuadraoCopy.text("copy.cuadraoSpacesSheet.7a4a474d52", spanish: spanish))
                Divider()
                if source.showsExtraSpaces {
                    ForEach([CanvasSpaceKind.business, .custom]) { kind in
                        choiceRow(kind, subtitle: kind == .business
                            ? (CuadraoCopy.text("copy.cuadraoSpacesSheet.a2f62cbd59", spanish: spanish))
                            : (CuadraoCopy.text("copy.cuadraoSpacesSheet.071af815dc", spanish: spanish)))
                        Divider()
                    }
                }
                manageRow
                Spacer(minLength: 0)
            }.padding(.horizontal, 24).padding(.top, 12)
                .navigationTitle(CuadraoCopy.text("copy.cuadraoSpacesSheet.d0f98ebfca", spanish: spanish)).navigationBarTitleDisplayMode(.inline)
                .toolbar { CuadraoDoneToolbar(title: CuadraoCopy.text("copy.guestClaimModel.bd6b05a681", spanish: spanish)) { dismiss() } }
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
        let label = Label(CuadraoCopy.text("copy.cuadraoSpacesSheet.0742223e69", spanish: spanish), systemImage: "slider.horizontal.3")
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
        if case .soon = choice { return CuadraoCopy.text("copy.cuadraoSpacesSheet.51cbb18414", spanish: spanish) }
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
                Text(CuadraoCopy.text("copy.cuadraoAccountManagement.9d191b79fb", spanish: spanish)).font(.subheadline)
                TextField(kind == .business ? (CuadraoCopy.text("copy.cuadraoSpacesSheet.3b21106a12", spanish: spanish))
                          : (CuadraoCopy.text("copy.cuadraoSpacesSheet.e7b976d60c", spanish: spanish)), text: $name)
                    .autocorrectionDisabled().focused($focused).submitLabel(.done)
                    .onSubmit { focused = false }.modifier(RegistrationField(focused: focused))
                    .onChange(of: name) { _, value in if value.count > 40 { name = String(value.prefix(40)) } }
                    .accessibilityIdentifier("space-name")
                if !name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !valid {
                    Text(CuadraoCopy.text("copy.cuadraoSpacesSheet.1e8f28976f", spanish: spanish))
                        .font(.footnote).foregroundStyle(.secondary)
                }
                Text(CuadraoCopy.text("copy.cuadraoSpacesSheet.2ff6620b59", spanish: spanish))
                    .font(.subheadline).foregroundStyle(.secondary)
                RegistrationButton(title: existing == nil ? (CuadraoCopy.text("copy.cuadraoSpacesSheet.42893ce89f", spanish: spanish))
                    : (CuadraoCopy.text("copy.cuadraoAccountManagement.553ab1bf1a", spanish: spanish)), enabled: valid) {
                    data.saveSpace(kind: kind, name: name, existing: existing); finished()
                }
            }.padding(24)
        }.background(WelcomePalette.background)
            .navigationTitle(existing == nil ? kind.title(spanish) : (CuadraoCopy.text("copy.cuadraoSpacesSheet.be04335b17", spanish: spanish)))
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
                Section(CuadraoCopy.text("copy.cuadraoSpacesSheet.e95aacbabf", spanish: spanish)) {
                    ForEach(data.spaces.filter { $0.archived && !$0.deleted }) { space in row(space) }
                }
            }
            if data.spaces.contains(where: \.deleted) {
                Section(CuadraoCopy.text("copy.cuadraoProfilePage.430d2f5049", spanish: spanish)) {
                    ForEach(data.spaces.filter(\.deleted)) { space in row(space) }
                }
            }
            if let deletedID {
                Button(CuadraoCopy.text("copy.cuadraoSpacesSheet.b20652d49d", spanish: spanish)) {
                    data.restoreSpace(deletedID); self.deletedID = nil
                }
            }
        }.navigationTitle(CuadraoCopy.text("copy.cuadraoSpacesSheet.0742223e69", spanish: spanish)).navigationBarTitleDisplayMode(.inline)
            .confirmationDialog(CuadraoCopy.text("copy.cuadraoSpacesSheet.a67f46be6f", spanish: spanish),
                isPresented: Binding(get: { deletion != nil }, set: { if !$0 { deletion = nil } }), titleVisibility: .visible) {
                if let deletion {
                    Button(CuadraoCopy.text("copy.cuadraoSpacesSheet.909fa4b9c2", spanish: spanish), role: .destructive) {
                        data.deleteSpace(deletion); deletedID = deletion.id; self.deletion = nil
                    }
                }
                Button(CuadraoCopy.text("copy.connectedCuadraoProfile.62a128b722", spanish: spanish), role: .cancel) { deletion = nil }
            } message: {
                Text(CuadraoCopy.text("copy.cuadraoSpacesSheet.2da4bedefe", spanish: spanish))
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
                    Text(space.deleted || space.archived ? (CuadraoCopy.text("copy.cuadraoSpacesSheet.f6831c7566", spanish: spanish))
                         : space.kind.title(spanish)).font(.caption).foregroundStyle(.secondary)
                }.frame(maxWidth: .infinity, minHeight: 44, alignment: .leading).contentShape(Rectangle())
            }.buttonStyle(.plain)
            if space.isPrivate && !space.deleted {
                Menu {
                    NavigationLink(CuadraoCopy.text("copy.cuadraoSpacesSheet.be04335b17", spanish: spanish)) {
                        CuadraoSpaceNameForm(data: data, kind: space.kind, spanish: spanish,
                            existing: space, finished: open)
                    }
                    Button(space.archived ? (CuadraoCopy.text("copy.connectedCuadraoHome.e203d01b16", spanish: spanish)) : (CuadraoCopy.text("copy.connectedCuadraoHome.0960027352", spanish: spanish)),
                        systemImage: space.archived ? "arrow.uturn.backward" : "archivebox") {
                        data.archiveSpace(space.id, archived: !space.archived)
                    }
                    if data.canDeleteSpace(space) {
                        Button(CuadraoCopy.text("copy.cuadraoSpacesSheet.dd995d889a", spanish: spanish), systemImage: "trash", role: .destructive) { deletion = space }
                    }
                } label: {
                    Image(systemName: "ellipsis").frame(width: 44, height: 44)
                }.accessibilityLabel((CuadraoCopy.text("copy.cuadraoSpacesSheet.63e6903cf8", spanish: spanish)) + space.title(spanish))
            }
        }
    }
}
