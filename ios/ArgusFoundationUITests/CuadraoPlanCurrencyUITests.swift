import XCTest

final class CuadraoPlanCurrencyUITests: XCTestCase {
    func testPersonalEuroCreationAndLockEnglish() {
        continueAfterFailure = false
        let app = openPlan(english: true)
        app.buttons["plan-create"].tap()
        app.textFields["plan-name"].tap(); app.textFields["plan-name"].typeText("Summer in euros\n")
        reveal(app, app.buttons["plan-edit-currency"])
        app.buttons["plan-edit-currency"].tap(); app.buttons["EUR"].tap()
        replace(app.textFields["plan-target"], "1250000.50")
        capture(app, "amount-personal-focused-en")
        app.dismissKeyboard()
        replace(app.textFields["plan-monthly"], "750.25")
        app.dismissKeyboard()
        capture(app, "currency-personal-choice-en")
        app.buttons["plan-save"].tap()
        XCTAssertTrue(app.buttons["plan-detail-options"].waitForExistence(timeout: 3))
        XCTAssertTrue(app.staticTexts["EUR 0"].exists)
        app.buttons["plan-detail-options"].tap(); app.buttons["Edit plan"].tap()
        let fixed = app.descendants(matching: .any).matching(identifier: "plan-currency-fixed").firstMatch
        reveal(app, fixed)
        XCTAssertFalse(app.buttons["plan-edit-currency"].exists)
        XCTAssertTrue(fixed.label.contains("EUR"))
        XCTAssertEqual(number(app.textFields["plan-target"]), 1250000.50)
        XCTAssertEqual(number(app.textFields["plan-monthly"]), 750.25)
        capture(app, "currency-personal-fixed-en")
        app.buttons["plan-save"].tap()
        XCTAssertTrue(app.buttons["plan-detail-options"].waitForExistence(timeout: 3))
    }
    func testSharedDollarSplitAndRepaymentSpanish() {
        continueAfterFailure = false
        let app = openPlan()
        app.segmentedControls["plan-audience"].buttons["En grupo"].tap()
        app.buttons["plan-create"].tap()
        app.textFields["group-name"].tap(); app.textFields["group-name"].typeText("Viaje en dólares\n")
        app.buttons["plan-edit-currency"].tap(); app.buttons["USD"].tap()
        replace(app.textFields["group-estimate"], "48000")
        app.dismissKeyboard()
        capture(app, "currency-group-choice-es")
        reveal(app, app.buttons["group-save"]); app.buttons["group-save"].tap()
        XCTAssertTrue(app.buttons["group-people-open"].waitForExistence(timeout: 3))
        XCTAssertEqual(app.staticTexts["group-own-share"].label, "USD 0")
        app.buttons["group-people-open"].tap()
        app.buttons["group-invite"].tap()
        reveal(app, app.buttons["group-invite-preview"]); app.buttons["group-invite-preview"].tap()
        reveal(app, app.buttons["group-invite-accept"]); app.buttons["group-invite-accept"].tap()
        app.buttons["Cerrar"].tap()
        app.segmentedControls["group-sections"].buttons["Gastos"].tap()
        app.buttons["group-add-expense"].tap()
        app.textFields["group-expense-name"].tap(); app.textFields["group-expense-name"].typeText("Cena\n")
        replace(app.textFields["group-expense-amount"], "100")
        app.dismissKeyboard()
        XCTAssertTrue(app.descendants(matching: .any).matching(identifier: "plan-currency-inherited").firstMatch.label.contains("USD"))
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label == %@", "USD 50")).count == 2)
        capture(app, "currency-dollar-split-es")
        reveal(app, app.buttons["group-expense-save"]); app.buttons["group-expense-save"].tap()
        app.segmentedControls["group-sections"].buttons["El plan"].tap()
        XCTAssertEqual(app.staticTexts["group-own-share"].label, "USD 50")
        reveal(app, app.buttons["group-settle"]); app.buttons["group-settle"].tap()
        XCTAssertTrue(app.descendants(matching: .any).matching(identifier: "plan-currency-inherited").firstMatch.label.contains("USD"))
        replace(app.textFields["group-repayment-amount"], "20")
        app.dismissKeyboard()
        capture(app, "amount-repayment-es")
        app.buttons["group-repayment-save"].tap()
        capture(app, "currency-dollar-balance-es")
        app.buttons["group-options"].tap(); app.buttons["Editar grupo"].tap()
        let fixed = app.descendants(matching: .any).matching(identifier: "plan-currency-fixed").firstMatch
        reveal(app, fixed)
        XCTAssertTrue(fixed.label.contains("USD"))
        XCTAssertFalse(app.buttons["plan-edit-currency"].exists)
        capture(app, "currency-group-fixed-es")
    }
    private func openPlan(english: Bool = false) -> XCUIApplication {
        let app = XCUIApplication.cuadraoPreview()
        app.launchArguments = CuadraoPreviewLaunch.arguments + ["--plan-reset", "-cuadrao.design.appearance", "light"] + (english ? ["--design-english"] : [])
        app.launch(); app.buttons["tab.plan"].tap(); return app
    }
    private func number(_ field: XCUIElement) -> Double? {
        Double((field.value as? String ?? "").replacingOccurrences(of: ",", with: ""))
    }
    private func replace(_ field: XCUIElement, _ text: String) {
        field.coordinate(withNormalizedOffset: CGVector(dx: 0.98, dy: 0.5)).tap()
        field.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: (field.value as? String ?? "").count)); field.typeText(text)
    }
    private func reveal(_ app: XCUIApplication, _ element: XCUIElement) {
        for _ in 0..<7 {
            let bar = app.buttons["tab.home"]
            if element.isHittable && element.frame.midY < (bar.exists ? bar.frame.minY - 12 : app.frame.maxY) { return }
            app.swipeUp()
        }
        XCTAssertTrue(element.isHittable)
    }
    private func capture(_ app: XCUIApplication, _ name: String) {
        Thread.sleep(forTimeInterval: 0.6)
        let item = XCTAttachment(screenshot: app.screenshot()); item.name = name; item.lifetime = .keepAlways; add(item)
    }
}
