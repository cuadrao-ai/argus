import SwiftUI

struct CanvasProfileDraft {
    let emailAddress = "alex@example.com"
    var name = "Alex Rivera"
    var preferredName = "Alex"
    var avatar: CuadraoAvatarSelection = .none
    var settings = CuadraoProfileSettingsDraft()
}

struct CuadraoProfileSettingsDraft {
    var currency = "DOP"
    var quietStart = Calendar.current.date(from: DateComponents(hour: 22)) ?? .now
    var quietEnd = Calendar.current.date(from: DateComponents(hour: 8)) ?? .now
    var responseLength = 0
    var tone = 0
    var instructions = ""
    var feedback = CanvasFeedbackDraft()
    var push = false
    var budgets = true
    var goals = true
    var payments = true
    var records = true
    var household = true
    var quietHours = false
}

struct CuadraoProfileIdentityValue {
    let name: String
    let emailAddress: String?
    let avatar: CuadraoAvatarSelection
}

enum CanvasProfileRoute: Hashable {
    case personal, preferences, personalization, notifications, security, privacy, usage, help
    case memory, files, conversations, shared, removed, voice, advanced, feedback, invitations
    func title(_ es: Bool) -> String {
        switch self {
        case .personal: es ? "Mi perfil" : "My profile"
        case .preferences: es ? "Preferencias" : "Preferences"
        case .personalization: es ? "Personalización" : "Personalization"
        case .notifications: es ? "Notificaciones" : "Notifications"
        case .security: es ? "Seguridad" : "Security"
        case .privacy: es ? "Datos y privacidad" : "Data and privacy"
        case .usage: es ? "Uso" : "Usage"
        case .help: es ? "Ayuda y comentarios" : "Help and feedback"
        case .memory: es ? "Memoria" : "Memory"
        case .files: CuadraoFirstRelease.savedReceipts ? SavedReceiptCopy(spanish: es).title : (es ? "Archivos" : "Files")
        case .conversations: es ? "Conversaciones" : "Conversations"
        case .shared: es ? "Conversaciones compartidas" : "Shared conversations"
        case .removed: es ? "Movimientos eliminados" : "Removed activity"
        case .voice: es ? "Voz" : "Voice"
        case .advanced: es ? "Más opciones" : "More options"
        case .feedback: es ? "Comentarios" : "Feedback"
        case .invitations: es ? "Invitaciones" : "Invitations"
        }
    }
    var symbol: String {
        switch self {
        case .personal: "person"
        case .preferences: "slider.horizontal.3"
        case .personalization: "sparkle"
        case .notifications: "bell"
        case .security: "lock"
        case .privacy: "hand.raised"
        case .usage: "chart.bar"
        case .help: "questionmark.circle"
        case .memory: "brain"
        case .files: "doc"
        case .conversations: "bubble.left.and.bubble.right"
        case .shared: "link"
        case .removed: "trash"
        case .voice: "waveform"
        case .advanced: "ellipsis"
        case .feedback: "bubble.left"
        case .invitations: "person.badge.plus"
        }
    }
}

/// Release builds hide designed controls whose backend is still owed. DEBUG builds show all of
/// them unless launched with `--cuadrao-release-gates`, which previews the release set.
enum CuadraoFirstRelease {
    static let unfinishedProfileRoutes: Set<CanvasProfileRoute> = [
        .personalization, .security, .shared, .removed, .memory, .usage, .advanced,
        // The free tier has no AI chats and no stored files yet, so these pages would only say "Nothing saved".
        .files, .conversations,
        // Notificaciones toggles request no permission and send nothing; Comentarios only keeps a draft on the iPhone.
        .notifications, .feedback
    ]
    #if CUADRAO_FOUNDER_PHONE
    /// The founder's phone build: the release layout with receipts and the guest door on, without launch arguments.
    static let founderPhone = true
    #else
    static let founderPhone = false
    #endif
    #if DEBUG
    static let hidesUnfinished = founderPhone || ProcessInfo.processInfo.arguments.contains("--cuadrao-release-gates")
    #else
    static let hidesUnfinished = true
    #endif
    /// Avatar choices, photos included, live only in this session until profile storage exists.
    static var editsAvatar: Bool { !hidesUnfinished }
    static var showsConversationBulkActions: Bool { !hidesUnfinished }
    /// Business and custom spaces are designed but have no backend, so Release hides them.
    static var showsExtraSpaces: Bool { !hidesUnfinished }
    /// The assistant answers from sample data until it is connected, so Release has no assistant tab
    /// and its third navigation slot is the add-movement action. The design Preview keeps its assistant.
    static var hasAssistant: Bool { !hidesUnfinished || CuadraoDesignPreview.isActive }
    /// The Updates bell and receipt capture are designed, but nothing feeds them yet.
    static var showsUpdates: Bool { !hidesUnfinished || CuadraoDesignPreview.isActive }
    static var showsReceiptCapture: Bool { !hidesUnfinished || CuadraoDesignPreview.isActive }
    /// Saved receipts are built and tested but stay off until receipt access is enabled (a separate founder approval).
    #if DEBUG
    static let savedReceipts = founderPhone || ProcessInfo.processInfo.arguments.contains("--cuadrao-saved-receipts") || savedReceiptsSample
    /// Sample data and no system pickers, so the screens can be driven without a server.
    static let savedReceiptsSample = ProcessInfo.processInfo.arguments.contains("--cuadrao-saved-receipts-sample")
    #else
    static let savedReceipts = false
    #endif

