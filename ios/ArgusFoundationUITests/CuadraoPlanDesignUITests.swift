import XCTest
import UIKit

final class CuadraoPlanDesignUITests: XCTestCase {
    func testForecastAndGoalPlaygrounds() {
        continueAfterFailure = false
        let app = openPlan()
        XCTAssertTrue(app.buttons["plan-explore"].waitForExistence(timeout: 3))
        capture(app, "plan-overview-es")
        app.buttons["plan-explore"].tap()
        XCTAssertTrue(app.staticTexts["forecast-ending"].waitForExistence(timeout: 3))
        let original = app.staticTexts["forecast-ending"].label
        capture(app, "plan-forecast-es")
        app.swipeUp()
        app.sliders["forecast-slider"].adjust(toNormalizedSliderPosition: 1)
        reveal(app, app.buttons["forecast-apply"])
        capture(app, "plan-forecast-shortfall")
        XCTAssertTrue(app.staticTexts["El balance estimado baja a DOP -5,800."].exists)
        app.buttons["forecast-reset"].tap()
        app.swipeDown()
        app.sliders["forecast-slider"].adjust(toNormalizedSliderPosition: 0.2)
        reveal(app, app.buttons["forecast-apply"])
        capture(app, "plan-forecast-experiment")
        app.buttons["forecast-apply"].tap()
        XCTAssertTrue(app.staticTexts["Ritmo guardado"].exists)
        app.navigationBars.buttons.element(boundBy: 0).tap()
        XCTAssertNotEqual(app.staticTexts["plan-month-ending"].label, original)
        app.swipeUp()
        app.buttons["plan-row-goal-personal"].tap()
        capture(app, "plan-goal-es")
        app.swipeUp()
        app.buttons["plan-in-3-months"].tap()
        reveal(app, app.buttons["plan-detail-apply"])
        capture(app, "plan-goal-experiment")
        app.buttons["plan-detail-apply"].tap()
        XCTAssertTrue(app.staticTexts["Tu plan, a tu ritmo."].exists)
        app.buttons["tab.home"].tap()
        app.buttons["tab.plan"].tap()
        XCTAssertTrue(app.staticTexts["Tu plan, a tu ritmo."].exists)
    }

    func testCreationEditingArchiveAndRecovery() {
        continueAfterFailure = false
        let app = openPlan()
        app.buttons["plan-create"].tap()
        XCTAssertTrue(app.textFields["plan-name"].waitForExistence(timeout: 3))
        XCTAssertFalse(app.buttons["plan-save"].isEnabled)
        app.textFields["plan-name"].tap(); app.textFields["plan-name"].typeText("Mi próxima laptop\n")
        app.textFields["plan-target"].tap(); app.textFields["plan-target"].typeText("60000")
        app.dismissKeyboard()
        app.textFields["plan-monthly"].tap(); app.textFields["plan-monthly"].typeText("5000")
        app.dismissKeyboard()
        capture(app, "plan-create-es")
        reveal(app, app.buttons["plan-save"])
        app.buttons["plan-save"].tap()
        XCTAssertTrue(app.buttons["plan-detail-options"].waitForExistence(timeout: 3))
        capture(app, "plan-created-es")
        app.buttons["plan-detail-options"].tap()
        app.buttons["Editar plan"].tap()
        app.textFields["plan-name"].tap(); app.textFields["plan-name"].typeText(" nueva\n")
        reveal(app, app.buttons["plan-save"]); app.buttons["plan-save"].tap()
        app.buttons["plan-detail-options"].tap(); app.buttons["Archivar"].tap()
        app.buttons["Archivar plan"].tap()
        reveal(app, app.buttons["plan-archives"]); app.buttons["plan-archives"].tap()
        XCTAssertTrue(app.buttons["Retomar"].waitForExistence(timeout: 3))
        capture(app, "plan-archived-es")
        app.buttons["Retomar"].tap()
        XCTAssertTrue(app.buttons["Retomar"].waitForNonExistence(timeout: 3))
        capture(app, "plan-restored-es")
    }

