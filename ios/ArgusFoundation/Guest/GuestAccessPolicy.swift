import Foundation

/// What the on-device book ("Probar sin cuenta") may show and do, decided in one pure place so the shell,
/// the add tray and the tests read the same answer. It names no view and no server model.
enum GuestAccessPolicy {
    enum AuthPhase: Equatable {
        case signedOut, authenticated
        /// Disabled, invalid configuration, pending sign out, deletion states and every other non-sign-in phase.
        case other
    }

    enum Route: Equatable {
        /// The ordinary connected app: welcome, sign in, or the signed-in shell.
        case connected
        /// The book is active but the launch restore has not finished; show a neutral screen, never the welcome.
        case launching
        case guest
    }

    /// The door flag must be open, the person must have chosen the book, and no account may be signed in.
    /// A signed-in person is never routed into the book, and the book never flashes before the restore ends.
    static func route(doorOpen: Bool, bookActive: Bool, restored: Bool, auth: AuthPhase) -> Route {
        guard doorOpen, bookActive else { return .connected }
        guard restored else { return .launching }
        return auth == .signedOut ? .guest : .connected
    }

    /// What the signed-out screen offers. Once an account has signed in on this iPhone the book is no longer a way in:
    /// only the login form shows, with one quiet line to reach guest data that is still on the device.
    enum Welcome: Equatable {
        /// The first-run welcome. `guestEntry` adds "Probar sin cuenta" while the door is open.
        case full(guestEntry: Bool)
        case loginOnly(openGuestLine: Bool)
    }

    static func welcome(doorOpen: Bool, accountSignedInBefore: Bool, hasGuestData: Bool) -> Welcome {
        accountSignedInBefore ? .loginOnly(openGuestLine: doorOpen && hasGuestData) : .full(guestEntry: doorOpen)
    }

    /// What the book can do with no server. Everything not listed as local is refused here, not hidden ad hoc.
    enum Capability: CaseIterable {
        case accounts, movements, plans, search, calculations, appearance, primaryCurrency, deleteData
        case assistant, voiceCapture, receipts, files, households, invitations, updates
        case avatarPhoto, sharing, debts, recurringBills, forecast, balanceChecks, refunds

        var isLocal: Bool {
            switch self {
            // Receipts stay on this iPhone: captured, saved and attached by hand, never sent or read by a model.
            case .accounts, .movements, .plans, .search, .calculations, .appearance, .primaryCurrency, .deleteData, .receipts: true
            case .assistant, .voiceCapture, .files, .households, .invitations, .updates,
                 .avatarPhoto, .sharing, .debts, .recurringBills, .forecast, .balanceChecks, .refunds: false
            }
        }
    }

    static func allows(_ capability: Capability) -> Bool { capability.isLocal }

    /// The third navigation slot is the add action: the book has no assistant.
    static var hasAssistant: Bool { allows(.assistant) }

    /// Rows of the + tray that exist yet. Slices add to this set as the screens behind them land.
    enum Built: Hashable { case accounts, movements, plans, receipts }
    static let built: Set<Built> = [.accounts, .movements, .plans, .receipts]

    static func addActions(activeAccounts: Int, built: Set<Built> = GuestAccessPolicy.built) -> [CuadraoAddAction] {
        var actions: [CuadraoAddAction] = []
        if built.contains(.accounts) { actions.append(.account) }
        if built.contains(.movements), activeAccounts > 0 { actions.append(.transaction) }
        if built.contains(.plans), activeAccounts > 0 { actions.append(.plan) }
        if built.contains(.receipts), allows(.receipts) { actions += [.scanCamera, .choosePhoto, .chooseFile] }
        return actions
    }
}
