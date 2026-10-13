/// What the first frames may show. Until the stored session is known the gate is `unknown`, and only the
/// launch screen draws: never sign-in, sign-up or Home.
enum LaunchGate: Equatable {
    case unknown, signedIn, signedOut

    init(restored: Bool, authenticated: Bool) {
        guard restored else { self = .unknown; return }
        self = authenticated ? .signedIn : .signedOut
    }

    var showsApp: Bool { self != .unknown }
}
