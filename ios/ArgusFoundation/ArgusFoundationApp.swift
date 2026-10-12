import SwiftUI
import AuthenticationServices

enum AppearancePreference: String, CaseIterable {
    case light, dark, system

    static let storageKey = "appearancePreference"

    var colorScheme: ColorScheme? {
        switch self {
        case .light: .light
        case .dark: .dark
        case .system: nil
        }
    }

    var title: LocalizedStringKey { LocalizedStringKey("appearance." + rawValue) }
}

@main
struct ArgusFoundationApp: App {
    @StateObject private var auth = ProfileAuthModel()
    @AppStorage(AppearancePreference.storageKey) private var appearance = AppearancePreference.system
    /// Design-preview only; separate from the connected app's appearance preference.
    @AppStorage(CuadraoAppearancePicker.storageKey) private var previewAppearance = AppearancePreference.light

    var body: some Scene {
        WindowGroup {
            appContent
        }
    }

    @ViewBuilder private var appContent: some View {
        #if DEBUG
        if ProcessInfo.processInfo.arguments.contains("--apple-session-harness") {
            AppleSessionHarness()
        } else if ProcessInfo.processInfo.arguments.contains("--cuadrao-release-ui") {
            ReleaseUIReview()
        } else if ProcessInfo.processInfo.arguments.contains("--invitations-harness") {
            InvitationsHarness()
        } else if ProcessInfo.processInfo.arguments.contains("--captcha-harness") {
            CaptchaHarness()
        } else if ProcessInfo.processInfo.arguments.contains("--receipt-journey-harness") {
            ReceiptJourneyHarness().preferredColorScheme(appearance.colorScheme)
        } else {
            connectedContent
        }
        #else
        connectedContent
        #endif
    }

    @ViewBuilder private var connectedContent: some View {
        Group {
            if CuadraoDesignPreview.isActive {

                CuadraoCanvas()
                    .preferredColorScheme(previewAppearance.colorScheme)
            } else {
                GuestModeRouter(appearance: $appearance) { ConnectedCuadraoRoot(appearance: $appearance) }
                    .environmentObject(auth)
                    .modifier(SessionLifecycle(model: auth))
                    .preferredColorScheme(appearance.colorScheme)
            }
        }.background(KeyboardTapAway())
    }
}

struct SessionLifecycle: ViewModifier {
    @ObservedObject var model: ProfileAuthModel
    @Environment(\.scenePhase) private var scenePhase

    func body(content: Content) -> some View {
        content
            .task { await model.start() }
            .onReceive(NotificationCenter.default.publisher(for: ASAuthorizationAppleIDProvider.credentialRevokedNotification)) { _ in
                Task { await model.restore() }
            }
            .onChange(of: scenePhase) { _, phase in
                if phase == .active { Task { await model.restore() } }
            }
    }
}
