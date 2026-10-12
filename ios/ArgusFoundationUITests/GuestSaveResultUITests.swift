import XCTest

/// A save shows its result: the sheet closes, a short notice names what happened, and "Ver" opens the new row.
extension FinancialLoopUITests {
    func testGuestSaveShowsANoticeAndViewOpensTheNewMovement() throws {
        launchSignedOut(arguments: ["--cuadrao-guest-book"])
        enterGuestBook()
        app.buttons["nav.add"].tap()
        XCTAssertTrue(app.buttons["add.tray.account"].waitForExistence(timeout: 5))
        app.buttons["add.tray.account"].tap()
        XCTAssertTrue(app.buttons["guest.account.type.checking"].waitForExistence(timeout: 10))
        app.buttons["guest.account.type.checking"].tap()
        app.textFields["guest.account.name"].tap()
        app.textFields["guest.account.name"].typeText("Main")
        dismissGuestKeyboard()
        app.buttons["guest.account.save"].tap()
        XCTAssertTrue(app.buttons["guest.account.save"].waitForNonExistence(timeout: 10))
        XCTAssertTrue(app.staticTexts["Account added"].waitForExistence(timeout: 5), "a saved account is named")

        app.buttons["nav.add"].tap()
        XCTAssertTrue(app.buttons["add.tray.transaction"].waitForExistence(timeout: 5))
        app.buttons["add.tray.transaction"].tap()
        XCTAssertTrue(app.buttons["guest.movement.save"].waitForExistence(timeout: 10))
        app.textFields["guest.movement.amount"].tap()
        app.textFields["guest.movement.amount"].typeText("850")
        dismissGuestKeyboard()
        app.buttons["guest.movement.save"].tap()
        XCTAssertTrue(app.buttons["guest.movement.save"].waitForNonExistence(timeout: 10), "the sheet closes")
        let notice = app.staticTexts["Transaction saved"]
        XCTAssertTrue(notice.waitForExistence(timeout: 5), "the save is named")
        XCTAssertFalse(app.buttons["guest.undo"].exists, "a create offers View, not Undo")
        let image = XCTAttachment(screenshot: app.screenshot()); image.name = "guest-save-toast-light-en"; image.lifetime = .keepAlways; add(image)
        app.buttons["toast.view"].tap()
        XCTAssertTrue(app.descendants(matching: .any)["guest.movement.detail"].waitForExistence(timeout: 10), "View opens the new movement")
        XCTAssertTrue(notice.waitForNonExistence(timeout: 5), "the notice leaves once used")
    }
}
