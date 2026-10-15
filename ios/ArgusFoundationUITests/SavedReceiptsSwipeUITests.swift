import XCTest

/// The connected saved-receipts list on the sample files (`--saved-receipts-harness`): its delete swipe is red.
final class SavedReceiptsSwipeUITests: XCTestCase {
    func testTheDeleteSwipeOnASavedReceiptIsRed() {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["--saved-receipts-harness", "-AppleLanguages", "(en)", "-AppleLocale", "en_US", "-appearancePreference", "light"]
        app.launch()
        let row = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'saved.receipts.row.'")).firstMatch
        XCTAssertTrue(row.waitForExistence(timeout: 20), "the sample receipts are listed")
        row.swipeLeft()
        let delete = app.buttons["Delete"].firstMatch
        XCTAssertTrue(delete.waitForExistence(timeout: 5))
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = "saved-receipt-delete-swipe"
        attachment.lifetime = .keepAlways
        add(attachment)
        let (red, green) = app.colorCounts(in: delete.frame)
        XCTAssertGreaterThan(red, 20, "the delete action is red")
        XCTAssertEqual(green, 0, "no brand-green pixels in the delete action")
    }
}
