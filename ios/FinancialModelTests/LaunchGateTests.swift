import XCTest
@testable import FinancialModels

final class LaunchGateTests: XCTestCase {
    private let start = Date(timeIntervalSinceReferenceDate: 800_000_000)

    func testUnknownUntilTheFirstRestoreEndsWhateverTheSessionSays() {
        XCTAssertEqual(LaunchGate(restored: false, authenticated: false), .unknown)
        XCTAssertEqual(LaunchGate(restored: false, authenticated: true), .unknown)
        XCTAssertFalse(LaunchGate.unknown.showsApp, "unknown never draws sign-in or Home")
    }

    func testAKnownSessionOpensTheApp() {
        XCTAssertEqual(LaunchGate(restored: true, authenticated: true), .signedIn)
        XCTAssertEqual(LaunchGate(restored: true, authenticated: false), .signedOut)
        XCTAssertTrue(LaunchGate.signedIn.showsApp)
        XCTAssertTrue(LaunchGate.signedOut.showsApp)
    }

    func testAHungCheckBecomesUnreachableAtTheDeadlineNotAnEndlessSpinner() {
        let before = start.addingTimeInterval(LaunchGate.deadline - 0.001)
        let at = start.addingTimeInterval(LaunchGate.deadline)
        XCTAssertEqual(LaunchGate(restored: false, authenticated: false, waitingSince: start, now: before), .unknown)
        XCTAssertEqual(LaunchGate(restored: false, authenticated: false, waitingSince: start, now: at), .unreachable)
        XCTAssertFalse(LaunchGate.unreachable.showsApp, "unreachable never draws sign-in or Home")
        XCTAssertEqual(LaunchGate(restored: true, authenticated: true, waitingSince: start, now: at), .signedIn,
                       "a restore that ends after the deadline still opens Home")
    }

    func testAStoredSessionTheServerCouldNotConfirmNeverFallsToSignIn() {
        XCTAssertEqual(LaunchGate(restored: true, authenticated: false, storedSessionUnconfirmed: true), .unreachable)
        XCTAssertEqual(LaunchGate(restored: true, authenticated: true, storedSessionUnconfirmed: true), .signedIn)
    }

    func testOnlyTheLoopOwnerResolvesWhileARestoreIsInFlight() {
        var progress = RestoreProgress()
        XCTAssertTrue(progress.enter(busy: false))
        XCTAssertFalse(progress.enter(busy: true), "a second restore joins the loop in flight")
        XCTAssertFalse(progress.known, "the joining call does not claim the session is known")
        progress.finishLoop()
        XCTAssertTrue(progress.known)
    }

    func testARestoreThatFindsAnotherOperationHoldingBusyStillResolves() {
        var progress = RestoreProgress()
        XCTAssertFalse(progress.enter(busy: true), "sign-in holds busy, so this restore does not run the loop")
        XCTAssertTrue(progress.known, "the snapshot it accepted is current, so the launch is known")
    }

    func testNoConfiguredSessionResolvesAtOnce() {
        var progress = RestoreProgress()
        progress.noSession()
        XCTAssertTrue(progress.known)
    }
}
