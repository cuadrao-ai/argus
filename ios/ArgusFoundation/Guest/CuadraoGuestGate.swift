import Foundation

extension CuadraoFirstRelease {
    /// The "Probar sin cuenta" door. Closed in Release; a development build opens it with `--cuadrao-guest-book`.
    /// Opening it for users is a separate founder approval.
    #if DEBUG
    static let guestBook = founderPhone || ProcessInfo.processInfo.arguments.contains("--cuadrao-guest-book")
    #else
    static let guestBook = false
    #endif

    /// Claiming the on-device book into an account stays off until it is approved. A development build opens it
    /// with `--cuadrao-guest-claim`, and so does the founder phone build (Debug only; Release is always off).
    #if DEBUG
    static let guestClaim = founderPhone || ProcessInfo.processInfo.arguments.contains("--cuadrao-guest-claim")
    #else
    static let guestClaim = false
    #endif
}

#if DEBUG
/// Development switches for the book: clear it at launch, or keep it in a chosen folder.
enum CuadraoGuestLaunch {
    static let resets = ProcessInfo.processInfo.arguments.contains("--cuadrao-guest-reset")
    /// Pretends an account has signed in on this iPhone before, to see the login-only screen.
    static let accountSignedInBefore = ProcessInfo.processInfo.arguments.contains("--cuadrao-account-signed-in-before")

    static var directory: URL? {
        let arguments = ProcessInfo.processInfo.arguments
        guard let flag = arguments.firstIndex(of: "--cuadrao-guest-directory"), arguments.indices.contains(flag + 1) else { return nil }
        return URL(fileURLWithPath: arguments[flag + 1], isDirectory: true)
    }
}
#endif
