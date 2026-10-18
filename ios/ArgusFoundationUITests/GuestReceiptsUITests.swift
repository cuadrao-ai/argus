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

    func testGuestSearchFindsAReceiptAndOpensItsMovement() throws {
        launchSignedOut(arguments: ["--cuadrao-guest-book", "--cuadrao-saved-receipts-sample"])
        enterGuestBook()
        guestReceiptAccount()
        guestReceiptExpense("250", note: "Colmado")
        app.buttons["nav.add"].tap()
        app.buttons["add.tray.choosePhoto"].tap()
        let choice = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'guest.receipt.movement.' AND label CONTAINS 'Colmado'")).firstMatch
        XCTAssertTrue(choice.waitForExistence(timeout: 10))
        choice.tap()
        app.buttons["tab.search"].tap()
        let field = app.textFields["search.query"]
        XCTAssertTrue(field.waitForExistence(timeout: 10))
        field.tap()
        field.typeText("Foto")
        let hit = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'guest.search.receipt.'")).firstMatch
        XCTAssertTrue(hit.waitForExistence(timeout: 10), "the receipt is found by its name")
        capture("guest-search-receipt")
        hit.tap()
        XCTAssertTrue(app.descendants(matching: .any)["guest.movement.detail"].waitForExistence(timeout: 10), "an attached receipt opens its movement")
        XCTAssertTrue(app.buttons["guest.movement.receipt.view"].exists)
    }

    func testGuestProfileListsReceiptsToViewAttachRemoveAndDelete() throws {
        launchSignedOut(arguments: ["--cuadrao-guest-book", "--cuadrao-saved-receipts-sample"])
        enterGuestBook()
        guestReceiptAccount()
        guestReceiptExpense("250", note: "Colmado")
        app.buttons["nav.add"].tap()
        app.buttons["add.tray.chooseFile"].tap()
        XCTAssertTrue(app.buttons["guest.receipt.later"].waitForExistence(timeout: 10))
        app.buttons["guest.receipt.later"].tap()

        app.buttons["header.profile"].tap()
        let entry = app.buttons["guest.profile.receipts"]
        for _ in 0..<4 where !(entry.exists && entry.isHittable) { app.swipeUp() }
        entry.tap()
        let row = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'guest.receipts.row.'")).firstMatch
        XCTAssertTrue(row.waitForExistence(timeout: 10), "the saved receipt is listed")
        capture("guest-profile-receipts")

        row.press(forDuration: 1.0)
        app.buttons["Attach to a movement"].tap()
        let choice = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'guest.receipt.movement.' AND label CONTAINS 'Colmado'")).firstMatch
        XCTAssertTrue(choice.waitForExistence(timeout: 10))
        choice.tap()
        XCTAssertTrue(app.staticTexts["Attached to Colmado"].waitForExistence(timeout: 10), "the list shows where it is attached")

        row.press(forDuration: 1.0)
        app.buttons["Remove receipt"].tap()
        XCTAssertTrue(app.staticTexts["Attached to Colmado"].waitForNonExistence(timeout: 10), "removed from the movement, still listed")
        XCTAssertTrue(row.exists)

        row.swipeLeft()
        app.buttons["Delete"].firstMatch.tap()
        app.buttons["guest.receipts.delete.confirm"].firstMatch.tap()
        XCTAssertTrue(app.descendants(matching: .any)["guest.receipts.empty"].waitForExistence(timeout: 10), "deleted from the iPhone")
    }

    private func openGuestReceiptsPage() {
        app.buttons["header.profile"].tap()
        let entry = app.buttons["guest.profile.receipts"]
        for _ in 0..<4 where !(entry.exists && entry.isHittable) { app.swipeUp() }
        entry.tap()
    }

    /// Receipts' empty state is Home's: the illustration, a title and a line, and one add button with the three sources.
    func testReceiptsEmptyStateMatchesHomesAndAddsAReceipt() throws {
        launchSignedOut(arguments: ["--cuadrao-guest-book", "--cuadrao-saved-receipts-sample"])
        enterGuestBook()
        openGuestReceiptsPage()
        XCTAssertTrue(app.descendants(matching: .any)["guest.receipts.empty"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.staticTexts["No receipts yet."].exists)
        let add = app.buttons["guest.receipts.add"]
        XCTAssertTrue(add.exists)
        XCTAssertEqual(add.label, "Add a receipt")
        capture("guest-receipts-empty")
        add.tap()
        for source in ["scan", "photos", "file"] {
            XCTAssertTrue(app.buttons["guest.receipts.add." + source].firstMatch.waitForExistence(timeout: 5), source)
        }
        app.buttons["guest.receipts.add.photos"].firstMatch.tap()
        XCTAssertTrue(app.staticTexts["Receipt saved on this iPhone"].waitForExistence(timeout: 10), "the receipt is kept on this iPhone")
    }

    /// A destructive swipe is red, never the app's green.
    func testDeleteSwipeOnAReceiptIsRed() throws {
        launchSignedOut(arguments: ["--cuadrao-guest-book", "--cuadrao-saved-receipts-sample"])
        enterGuestBook()
        openGuestReceiptsPage()
        app.buttons["guest.receipts.add"].tap()
        app.buttons["guest.receipts.add.photos"].firstMatch.tap()
        XCTAssertTrue(app.buttons["guest.receipt.later"].waitForExistence(timeout: 10))
        app.buttons["guest.receipt.later"].tap()
        let row = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'guest.receipts.row.'")).firstMatch
        XCTAssertTrue(row.waitForExistence(timeout: 10))
        row.swipeLeft()
        let delete = app.buttons["Delete"].firstMatch
        XCTAssertTrue(delete.waitForExistence(timeout: 5))
        capture("guest-receipt-delete-swipe")
        let (red, green) = app.colorCounts(in: delete.frame)
        XCTAssertGreaterThan(red, 20, "the delete action is red")
        XCTAssertEqual(green, 0, "no brand-green pixels in the delete action")
    }
}