    static func shows(_ route: CanvasProfileRoute) -> Bool {
        if route == .voice { return CuadraoDesignPreview.voiceSelection }
        if route == .files, savedReceipts { return true }
        return !(hidesUnfinished && unfinishedProfileRoutes.contains(route))
    }
}

enum CanvasSettingsStyle {
    static let surface = WelcomePalette.surface
    static let separator = WelcomePalette.separator
}

struct CuadraoProfileCanvas: View {
    let spanish: Bool
    let includeExamples: Bool
    @Binding var profile: CanvasProfileDraft
    @Binding var path: [CanvasProfileRoute]
    let bottomSpace: CGFloat
    @State private var signOut = false
    @State private var editor: CanvasProfileRoute?

    var body: some View {
        NavigationStack(path: $path) {
            CuadraoProfileBody(spanish: spanish,
                identity: .init(name: profile.name, emailAddress: profile.emailAddress, avatar: profile.avatar),
                bottomSpace: bottomSpace, editProfile: { editor = .personal }) {
                EmptyView()
            } accountActions: {
                Button(spanish ? "Cerrar sesión" : "Sign out") { signOut = true }
                    .font(.subheadline).foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, minHeight: 44)
                    .accessibilityIdentifier("cuadrao.profile.signout")
            }
            .navigationDestination(for: CanvasProfileRoute.self) { route in
                CuadraoProfilePage(route: route, profile: $profile, spanish: spanish, includeExamples: includeExamples)
            }
            .sheet(item: $editor) { _ in
                NavigationStack {
                    CuadraoProfileEditor(name: $profile.name, preferredName: $profile.preferredName,
                        emailAddress: profile.emailAddress, avatar: $profile.avatar, spanish: spanish)
                }.tint(WelcomePalette.pine)
            }
            .alert(spanish ? "Cerrar sesión" : "Sign out", isPresented: $signOut) {
                Button(spanish ? "Entendido" : "Got it", role: .cancel) {}
            } message: {
                Text(spanish ? "Esta vista previa no tiene una sesión conectada. Tu sesión de Argus sigue abierta."
                     : "This preview has no connected session. Your Argus session remains signed in.")
            }
        }.toolbar(.hidden, for: .tabBar)
    }
}

