import XCTest

/// The receipt journey with the debug sample server (`--cuadrao-saved-receipts-sample`): consent first, the reading,
/// a review filled from the receipt, one confirmation, and the saved expense.
extension FinancialLoopUITests {
    func testReceiptJourneyReadsReviewsAndSavesTheExpenseOnlyAfterConfirmation() throws {
        try signIn()
        app.terminate()
        app.launchArguments = ["-AppleLanguages", "(en)", "-AppleLocale", "en_US", "--cuadrao-release-gates", "--cuadrao-saved-receipts-sample"]
        app.launch()
        let add = app.buttons["nav.add"]
        XCTAssertTrue(add.waitForExistence(timeout: 20))
        add.tap()
        app.buttons["add.tray.scanCamera"].tap()

        // Nothing is sent before the answer, and the answer names who reads it.
        XCTAssertTrue(app.buttons["receipt.journey.read"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label CONTAINS 'Google Gemini'")).firstMatch.exists)
        capture("receipt-journey-consent")
        app.buttons["receipt.journey.read"].tap()

        // The review shows what the reading found; confirming waits for the account that paid.
        let merchant = app.textFields["receipt.review.merchant"]
        XCTAssertTrue(merchant.waitForExistence(timeout: 20), "the reading settles into the review")
        XCTAssertTrue((merchant.value as? String ?? "").contains("La Sirena"))
        XCTAssertTrue((app.textFields["receipt.review.total"].value as? String ?? "").contains("250.50"))
        XCTAssertTrue(app.descendants(matching: .any)["receipt.review.items"].exists)
        let confirm = app.buttons["receipt.journey.confirm"]
        XCTAssertFalse(confirm.isEnabled, "no account chosen yet")
        capture("receipt-journey-review")
        app.buttons["receipt.review.account"].tap()
        app.buttons["Banreservas"].firstMatch.tap()
        XCTAssertTrue(confirm.isEnabled)
        confirm.tap()

        XCTAssertTrue(app.staticTexts["Expense saved"].waitForExistence(timeout: 10))
        capture("receipt-journey-saved")
        app.buttons["receipt.journey.done"].tap()
        XCTAssertTrue(app.descendants(matching: .any)["receipt.journey"].waitForNonExistence(timeout: 10))
    }

    func testReceiptJourneyLaterKeepsTheReceiptAndCancelSendsNothing() throws {
        try signIn()
        app.terminate()
        app.launchArguments = ["-AppleLanguages", "(es-419)", "-AppleLocale", "es_DO", "--cuadrao-release-gates", "--cuadrao-saved-receipts-sample"]
        app.launch()
        let add = app.buttons["nav.add"]
        XCTAssertTrue(add.waitForExistence(timeout: 20))
        add.tap()
        app.buttons["add.tray.chooseFile"].tap()
        let question = app.descendants(matching: .any)["receipt.journey.consent"]
        XCTAssertTrue(question.waitForExistence(timeout: 10))
        XCTAssertTrue(question.label.contains("¿Leemos tus recibos con IA?"))
        capture("receipt-journey-consent-es")
        app.buttons["receipt.journey.cancel"].tap()
        XCTAssertTrue(app.descendants(matching: .any)["receipt.journey"].waitForNonExistence(timeout: 10), "cancel closes without sending")

        add.tap()
        app.buttons["add.tray.chooseFile"].tap()
        app.buttons["receipt.journey.read"].tap()
        XCTAssertTrue(app.buttons["receipt.journey.later"].waitForExistence(timeout: 10))
        app.buttons["receipt.journey.later"].tap()
        XCTAssertTrue(app.descendants(matching: .any)["receipt.journey"].waitForNonExistence(timeout: 10), "Después keeps the receipt for later")
    }

    /// Against a real API (`--cuadrao-synthetic-receipt` draws a known receipt): the reading fills the review, the
    /// person picks the account, the expense is recorded once, and the movement shows its receipt.
    func testStagingReceiptJourneyRecordsTheExpenseWithItsReceipt() throws {
        try signIn()
        app.terminate()
        app.launchArguments = ["-AppleLanguages", "(en)", "-AppleLocale", "en_US", "--cuadrao-release-gates", "--cuadrao-saved-receipts", "--cuadrao-synthetic-receipt"]
        app.launch()
        let add = app.buttons["nav.add"]
        XCTAssertTrue(add.waitForExistence(timeout: 30))
        add.tap()
        app.buttons["add.tray.scanCamera"].tap()
        XCTAssertTrue(app.buttons["receipt.journey.read"].waitForExistence(timeout: 10))
        capture("staging-receipt-consent")
        app.buttons["receipt.journey.read"].tap()

        let merchant = app.textFields["receipt.review.merchant"]
        let failed = app.descendants(matching: .any)["receipt.journey.failed"]
        let still = app.descendants(matching: .any)["receipt.journey.still"]
        let settled = NSPredicate { _, _ in merchant.exists || failed.exists || still.exists }
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: settled, object: nil)], timeout: 150), .completed)
        capture("staging-receipt-after-reading")
        XCTAssertTrue(merchant.exists, failed.exists ? "reading failed: \(failed.label)" : "still reading after the wait")
        let total = app.textFields["receipt.review.total"].value as? String ?? ""
        XCTAssertTrue(total.contains("250.50"), total)

        app.buttons["receipt.review.account"].tap()
        // The menu lists "Choose the account that paid" first, then the accounts that can pay; take the first account.
        let firstAccount = app.collectionViews.buttons.element(boundBy: 1)
        XCTAssertTrue(firstAccount.waitForExistence(timeout: 5), "an open DOP account can pay")
        firstAccount.tap()
        let confirm = app.buttons["receipt.journey.confirm"]
        XCTAssertTrue(confirm.isEnabled, "an account was chosen")
        capture("staging-receipt-review")
        confirm.tap()
        XCTAssertTrue(app.staticTexts["Expense saved"].waitForExistence(timeout: 60), "the expense is recorded")
        capture("staging-receipt-saved")
        app.buttons["receipt.journey.done"].tap()

        // The movement on Home carries its receipt.
        app.revealConnectedTabBar()
        app.buttons["tab.home"].tap()
        let row = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'home.activity.' AND label CONTAINS[c] 'sirena'")).firstMatch
        XCTAssertTrue(row.waitForExistence(timeout: 20), "the expense is on Home")
        openMovement(row)
        let view = app.buttons["activity.receipt"]
        for _ in 0..<4 where !(view.exists && view.isHittable) { app.swipeUp() }
        XCTAssertTrue(view.waitForExistence(timeout: 20), "the recorded movement shows its receipt")
        capture("staging-movement-receipt")
        view.tap()
        XCTAssertTrue(app.buttons["Done"].waitForExistence(timeout: 20), "the receipt opens from the movement")
        app.buttons["Done"].tap()
    }

    /// One receipt file against a real API (`TEST_RUNNER_RECEIPT_FILE`, staged where the app can read it). It stops at
    /// the review and records nothing. Failure messages name only the kind of outcome, never what the receipt says.
    func testStagingReceiptFileReadsIntoAReview() throws {
        let path = try XCTUnwrap(ProcessInfo.processInfo.environment["RECEIPT_FILE"], "set RECEIPT_FILE")
        let quiet = ProcessInfo.processInfo.environment["RECEIPT_PRIVATE"] == "1"
        try signIn()
        app.terminate()
        app.launchArguments = ["-AppleLanguages", "(en)", "-AppleLocale", "en_US", "--cuadrao-release-gates", "--cuadrao-saved-receipts",
                               "--cuadrao-receipt-file", path]
        app.launch()
        let add = app.buttons["nav.add"]
        XCTAssertTrue(add.waitForExistence(timeout: 30))
        add.tap()
        app.buttons["add.tray.chooseFile"].tap()
        XCTAssertTrue(app.buttons["receipt.journey.read"].waitForExistence(timeout: 15), "consent")
        app.buttons["receipt.journey.read"].tap()
        let merchant = app.textFields["receipt.review.merchant"]
        let failed = app.descendants(matching: .any)["receipt.journey.failed"]
        let still = app.descendants(matching: .any)["receipt.journey.still"]
        let settled = NSPredicate { _, _ in merchant.exists || failed.exists || still.exists }
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: settled, object: nil)], timeout: 180), .completed, "outcome: no answer")
        if !quiet { capture("file-receipt-outcome") }
        XCTAssertFalse(failed.exists, "outcome: failed")
        XCTAssertFalse(still.exists, "outcome: still reading")
        let total = app.textFields["receipt.review.total"].value as? String ?? ""
        let date = app.descendants(matching: .any)["receipt.review.date"].label
        XCTAssertFalse((merchant.value as? String ?? "").isEmpty, "outcome: no merchant")
        XCTAssertFalse(date.contains("Unknown"), "outcome: no date")
        XCTAssertFalse(total.contains("Unknown"), "outcome: no total")
        print("RECEIPT_TOTAL_FOR_SYNTHETIC_CHECK " + (quiet ? "withheld" : total))
        app.buttons["receipt.journey.later"].tap()
    }
}
