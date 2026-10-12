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
        let merchant = app.descendants(matching: .any)["receipt.review.merchant"]
        XCTAssertTrue(merchant.waitForExistence(timeout: 20), "the reading settles into the review")
        XCTAssertTrue(merchant.label.contains("La Sirena"))
        XCTAssertTrue(app.descendants(matching: .any)["receipt.review.total"].label.contains("250.50"))
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
        XCTAssertTrue(app.staticTexts["¿Leemos este recibo?"].waitForExistence(timeout: 10))
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
}