struct CuadraoProfileBody<AccountRows: View, AccountActions: View>: View {
    let spanish: Bool
    let identity: CuadraoProfileIdentityValue
    let bottomSpace: CGFloat
    let editProfile: () -> Void
    @ViewBuilder var accountRows: () -> AccountRows
    @ViewBuilder var accountActions: () -> AccountActions
    @Environment(\.dynamicTypeSize) private var typeSize

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                identityRow.padding(.bottom, 4)
                group("App", routes: [.preferences, .personalization, .notifications])
                group(spanish ? "Cuenta" : "Account", routes: [.security, .privacy, .usage], includesAccountRows: true)
                group(spanish ? "Soporte" : "Support", routes: [.help])
                accountActions()
            }.padding(.horizontal, 24).padding(.top, 24).padding(.bottom, bottomSpace + 24)
        }
        .background(WelcomePalette.background).toolbar(.hidden, for: .navigationBar)
    }

    private var identityRow: some View {
        Button(action: editProfile) { identityContent }
            .buttonStyle(.plain).accessibilityIdentifier("cuadrao.profile.identity")
    }

    private var identityContent: some View {
        let layout = typeSize.isAccessibilitySize ? AnyLayout(VStackLayout(alignment: .leading, spacing: 18)) : AnyLayout(HStackLayout(spacing: 20))
        return layout {
            CanvasProfileAvatar(name: identity.name, style: identity.avatar, size: 76)
            VStack(alignment: .leading, spacing: 6) {
                Text(identity.name).font(.system(.title2, design: .default, weight: .semibold))
                    .foregroundStyle(.primary)
                if let email = identity.emailAddress {
                    Text(email).font(.subheadline).foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Text(spanish ? "Editar perfil" : "Edit profile")
                    .font(.subheadline.weight(.medium)).foregroundStyle(WelcomePalette.pine)
                    .padding(.top, 4)
            }
            Spacer(minLength: 0)
        }.contentShape(Rectangle())
    }

    @ViewBuilder private func group(_ title: String, routes all: [CanvasProfileRoute], includesAccountRows: Bool = false) -> some View {
        let routes = all.filter { CuadraoFirstRelease.shows($0) }
        if !routes.isEmpty {
            VStack(alignment: .leading, spacing: 10) {
                Text(title).font(.subheadline).foregroundStyle(.secondary).accessibilityAddTraits(.isHeader)
                VStack(spacing: 0) {
                    ForEach(routes, id: \.self) { route in
                        NavigationLink(value: route) {
                            CanvasProfileRow(route: route, spanish: spanish)
                        }.buttonStyle(.plain).accessibilityIdentifier("cuadrao.profile.\(route)")
                        if route != routes.last {
                            Rectangle().fill(CanvasSettingsStyle.separator).frame(height: 0.5)
                                .padding(.leading, 54).padding(.trailing, 18).accessibilityHidden(true)
                        }
                    }
                    if includesAccountRows { accountRows() }
                }.background(CanvasSettingsStyle.surface, in: RoundedRectangle(cornerRadius: 22))
            }
        }
    }
}

extension CanvasProfileRoute: Identifiable {
    var id: Self { self }
}

struct CanvasProfileIcon: View {
    let route: CanvasProfileRoute
    var body: some View {
        Group {
            if route == .notifications {
                Image("CuadraoNotifications").resizable().scaledToFit()
            } else {
                Image(systemName: route.symbol).font(.system(size: 19, weight: .regular))
                    .environment(\.symbolVariants, .none)
            }
        }.frame(width: 22, height: 22).foregroundStyle(.secondary).accessibilityHidden(true)
    }
}

struct CanvasProfileRow: View {
    let route: CanvasProfileRoute
    let spanish: Bool
    var body: some View {
        HStack(spacing: 14) {
            CanvasProfileIcon(route: route)
            Text(route.title(spanish)).font(.body)
            Spacer(minLength: 8)
            Image(systemName: "chevron.right").font(.system(size: 12, weight: .semibold))
                .foregroundStyle(.tertiary).accessibilityHidden(true)
        }.padding(.horizontal, 18).padding(.vertical, 16)
            .frame(minHeight: 56).contentShape(Rectangle())
    }
}

struct CuadraoProfileEditor: View {
    @Binding private var savedName: String
    @Binding private var savedPreferred: String
    @Binding private var savedAvatar: CuadraoAvatarSelection
    let emailAddress: String?
    let spanish: Bool
    private let saveNames: ((String, String) async -> Bool)?
    @Environment(\.dismiss) private var dismiss
    @State private var name: String
    @State private var preferred: String
    @State private var avatar: CuadraoAvatarSelection
    @State private var photoLoading = false
    @State private var cropRequest: CanvasAvatarCropRequest?
    @State private var saving = false
    @State private var saveFailed = false

