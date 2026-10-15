import XCTest

/// An accepted deletion (202) shows "Eliminación en curso" once; the next launch is the signed-out entry, not that screen.
/// Needs the isolated stack with `ARGUS_ACCOUNT_DELETION_ENABLED` on and an identity it may delete.
extension FinancialLoopUITests {
    func testAcceptedDeletionRelaunchesSignedOut() throws {
        try signIn()
        app.terminate()
        app.launchArguments = ["-AppleLanguages", "(es-419)", "-AppleLocale", "es_DO", "--cuadrao-release-gates"]
        app.launch()
        app.openProfileSurface()
        tapVisible(app.buttons["cuadrao.profile.privacy"])
        tapVisible(app.buttons["cuadrao.profile.deleteAccount"])
        tapVisible(app.buttons["identity.delete.continue"])
        let verification = app.textFields["identity.delete.verification"]
        XCTAssertTrue(verification.waitForExistence(timeout: 5))
        verification.tap(); verification.typeText("DELETE")
        let submit = app.buttons["identity.delete.submit"]
        for _ in 0..<4 where !submit.isHittable { app.swipeUp() }
        submit.tap()
        let inProgress = app.staticTexts["identity.delete.inProgress"]
        XCTAssertTrue(inProgress.waitForExistence(timeout: 30), "the server accepted the deletion")
        capture("deletion-accepted")

        for launch in 1...2 {
            app.terminate()
            app.launch()
            let signedOut = app.buttons["cuadrao.welcome.signin"].firstMatch
            let loginOnly = app.textFields["auth.email"].firstMatch
            let entry = NSPredicate { _, _ in signedOut.exists || loginOnly.exists }
            XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: entry, object: nil)], timeout: 30), .completed,
                           "launch \(launch) opens the signed-out entry")
            XCTAssertFalse(inProgress.exists, "launch \(launch) no longer shows Eliminación en curso")
            XCTAssertFalse(app.buttons["header.profile"].exists, "launch \(launch) shows no account")
            capture("deletion-relaunch-\(launch)")
        }
    }
}
