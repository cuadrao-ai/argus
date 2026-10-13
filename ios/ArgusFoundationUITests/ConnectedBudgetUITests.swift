import XCTest

extension FinancialLoopUITests {
    func testConnectedBudgetSpendingCorrectionRefundSearchAndReopen() throws {
        try signIn()
        let stamp = String(UUID().uuidString.prefix(5))
        let checking = createMoneyAccount("Budget bank " + stamp, type: "checking", amount: "1000")
        budgetExpense(amount: "120", note: "Budget groceries " + stamp)
        let card = createMoneyAccount("Budget card " + stamp, type: "credit_card", amount: "0")
        let unknown = createMoneyAccount("Budget refund account " + stamp, type: "checking")
        let title = "Food " + stamp
        createBudget(title, accounts: [checking, card])
        openBudget(title)
        assertBudget(spent: "120.00", status: "30.00")
        capture("budget-initial-limit-and-scope")
        app.returnFromDetail("budget.close")
        openMoneyAccount(card)
        budgetExpense(amount: "80", note: "Card groceries " + stamp)
        openBudget(title)
        assertBudget(spent: "200.00", status: "50.00", over: true)
        capture("budget-over-limit-after-card-purchase")
        let contributor = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'budget.activity.' AND label CONTAINS %@", "Card groceries " + stamp)).firstMatch
        tapVisible(contributor)
        tapVisible(app.buttons["activity.correct"])
        replaceMoneyField("loop.amount", with: "60")
        fillMoneyField("loop.reason", with: "Correct the grocery receipt")
        dismissMoneyKeyboard(); reviewMoney(); tapVisible(app.buttons["loop.confirm"])
        XCTAssertTrue(app.buttons["loop.confirm"].waitForNonExistence(timeout: 15))
        app.swipeBack(cancel: true)
        XCTAssertTrue(app.buttons["activity.correct"].waitForExistence(timeout: 5))
        app.swipeBack()
        assertBudget(spent: "180.00", status: "30.00", over: true)
        capture("budget-contributor-correction-propagated")
        app.returnFromDetail("budget.close")
        openMoneyAccount(unknown)
        recordMoney(kind: "refund", amount: "25", note: "Budget refund " + stamp, purchase: "Card groceries " + stamp)
        assertText("Balance unknown")
        openBudget(title)
        assertBudget(spent: "155.00", status: "5.00", over: true)
        XCTAssertEqual(app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'budget.activity.'")).count, 3)
        capture("budget-cross-account-refund")
        let oldest = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'budget.activity.' AND label CONTAINS %@", "Budget groceries " + stamp)).firstMatch
        tapVisible(oldest)
        app.returnFromDetail("budget.activity.back")
        XCTAssertTrue(oldest.waitForExistence(timeout: 15))
        let savedY = oldest.frame.minY
        app.terminate(); app.launch()
        XCTAssertTrue(oldest.waitForExistence(timeout: 15))
        let restoredPosition = NSPredicate { _, _ in oldest.isHittable && abs(oldest.frame.minY - savedY) < 12 }
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: restoredPosition, object: nil)], timeout: 15), .completed)
        capture("budget-contributor-position-restored")
        choosePlanDetailAction("budget.edit")
        replaceMoneyField("budget.limit", with: "160")
        dismissMoneyKeyboard(); tapVisible(app.buttons["budget.save"])
        assertBudget(spent: "155.00", status: "5.00")
        choosePlanDetailAction("budget.remove")
        app.buttons.matching(identifier: "budget.remove.confirm").firstMatch.tap()
        XCTAssertTrue(app.buttons["budget.restore"].waitForExistence(timeout: 15))
        capture("budget-reversible-removal")
        tapVisible(app.buttons["budget.restore"])
        choosePlanDetailAction("budget.edit")
        XCTAssertTrue(app.buttons["budget.save"].waitForExistence(timeout: 15))
        tapVisible(app.buttons["Cancel"])
        XCTAssertTrue(app.buttons["budget.save"].waitForNonExistence(timeout: 10))
        app.returnFromDetail("budget.close")
        verifyBudgetSearchAndReopen(title)
    }

    func testRetainedBudgetViewportRestoration() throws {
        guard let title = ProcessInfo.processInfo.environment["ARGUS_TEST_SEARCH_QUERY"] else {
            throw XCTSkip("Requires a retained isolated budget journey.")
        }
        try signIn(fresh: true, user: "A")
        openPersonalAccounts()
        openBudget(title)
        let rows = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'budget.activity.'"))
        XCTAssertEqual(rows.count, 3)
        let oldest = rows.element(boundBy: rows.count - 1)
        app.swipeDown()
        let topPosition = oldest.frame.minY
        app.swipeUp()
        XCTAssertLessThan(oldest.frame.minY, topPosition - 12)
        tapVisible(oldest)
        app.returnFromDetail("budget.activity.back")
        XCTAssertTrue(oldest.waitForExistence(timeout: 15))
        let savedY = oldest.frame.minY
        let savedLabels = rows.allElementsBoundByIndex.map(\.label)
        capture("budget-viewport-before-relaunch")
        app.terminate(); app.launch()
        XCTAssertTrue(oldest.waitForExistence(timeout: 15))
        let restored = NSPredicate { _, _ in oldest.isHittable && abs(oldest.frame.minY - savedY) < 12 }
        let result = XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: restored, object: nil)], timeout: 15)
        capture("budget-viewport-after-relaunch")
        XCTAssertEqual(result, .completed, "Expected Y \(savedY), restored Y \(oldest.frame.minY), hittable \(oldest.isHittable)")
        XCTAssertEqual(rows.allElementsBoundByIndex.map(\.label), savedLabels)
        tapVisible(oldest)
        tapVisible(app.buttons["activity.correct"])
        XCTAssertTrue(app.textFields["loop.amount"].waitForExistence(timeout: 10))
        tapVisible(app.buttons["Cancel"])
        app.returnFromDetail("budget.activity.back")
        choosePlanDetailAction("budget.edit")
        XCTAssertTrue(app.buttons["budget.save"].waitForExistence(timeout: 10))
        tapVisible(app.buttons["Cancel"])
    }

    func testExistingBudgetHomeSearchAndReopen() throws {
        guard let title = ProcessInfo.processInfo.environment["ARGUS_TEST_SEARCH_QUERY"] else {
            throw XCTSkip("Requires a retained isolated budget journey.")
        }
        try signIn()
        app.buttons["tab.home"].tap()
        let home = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'budget.row.home.' AND label CONTAINS %@", title)).firstMatch
        tapVisible(home)
        assertBudget(spent: "155.00", status: "5.00")
        app.returnFromDetail("budget.close")
        XCTAssertTrue(home.waitForExistence(timeout: 15))
        XCTAssertTrue(home.isHittable)
        capture("budget-home-progress-and-return")
        verifyBudgetSearchAndReopen(title)
    }

    func testRetainedBudgetSearchFromActivityPerspective() throws {
        guard let title = ProcessInfo.processInfo.environment["ARGUS_TEST_SEARCH_QUERY"] else {
            throw XCTSkip("Requires a retained isolated budget journey.")
        }
        try signIn()
        app.revealConnectedTabBar()
        tapVisible(app.buttons["tab.search"])
        tapVisible(app.buttons["search.filter.activity"])
        XCTAssertTrue(app.buttons["search.filter.activity"].isSelected)
        verifyBudgetSearchAndReopen(title)
    }

    private func verifyBudgetSearchAndReopen(_ title: String) {
        app.buttons["tab.search"].tap()
        let query = app.textFields["search.query"]
        XCTAssertTrue(query.waitForExistence(timeout: 10))
        query.tap()
        if app.buttons["search.clear"].exists { app.buttons["search.clear"].tap(); query.tap() }
        query.typeText(title + "\n")
        chooseSearchPlans()
        let hit = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'search.row.budget.' AND label CONTAINS %@", title)).firstMatch
        tapVisible(hit)
        assertBudget(spent: "155.00", status: "5.00")
        app.terminate(); app.launch()
        assertBudget(spent: "155.00", status: "5.00")
        capture("budget-detail-restored-after-relaunch")
        app.returnFromDetail("budget.close")
        XCTAssertEqual(app.textFields["search.query"].value as? String, title)
        XCTAssertTrue(hit.waitForExistence(timeout: 15))
        capture("budget-search-origin-restored")
        tapVisible(hit)
        app.terminate()
        app.launchArguments = ["-AppleLanguages", "(es-419)", "-AppleLocale", "es_DO", "-appearancePreference", "light"]
        app.launch()
        XCTAssertTrue(app.staticTexts["budget.spent"].waitForExistence(timeout: 15))
        XCTAssertFalse(app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH 'budget.'")).firstMatch.exists)
        capture("budget-spanish-detail")
        app.returnFromDetail("budget.close")
    }

    func testBudgetResponseLossRecoversExactCommandAfterRelaunch() throws {
        try requireResponseLossProxy()
        try signIn()
        let stamp = String(UUID().uuidString.prefix(5))
        let checking = createMoneyAccount("Budget retry " + stamp, type: "checking", amount: "100")
        let title = "Retry budget " + stamp
        prepareBudget(title, accounts: [checking])
        let before = try faultStatus(arm: true)
        tapVisible(app.buttons["budget.save"])
        XCTAssertTrue(app.buttons["loop.pending.retry"].waitForExistence(timeout: 30))
        XCTAssertEqual(try faultStatus(arm: false), before + 1)
        app.terminate(); app.launch()
        app.openPlanSurface()
        tapVisible(app.scrollViews["screen.plan"].buttons["loop.pending.retry"])
        XCTAssertTrue(app.buttons["loop.pending.retry"].waitForNonExistence(timeout: 20))
        openBudget(title)
        assertBudget(spent: "0.00", status: "150.00")
        XCTAssertEqual(try faultStatus(arm: false), before + 1)
        capture("budget-exact-command-recovered-once")
        app.returnFromDetail("budget.close")
        XCTAssertEqual(planCards("budget", title).count, 1)
    }

    func budgetExpense(amount: String, note: String) {
        tapVisible(app.buttons["accounts.record"])
        tapVisible(app.buttons["loop.kind.expense"])
        fillMoneyField("loop.amount", with: amount)
        dismissMoneyKeyboard()
        tapVisible(app.buttons["loop.category"])
        app.buttons["Groceries"].tap()
        fillMoneyField("loop.note", with: note)
        dismissMoneyKeyboard(); confirmMoney()
    }

    func prepareBudget(_ title: String, accounts: [MoneyAccount]) {
        app.openPlanSurface()
        startPlan("budget")
        fillMoneyField("budget.name", with: title)
        fillMoneyField("budget.limit", with: "150")
        dismissMoneyKeyboard()
        tapVisible(app.buttons["budget.currency"])
        app.buttons["DOP"].tap()
        for account in accounts { tapVisible(app.switches["budget.account." + account.id]) }
        tapVisible(app.switches["budget.category.groceries"])
    }

    func createBudget(_ title: String, accounts: [MoneyAccount]) {
        prepareBudget(title, accounts: accounts)
        tapVisible(app.buttons["budget.save"])
        XCTAssertTrue(app.buttons["budget.save"].waitForNonExistence(timeout: 15))
    }

    func openBudget(_ title: String) {
        app.openPlanSurface()
        let row = planCards("budget", title).firstMatch
        tapVisible(row)
        XCTAssertTrue(app.staticTexts["budget.spent"].waitForExistence(timeout: 15))
    }

    func assertBudget(spent: String, status: String, over: Bool = false) {
        let detail = app.descendants(matching: .any)["budget.detail"]
        let amount = detail.staticTexts["budget.spent"]
        let remaining = detail.descendants(matching: .any)["budget.remaining"]
        let direction = over ? "over budget" : "remaining"
        let expected = NSPredicate { _, _ in
            amount.exists && amount.label == "DOP " + spent
                && remaining.exists && remaining.label.contains(status)
                && remaining.label.contains(direction)
        }
        let result = XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: expected, object: nil)], timeout: 15)
        XCTAssertEqual(result, .completed,
                       "Expected spent DOP \(spent) and \(status) \(direction); actual spent: \(amount.exists ? amount.label : "<missing>"), status: \(remaining.exists ? remaining.label : "<missing>")")
    }
}