    /// `saveNames` persists the trimmed names elsewhere and reports whether they were kept.
    init(name: Binding<String>, preferredName: Binding<String>, emailAddress: String?,
         avatar: Binding<CuadraoAvatarSelection>, spanish: Bool, saveNames: ((String, String) async -> Bool)? = nil) {
        _savedName = name; _savedPreferred = preferredName; _savedAvatar = avatar
        self.emailAddress = emailAddress; self.spanish = spanish; self.saveNames = saveNames
        _name = State(initialValue: name.wrappedValue)
        _preferred = State(initialValue: preferredName.wrappedValue)
        _avatar = State(initialValue: avatar.wrappedValue)
    }
    private var trimmedName: String { name.trimmingCharacters(in: .whitespacesAndNewlines) }
    private var trimmedPreferred: String { preferred.trimmingCharacters(in: .whitespacesAndNewlines) }
    private var valid: Bool {
        !trimmedName.isEmpty && name.count <= 60 && preferred.count <= 40
    }
    private var namesChanged: Bool { trimmedName != savedName || trimmedPreferred != savedPreferred }
    private var changed: Bool { namesChanged || avatar != savedAvatar }
    var body: some View {
        Form {
            Section {
                HStack { Spacer(); CanvasProfileAvatar(name: name, style: avatar); Spacer() }
                    .padding(.vertical, 12).listRowBackground(Color.clear)
            }
            if CuadraoFirstRelease.editsAvatar {
                CuadraoProfileAvatarPicker(name: name, spanish: spanish, avatar: $avatar, loading: $photoLoading, cropRequest: $cropRequest)
            }
            Section {
                field(spanish ? "Nombre" : "Name", text: $name, id: "cuadrao.profile.name")
                    .textContentType(.name).disabled(saving)
                field(spanish ? "Cómo te llamamos" : "What we call you", text: $preferred,
                      id: "cuadrao.profile.preferred")
                    .textContentType(.nickname).disabled(saving)
            } footer: {
                Text(spanish ? "Usaremos tu nombre preferido al conversar contigo."
                     : "We'll use your preferred name when we talk with you.")
            }.listRowBackground(CanvasSettingsStyle.surface)
            if let emailAddress {
                Section {
                    VStack(alignment: .leading, spacing: 7) {
                        Text(spanish ? "Correo" : "Email").font(.subheadline).foregroundStyle(.secondary)
                        Text(emailAddress)
                    }.padding(.vertical, 6)
                }.listRowBackground(CanvasSettingsStyle.surface)
            }
            if !valid {
                Text(spanish ? "Escribe un nombre de hasta 60 caracteres y un nombre preferido de hasta 40."
                     : "Enter a name up to 60 characters and a preferred name up to 40.")
                    .font(.footnote).foregroundStyle(.secondary).listRowBackground(Color.clear)
            }
            if saveFailed {
                Text(spanish ? "No pudimos guardar tu nombre. Inténtalo de nuevo."
                     : "We couldn't save your name. Try again.")
                    .font(.footnote).foregroundStyle(.secondary).listRowBackground(Color.clear)
                    .accessibilityIdentifier("cuadrao.profile.save.error")
            }
        }.scrollContentBackground(.hidden).background(WelcomePalette.background)
            .sheet(item: $cropRequest) { request in
                CanvasAvatarCropSheet(request: request, spanish: spanish) { avatar = .photo($0) }
            }
            .navigationTitle(spanish ? "Editar perfil" : "Edit profile").navigationBarTitleDisplayMode(.inline)
            .toolbar {
                CuadraoCancelToolbar(title: spanish ? "Cancelar" : "Cancel", identifier: "cuadrao.profile.cancel") { dismiss() }
                CuadraoConfirmToolbar(title: spanish ? "Guardar" : "Save", disabled: !valid || !changed || photoLoading || saving,
                                      identifier: "cuadrao.profile.save", action: save)
            }
    }
    private func save() {
        guard let saveNames, namesChanged else {
            savedName = trimmedName; savedPreferred = trimmedPreferred; savedAvatar = avatar
            dismiss()
            return
        }
        saving = true; saveFailed = false
        Task {
            let kept = await saveNames(trimmedName, trimmedPreferred)
            saving = false
            if kept { savedAvatar = avatar; dismiss() } else { saveFailed = true }
        }
    }
    private func field(_ label: String, text: Binding<String>, id: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(label).font(.subheadline).foregroundStyle(.secondary)
            TextField(label, text: text).accessibilityLabel(label).accessibilityIdentifier(id)
        }.padding(.vertical, 6)
    }
}
