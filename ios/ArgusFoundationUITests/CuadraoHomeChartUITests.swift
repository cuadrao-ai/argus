import XCTest

final class CuadraoHomeChartUITests: XCTestCase {
    func testHomeBalanceChartAndSpaces() {
        continueAfterFailure = false
        let app = launch()
        XCTAssertEqual(app.staticTexts["home-chart-amount"].label, "153,920.00")
        XCTAssertFalse(app.segmentedControls["home-chart-view"].exists)
        XCTAssertTrue(app.buttons["home-range-year"].exists)
        shot(app, "quiet-home-es")
        let chart = app.otherElements.matching(identifier: "home-balance-chart").firstMatch
        chart.coordinate(withNormalizedOffset: CGVector(dx: 0.2, dy: 0.5)).tap()
        XCTAssertNotEqual(app.staticTexts["home-chart-date"].label, "Balance neto")
        let earlier = app.staticTexts["home-chart-date"].label
        chart.coordinate(withNormalizedOffset: CGVector(dx: 0.2, dy: 0.5)).press(forDuration: 0.35, thenDragTo: chart.coordinate(withNormalizedOffset: CGVector(dx: 0.75, dy: 0.5)))
        XCTAssertNotEqual(app.staticTexts["home-chart-date"].label, earlier)
        app.buttons["home-chart-today"].tap()
        XCTAssertEqual(app.staticTexts["home-chart-amount"].label, "153,920.00")
        app.buttons["cuadrao-space-household"].tap()
        XCTAssertEqual(app.staticTexts["home-chart-amount"].label, "43,500.00")
        shot(app, "quiet-home-household-es")
    }
    func testHistoryRangesAndDistribution() {
        continueAfterFailure = false
        let app = launch()
        app.buttons["home-history-expand"].tap()
        let period = app.otherElements.matching(identifier: "home-balance-chart").firstMatch
        XCTAssertTrue(period.waitForExistence(timeout: 3))
        let current = period.value as? String
        let chart = app.otherElements.matching(identifier: "home-balance-chart").firstMatch
        chart.swipeRight(velocity: .fast)
        XCTAssertNotEqual(period.value as? String, current)
        let previous = period.value as? String
        chart.coordinate(withNormalizedOffset: CGVector(dx: 0.2, dy: 0.5)).press(forDuration: 0.35, thenDragTo: chart.coordinate(withNormalizedOffset: CGVector(dx: 0.75, dy: 0.5)))
        XCTAssertEqual(period.value as? String, previous, "Inspection must not page the calendar")
        shot(app, "history-previous-inspect-es")
        app.buttons["home-view-distribution"].tap()
        XCTAssertTrue(app.buttons["home-period-year"].exists)
        XCTAssertFalse(app.buttons["home-period-previous"].exists)
        app.buttons["home-view-history"].tap()
        XCTAssertEqual(period.value as? String, previous, "Returning restores the history period")
        chart.swipeLeft(velocity: .fast)
        XCTAssertEqual(period.value as? String, current)
        chart.swipeLeft(velocity: .fast)
        XCTAssertEqual(period.value as? String, current, "No future periods")
        XCTAssertFalse(app.buttons["home-period-next"].exists)
        app.buttons["home-period-year"].tap()
        chart.swipeRight(velocity: .fast)
        chart.swipeLeft(velocity: .fast)
        XCTAssertFalse(app.buttons["home-period-next"].exists)
        shot(app, "history-year-es")
        app.buttons["home-view-distribution"].tap()
        XCTAssertTrue(app.buttons["home-distribution-segment-savings"].waitForExistence(timeout: 3))
        shot(app, "distribution-whole-es")
        app.buttons["home-distribution-savings"].tap()
        XCTAssertTrue(app.scrollViews["home-insights-content"].staticTexts.containing(NSPredicate(format: "label CONTAINS %@", "Mi tranquilidad")).firstMatch.exists)
        shot(app, "distribution-savings-es")
        app.buttons["home-distribution-all"].tap()
        XCTAssertEqual(app.buttons["home-distribution-savings"].value as? String, "Contraído")
        app.buttons["home-distribution-segment-checking"].tap()
        XCTAssertEqual(app.buttons["home-distribution-checking"].value as? String, "Expandido")
        shot(app, "distribution-checking-es")
        app.buttons["home-history-done"].tap()
        XCTAssertTrue(app.staticTexts["home-greeting"].exists)
    }
    func testDarkAndLargeEnglish() {
        continueAfterFailure = false
        let app = launch(english: true)
        shot(app, "quiet-home-dark-large-en")
        app.buttons["home-history-expand"].tap()
        app.buttons["home-view-distribution"].tap()
        shot(app, "distribution-dark-large-en")
        let row = app.buttons["home-distribution-savings"]
        for _ in 0..<4 {
            if row.isHittable { break }
            app.scrollViews["home-insights-content"].swipeUp()
        }
        XCTAssertTrue(row.isHittable)
        row.tap()
        shot(app, "distribution-dark-large-expanded-en")
        app.buttons["home-history-done"].tap()
        XCTAssertTrue(app.staticTexts["home-greeting"].exists)
    }
    func testDistributionAccountRoundTrip() {
        continueAfterFailure = false
        let app = launch()
        app.buttons["home-history-expand"].tap()
        app.buttons["home-view-distribution"].tap()
        app.buttons["home-distribution-checking"].tap()
        let content = app.scrollViews["home-insights-content"]
        let link = content.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@ AND label CONTAINS %@", "home-distribution-account-", "Gastos de casa")).firstMatch
        for _ in 0..<3 {
            if link.isHittable && link.frame.maxY < app.frame.maxY - 50 { break }
            content.swipeUp()
        }
        XCTAssertTrue(link.isHittable)
        let linkID = link.identifier
        let originalY = link.frame.minY
        shot(app, "distribution-before-account-es")
        link.tap()
        XCTAssertEqual(app.staticTexts["account-detail-title"].label, "Gastos de casa")
        shot(app, "distribution-account-detail-es")
        app.buttons["account-detail-record"].tap()
        XCTAssertTrue(app.navigationBars["Añadir movimiento"].waitForExistence(timeout: 3))
        app.buttons["Cancelar"].tap()
        app.buttons["Opciones de cuenta"].tap()
        app.buttons["Cambiar nombre"].tap()
        let field = app.textFields.firstMatch
        XCTAssertTrue(field.waitForExistence(timeout: 3))
        field.tap()
        field.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: (field.value as? String ?? "").count))
        field.typeText("Gastos del hogar")
        app.buttons["Guardar"].tap()
        XCTAssertEqual(app.staticTexts["account-detail-title"].label, "Gastos del hogar")
        app.navigationBars.buttons.element(boundBy: 0).tap()
        XCTAssertEqual(app.buttons["home-distribution-checking"].value as? String, "Expandido")
        let returned = content.buttons[linkID]
        XCTAssertTrue(returned.label.contains("Gastos del hogar"), "Return must reflect the same account state")
        XCTAssertEqual(returned.frame.minY, originalY, accuracy: 3, "Return preserves scroll position")
        shot(app, "distribution-account-return-es")
        app.buttons["home-history-done"].tap()
        XCTAssertTrue(app.staticTexts["home-greeting"].exists)
    }
    func testExpenseActivityPeriodsAndBreakdown() {
        continueAfterFailure = false
        let app = launch()
        app.buttons["home-history-expand"].tap()
        app.buttons["home-insight-metric"].tap()
        app.buttons["Actividad"].tap()
        let chart = app.otherElements.matching(identifier: "home-spending-chart").firstMatch
        XCTAssertTrue(chart.waitForExistence(timeout: 3))
        XCTAssertFalse(app.buttons["home-period-previous"].exists)
        XCTAssertFalse(app.buttons["home-chart-today"].exists)
        let current = app.staticTexts["home-spending-total"].label
        chart.swipeRight(velocity: .fast)
        XCTAssertEqual(chart.value as? String, "-1")
        XCTAssertNotEqual(app.staticTexts["home-spending-total"].label, current)
        shot(app, "activity-month-es")
        chart.coordinate(withNormalizedOffset: CGVector(dx: 0.2, dy: 0.5)).press(forDuration: 0.35, thenDragTo: chart.coordinate(withNormalizedOffset: CGVector(dx: 0.75, dy: 0.5)))
        XCTAssertEqual(chart.value as? String, "-1", "Inspecting a weekly bucket must not page the month")
        app.buttons["home-view-distribution"].tap()
        XCTAssertEqual(app.staticTexts["home-spending-total"].label.isEmpty, false)
        app.buttons["home-spending-segment-home"].tap()
        XCTAssertTrue(app.buttons["home-spending-all"].waitForExistence(timeout: 2))
        app.buttons["home-spending-all"].tap()
        XCTAssertTrue(app.buttons["home-spending-all"].exists)
        shot(app, "activity-distribution-es")
        app.buttons["home-view-history"].tap()
        XCTAssertEqual(chart.value as? String, "-1")
        chart.swipeLeft(velocity: .fast)
        chart.swipeLeft(velocity: .fast)
        XCTAssertEqual(chart.value as? String, "0")
        app.buttons["home-period-week"].tap()
        shot(app, "activity-week-es")
        app.buttons["home-period-year"].tap()
        XCTAssertEqual(chart.value as? String, "0")
        shot(app, "activity-year-es")
        chart.swipeRight(velocity: .fast)
        XCTAssertEqual(chart.value as? String, "-1")
        shot(app, "activity-full-previous-year-es")
        chart.swipeRight(velocity: .fast)
        XCTAssertEqual(chart.value as? String, "-1", "Oldest fully populated year is the boundary")
    }
    func testExpenseLargeEnglish() {
        continueAfterFailure = false
        let app = launch(english: true)
        app.buttons["home-history-expand"].tap()
        app.buttons["home-insight-metric"].tap()
        app.buttons["Activity"].tap()
        app.buttons["home-period-year"].tap()
        XCTAssertTrue(app.staticTexts["home-spending-total"].exists)
        shot(app, "activity-dark-large-en")
        app.scrollViews["home-insights-content"].swipeUp()
        shot(app, "activity-dark-large-axis-en")
    }
    func testSpendingHighlightsAndReturn() {
        continueAfterFailure = false
        let app = launch()
        openActivity(app)
        let chart = app.otherElements.matching(identifier: "home-spending-chart").firstMatch
        chart.swipeRight(velocity: .fast)
        shot(app, "story-month-title-es")
        let content = app.scrollViews["home-insights-content"]
        let highlight = app.buttons["home-highlight-all-average-6"]
        for _ in 0..<8 {
            if highlight.isHittable && highlight.frame.maxY < app.frame.maxY - 40 { break }
            content.swipeUp()
        }
        XCTAssertTrue(highlight.isHittable)
        shot(app, "story-history-average-es")
        highlight.tap()
        XCTAssertTrue(app.scrollViews["home-highlight-records"].waitForExistence(timeout: 3))
        shot(app, "story-supporting-months-es")
        app.navigationBars.buttons.element(boundBy: 0).tap()
        let all = app.buttons["home-highlights-all"]
        for _ in 0..<4 { if all.isHittable { break }; content.swipeDown() }
        all.tap()
        XCTAssertTrue(app.scrollViews["home-all-highlights"].waitForExistence(timeout: 3))
        shot(app, "story-all-highlights-es")
        let comparison = app.buttons["home-highlight-comparison"]
        for _ in 0..<8 { if comparison.isHittable { break }; app.scrollViews["home-all-highlights"].swipeUp() }
        XCTAssertTrue(comparison.isHittable)
        comparison.tap()
        XCTAssertTrue(app.scrollViews["home-highlight-records"].waitForExistence(timeout: 3))
        app.navigationBars.buttons.element(boundBy: 0).tap()
        app.navigationBars.buttons.element(boundBy: 0).tap()
        for _ in 0..<8 { content.swipeDown(velocity: .fast) }
        XCTAssertEqual(chart.value as? String, "-1")
        app.buttons["home-view-distribution"].tap()
        let segment = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@", "home-spending-segment-")).firstMatch
        XCTAssertTrue(segment.waitForExistence(timeout: 3))
        segment.tap()
        XCTAssertTrue(app.buttons["home-spending-all"].waitForExistence(timeout: 2))
        shot(app, "story-distribution-decomposition-es")
    }
    func testInteractivePagingAndBalanceMeaning() {
        continueAfterFailure = false
        let app = launch()
        app.buttons["home-history-expand"].tap()
        let chart = app.otherElements.matching(identifier: "home-balance-chart").firstMatch
        XCTAssertTrue(chart.waitForExistence(timeout: 3))
        let period = chart.value as? String
        let amount = app.scrollViews["home-insights-content"].staticTexts["home-chart-amount"].label
        app.buttons["home-view-distribution"].tap()
        XCTAssertEqual(app.staticTexts["home-distribution-total"].label, amount)
        app.buttons["home-view-history"].tap()
        let start = chart.coordinate(withNormalizedOffset: CGVector(dx: 0.3, dy: 0.5))
        start.press(forDuration: 0.01, thenDragTo: chart.coordinate(withNormalizedOffset: CGVector(dx: 0.34, dy: 0.5)), withVelocity: .slow, thenHoldForDuration: 0.3)
        XCTAssertEqual(chart.value as? String, period, "A cancelled short drag retains its page")
        chart.coordinate(withNormalizedOffset: CGVector(dx: 0.08, dy: 0.5)).press(forDuration: 0.01, thenDragTo: chart.coordinate(withNormalizedOffset: CGVector(dx: 0.98, dy: 0.5)), withVelocity: .slow, thenHoldForDuration: 0.1)
        XCTAssertNotEqual(chart.value as? String, period)
        let prior = chart.value as? String
        chart.coordinate(withNormalizedOffset: CGVector(dx: 0.2, dy: 0.5)).press(forDuration: 0.35, thenDragTo: chart.coordinate(withNormalizedOffset: CGVector(dx: 0.75, dy: 0.5)))
        XCTAssertEqual(chart.value as? String, prior)
        chart.swipeLeft()
        XCTAssertEqual(chart.value as? String, period, "One committed drag advances one period")
        shot(app, "interactive-paging-balance-es")
    }
    func testSpendingEmptyAndUnavailable() {
        continueAfterFailure = false
        let app = launch(extra: ["--insights-empty-month"])
        openActivity(app)
        // Known zero (Home comparisons lock): confirmed coverage with no spending shows 0, not Sin datos.
        XCTAssertEqual(app.staticTexts["home-spending-total"].label, "0.00")
        XCTAssertFalse(app.staticTexts["Sin datos"].exists)
        XCTAssertTrue(app.staticTexts["Sin gastos"].exists)
        XCTAssertTrue(app.staticTexts["Aún no hay gastos registrados en este período."].exists)
        XCTAssertFalse(app.staticTexts["home-spending-insight"].label.contains("%"))
        XCTAssertTrue(app.otherElements.matching(identifier: "home-spending-chart").firstMatch.exists)
        app.buttons["home-view-distribution"].tap()
        XCTAssertTrue(app.staticTexts["Aún no hay gastos registrados en este período."].exists)
        XCTAssertFalse(app.buttons["home-spending-all"].exists)
        app.buttons["home-view-history"].tap()
        XCTAssertFalse(app.buttons["home-highlight-comparison"].exists)
        XCTAssertFalse(app.buttons["home-highlight-largest"].exists)
        shot(app, "story-empty-month-es")
        app.otherElements.matching(identifier: "home-spending-chart").firstMatch.swipeRight(velocity: .fast)
        XCTAssertNotEqual(app.staticTexts["home-spending-total"].label, "0.00")
        app.terminate()
        let unavailable = launch(extra: ["--insights-empty-month", "--insights-no-coverage"])
        openActivity(unavailable)
        XCTAssertEqual(unavailable.staticTexts["home-spending-total"].label, "Sin datos")
        XCTAssertTrue(unavailable.staticTexts["El historial de este período está incompleto. No lo contamos como cero."].exists)
        shot(unavailable, "story-unknown-month-es")
    }
    func testSpendingHighlightsLargeEnglish() {
        continueAfterFailure = false
        let app = launch(english: true)
        openActivity(app, english: true)
        let content = app.scrollViews["home-insights-content"]
        let chart = app.otherElements.matching(identifier: "home-spending-chart").firstMatch
        chart.swipeRight(velocity: .fast)
        let highlight = app.buttons["home-highlight-all-average-6"]
        for _ in 0..<9 {
            if highlight.isHittable { break }
            content.swipeUp()
        }
        shot(app, "story-highlight-dark-large-en")
        XCTAssertTrue(highlight.isHittable)
        highlight.tap()
        XCTAssertTrue(app.scrollViews["home-highlight-records"].waitForExistence(timeout: 3))
    }
    func testBalanceBreakdownAndAccountReturn() {
        continueAfterFailure = false
        let app = launch()
        app.buttons["home-history-expand"].tap()
        let content = app.scrollViews["home-insights-content"]
        let period = app.staticTexts["home-insight-period"].label
        let row = content.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@ AND label CONTAINS %@", "home-balance-change-", "Día a día")).firstMatch
        for _ in 0..<5 { if row.isHittable && row.frame.maxY < app.frame.maxY - 50 { break }; content.swipeUp() }
        XCTAssertTrue(row.isHittable)
        XCTAssertTrue(app.staticTexts["Qué cambió"].exists)
        shot(app, "balance-change-breakdown-es")
        row.tap()
        XCTAssertEqual(app.staticTexts["account-detail-title"].label, "Día a día")
        app.navigationBars.buttons.element(boundBy: 0).tap()
        XCTAssertTrue(row.isHittable)
        for _ in 0..<5 { content.swipeDown(velocity: .fast) }
        XCTAssertEqual(app.staticTexts["home-insight-period"].label, period)
        let amount = content.staticTexts["home-chart-amount"].label
        app.buttons["home-view-distribution"].tap()
        XCTAssertEqual(content.staticTexts["home-distribution-total"].label, amount)
    }
    func testFirstObservationAndFirstExpense() {
        continueAfterFailure = false
        let app = launch(extra: ["--insights-first-use"])
        app.buttons["home-history-expand"].tap()
        let content = app.scrollViews["home-insights-content"]
        XCTAssertEqual(content.staticTexts["home-chart-amount"].label, "153,920.00")
        content.swipeUp()
        XCTAssertTrue(app.staticTexts["Tu punto de partida"].exists)
        XCTAssertFalse(app.staticTexts["home-balance-net-change"].exists)
        shot(app, "balance-first-observation-es")
        app.buttons["home-insight-metric"].tap(); app.buttons["Actividad"].tap()
        XCTAssertEqual(app.staticTexts["home-spending-total"].label, "Sin datos", "First use has no coverage, so no zero")
        XCTAssertTrue(app.staticTexts["Tu historia empieza aquí"].exists)
        shot(app, "activity-first-use-es")
        app.buttons["chart-state-action"].tap()
        app.buttons["Día a día"].tap()
        XCTAssertTrue(app.navigationBars["Añadir movimiento"].waitForExistence(timeout: 3))
        let amount = app.textFields["cuadrao-amount"]
        amount.tap(); amount.typeText("250")
        app.dismissKeyboard()
        app.buttons["Revisar"].tap(); app.buttons["Guardar"].tap()
        XCTAssertTrue(app.staticTexts["home-spending-total"].waitForExistence(timeout: 3))
        XCTAssertEqual(app.staticTexts["home-spending-total"].label, "250.00")
        XCTAssertFalse(app.staticTexts["Tu historia empieza aquí"].exists)
        XCTAssertTrue(app.otherElements.matching(identifier: "home-spending-chart").firstMatch.exists)
        shot(app, "activity-first-expense-es")
    }
    func testBalanceBreakdownLargeEnglish() {
        continueAfterFailure = false
        let app = launch(english: true)
        app.buttons["home-history-expand"].tap()
        let content = app.scrollViews["home-insights-content"]
        let change = app.staticTexts["home-balance-net-change"]
        for _ in 0..<9 { if change.isHittable { break }; content.swipeUp() }
        XCTAssertTrue(change.isHittable)
        shot(app, "balance-change-dark-large-en")
    }
    private func openActivity(_ app: XCUIApplication, english: Bool = false) {
        app.buttons["home-history-expand"].tap()
        app.buttons["home-insight-metric"].tap()
        app.buttons[english ? "Activity" : "Actividad"].tap()
    }
    private func launch(english: Bool = false, extra: [String] = []) -> XCUIApplication {
        let app = XCUIApplication()
        // Without the preview arguments this lands on Connected and never reaches the charts.
        app.launchArguments = CuadraoPreviewLaunch.arguments
            + ["--plan-reset", "-cuadrao.design.appearance", english ? "dark" : "light"] + extra
        if english { app.launchArguments += ["--design-english", "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityM"] }
        app.launch()
        return app
    }
    private func shot(_ app: XCUIApplication, _ name: String) {
        let a = XCTAttachment(screenshot: app.screenshot()); a.name = name; a.lifetime = .keepAlways; add(a)
    }
}
