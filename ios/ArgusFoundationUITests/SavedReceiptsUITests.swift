import XCTest

/// Saved receipts with the debug sample data (`--cuadrao-saved-receipts-sample`): the + menu gains its file rows,
/// saving answers in the approved words, and the list opens, shows and deletes a receipt.
extension FinancialLoopUITests {
    func testSavedReceiptsSaveAlreadySavedViewAndDelete() throws {
        try signIn()
        app.terminate()
        app.launchArguments = ["-AppleLanguages", "(en)", "-AppleLocale", "en_US", "--cuadrao-release-gates", "--cuadrao-saved-receipts-sample"]
        app.launch()
        XCTAssertTrue(app.buttons["header.profile"].waitForExistence(timeout: 20))
        app.buttons["header.profile"].tap()

        // The + menu shows the three file rows below a divider once receipts are on.
        let add = app.buttons["nav.add"]
        XCTAssertTrue(add.waitForExistence(timeout: 10))
        add.tap()
        for row in ["account", "transaction", "plan", "scanCamera", "choosePhoto", "chooseFile"] {
            XCTAssertTrue(app.buttons["add.tray." + row].waitForExistence(timeout: 5), row)
        }
        XCTAssertLessThan(app.buttons["add.tray.chooseFile"].frame.maxY, add.frame.minY, "the taller card still stops above the bar")
        capture("saved-receipts-add-menu-with-file-rows")

        // A photo first asks whether it may be read. Save only answers "Receipt saved"; the same photo again says it was
        // already saved.
        app.buttons["add.tray.choosePhoto"].tap()
        XCTAssertTrue(app.buttons["receipt.journey.saveOnly"].waitForExistence(timeout: 10), "consent comes first")
        app.buttons["receipt.journey.saveOnly"].tap()
        XCTAssertTrue(app.staticTexts["Receipt saved"].waitForExistence(timeout: 10), "saved")
        capture("saved-receipts-saved")
        app.buttons["receipt.journey.done"].tap()
        add.tap()
        app.buttons["add.tray.choosePhoto"].tap()
        XCTAssertTrue(app.buttons["receipt.journey.saveOnly"].waitForExistence(timeout: 10))
        app.buttons["receipt.journey.saveOnly"].tap()
        XCTAssertTrue(app.staticTexts["You already had this receipt saved."].waitForExistence(timeout: 10), "already saved")
        app.buttons["receipt.journey.done"].tap()

        // The Profile row opens the list, which holds the two samples and the new photo.
        let privacy = app.buttons["Data and privacy"]
        for _ in 0..<6 where !(privacy.exists && privacy.isHittable) { app.swipeUp() }
        privacy.tap()
        let row = app.buttons["Saved receipts"]
        XCTAssertTrue(row.waitForExistence(timeout: 10))
        for _ in 0..<4 where !row.isHittable { app.swipeUp() }
        XCTAssertTrue(row.isHittable, "Profile lists Saved receipts when receipts are on")
        row.tap()
        XCTAssertTrue(app.descendants(matching: .any)["saved.receipts.list"].waitForExistence(timeout: 10))
        for id in ["sample-1", "sample-2", "sample-3"] {
            XCTAssertTrue(app.buttons["saved.receipts.row." + id].waitForExistence(timeout: 5), id)
        }
        capture("saved-receipts-list")

        // Viewing opens the file; Done closes it.
        app.buttons["saved.receipts.row.sample-1"].tap()
        XCTAssertTrue(app.buttons["Done"].waitForExistence(timeout: 10), "the viewer opened")
        capture("saved-receipts-viewer")
        app.buttons["Done"].tap()

        // Deleting asks first, says what happens, and removes only that receipt.
        app.buttons["saved.receipts.row.sample-2"].swipeLeft()
        app.buttons["Delete"].firstMatch.tap()
        XCTAssertTrue(app.staticTexts["It is deleted from your account and our servers. Your activity does not change."].waitForExistence(timeout: 5))
        capture("saved-receipts-delete-confirmation")
        app.buttons["saved.receipts.delete.confirm"].firstMatch.tap()
        XCTAssertTrue(app.buttons["saved.receipts.row.sample-2"].waitForNonExistence(timeout: 10), "the receipt is gone")
        XCTAssertTrue(app.buttons["saved.receipts.row.sample-1"].exists && app.buttons["saved.receipts.row.sample-3"].exists)
    }

    /// Without the switch, a Release-like launch offers no file rows and no Saved receipts row.
    func testSavedReceiptsStayOffByDefault() throws {
        try signIn()
        app.terminate()
        app.launchArguments = ["-AppleLanguages", "(en)", "-AppleLocale", "en_US", "--cuadrao-release-gates"]
        app.launch()
        XCTAssertTrue(app.buttons["nav.add"].waitForExistence(timeout: 20))
        app.buttons["nav.add"].tap()
        XCTAssertTrue(app.buttons["add.tray.account"].waitForExistence(timeout: 5))
        for row in ["scanCamera", "choosePhoto", "chooseFile"] { XCTAssertFalse(app.buttons["add.tray." + row].exists, row) }
        app.buttons["nav.add"].tap()
        app.buttons["header.profile"].tap()
        let privacy = app.buttons["Data and privacy"]
        for _ in 0..<6 where !(privacy.exists && privacy.isHittable) { app.swipeUp() }
        privacy.tap()
        XCTAssertTrue(app.navigationBars.firstMatch.waitForExistence(timeout: 10))
        XCTAssertFalse(app.buttons["Saved receipts"].exists)
        XCTAssertFalse(app.buttons["Files"].exists)
    }
}
