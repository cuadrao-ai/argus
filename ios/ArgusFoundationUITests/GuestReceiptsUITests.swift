import XCTest

/// Receipts in the on-device book (`--cuadrao-saved-receipts-sample` stands in for the camera, photos and files):
/// kept on this iPhone, attached to a movement by hand, viewed and removed. Nothing goes to a server.
extension FinancialLoopUITests {
    private func guestReceiptAccount() {
        tapVisible(app.buttons["accounts.add"])
        XCTAssertTrue(app.buttons["guest.account.type.cash"].waitForExistence(timeout: 10))
        app.buttons["guest.account.type.cash"].tap()
        app.textFields["guest.account.name"].tap()
        app.textFields["guest.account.name"].typeText("Efectivo")
        dismissGuestKeyboard()
        app.textFields["guest.account.amount"].tap()
        app.textFields["guest.account.amount"].typeText("1000")
        dismissGuestKeyboard()
        app.buttons["guest.account.save"].tap()
        XCTAssertTrue(app.buttons["guest.account.save"].waitForNonExistence(timeout: 10))
    }

    private func guestReceiptExpense(_ amount: String, note: String) {
        app.buttons["nav.add"].tap()
        XCTAssertTrue(app.buttons["add.tray.transaction"].waitForExistence(timeout: 5))
        app.buttons["add.tray.transaction"].tap()
        XCTAssertTrue(app.buttons["guest.movement.save"].waitForExistence(timeout: 10))
        app.textFields["guest.movement.amount"].tap()
        app.textFields["guest.movement.amount"].typeText(amount)
        dismissGuestKeyboard()
        app.textFields["guest.movement.note"].tap()
        app.textFields["guest.movement.note"].typeText(note)
        dismissGuestKeyboard()
        app.buttons["guest.movement.save"].tap()
        XCTAssertTrue(app.buttons["guest.movement.save"].waitForNonExistence(timeout: 10))
    }

    private func guestMovementRow(_ text: String) -> XCUIElement {
        app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'guest.movement.row.' AND label CONTAINS %@", text)).firstMatch
    }

    func testGuestReceiptIsKeptOnTheIPhoneAttachedViewedAndRemoved() throws {
        launchSignedOut(arguments: ["--cuadrao-guest-book", "--cuadrao-saved-receipts-sample"])
        enterGuestBook()
        guestReceiptAccount()
        guestReceiptExpense("250", note: "La Sirena")

        // The + tray offers the three receipt rows; a photo is kept here and offered to a movement.
        app.buttons["nav.add"].tap()
        for row in ["scanCamera", "choosePhoto", "chooseFile"] {
            XCTAssertTrue(app.buttons["add.tray." + row].waitForExistence(timeout: 5), row)
        }
        app.buttons["add.tray.choosePhoto"].tap()
        XCTAssertTrue(app.staticTexts["Receipt saved on this iPhone"].waitForExistence(timeout: 10))
        capture("guest-receipt-saved")
        let choice = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'guest.receipt.movement.' AND label CONTAINS 'La Sirena'")).firstMatch
        XCTAssertTrue(choice.waitForExistence(timeout: 5))
        choice.tap()
        XCTAssertTrue(app.staticTexts["Receipt saved on this iPhone"].waitForNonExistence(timeout: 10))

        // The movement shows its receipt, which opens and can be removed.
        tapVisible(guestMovementRow("La Sirena"))
        XCTAssertTrue(app.descendants(matching: .any)["guest.movement.detail"].waitForExistence(timeout: 10))
        let view = app.buttons["guest.movement.receipt.view"]
        XCTAssertTrue(view.waitForExistence(timeout: 5), "the attached receipt is on the movement")
        capture("guest-movement-with-receipt")
        view.tap()
        XCTAssertTrue(app.buttons["Done"].waitForExistence(timeout: 10), "the receipt opens")
        app.buttons["Done"].tap()
        app.buttons["guest.movement.receipt.remove"].tap()
        XCTAssertTrue(app.buttons["guest.movement.receipt.attach"].waitForExistence(timeout: 5))

        // Attaching from the movement offers the saved receipt again.
        app.buttons["guest.movement.receipt.attach"].tap()
        let saved = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'guest.receipt.choice.'")).firstMatch
        XCTAssertTrue(saved.waitForExistence(timeout: 5))
        capture("guest-attach-receipt")
        saved.tap()
        XCTAssertTrue(app.buttons["guest.movement.receipt.view"].waitForExistence(timeout: 10))
    }

    func testGuestReceiptLaterKeepsItUnattachedInSpanish() throws {
        launchSignedOut(arguments: ["--cuadrao-guest-book", "--cuadrao-saved-receipts-sample"], language: "es-419")
        enterGuestBook()
        app.buttons["nav.add"].tap()
        XCTAssertTrue(app.buttons["add.tray.chooseFile"].waitForExistence(timeout: 5), "receipts do not need an account")
        app.buttons["add.tray.chooseFile"].tap()
        XCTAssertTrue(app.staticTexts["Recibo guardado en este iPhone"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.staticTexts["Aún no tienes movimientos."].exists)
        capture("guest-receipt-saved-es")
        app.buttons["guest.receipt.later"].tap()
        XCTAssertTrue(app.staticTexts["Recibo guardado en este iPhone"].waitForNonExistence(timeout: 10))
    }
}