    func testSharedBudgetDebtEnglishAndColdStart() {
        continueAfterFailure = false
        let app = openPlan(english: true)
        capture(app, "plan-overview-en")
        reveal(app, app.buttons["plan-row-goal-household"]); app.buttons["plan-row-goal-household"].tap()
        capture(app, "plan-household-en")
        app.swipeUp(); app.swipeUp()
        XCTAssertTrue(app.staticTexts["Better together."].exists)
        capture(app, "plan-household-detail-en")
        app.navigationBars.buttons.element(boundBy: 0).tap()
        app.swipeDown(); app.swipeDown()
        reveal(app, app.buttons["plan-row-budget-personal"])
        app.buttons["plan-row-budget-personal"].tap()
        capture(app, "plan-budget-en")
        app.navigationBars.buttons.element(boundBy: 0).tap()
        reveal(app, app.buttons["plan-row-debt-personal"])
        app.buttons["plan-row-debt-personal"].tap()
        capture(app, "plan-debt-en")
        app.terminate()
        app.launchArguments = CuadraoPreviewLaunch.arguments + ["--plan-empty", "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryXXXL"]
        app.launch(); app.buttons["tab.plan"].tap()
        capture(app, "plan-cold-start-large-es")
        XCTAssertTrue(app.buttons["Explorar un mes de ejemplo"].exists)
        app.buttons["Explorar un mes de ejemplo"].tap()
        XCTAssertFalse(app.buttons["plan-row-goal-personal"].exists)
    }

