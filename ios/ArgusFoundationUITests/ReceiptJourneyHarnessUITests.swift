import XCTest

/// The receipt journey's screens through `--receipt-journey-harness`: the sample server and a synthetic session,
/// no sign-in. The signed-in entry points are covered by ReceiptJourneyUITests when a synthetic API is available.
final class ReceiptJourneyHarnessUITests: XCTestCase {
    private let app = XCUIApplication()

    private func launch(_ language: String = "en") {
        continueAfterFailure = false
        let locale = language == "es" ? ["-AppleLanguages", "(es-419)", "-AppleLocale", "es_DO"] : ["-AppleLanguages", "(en)", "-AppleLocale", "en_US"]
        app.launchArguments = locale + ["--receipt-journey-harness"]
        app.launch()
    }

    private func capture(_ name: String) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }

    private func readUntilReview() {
        XCTAssertTrue(app.buttons["receipt.journey.read"].waitForExistence(timeout: 10))
        app.buttons["receipt.journey.read"].tap()
        XCTAssertTrue(app.descendants(matching: .any)["receipt.review.merchant"].waitForExistence(timeout: 15), "the reading opens the review")
    }

    func testConsentReadReviewChooseAccountAndConfirmSavesTheExpense() {
        launch()
        app.buttons["harness.receipt"].tap()
        XCTAssertTrue(app.staticTexts["Should we read this receipt?"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label CONTAINS 'Google Gemini'")).firstMatch.exists, "names who reads it")
        capture("receipt-journey-consent")
        readUntilReview()
        XCTAssertTrue(app.descendants(matching: .any)["receipt.review.merchant"].label.contains("La Sirena"))
        XCTAssertTrue(app.descendants(matching: .any)["receipt.review.total"].label.contains("250.50"))
        XCTAssertTrue(app.descendants(matching: .any)["receipt.review.items"].exists, "receipt items are shown as detail")
        let confirm = app.buttons["receipt.journey.confirm"]
        XCTAssertFalse(confirm.isEnabled, "the account that paid comes first")
        capture("receipt-journey-review")
        app.buttons["receipt.review.account"].tap()
        XCTAssertTrue(app.buttons["Banreservas"].firstMatch.waitForExistence(timeout: 5))
        app.buttons["Banreservas"].firstMatch.tap()
        XCTAssertTrue(confirm.isEnabled)
        confirm.tap()
        XCTAssertTrue(app.staticTexts["Expense saved"].waitForExistence(timeout: 10))
        capture("receipt-journey-saved")
        app.buttons["receipt.journey.done"].tap()
        XCTAssertTrue(app.staticTexts["recorded 250.50"].waitForExistence(timeout: 10))
    }

    func testCorrectingTheDetailsChangesWhatIsShown() {
        launch()
        app.buttons["harness.receipt"].tap()
        readUntilReview()
        app.descendants(matching: .any)["receipt.review.correct"].firstMatch.tap()
        let merchant = app.textFields["receipt.review.merchant.edit"]
        XCTAssertTrue(merchant.waitForExistence(timeout: 5))
        merchant.tap()
        merchant.typeText(" Naco")
        XCTAssertTrue(app.descendants(matching: .any)["receipt.review.merchant"].label.contains("La Sirena Naco"))
        capture("receipt-journey-correct")
    }

    func testSaveOnlyKeepsTheFileWithoutReading() {
        launch()
        app.buttons["harness.receipt"].tap()
        XCTAssertTrue(app.buttons["receipt.journey.saveOnly"].waitForExistence(timeout: 10))
        app.buttons["receipt.journey.saveOnly"].tap()
        XCTAssertTrue(app.staticTexts["Receipt saved"].waitForExistence(timeout: 10))
        app.buttons["receipt.journey.done"].tap()
        XCTAssertTrue(app.staticTexts["saved only"].waitForExistence(timeout: 10))
    }

    func testAnAlreadyRecordedPurchaseTakesTheReceipt() {
        launch()
        app.buttons["harness.duplicate"].tap()
        readUntilReview()
        let link = app.buttons["receipt.review.link"]
        for _ in 0..<4 where !link.isHittable { app.swipeUp() }
        link.tap()
        XCTAssertTrue(app.staticTexts["Receipt added to the movement"].waitForExistence(timeout: 10))
        capture("receipt-journey-linked")
    }

    func testSpanishConsentAndLaterKeepsTheReceipt() {
        launch("es")
        app.buttons["harness.receipt"].tap()
        XCTAssertTrue(app.staticTexts["¿Leemos este recibo?"].waitForExistence(timeout: 10))
        capture("receipt-journey-consent-es")
        app.buttons["receipt.journey.read"].tap()
        XCTAssertTrue(app.buttons["receipt.journey.later"].waitForExistence(timeout: 10))
        app.buttons["receipt.journey.later"].tap()
        XCTAssertTrue(app.descendants(matching: .any)["receipt.journey"].waitForNonExistence(timeout: 10))
    }

    func testTwoReceiptsShareOneAnswerAndAreReviewedInTurn() {
        launch()
        app.buttons["harness.two"].tap()
        readUntilReview()
        app.buttons["receipt.review.account"].tap()
        app.buttons["Banreservas"].firstMatch.tap()
        app.buttons["receipt.journey.confirm"].tap()
        XCTAssertTrue(app.staticTexts["Expense saved"].waitForExistence(timeout: 10))
        let next = app.buttons["receipt.journey.next"]
        XCTAssertTrue(next.exists, "the second receipt waits its turn")
        capture("receipt-journey-next")
        next.tap()
        XCTAssertTrue(app.descendants(matching: .any)["receipt.review.merchant"].waitForExistence(timeout: 15), "the second review opens")
        XCTAssertFalse(app.buttons["receipt.journey.read"].exists, "no second consent question")
    }
}
