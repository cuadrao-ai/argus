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
        case .personal: CuadraoCopy.text("copy.cuadraoProfileCanvas.c8aa69bab4", spanish: es)
        case .preferences: CuadraoCopy.text("copy.cuadraoProfileCanvas.7f8139b9a4", spanish: es)
        case .personalization: CuadraoCopy.text("copy.cuadraoProfileCanvas.a375f1276e", spanish: es)
        case .notifications: CuadraoCopy.text("copy.cuadraoProfileCanvas.e66eecd5cf", spanish: es)
        case .security: CuadraoCopy.text("copy.cuadraoProfileCanvas.065299bb82", spanish: es)
        case .privacy: CuadraoCopy.text("copy.cuadraoProfileCanvas.2c59cb5dad", spanish: es)
        case .usage: CuadraoCopy.text("copy.cuadraoProfileCanvas.38d965c260", spanish: es)
        case .help: CuadraoCopy.text("copy.cuadraoProfileCanvas.245c17ba74", spanish: es)
        case .memory: CuadraoCopy.text("copy.cuadraoProfileCanvas.7fa6d06e03", spanish: es)
        case .files: CuadraoFirstRelease.savedReceipts ? SavedReceiptCopy(spanish: es).title : (CuadraoCopy.text("copy.cuadraoProfileCanvas.2cec6f3871", spanish: es))
        case .conversations: CuadraoCopy.text("copy.cuadraoProfileCanvas.d9659690c0", spanish: es)
        case .shared: CuadraoCopy.text("copy.cuadraoProfileCanvas.722f6f27e2", spanish: es)
        case .removed: CuadraoCopy.text("copy.cuadraoProfileCanvas.9e5f002093", spanish: es)
        case .voice: CuadraoCopy.text("copy.cuadraoProfileCanvas.d0a8b9cb41", spanish: es)
        case .advanced: CuadraoCopy.text("copy.cuadraoProfileCanvas.cc958ca371", spanish: es)
        case .feedback: CuadraoCopy.text("copy.cuadraoProfileCanvas.1b153643ac", spanish: es)
        case .invitations: CuadraoCopy.text("copy.cuadraoProfileCanvas.4970c3efc4", spanish: es)
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
                Button(CuadraoCopy.text("copy.connectedCuadraoProfile.a47c0e9665", spanish: spanish)) { signOut = true }
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
            .alert(CuadraoCopy.text("copy.connectedCuadraoProfile.a47c0e9665", spanish: spanish), isPresented: $signOut) {
                Button(CuadraoCopy.text("copy.cuadraoAccountCanvas.43385c465a", spanish: spanish), role: .cancel) {}
            } message: {
                Text(CuadraoCopy.text("copy.cuadraoProfileCanvas.a33ac583d8", spanish: spanish))
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
                group(CuadraoCopy.text("copy.cuadraoProfileCanvas.b67b6e77f6", spanish: CuadraoCopy.isSpanish()), routes: [.preferences, .personalization, .notifications])
                group(CuadraoCopy.text("copy.connectedAccountPresentation.f9d32ca2e5", spanish: spanish), routes: [.security, .privacy, .usage], includesAccountRows: true)
                group(CuadraoCopy.text("copy.cuadraoProfileCanvas.4a0be06897", spanish: spanish), routes: [.help])
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
                Text(CuadraoCopy.text("copy.cuadraoProfileCanvas.6f4cb9c965", spanish: spanish))
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
                field(CuadraoCopy.text("copy.cuadraoAccountManagement.9d191b79fb", spanish: spanish), text: $name, id: "cuadrao.profile.name")
                    .textContentType(.name).disabled(saving)
                field(CuadraoCopy.text("copy.cuadraoProfileCanvas.63d6906c02", spanish: spanish), text: $preferred,
                      id: "cuadrao.profile.preferred")
                    .textContentType(.nickname).disabled(saving)
            } footer: {
                Text(CuadraoCopy.text("copy.cuadraoProfileCanvas.3992f504c2", spanish: spanish))
            }.listRowBackground(CanvasSettingsStyle.surface)
            if let emailAddress {
                Section {
                    VStack(alignment: .leading, spacing: 7) {
                        Text(CuadraoCopy.text("copy.cuadraoProfileCanvas.c02619e107", spanish: spanish)).font(.subheadline).foregroundStyle(.secondary)
                        Text(emailAddress)
                    }.padding(.vertical, 6)
                }.listRowBackground(CanvasSettingsStyle.surface)
            }
            if !valid {
                Text(CuadraoCopy.text("copy.cuadraoProfileCanvas.3d6348b8db", spanish: spanish))
                    .font(.footnote).foregroundStyle(.secondary).listRowBackground(Color.clear)
            }
            if saveFailed {
                Text(CuadraoCopy.text("copy.cuadraoProfileCanvas.53c6ddfb22", spanish: spanish))
                    .font(.footnote).foregroundStyle(.secondary).listRowBackground(Color.clear)
                    .accessibilityIdentifier("cuadrao.profile.save.error")
            }
        }.scrollContentBackground(.hidden).background(WelcomePalette.background)
            .sheet(item: $cropRequest) { request in
                CanvasAvatarCropSheet(request: request, spanish: spanish) { avatar = .photo($0) }
            }
            .navigationTitle(CuadraoCopy.text("copy.cuadraoProfileCanvas.6f4cb9c965", spanish: spanish)).navigationBarTitleDisplayMode(.inline)
            .toolbar {
                CuadraoCancelToolbar(title: CuadraoCopy.text("copy.connectedCuadraoProfile.62a128b722", spanish: spanish), identifier: "cuadrao.profile.cancel") { dismiss() }
                CuadraoConfirmToolbar(title: CuadraoCopy.text("copy.cuadraoAccountManagement.553ab1bf1a", spanish: spanish), disabled: !valid || !changed || photoLoading || saving,
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
