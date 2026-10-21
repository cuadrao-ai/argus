import XCTest

extension FinancialLoopUITests {
    func testPlanAmountIdentityFollowsSelectedKind() throws {
        try signIn()
        app.openPlanSurface()
        tapVisible(app.buttons["plan-create"])
        let goalAmount = app.textFields["goal.target"]
        let budgetAmount = app.textFields["budget.limit"]
        XCTAssertTrue(goalAmount.waitForExistence(timeout: 5))
        XCTAssertFalse(budgetAmount.exists)

        tapVisible(app.buttons["plan-kind-budget"])
        XCTAssertTrue(app.textFields["budget.name"].waitForExistence(timeout: 5))
        XCTAssertTrue(budgetAmount.waitForExistence(timeout: 5))
        XCTAssertFalse(goalAmount.exists)

        tapVisible(app.buttons["plan-kind-goal"])
        XCTAssertTrue(app.textFields["goal.name"].waitForExistence(timeout: 5))
        XCTAssertTrue(goalAmount.waitForExistence(timeout: 5))
        XCTAssertFalse(budgetAmount.exists)
        tapVisible(app.buttons["Cancel"])
        XCTAssertTrue(goalAmount.waitForNonExistence(timeout: 5))
    }

    func testPlanDisclosuresAndExampleKeepRealForecastUnchanged() throws {
        try signIn()
        let bank = createMoneyAccount("Plan display " + UUID().uuidString.prefix(5), type: "checking", amount: "150")
        selectPlanAccounts([bank])
        assertPlanProjected("DOP 150.00")
        app.terminate(); app.launch()
        app.openPlanSurface()
        XCTAssertTrue(app.staticTexts["plan-heading"].waitForExistence(timeout: 15))
        XCTAssertFalse(app.datePickers["plan.until"].exists)
        XCTAssertFalse(app.buttons["plan.accounts"].exists)
        tapVisible(app.buttons["plan-create"])
        XCTAssertTrue(app.buttons["Add goal"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.buttons["Add budget"].exists)
        XCTAssertTrue(app.buttons["Add debt plan"].exists)
        XCTAssertTrue(app.buttons["Add an expectation"].exists)
        app.staticTexts["plan-heading"].tap()
        capture("plan-approved-overview-with-real-balance")

        #if DEBUG
        let explore = app.buttons["plan-explore"]
        XCTAssertTrue(explore.waitForExistence(timeout: 5))
        tapVisible(explore)
        XCTAssertTrue(app.otherElements["forecast-example-notice"].waitForExistence(timeout: 5)
            || app.staticTexts["Example scenario"].exists)
        tapVisible(app.sliders["forecast-slider"])
        app.sliders["forecast-slider"].adjust(toNormalizedSliderPosition: 0.9)
        tapVisible(app.buttons["forecast-apply"])
        assertText("Example updated")
        XCTAssertFalse(app.staticTexts["Pace saved"].exists)
        capture("plan-isolated-scenario-example")
        app.navigationBars.buttons.element(boundBy: 0).tap()
        assertPlanProjected("DOP 150.00")
        #else
        XCTAssertFalse(app.buttons["plan-explore"].exists)
        #endif

        revealPlanForecastControls()
        XCTAssertTrue(app.datePickers["plan.until"].exists)
        XCTAssertTrue(app.buttons["plan.accounts"].exists)
        tapVisible(app.buttons["plan-archives"])
        XCTAssertTrue(app.navigationBars["Archived"].waitForExistence(timeout: 5))
        app.navigationBars.buttons.element(boundBy: 0).tap()
        assertPlanProjected("DOP 150.00")
    }

    func testConnectedPlanRecordsLinksCorrectsAndReopens() throws {
        try signIn()
        let baseline = homeValue()
        let stamp = String(UUID().uuidString.prefix(4))
        let bank = createMoneyAccount("Plan bank " + stamp, type: "checking", amount: "100")
        let bill = "Electricity " + stamp
        let income = "Commission " + stamp
        addPlanExpectation(bill, kind: "Bill", amount: "200", account: bank)
        addPlanExpectation(income, kind: "Income", amount: "500", account: bank, daysAhead: 5)
        selectPlanAccounts([bank])
        assertPlanProjected("DOP 400.00")
        XCTAssertTrue(app.staticTexts["plan.shortfall.DOP"].exists)
        capture("plan-shortfall-before-later-income")
        assertHome(baseline + 100)
        for _ in 0..<8 {
            if app.buttons["home.viewPlan"].exists { break }
            app.scrollViews["screen.home"].swipeUp()
        }
        tapVisible(app.buttons["home.viewPlan"])
        openPlanOccurrence(bill)
        tapVisible(app.buttons["plan.record"])
        XCTAssertTrue(app.textFields["loop.amount"].waitForExistence(timeout: 10))
        XCTAssertEqual(app.textFields["loop.amount"].value as? String, "200.00")
        confirmPlanMoney()
        assertPlanProjected("DOP 400.00")
        openPlanOccurrence(bill)
        assertText("Recorded")
        capture("plan-payment-linked-to-original-activity")
        tapVisible(app.buttons["plan.viewActivity"])
        replaceMoneyField("loop.amount", with: "180")
        fillMoneyField("loop.reason", with: "Correct electricity receipt")
        dismissMoneyKeyboard(); confirmPlanMoney()
        assertPlanProjected("DOP 420.00")
        openMoneyAccount(bank)
        assertText("DOP -80.00")
        recordMoney(kind: "income", amount: "450", note: income)
        assertText("DOP 370.00")
        openPlanOccurrence(income)
        tapVisible(app.buttons["plan.link"])
        let candidate = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'plan.candidate.' AND label CONTAINS %@", income)).firstMatch
        tapVisible(candidate)
        capture("plan-link-existing-income-review")
        tapVisible(app.buttons["plan.link.confirm"])
        assertPlanProjected("DOP 370.00")
        openPlanOccurrence(income)
        assertText("Recorded")
        tapVisible(app.buttons["plan.editExpectation"])
        replaceMoneyField("plan.expectation.amount", with: "600")
        dismissMoneyKeyboard(); tapVisible(app.buttons["plan.expectation.save"])
        assertPlanProjected("DOP 370.00")
        assertHome(baseline + 370)
        capture("plan-home-after-recording-and-linking")
        app.terminate(); app.launch()
        assertHome(baseline + 370)
        assertPlanProjected("DOP 370.00")
        openPlanOccurrence(bill); assertText("Recorded")
        assertText("DOP 180.00")
        capture("plan-correction-preserved-after-reopen")
        app.buttons["Close"].tap()
        openMoneyAccount(bank); assertText("DOP 370.00")
        addPlanExpectation("Weekly transport " + stamp, kind: "Bill", amount: "10", account: bank,
                           daysAhead: 7, cadence: "Every week")
        capture("plan-recurring-expectations")
        assertHome(baseline + 370)
    }

    func testPlanResponseLossRecoversOnceAfterRelaunch() throws {
        try requireResponseLossProxy()
        let stamp = String(UUID().uuidString.prefix(4))
        try signIn(fresh: true, user: "B")
        let isolated = createMoneyAccount("Plan identity B " + stamp, type: "checking", amount: "111")
        try signIn(fresh: true)
        let bank = createMoneyAccount("Recovery plan " + stamp, type: "checking", amount: "100")
        let title = "Interrupted bill " + stamp
        addPlanExpectation(title, kind: "Bill", amount: "20", account: bank)
        selectPlanAccounts([bank])
        openPlanOccurrence(title)
        tapVisible(app.buttons["plan.record"])
        reviewMoney()
        let before = try faultStatus(arm: true)
        tapVisible(app.buttons["loop.confirm"])
        XCTAssertTrue(app.staticTexts["loop.error"].waitForExistence(timeout: 30))
        XCTAssertEqual(try faultStatus(arm: false), before + 1)
        capture("plan-committed-payment-response-lost")
        app.terminate(); app.launch()
        try signIn(fresh: true, user: "B")
        openMoneyAccount(isolated); assertText("DOP 111.00")
        app.revealConnectedTabBar()
        app.openPlanSurface()
        XCTAssertFalse(app.buttons["loop.pending.retry"].exists)
        XCTAssertFalse(app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'plan.occurrence.' AND label CONTAINS %@", title)).firstMatch.exists)
        capture("plan-pending-command-isolated-from-user-b")
        try signIn(fresh: true)
        app.openPlanSurface()
        tapVisible(app.buttons["loop.pending.retry"])
        XCTAssertTrue(app.buttons["loop.pending.retry"].waitForNonExistence(timeout: 15))
        XCTAssertEqual(try faultStatus(arm: false), before + 1)
        openPlanOccurrence(title); assertText("Recorded")
        app.buttons["Close"].tap()
        openMoneyAccount(bank); assertText("DOP 80.00")
        XCTAssertEqual(app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'activity.row.'")).count, 1)
        capture("plan-payment-recovered-once-after-reopen")
    }

    func testPlanKeepsABlankDollarAccountAtZeroAndLocalizedPresentation() throws {
        try signIn()
        let stamp = String(UUID().uuidString.prefix(4))
        let dollars = createMoneyAccount("Plan dollars " + stamp, type: "checking", currency: "USD")
        addPlanExpectation("Monthly remittance " + stamp, kind: "Income", amount: "100", account: dollars,
                           cadence: "Every month", currency: "USD")
        selectPlanAccounts([dollars])
        XCTAssertTrue(app.staticTexts["plan.projected.USD"].waitForExistence(timeout: 15),
                      "A blank account starts at a recorded 0.00, so its dollars project")
        XCTAssertFalse(app.staticTexts["plan.projected.DOP"].exists)
        XCTAssertFalse(app.staticTexts["home.projected.DOP"].exists)
        XCTAssertFalse(app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "Balance unknown")).firstMatch.exists)
        capture("plan-zero-dollar-balance")
        openMoneyAccount(dollars); assertText("USD 0.00")
        app.terminate()
        app.launchArguments = ["-AppleLanguages", "(es-419)", "-AppleLocale", "es_DO", "-appearancePreference", "light"]
        app.launch()
        app.openPlanSurface()
        revealPlanForecastControls()
        XCTAssertTrue(app.buttons["plan.accounts"].waitForExistence(timeout: 15))
        XCTAssertFalse(app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH 'plan.'")).firstMatch.exists)
        capture("plan-spanish-light-unknown-currency")
        app.terminate(); try signIn()
    }

    func testPlanCanRemoveArchivedSelectedAccounts() throws {
        try signIn()
        let stamp = String(UUID().uuidString.prefix(4))
        let archived = createMoneyAccount("Archived plan " + stamp, type: "checking", amount: "100")
        selectPlanAccounts([archived])
        openMoneyAccount(archived)
        tapVisible(app.buttons["accounts.archive"])
        app.confirmAccountArchive()
        selectPlanAccounts([])
        XCTAssertFalse(app.staticTexts["plan.projected.DOP"].exists)
        XCTAssertFalse(app.staticTexts["home.projected.DOP"].exists)
        // A changed account needs one with no recorded balance; a blank account now starts at 0.00
        // and keeps its type, so the server test test_changed_empty_account_is_explicitly_excluded owns that case.
    }

    func choosePlanDetailAction(_ identifier: String) {
        let options = app.buttons["plan-detail-options"]
        XCTAssertTrue(options.waitForExistence(timeout: 10))
        options.tap()
        let action = app.buttons[identifier]
        XCTAssertTrue(action.waitForExistence(timeout: 10))
        action.tap()
    }

    func confirmPlanMoney() {
        reviewMoney()
        tapVisible(app.buttons["loop.confirm"])
        XCTAssertTrue(app.buttons["loop.confirm"].waitForNonExistence(timeout: 15))
    }

    func addPlanExpectation(_ title: String, kind: String, amount: String, account: MoneyAccount,
                            daysAhead: Int = 0, cadence: String = "Once", currency: String = "DOP") {
        // Connected hides the tab bar on account detail; pop before Plan.
        app.revealConnectedTabBar()
        app.openPlanSurface()
        tapVisible(app.buttons["plan.add"])
        tapVisible(app.buttons["plan.expectation.kind"])
        app.buttons[kind].tap()
        tapVisible(app.buttons["plan.expectation.currency"])
        app.buttons[currency].tap()
        fillMoneyField("plan.expectation.name", with: title)
        fillMoneyField("plan.expectation.amount", with: amount)
        dismissMoneyKeyboard()
        tapVisible(app.buttons["plan.expectation.account"])
        let accountOption = app.buttons[account.name]
        for _ in 0..<12 {
            if accountOption.exists && accountOption.isHittable { break }
            app.swipeUp()
        }
        XCTAssertTrue(accountOption.waitForExistence(timeout: 5))
        accountOption.tap()
        if daysAhead != 0 { choosePlanDate(daysAhead: daysAhead) }
        if cadence != "Once" {
            tapVisible(app.buttons["plan.expectation.recurrence"])
            app.buttons[cadence].tap()
        }
        capture("plan-expectation-entry")
        tapVisible(app.buttons["plan.expectation.save"])
        XCTAssertTrue(app.buttons["plan.expectation.save"].waitForNonExistence(timeout: 15))
    }

    func selectPlanAccounts(_ accounts: [MoneyAccount]) {
        app.revealConnectedTabBar()
        app.openPlanSurface()
        revealPlanForecastControls()
        tapVisible(app.buttons["plan.accounts"])
        let ids = Set(accounts.map { "plan.selection." + $0.id.uppercased() })
        let switches = app.switches.matching(NSPredicate(format: "identifier BEGINSWITH 'plan.selection.'")).allElementsBoundByIndex
        XCTAssertFalse(switches.isEmpty)
        for item in switches {
            if (item.value as? String == "1") != ids.contains(item.identifier) { tapVisible(item) }
        }
        tapVisible(app.buttons["plan.selection.save"])
        XCTAssertTrue(app.buttons["plan.selection.save"].waitForNonExistence(timeout: 15))
    }

    func revealPlanForecastControls() {
        if !app.buttons["plan.accounts"].exists {
            tapVisible(app.buttons["plan.forecast.details"])
        }
    }

    func startPlan(_ kind: String) {
        tapVisible(app.buttons["plan-create"])
        tapVisible(app.buttons["plan-kind-" + kind])
    }

    func planCards(_ kind: String, _ title: String) -> XCUIElementQuery {
        app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@ AND label CONTAINS %@", "plan.card." + kind + ".", title))
    }

    func openPlanOccurrence(_ title: String) {
        app.revealConnectedTabBar()
        app.openPlanSurface()
        let row = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'plan.occurrence.' AND label CONTAINS %@", title)).firstMatch
        if !row.exists, app.buttons["plan.showMore"].exists { tapVisible(app.buttons["plan.showMore"]) }
        tapVisible(row)
    }

    func assertPlanProjected(_ value: String) {
        app.revealConnectedTabBar()
        app.openPlanSurface()
        let amount = app.staticTexts["plan.projected.DOP"]
        XCTAssertTrue(amount.waitForExistence(timeout: 15))
        let expected = NSPredicate(format: "label == %@", value)
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: expected, object: amount)], timeout: 10), .completed)
    }

    func choosePlanDate(daysAhead: Int) {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "America/Santo_Domingo")!
        let target = calendar.date(byAdding: .day, value: daysAhead, to: Date())!
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US")
        formatter.timeZone = calendar.timeZone
        formatter.dateFormat = "EEEE, MMMM d"
        tapVisible(app.datePickers["plan.expectation.date"])
        let day = app.buttons.matching(NSPredicate(format: "label CONTAINS %@", formatter.string(from: target))).firstMatch
        if !day.exists { app.buttons["Next Month"].tap() }
        XCTAssertTrue(day.waitForExistence(timeout: 5)); day.tap()
        app.navigationBars.firstMatch.coordinate(withNormalizedOffset: CGVector(dx: 0.7, dy: 0.5)).tap()
    }
}
