import XCTest

/// The receipt journey's screens through `--receipt-journey-harness`: the sample server and a synthetic session,
/// no sign-in. The signed-in entry points are covered by ReceiptJourneyUITests when a synthetic API is available.
final class ReceiptJourneyHarnessUITests: XCTestCase {
    private let app = XCUIApplication()

    private func launch(_ language: String = "en", allowed: Bool = false, dark: Bool = false, slow: Bool = false) {
        continueAfterFailure = false
        let locale = language == "es" ? ["-AppleLanguages", "(es-419)", "-AppleLocale", "es_DO"] : ["-AppleLanguages", "(en)", "-AppleLocale", "en_US"]
        app.launchArguments = locale + ["--receipt-journey-harness", "-appearancePreference", dark ? "dark" : "light"]
            + (allowed ? ["--receipt-reading-allowed"] : []) + (slow ? ["--receipt-slow-reading"] : [])
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
        XCTAssertTrue(app.descendants(matching: .any)["receipt.journey.consent"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label CONTAINS 'Google Gemini'")).firstMatch.exists, "names who reads it")
        XCTAssertTrue(app.buttons["receipt.journey.saveOnly"].exists, "two choices only")
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
        XCTAssertTrue(app.descendants(matching: .any)["receipt.journey.consent"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH 'Google Gemini lee la foto'")).firstMatch.exists)
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

    func testAfterTheFirstYesEachReceiptOffersOnlyReadAndSaveOnly() {
        launch(allowed: true)
        app.buttons["harness.receipt"].tap()
        XCTAssertTrue(app.descendants(matching: .any)["receipt.journey.choice"].waitForExistence(timeout: 10))
        XCTAssertFalse(app.descendants(matching: .any)["receipt.journey.disclosure"].exists, "no long text after the first answer")
        XCTAssertTrue(app.buttons["receipt.journey.read"].exists)
        XCTAssertTrue(app.buttons["receipt.journey.saveOnly"].exists)
        capture("receipt-choice-en")
        readUntilReview()
    }

    func testUnreadableReceiptSaysSoAndOffersAnotherReading() {
        launch("es")
        app.buttons["harness.unreadable"].tap()
        app.buttons["receipt.journey.read"].tap()
        XCTAssertTrue(app.descendants(matching: .any)["receipt.journey.failed"].waitForExistence(timeout: 15))
        XCTAssertTrue(app.buttons["receipt.journey.readAgain"].exists)
        capture("receipt-unreadable-es")
    }

    func testOfflineKeepsTheReceiptAndOffersToTryAgain() {
        launch("es")
        app.buttons["harness.offline"].tap()
        app.buttons["receipt.journey.read"].tap()
        let failed = app.descendants(matching: .any)["receipt.journey.failed"]
        XCTAssertTrue(failed.waitForExistence(timeout: 10))
        XCTAssertTrue(failed.label.contains("Sin conexión"))
        XCTAssertTrue(app.buttons["receipt.journey.retry"].exists)
        capture("receipt-offline-es")
    }

    /// The screens the founder reviews, Spanish first, light and dark: first question, choice, reading, review.
    func testDesignScreensSpanishFirstLightAndDark() {
        for (language, dark) in [("es", false), ("es", true), ("en", false), ("en", true)] {
            let tag = language + (dark ? "-dark" : "-light")
            launch(language, dark: dark, slow: true)
            app.buttons["harness.receipt"].tap()
            XCTAssertTrue(app.descendants(matching: .any)["receipt.journey.consent"].waitForExistence(timeout: 10))
            capture("receipt-first-question-" + tag)
            app.buttons["receipt.journey.read"].tap()
            XCTAssertTrue(app.descendants(matching: .any)["receipt.journey.progress"].waitForExistence(timeout: 10))
            capture("receipt-reading-" + tag)
            XCTAssertTrue(app.descendants(matching: .any)["receipt.review.merchant"].waitForExistence(timeout: 15))
            capture("receipt-review-" + tag)
            app.terminate()
            launch(language, allowed: true, dark: dark)
            app.buttons["harness.two"].tap()
            XCTAssertTrue(app.descendants(matching: .any)["receipt.journey.choice"].waitForExistence(timeout: 10))
            capture("receipt-choice-two-" + tag)
            app.buttons["receipt.journey.cancel"].tap()
            app.buttons["harness.offline"].tap()
            app.buttons["receipt.journey.read"].tap()
            XCTAssertTrue(app.descendants(matching: .any)["receipt.journey.failed"].waitForExistence(timeout: 10))
            capture("receipt-offline-" + tag)
            app.buttons["receipt.journey.later"].tap()
            app.buttons["harness.unreadable"].tap()
            app.buttons["receipt.journey.read"].tap()
            XCTAssertTrue(app.descendants(matching: .any)["receipt.journey.failed"].waitForExistence(timeout: 15))
            capture("receipt-unreadable-" + tag)
            app.terminate()
        }
    }
}
