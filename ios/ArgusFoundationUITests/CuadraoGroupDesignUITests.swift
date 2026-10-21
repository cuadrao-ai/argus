import XCTest

final class CuadraoGroupDesignUITests: XCTestCase {
    func testSharedJourneySpanish() {
        continueAfterFailure = false
        let app = openGroups()
        shot(app, "plan-together-es")
        app.buttons["group-card-trip"].tap()
        XCTAssertTrue(app.staticTexts["group-own-share"].waitForExistence(timeout: 3))
        XCTAssertEqual(app.staticTexts["group-own-share"].label, "DOP 3,000")
        shot(app, "plan-group-detail-es")
        let original = app.staticTexts["group-own-share"].label
        reveal(app, app.sliders["group-people-slider"])
        app.sliders["group-people-slider"].adjust(toNormalizedSliderPosition: 0.3)
        app.buttons["group-save-estimate"].tap()
        app.swipeDown(); app.swipeDown()
        XCTAssertEqual(app.staticTexts["group-own-share"].label, original)
        app.buttons["group-people-open"].tap()
        app.buttons["group-invite"].tap()
        shot(app, "plan-invitation-es")
        reveal(app, app.buttons["group-invite-code"]); app.buttons["group-invite-code"].tap()
        shot(app, "plan-invitation-qr-es")
        app.buttons["Listo"].tap()
        app.buttons["group-invite-preview"].tap()
        reveal(app, app.buttons["group-invite-accept"])
        shot(app, "plan-invitation-guest-es")
        app.buttons["group-invite-accept"].tap()
        XCTAssertTrue(app.buttons["Ya estás en el plan"].exists)
        app.buttons["Cerrar"].tap()
        app.segmentedControls["group-sections"].buttons["Gastos"].tap()
        app.buttons["group-add-expense"].tap()
        app.textFields["group-expense-name"].tap(); app.textFields["group-expense-name"].typeText("Cena del viernes\n")
        replace(app.textFields["group-expense-amount"], with: "2000")
        app.dismissKeyboard()
        reveal(app, app.buttons["group-expense-draft"])
        shot(app, "plan-split-editor-es")
        app.buttons["group-expense-draft"].tap()
        XCTAssertTrue(app.buttons["group-entry-draft"].waitForExistence(timeout: 3))
        shot(app, "plan-receipt-draft-es")
        app.buttons["group-entry-draft"].tap()
        reveal(app, app.buttons["group-expense-save"]); app.buttons["group-expense-save"].tap()
        XCTAssertFalse(app.buttons["group-entry-draft"].exists)
        app.buttons.matching(identifier: "group-entry-recorded").element(boundBy: 0).tap()
        replace(app.textFields["Parte de Tú"], with: "500")
        replace(app.textFields["Parte de Ana"], with: "300")
        app.dismissKeyboard()
        reveal(app, app.buttons["group-expense-save"])
        XCTAssertTrue(app.buttons["group-expense-save"].wait(for: \.isEnabled, toEqual: true, timeout: 2), "A split that adds up can be saved")
        shot(app, "plan-unequal-split-es")
        app.buttons["group-expense-save"].tap()
        app.segmentedControls["group-sections"].buttons["El plan"].tap()
        reveal(app, app.buttons["group-settle"]); app.buttons["group-settle"].tap()
        let repayment = app.textFields["group-repayment-amount"], record = app.buttons["group-repayment-save"]
        XCTAssertEqual(repayment.value as? String, "3,300.00", "Ana owes her 3,000 house share plus 300 of the dinner")
        replace(repayment, with: "3301")
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "value == %@", "3,301"), object: repayment)], timeout: 3), .completed, "The over-cap amount is in the field before the refusal is read")
        XCTAssertTrue(record.wait(for: \.isEnabled, toEqual: false, timeout: 2), "A repayment cannot exceed what the sender owes")
        replace(repayment, with: "500")
        XCTAssertTrue(record.wait(for: \.isEnabled, toEqual: true, timeout: 2), "A partial repayment under the cap can be recorded")
        shot(app, "plan-partial-repayment-es")
        record.tap()
        XCTAssertTrue(repayment.waitForNonExistence(timeout: 3), "Recording a repayment closes the sheet")
    }
    func testSampleCardNativeSharing() {
        continueAfterFailure = false
        let app = openGroups()
        openSampleCode(app)
        XCTAssertTrue(app.images["group-code-qr"].waitForExistence(timeout: 3))
        XCTAssertTrue(app.staticTexts["group-code-disclosure"].label.contains("No permite unirse"))
        shot(app, "group-code-artwork-es")
        let share = app.buttons["group-code-share"]
        reveal(app, share); share.tap()
        XCTAssertTrue(app.buttons["Close"].waitForExistence(timeout: 5))
        shot(app, "group-code-native-share")
        app.buttons["Close"].tap()
        XCTAssertTrue(app.buttons["group-code-done"].waitForExistence(timeout: 3))
        app.buttons["group-code-done"].tap()
        XCTAssertTrue(app.buttons["group-invite-code"].waitForExistence(timeout: 3))
    }

    func testSampleCardAtLargeTextEnglish() {
        continueAfterFailure = false
        let app = openGroups(english: true, dark: true, extra: ["-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"])
        openSampleCode(app)
        reveal(app, app.staticTexts["group-code-disclosure"])
        XCTAssertTrue(app.staticTexts["group-code-disclosure"].label.contains("doesn't join a real group"))
        shot(app, "group-code-large-en-disclosure")
        reveal(app, app.buttons["group-code-share"])
        XCTAssertTrue(app.buttons["group-code-share"].isHittable)
        XCTAssertTrue(app.buttons["group-code-done"].isHittable)
    }

    func testSampleCardSaveImage() {
        continueAfterFailure = false
        let app = openGroups(english: true)
        openSampleCode(app)
        reveal(app, app.buttons["group-code-share"])
        app.buttons["group-code-share"].tap()
        let save = app.cells.matching(NSPredicate(format: "label == %@", "Save Image")).firstMatch
        XCTAssertTrue(save.waitForExistence(timeout: 5))
        save.tap()
        let springboard = XCUIApplication(bundleIdentifier: "com.apple.springboard")
        let allow = springboard.alerts.buttons["Allow"]
        if allow.waitForExistence(timeout: 3) { allow.tap() }
        XCTAssertFalse(springboard.alerts.firstMatch.exists)
        XCTAssertTrue(app.buttons["group-code-done"].waitForExistence(timeout: 5))
        shot(app, "group-code-after-save-image")
    }

    private func openSampleCode(_ app: XCUIApplication) {
        reveal(app, app.buttons["group-card-trip"]); app.buttons["group-card-trip"].tap()
        app.buttons["group-people-open"].tap()
        app.buttons["group-invite"].tap()
        reveal(app, app.buttons["group-invite-code"]); app.buttons["group-invite-code"].tap()
    }

    func testGroupCreationSavingsEnglishDark() {
        continueAfterFailure = false
        let app = openGroups(english: true, dark: true)
        shot(app, "plan-together-dark-en")
        app.buttons["plan-create"].tap()
        app.textFields["group-name"].tap(); app.textFields["group-name"].typeText("Our summer\n")
        app.segmentedControls.buttons["Save together"].tap()
        replace(app.textFields["group-estimate"], with: "48000")
        app.dismissKeyboard()
        reveal(app, app.buttons["group-save"])
        shot(app, "plan-group-create-en")
        app.buttons["group-save"].tap()
        XCTAssertTrue(app.buttons["group-people-open"].waitForExistence(timeout: 3))
        reveal(app, app.buttons["group-add-expense"]); app.buttons["group-add-expense"].tap()
        app.textFields["group-expense-name"].tap(); app.textFields["group-expense-name"].typeText("First step\n")
        replace(app.textFields["group-expense-amount"], with: "250")
        app.dismissKeyboard()
        reveal(app, app.buttons["group-expense-save"]); app.buttons["group-expense-save"].tap()
        app.swipeDown(); app.swipeDown()
        XCTAssertTrue(app.staticTexts["DOP 250"].exists)
        shot(app, "plan-shared-goal-dark-en")
        app.buttons["tab.home"].tap(); app.buttons["tab.plan"].tap()
        XCTAssertTrue(app.staticTexts["DOP 250"].exists)
    }
    func testPersonalPolishAndLargeText() {
        continueAfterFailure = false
        let app = XCUIApplication.cuadraoPreview()
        app.launchArguments = CuadraoPreviewLaunch.arguments + ["--plan-reset", "-cuadrao.design.appearance", "light"]
        app.launch(); app.buttons["tab.plan"].tap()
        shot(app, "plan-refined-overview-es")
        reveal(app, app.buttons["plan-row-goal-personal"]); app.buttons["plan-row-goal-personal"].tap()
        XCTAssertTrue(app.sliders["plan-detail-slider"].isHittable)
        shot(app, "plan-refined-goal-es")
        app.sliders["plan-detail-slider"].adjust(toNormalizedSliderPosition: 0.6)
        shot(app, "plan-refined-goal-change-es")
        reveal(app, app.buttons["plan-detail-apply"]); app.buttons["plan-detail-apply"].tap()
        app.navigationBars.buttons.element(boundBy: 0).tap()
        app.swipeDown(); app.swipeDown()
        app.buttons["plan-create"].tap()
        XCTAssertTrue(app.buttons["plan-save"].isHittable)
        shot(app, "plan-refined-creation-es")
        app.terminate()
        app.launchArguments = CuadraoPreviewLaunch.arguments + ["--plan-reset", "--design-english", "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityM"]
        app.launch(); app.buttons["tab.plan"].tap()
        app.segmentedControls["plan-audience"].buttons["Together"].tap()
        shot(app, "plan-together-large-en")
        reveal(app, app.buttons["group-card-trip"]); app.buttons["group-card-trip"].tap()
        shot(app, "plan-group-large-en")
    }
    private func openGroups(english: Bool = false, dark: Bool = false, extra: [String] = []) -> XCUIApplication {
        let app = XCUIApplication.cuadraoPreview()
        app.launchArguments = CuadraoPreviewLaunch.arguments + ["--plan-reset", "-cuadrao.design.appearance", dark ? "dark" : "light"] + (english ? ["--design-english"] : []) + extra
        app.launch(); app.buttons["tab.plan"].tap()
        app.segmentedControls["plan-audience"].buttons[english ? "Together" : "En grupo"].tap()
        return app
    }
    private func replace(_ field: XCUIElement, with text: String) {
        field.coordinate(withNormalizedOffset: CGVector(dx: 0.98, dy: 0.5)).tap(); field.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: (field.value as? String ?? "").count)); field.typeText(text)
        let typed = NSPredicate { _, _ in (field.value as? String)?.replacingOccurrences(of: ",", with: "") == text }
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: typed, object: nil)], timeout: 3), .completed,
                       "\(field) holds '\(field.value as? String ?? "")' after replacing it with '\(text)'")
    }
    private func reveal(_ app: XCUIApplication, _ element: XCUIElement) {
        for _ in 0..<7 {
            let navigation = app.buttons["tab.home"]
            let bottom = navigation.exists ? navigation.frame.minY - 12 : app.frame.maxY
            if element.isHittable && element.frame.midY < bottom { return }
            app.swipeUp()
        }
        XCTAssertTrue(element.isHittable)
    }
    private func shot(_ app: XCUIApplication, _ name: String) {
        Thread.sleep(forTimeInterval: 0.6) // Let native sheet presentation finish before capture.
        let attachment = XCTAttachment(screenshot: app.screenshot()); attachment.name = name; attachment.lifetime = .keepAlways; add(attachment)
    }
}
