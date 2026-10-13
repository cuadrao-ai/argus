import XCTest
@testable import FinancialModels

final class LaunchGateTests: XCTestCase {
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
}
