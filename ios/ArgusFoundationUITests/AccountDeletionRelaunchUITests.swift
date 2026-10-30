import XCTest

/// An accepted deletion (202) shows "Eliminación en curso" once; the next launch is the signed-out entry, not that screen.
/// Needs the isolated stack with `CUADRAO_ACCOUNT_DELETION_ENABLED` on and an identity it may delete.
extension FinancialLoopUITests {
    func testAcceptedDeletionRelaunchesSignedOut() throws {
        try signIn()
        let inProgress = submitAcceptedDeletion()
        capture("deletion-accepted")

        for launch in 1...2 {
            relaunchToSignedOutEntry("launch \(launch)")
            XCTAssertFalse(inProgress.exists, "launch \(launch) no longer shows Eliminación en curso")
            capture("deletion-relaunch-\(launch)")
        }
    }

    /// The deleted account's local receipt drafts leave with it; checked on disk by the lane run. Here: another
    /// account's draft on the same iPhone is still there after the accepted deletion and a relaunch.
    func testAcceptedDeletionKeepsAnotherAccountsReceiptDraft() throws {
        #if !DEBUG
        throw XCTSkip("Receipt capture remains a development-only local draft.")
        #else
        try signIn(fresh: true, user: "B")
        let kept = addConnectedSampleDraft()
        try signIn(fresh: true)
        _ = addConnectedSampleDraft()
        capture("deletion-drafts-before")
        _ = submitAcceptedDeletion()
        capture("deletion-drafts-accepted")
        relaunchToSignedOutEntry("relaunch")
        try signIn(user: "B")
        openConnectedSavedReceipts()
        XCTAssertTrue(app.buttons[kept].waitForExistence(timeout: 5), "another account's draft stays on this iPhone")
        capture("deletion-drafts-other-account-kept")
        app.buttons["Done"].tap()
        #endif
    }

    private func submitAcceptedDeletion() -> XCUIElement {
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
        return inProgress
    }

    private func relaunchToSignedOutEntry(_ label: String) {
        app.terminate()
        app.launch()
        let signedOut = app.buttons["cuadrao.welcome.signin"].firstMatch
        let loginOnly = app.textFields["auth.email"].firstMatch
        let entry = NSPredicate { _, _ in signedOut.exists || loginOnly.exists }
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: entry, object: nil)], timeout: 30), .completed,
                       "\(label) opens the signed-out entry")
        XCTAssertFalse(app.buttons["header.profile"].exists, "\(label) shows no account")
    }

    private func addConnectedSampleDraft() -> String {
        openConnectedSavedReceipts()
        tapVisible(app.buttons["saved-add-receipt"])
        tapVisible(app.buttons["receipt-sample"])
        XCTAssertTrue(app.staticTexts["receipt-local-draft-notice"].waitForExistence(timeout: 5))
        app.buttons["receipt-later"].tap()
        openConnectedSavedReceipts()
        let card = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'receipt-card-'")).firstMatch
        XCTAssertTrue(card.waitForExistence(timeout: 5))
        let id = card.identifier
        app.buttons["Done"].tap()
        return id
    }
}
