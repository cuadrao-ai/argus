import SwiftUI

/// What the signed-out screen shows about the book, and how to open it.
struct GuestWelcomeContext {
    let shape: GuestAccessPolicy.Welcome
    let open: () -> Void
}

private struct GuestWelcomeKey: EnvironmentKey {
    static let defaultValue: GuestWelcomeContext? = nil
}

extension EnvironmentValues {
    /// Set only while the guest door is open; nil means the welcome screen has the two native actions and nothing else.
    var cuadraoGuestWelcome: GuestWelcomeContext? {
        get { self[GuestWelcomeKey.self] }
        set { self[GuestWelcomeKey.self] = newValue }
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

    /// The profile offers the claim only while it is switched on, an account is signed in and a book is on the iPhone.
    private var claimEntry: GuestClaimEntry? {
        guard CuadraoFirstRelease.guestClaim, auth.state == .authenticated, controller.hasStoredBook else { return nil }
        return GuestClaimEntry(directory: controller.bookDirectory, discard: { await controller.discardStoredBook() })
    }

    var body: some View {
        Group {
            switch route {
            case .connected:
                content.environment(\.cuadraoGuestClaim, claimEntry).environment(\.cuadraoGuestWelcome, GuestWelcomeContext(
                    shape: GuestAccessPolicy.welcome(doorOpen: true, accountSignedInBefore: controller.accountSignedInBefore,
                                                     hasGuestData: controller.hasStoredBook),
                    open: { controller.enter() }))
            case .launching:
                WelcomePalette.brandPaper.ignoresSafeArea().accessibilityIdentifier("guest.launching")
            case .guest:
                if let model = controller.model {
                    GuestRoot(model: model, appearance: $appearance,
                              leave: { controller.leave() }, deleteData: { await controller.deleteDataAndLeave() })
                        .environment(\.guestReceipts, controller.receipts)
                }
            }
        }
        // Signing in always wins: the book stays on the device and the signed-in app opens.
        .onChange(of: auth.state) { _, state in
            if state == .authenticated { controller.noteAccountSignedIn() }
            if state == .authenticated, controller.active { controller.leave() }
        }
        .onAppear { if auth.state == .authenticated { controller.noteAccountSignedIn() } }
    }
}