    func testExactAmountsDarkModeAndVoiceContinuity() {
        continueAfterFailure = false
        let app = XCUIApplication.cuadraoPreview()
        app.launchArguments = CuadraoPreviewLaunch.arguments + ["--plan-reset", "-cuadrao.design.appearance", "dark"]
        app.launch(); app.buttons["tab.plan"].tap()
        capture(app, "plan-overview-dark-es")
        app.buttons["plan-explore"].tap()
        app.buttons["forecast-exact"].tap()
        let field = app.textFields["plan-exact-input"]
        XCTAssertTrue(field.waitForExistence(timeout: 3))
        field.tap()
        field.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: (field.value as? String ?? "").count))
        field.typeText("900")
        app.buttons["plan-exact-done"].tap()
        reveal(app, app.buttons["forecast-apply"])
        capture(app, "plan-exact-dark-es")
        app.buttons["forecast-apply"].tap()
        app.buttons["tab.argus"].tap()
        app.buttons["chat-voice-entry"].tap()
        XCTAssertTrue(app.buttons["voice-minimize"].waitForExistence(timeout: 3))
        app.buttons["voice-minimize"].tap()
        app.buttons["tab.plan"].tap()
        XCTAssertTrue(app.buttons["voice-expand"].exists)
        XCTAssertTrue(app.buttons["tab.home"].isHittable)
        capture(app, "plan-with-voice-dark-es")
        app.buttons["voice-end-compact"].tap()
        XCTAssertFalse(app.buttons["voice-expand"].exists)
    }

    func testCreateMonthlyAndDebtPlans() {
        continueAfterFailure = false
        let app = openPlan()
        for kind in ["budget", "debt"] {
            app.buttons["plan-create"].tap()
            app.buttons["plan-kind-\(kind)"].tap()
            app.textFields["plan-name"].tap()
            app.textFields["plan-name"].typeText((kind == "budget" ? "Mis salidas" : "Mi préstamo") + "\n")
            app.textFields["plan-target"].tap(); app.textFields["plan-target"].typeText("60000")
            app.dismissKeyboard()
            if kind == "budget" { XCTAssertFalse(app.textFields["plan-monthly"].exists) }
            else {
                app.textFields["plan-monthly"].tap(); app.textFields["plan-monthly"].typeText("5000")
                app.dismissKeyboard()
            }
            reveal(app, app.buttons["plan-save"])
            capture(app, "plan-create-\(kind)-es")
            app.buttons["plan-save"].tap()
            XCTAssertTrue(app.buttons["plan-detail-options"].waitForExistence(timeout: 3))
            if kind == "budget" {
                XCTAssertTrue(app.staticTexts["Tu ritmo aparecerá con tus primeros movimientos."].exists)
            }
            capture(app, "plan-new-\(kind)-es")
            app.navigationBars.buttons.element(boundBy: 0).tap()
        }
    }

    func testNativeEditMenuKeepsKeyboardAndAcceptsReplacement() {
        continueAfterFailure = false
        let app = openPlan(english: true)
        app.buttons["plan-create"].tap()
        let field = app.textFields["plan-name"]
        field.tap()
        field.typeText("Original name")
        field.press(forDuration: 1.1)
        let selectAll = app.menuItems["Select All"]
        XCTAssertTrue(selectAll.waitForExistence(timeout: 3))
        selectAll.tap()
        XCTAssertTrue(app.keyboards.firstMatch.exists)
        field.typeText("Replaced name")
        XCTAssertEqual(field.value as? String, "Replaced name")
        UIPasteboard.general.string = " plus pasted text"
        defer { UIPasteboard.general.items = [] }
        field.press(forDuration: 1.1)
        let paste = app.menuItems["Paste"]
        XCTAssertTrue(paste.waitForExistence(timeout: 3))
        paste.tap()
        let permission = app.alerts.buttons["Allow Paste"]
        if permission.waitForExistence(timeout: 1) { permission.tap() }
        XCTAssertTrue(app.keyboards.firstMatch.exists)
        field.typeText("!")
        XCTAssertEqual(field.value as? String, "Replaced name plus pasted text!")
        capture(app, "native-edit-menu-keeps-focus")
        app.dismissKeyboard()
    }

    func testDebtRateSavesWhileKeyboardIsFocusedAndSurvivesRelaunch() {
        continueAfterFailure = false
        let app = openPlan(english: true)
        app.buttons["plan-create"].tap()
        app.buttons["plan-kind-debt"].tap()
        let name = "Rate persistence"
        app.textFields["plan-name"].tap()
        app.textFields["plan-name"].typeText(name + "\n")
        app.textFields["plan-target"].tap()
        app.textFields["plan-target"].typeText("60000")
        app.dismissKeyboard()
        app.textFields["plan-monthly"].tap()
        app.textFields["plan-monthly"].typeText("5000")
        app.dismissKeyboard()
        let startingPoint = app.buttons["Starting point"]
        reveal(app, startingPoint)
        startingPoint.tap()
        let rate = app.textFields["plan-rate"]
        reveal(app, rate)
        rate.tap()
        rate.typeText("12.75")
        XCTAssertTrue(app.keyboards.firstMatch.exists)
        app.buttons["plan-save"].tap()
        XCTAssertTrue(app.buttons["plan-detail-options"].waitForExistence(timeout: 5))
        app.buttons["plan-detail-options"].tap()
        app.buttons["Edit plan"].tap()
        reveal(app, startingPoint)
        startingPoint.tap()
        XCTAssertEqual(rate.value as? String, "12.75")
        reveal(app, rate)
        capture(app, "debt-rate-persisted-after-focused-save")
        app.terminate()
        app.launchArguments.removeAll { $0 == "--plan-reset" }
        app.launch()
        app.buttons["tab.plan"].tap()
        let saved = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@ AND label CONTAINS %@", "plan-row-", name)).firstMatch
        reveal(app, saved)
        saved.tap()
        app.buttons["plan-detail-options"].tap()
        app.buttons["Edit plan"].tap()
        reveal(app, startingPoint)
        startingPoint.tap()
        XCTAssertEqual(rate.value as? String, "12.75")
        reveal(app, rate)
        capture(app, "debt-rate-persisted-after-relaunch")
    }

    private func openPlan(english: Bool = false) -> XCUIApplication {
        let app = XCUIApplication.cuadraoPreview()
        app.launchArguments = CuadraoPreviewLaunch.arguments + ["--plan-reset", "-cuadrao.design.appearance", "light"] + (english ? ["--design-english"] : [])
        app.launch(); app.buttons["tab.plan"].tap(); return app
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
    private func capture(_ app: XCUIApplication, _ name: String) {
        let item = XCTAttachment(screenshot: app.screenshot())
        item.name = name; item.lifetime = .keepAlways; add(item)
    }
}
