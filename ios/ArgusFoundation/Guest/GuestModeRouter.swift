import SwiftUI

private struct GuestEntryKey: EnvironmentKey {
    static let defaultValue: (() -> Void)? = nil
}

extension EnvironmentValues {
    /// Set only while the guest door is open; the welcome screen shows "Probar sin cuenta" when it is non-nil.
    var cuadraoGuestEntry: (() -> Void)? {
        get { self[GuestEntryKey.self] }
        set { self[GuestEntryKey.self] = newValue }
    }
}

/// Chooses between the connected app and the on-device book. With the door closed it returns the connected
/// app untouched, so Release builds neither create the controller nor read the book.
struct GuestModeRouter<Content: View>: View {
    @Binding var appearance: AppearancePreference
    @ViewBuilder let content: () -> Content

    var body: some View {
        if CuadraoFirstRelease.guestBook {
            GuestModeHost(appearance: $appearance, content: content())
        } else {
            content()
        }
    }
}

private struct GuestModeHost<Content: View>: View {
    @Binding var appearance: AppearancePreference
    let content: Content
    @EnvironmentObject private var auth: ProfileAuthModel
    @StateObject private var controller = GuestModeController()

    private var phase: GuestAccessPolicy.AuthPhase {
        switch auth.state {
        case .signedOut: .signedOut
        case .authenticated: .authenticated
        default: .other
        }
    }

    private var route: GuestAccessPolicy.Route {
        let bookReady = controller.model.map { $0.phase != .loading } ?? true
        return GuestAccessPolicy.route(doorOpen: CuadraoFirstRelease.guestBook, bookActive: controller.active,
                                       restored: auth.hasRestored && bookReady, auth: phase)
    }

    var body: some View {
        Group {
            switch route {
            case .connected:
                content.environment(\.cuadraoGuestEntry, { controller.enter() })
            case .launching:
                // The brief wait while the saved book opens: blocks in the shape of Home, never an empty page.
                GuestLaunchSkeleton()
            case .guest:
                if let model = controller.model {
                    GuestRoot(model: model, appearance: $appearance, webURL: auth.configuration?.webURL,
                              leave: { controller.leave() }, deleteData: { await controller.deleteDataAndLeave() })
                        .environment(\.guestReceipts, controller.receipts)
                }
            }
        }
        // Signing in always wins: the book stays on the device and the signed-in app opens.
        .onChange(of: auth.state) { _, state in
            if state == .authenticated, controller.active { controller.leave() }
        }
    }
}

/// Home's blocks while the saved book opens. The top space follows the text size, as Home's greeting does.
private struct GuestLaunchSkeleton: View {
    @ScaledMetric(relativeTo: .largeTitle) private var top = 72

    var body: some View {
        ZStack(alignment: .top) {
            WelcomePalette.brandPaper.ignoresSafeArea()
            CuadraoSkeleton(layout: .home, identifier: "guest.loading").padding(.horizontal, 20).padding(.top, top)
        }
    }
}
