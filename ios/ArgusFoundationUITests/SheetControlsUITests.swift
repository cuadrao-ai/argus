import XCTest

/// Sheets close and confirm the same way everywhere: plain-text Cancel on the left, a check on the right only
/// when the sheet has no button of its own, plain-text Done on sheets that only show something.
extension FinancialLoopUITests {
    func testSheetsCancelAndConfirmTheSameWay() throws {
        try signIn()
        app.terminate()
        app.launchArguments = ["-AppleLanguages", "(en)", "-AppleLocale", "en_US", "--cuadrao-release-gates"]
        app.launch()
        XCTAssertTrue(app.buttons["header.profile"].waitForExistence(timeout: 20))

        // Edit profile has no button of its own: Cancel and a check.
        app.buttons["header.profile"].tap()
        app.staticTexts["Edit profile"].firstMatch.tap()
        let cancel = app.buttons["cuadrao.profile.cancel"]
        XCTAssertTrue(cancel.waitForExistence(timeout: 10), "profile Cancel")
        XCTAssertEqual(cancel.label, "Cancel")
        let save = app.buttons["cuadrao.profile.save"]
        XCTAssertTrue(save.exists)
        XCTAssertEqual(save.label, "Save")
        XCTAssertLessThan(cancel.frame.midX, save.frame.midX, "Cancel is on the left, the check on the right")
        XCTAssertEqual(cancel.frame.midY, save.frame.midY, accuracy: 4, "both sit on the same bar")
        capture("sheet-controls-edit-profile")
        cancel.tap()

        // A sheet with its own button has Cancel only: nothing else sits in the navigation bar.
        app.buttons["nav.add"].tap()
        app.buttons["add.tray.account"].tap()
        let accountCancel = app.buttons["Cancel"].firstMatch
        XCTAssertTrue(accountCancel.waitForExistence(timeout: 10), "account sheet Cancel")
        let barButtons = app.navigationBars.firstMatch.buttons.allElementsBoundByIndex
        XCTAssertFalse(barButtons.contains { $0.frame.midX > app.frame.width / 2 }, "no second confirm beside the sheet's own button")
        capture("sheet-controls-account-sheet")

        // The amount keypad has no Done pill; tapping away closes it.
        app.buttons.matching(NSPredicate(format: "label == 'Cash'")).firstMatch.tap()
        let amount = app.textFields.allElementsBoundByIndex.last
        XCTAssertNotNil(amount)
        amount?.tap()
        amount?.typeText("12")
        XCTAssertTrue(app.keyboards.firstMatch.waitForExistence(timeout: 5))
        let pad = app.keyboards.firstMatch.frame.minY
        let pill = app.buttons.allElementsBoundByIndex.filter { ["Done", "Listo"].contains($0.label) && $0.frame.maxY <= pad + 1 && $0.frame.maxY > pad - 120 }
        XCTAssertTrue(pill.isEmpty, "no Done pill over the amount keypad: \(pill.map(\.debugDescription))")
        capture("sheet-controls-amount-keypad")
        app.navigationBars.firstMatch.staticTexts.firstMatch.tap()
        XCTAssertTrue(app.keyboards.firstMatch.waitForNonExistence(timeout: 5), "tapping away closes the keypad")
        accountCancel.tap()

        // Typing in a field never shows a floating Done pill above the keyboard or beside the Create button.
        app.buttons["nav.add"].tap()
        app.buttons["add.tray.plan"].tap()
        let name = app.textFields.matching(NSPredicate(format: "identifier IN {'goal.name', 'budget.name', 'debt.name', 'plan-name'}")).firstMatch
        XCTAssertTrue(name.waitForExistence(timeout: 10), "plan name field")
        name.tap()
        name.typeText("Trip")
        XCTAssertTrue(app.keyboards.firstMatch.waitForExistence(timeout: 5))
        let keyboardTop = app.keyboards.firstMatch.frame.minY
        let aboveKeyboard = app.buttons.allElementsBoundByIndex.filter { ["Done", "Listo"].contains($0.label) && $0.frame.maxY <= keyboardTop + 1 && $0.frame.maxY > keyboardTop - 120 }
        XCTAssertTrue(aboveKeyboard.isEmpty, "no floating Done above the keyboard: \(aboveKeyboard.map(\.debugDescription))")
        capture("sheet-controls-plan-keyboard")
        name.typeText("\n")
        XCTAssertTrue(app.keyboards.firstMatch.waitForNonExistence(timeout: 5), "Return closes the keyboard")
        app.buttons["Cancel"].firstMatch.tap()
    }
}
