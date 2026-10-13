import Foundation

/// What the first frames may show. Until the stored session is known the gate is `unknown`, and only the
/// launch screen draws: never sign-in, sign-up or Home. A check that passes the deadline, or a stored session
/// the server could not confirm, is `unreachable`: a sentence and Reintentar, never an endless spinner and
/// never sign-in for someone who still holds a session.
enum LaunchGate: Equatable {
    case unknown, signedIn, signedOut, unreachable

    static let deadline: TimeInterval = 8

    init(restored: Bool, authenticated: Bool, storedSessionUnconfirmed: Bool = false,
         waitingSince: Date = .distantFuture, now: Date = .distantPast) {
        if restored {
            if authenticated { self = .signedIn }
            else if storedSessionUnconfirmed { self = .unreachable }
            else { self = .signedOut }
        } else {
            self = now.timeIntervalSince(waitingSince) >= Self.deadline ? .unreachable : .unknown
        }
    }

    var showsApp: Bool { self == .signedIn || self == .signedOut }
}

/// When a launch is known. Only the restore that runs the loop, or a call that finds the lock held by another
/// operation, resolves it; a call that finds a restore loop in flight leaves it to that loop.
struct RestoreProgress: Equatable {
    private(set) var known = false
    private(set) var loopRunning = false

    /// Returns true when this call should run the restore loop.
    mutating func enter(busy: Bool) -> Bool {
        guard busy else { loopRunning = true; return true }
        if !loopRunning { known = true }
        return false
    }

    mutating func finishLoop() {
        loopRunning = false
        known = true
    }

    mutating func noSession() { known = true }
}
