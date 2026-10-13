import XCTest

/// PRUEBA_MOVIL steps 10 to 12 through the founder's own path: + then Plan, each to an enabled button and a saved plan.
extension FinancialLoopUITests {
    func testFounderStepTenBudgetWithThreeAccountsAndGroceriesSaves() throws {
        try signIn()
        let stamp = String(UUID().uuidString.prefix(4))
        let accounts = ["Banco", "Efectivo", "Ahorro"].map { createMoneyAccount($0 + " " + stamp, type: "checking", amount: "1000") }
        openPlanFromAdd()
        tapVisible(app.buttons["plan-kind-budget"])
        fillMoneyField("budget.name", with: "Comida " + stamp)
        fillMoneyField("budget.limit", with: "5000")
        dismissMoneyKeyboard()
        for account in accounts { tapVisible(app.switches["budget.account." + account.id]) }
        XCTAssertFalse(app.buttons["budget.save"].isEnabled)
        XCTAssertTrue(app.staticTexts["plan.missing"].label.contains("categoría") || app.staticTexts["plan.missing"].label.contains("category"))
        tapVisible(app.switches["budget.category.groceries"])
        assertSavesAndCloses("budget.save")
        app.openPlanSurface()
        XCTAssertTrue(planCards("budget", "Comida " + stamp).firstMatch.waitForExistence(timeout: 15))
    }

    func testFounderStepElevenGoalSavesWithAnAmountOnly() throws {
        try signIn()
        let stamp = String(UUID().uuidString.prefix(4))
        openPlanFromAdd()
        tapVisible(app.buttons["plan-kind-goal"])
        fillMoneyField("goal.name", with: "Viaje " + stamp)
        fillMoneyField("goal.target", with: "20000")
        dismissMoneyKeyboard()
        assertSavesAndCloses("goal.save")
        app.openPlanSurface()
        XCTAssertTrue(planCards("goal", "Viaje " + stamp).firstMatch.waitForExistence(timeout: 15))
    }

    func testFounderStepTwelveMonthlyBillOnTheFifteenthSaves() throws {
        try signIn()
        let stamp = String(UUID().uuidString.prefix(4))
        let bank = createMoneyAccount("Banco factura " + stamp, type: "checking", amount: "5000")
        addPlanExpectation("Factura " + stamp, kind: "Bill", amount: "1000", account: bank, cadence: "Every month")
        openPlanOccurrence("Factura " + stamp)
        assertText("1,000.00")
    }

    /// The release bar's + opens the same plan editor as the Plan tab's create button; use whichever this build shows.
    func openPlanFromAdd() {
        app.revealConnectedTabBar()
        if app.buttons["nav.add"].waitForExistence(timeout: 3) {
            tapVisible(app.buttons["nav.add"])
            tapVisible(app.buttons["add.tray.plan"])
        } else {
            app.openPlanSurface()
            tapVisible(app.buttons["plan-create"])
        }
        XCTAssertTrue(app.buttons["plan-kind-goal"].waitForExistence(timeout: 15), "the plan sheet opens")
    }

    func assertSavesAndCloses(_ identifier: String) {
        let save = app.buttons[identifier]
        XCTAssertTrue(save.waitForExistence(timeout: 5))
        let enabled = NSPredicate(format: "isEnabled == true")
        expectation(for: enabled, evaluatedWith: save)
        waitForExpectations(timeout: 15)
        tapVisible(save)
        XCTAssertTrue(save.waitForNonExistence(timeout: 15), "the plan saves and the sheet closes")
    }
}
