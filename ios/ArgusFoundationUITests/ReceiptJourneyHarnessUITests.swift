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
        XCTAssertTrue(app.textFields["receipt.review.merchant"].waitForExistence(timeout: 15), "the reading opens the review")
    }

    func testConsentReadReviewChooseAccountAndConfirmSavesTheExpense() {
        launch()
        app.buttons["harness.receipt"].tap()
        XCTAssertTrue(app.descendants(matching: .any)["receipt.journey.consent"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label CONTAINS 'Google Gemini'")).firstMatch.exists, "names who reads it")
        XCTAssertTrue(app.buttons["receipt.journey.saveOnly"].exists, "two choices only")
        capture("receipt-journey-consent")
        readUntilReview()
        XCTAssertEqual(app.textFields["receipt.review.merchant"].value as? String, "La Sirena")
        XCTAssertTrue((app.textFields["receipt.review.total"].value as? String ?? "").contains("250.50"))
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

    func testFieldsAreEditedWhereTheyAreShown() {
        launch()
        app.buttons["harness.receipt"].tap()
        readUntilReview()
        XCTAssertFalse(app.descendants(matching: .any)["receipt.review.correct"].exists, "no separate correction block")
        let merchant = app.textFields["receipt.review.merchant"]
        merchant.coordinate(withNormalizedOffset: CGVector(dx: 0.97, dy: 0.5)).tap()
        merchant.typeText(" Naco")
        XCTAssertEqual(merchant.value as? String, "La Sirena Naco")
        capture("receipt-journey-inline-edit")
    }

    func testAReceiptWithoutADateSaysSoUntilOneIsChosen() {
        launch("es")
        app.buttons["harness.undated"].tap()
        readUntilReview()
        let missing = app.buttons["receipt.review.date.missing"]
        XCTAssertTrue(missing.waitForExistence(timeout: 5))
        XCTAssertTrue(missing.label.contains("Sin dato"), missing.label)
        XCTAssertFalse(app.descendants(matching: .any)["receipt.review.date"].exists, "no date is shown that the reading did not find")
        app.buttons["receipt.review.account"].tap()
        app.buttons["Banreservas"].firstMatch.tap()
        XCTAssertFalse(app.buttons["receipt.journey.confirm"].isEnabled, "the date comes first")
        capture("receipt-review-no-date-es")
        missing.tap()
        app.buttons["receipt.review.date.use"].tap()
        XCTAssertTrue(app.descendants(matching: .any)["receipt.review.date"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.buttons["receipt.journey.confirm"].isEnabled)
    }

    func testADuplicateIsAskedOnTopWithAddToThatMovementFirst() {
        launch("es")
        app.buttons["harness.duplicate"].tap()
        readUntilReview()
        let banner = app.descendants(matching: .any)["receipt.review.duplicate"]
        XCTAssertTrue(banner.waitForExistence(timeout: 5))
        let merchant = app.textFields["receipt.review.merchant"]
        XCTAssertLessThan(banner.frame.minY, merchant.frame.minY, "the banner sits above the fields")
        let add = app.buttons["receipt.review.link"], other = app.buttons["receipt.review.newPurchase"]
        XCTAssertEqual(add.label, "Añadir a ese movimiento")
        XCTAssertTrue(add.frame.minY < other.frame.minY || add.frame.minX < other.frame.minX, "adding to the movement comes first")
        capture("receipt-duplicate-banner-es")
        other.tap()
        XCTAssertFalse(banner.exists, "a new expense keeps the review without the banner")
    }

    func testAnUnreadableReceiptCanBeWrittenByHand() {
        launch("es")
        app.buttons["harness.unreadable"].tap()
        app.buttons["receipt.journey.read"].tap()
        let byHand = app.buttons["receipt.journey.byHand"]
        XCTAssertTrue(byHand.waitForExistence(timeout: 15))
        XCTAssertEqual(byHand.label, "Escribirlo a mano")
        capture("receipt-write-by-hand-es")
        byHand.tap()
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH 'by hand '")).firstMatch.waitForExistence(timeout: 10),
                      "the receipt is handed to the movement sheet")
        XCTAssertTrue(app.descendants(matching: .any)["receipt.journey"].waitForNonExistence(timeout: 10))
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
        XCTAssertTrue(link.isHittable, "the duplicate question is on top, no scrolling")
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
        XCTAssertTrue(app.textFields["receipt.review.merchant"].waitForExistence(timeout: 15), "the second review opens")
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

    func testReviewAtTheLargestTextSize() {
        app.launchArguments = ["-AppleLanguages", "(es-419)", "-AppleLocale", "es_DO", "--receipt-journey-harness",
                               "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"]
        continueAfterFailure = false
        app.launch()
        app.buttons["harness.duplicate"].tap()
        readUntilReview()
        let banner = app.descendants(matching: .any)["receipt.review.duplicate"]
        XCTAssertTrue(banner.exists)
        XCTAssertTrue(banner.staticTexts["¿Ya anotaste este gasto?"].exists, "the question is the banner's title")
        XCTAssertFalse(banner.staticTexts.matching(NSPredicate(format: "label CONTAINS 'DOP'")).firstMatch.exists,
                       "the banner states no amount the server did not return")
        let add = app.buttons["receipt.review.link"], other = app.buttons["receipt.review.newPurchase"]
        XCTAssertEqual(add.label, "Añadir a ese movimiento")
        XCTAssertLessThan(add.frame.minY, other.frame.minY, "at the largest text the two choices stack, adding first")
        XCTAssertLessThan(banner.frame.minY, app.textFields["receipt.review.merchant"].frame.minY, "the banner sits above the fields")
        capture("receipt-review-duplicate-xxxl-es")
        app.swipeUp()
        capture("receipt-review-xxxl-es-lower")
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
            XCTAssertTrue(app.textFields["receipt.review.merchant"].waitForExistence(timeout: 15))
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
