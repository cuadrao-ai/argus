import XCTest

extension FinancialLoopUITests {
    func testPlanCardKeepsItsOriginAfterCloseAndRelaunch() throws {
        try signIn()
        let stamp = String(UUID().uuidString.prefix(5))
        let account = createMoneyAccount("Plan card " + stamp, type: "savings", amount: "100")
        let title = "Return to Plan " + stamp
        app.revealConnectedTabBar()
        prepareGoal(title, destination: account)
        tapVisible(app.buttons["goal.save"])
        XCTAssertTrue(app.buttons["goal.save"].waitForNonExistence(timeout: 15))
        let card = planCards("goal", title).firstMatch
        tapVisible(card)
        assertGoal("DOP 0.00")
        XCTAssertTrue(app.navigationBars.buttons["BackButton"].waitForExistence(timeout: 5))
        app.swipeBack(cancel: true)
        assertGoal("DOP 0.00")
        XCTAssertFalse(app.buttons["tab.home"].exists)
        app.swipeBack()
        XCTAssertTrue(card.waitForExistence(timeout: 10))
        tapVisible(card)
        assertGoal("DOP 0.00")
        app.terminate(); app.launch()
        assertGoal("DOP 0.00")
        tapVisible(app.buttons["goal.allocate"])
        let allocation = app.textFields.matching(NSPredicate(format: "identifier BEGINSWITH 'goal.allocation.amount.'")).firstMatch
        XCTAssertTrue(allocation.waitForExistence(timeout: 10))
        app.buttons["goal.action.cancel"].tap()
        tapVisible(app.buttons["goal.record"])
        XCTAssertTrue(app.textFields["loop.amount"].waitForExistence(timeout: 10))
        app.navigationBars.buttons["Cancel"].tap()
        app.returnFromDetail("goal.close")
        XCTAssertTrue(card.waitForExistence(timeout: 10))
        capture("plan-card-returned-to-overview")
        _ = openGoal(title)
        app.terminate(); app.launch()
        assertGoal("DOP 0.00")
        app.returnFromDetail("goal.close")
        XCTAssertTrue(card.waitForExistence(timeout: 10))
    }

    func testConnectedGoalAllocationContributionCorrectionSearchAndRestore() throws {
        try signIn()
        let stamp = String(UUID().uuidString.prefix(5))
        let source = createMoneyAccount("Goal funding " + stamp, type: "checking", amount: "1000")
        let destination = createMoneyAccount("Goal savings " + stamp, type: "savings", amount: "1000")
        let title = "Emergency " + stamp
        prepareGoal(title, destination: destination)
        tapVisible(app.buttons["goal.save"])
        XCTAssertTrue(app.buttons["goal.save"].waitForNonExistence(timeout: 15))
        let id = openGoal(title)
        assertGoal("DOP 0.00")
        verifyGoalSheetCancellation()
        tapVisible(app.buttons["goal.allocate"])
        let amount = "goal.allocation.amount." + id
        replaceMoneyField(amount, with: "600")
        dismissMoneyKeyboard(); tapVisible(app.buttons["goal.allocation.save"])
        assertGoal("DOP 600.00")
        capture("goal-existing-allocation-backed")
        tapVisible(app.buttons["goal.record"])
        chooseMoneyAccount("loop.source", account: source)
        replaceMoneyField("loop.amount", with: "200")
        dismissMoneyKeyboard(); reviewMoney(); tapVisible(app.buttons["loop.confirm"])
        XCTAssertTrue(app.buttons["loop.confirm"].waitForNonExistence(timeout: 15))
        assertGoal("DOP 800.00")
        capture("goal-recorded-contribution-once")
        let contribution = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'goal.activity.' AND identifier != 'goal.activity.back'")).firstMatch
        tapVisible(contribution)
        tapVisible(app.buttons["activity.correct"])
        replaceMoneyField("loop.amount", with: "150")
        fillMoneyField("loop.reason", with: "Correct contribution amount")
        dismissMoneyKeyboard(); reviewMoney(); tapVisible(app.buttons["loop.confirm"])
        XCTAssertTrue(app.buttons["loop.confirm"].waitForNonExistence(timeout: 15))
        app.returnFromDetail("goal.activity.back")
        assertGoal("DOP 750.00")
        capture("goal-original-correction-propagated")
        let release = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'goal.release.' AND identifier != 'goal.release.confirm'")).firstMatch
        tapVisible(release)
        app.buttons.matching(identifier: "goal.release.confirm").firstMatch.tap()
        assertGoal("DOP 600.00")
        tapVisible(app.buttons["goal.link"])
        let candidate = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'goal.candidate.' AND label CONTAINS %@", title)).firstMatch
        tapVisible(candidate); tapVisible(app.buttons["goal.link.confirm"])
        assertGoal("DOP 750.00")
        capture("goal-released-original-relinked-once")
        choosePlanDetailAction("goal.edit")
        replaceMoneyField("goal.target", with: "2500")
        dismissMoneyKeyboard(); tapVisible(app.buttons["goal.save"])
        XCTAssertTrue(app.buttons["goal.save"].waitForNonExistence(timeout: 15))
        assertGoal("DOP 750.00")
        tapVisible(app.buttons["The details, clearly"])
        assertText("DOP 2,500.00")
        capture("goal-target-edited")
        choosePlanDetailAction("goal.archive")
        app.buttons.matching(identifier: "goal.archive.confirm").firstMatch.tap()
        XCTAssertTrue(app.buttons["goal.restore"].waitForExistence(timeout: 15))
        tapVisible(app.buttons["goal.restore"])
        assertGoal("DOP 750.00")
        app.returnFromDetail("goal.close")
        verifyGoalSearch(title, supported: "DOP 750.00")
    }

    func testGoalResponseLossRecoversExactCommandAfterRelaunch() throws {
        try requireResponseLossProxy()
        try signIn()
        let stamp = String(UUID().uuidString.prefix(5))
        let destination = createMoneyAccount("Goal retry " + stamp, type: "savings", amount: "1000")
        let title = "Retry goal " + stamp
        prepareGoal(title, destination: destination)
        let before = try faultStatus(arm: true)
        tapVisible(app.buttons["goal.save"])
        XCTAssertTrue(app.buttons["loop.pending.retry"].waitForExistence(timeout: 30))
        XCTAssertEqual(try faultStatus(arm: false), before + 1)
        app.terminate(); app.launch()
        app.openPlanSurface()
        tapVisible(app.scrollViews["screen.plan"].buttons["loop.pending.retry"])
        XCTAssertTrue(app.buttons["loop.pending.retry"].waitForNonExistence(timeout: 20))
        _ = openGoal(title)
        assertGoal("DOP 0.00")
        XCTAssertEqual(try faultStatus(arm: false), before + 1)
        capture("goal-exact-command-recovered-once")
        app.returnFromDetail("goal.close")
        XCTAssertEqual(planCards("goal", title).count, 1)
    }

    func testGoalContributionResponseLossRecoversOneTransferAfterRelaunch() throws {
        try requireResponseLossProxy()
        try signIn()
        let stamp = String(UUID().uuidString.prefix(5))
        let source = createMoneyAccount("Contribution source " + stamp, type: "checking", amount: "1000")
        let destination = createMoneyAccount("Contribution savings " + stamp, type: "savings", amount: "1000")
        let title = "Contribution retry " + stamp
        prepareGoal(title, destination: destination)
        tapVisible(app.buttons["goal.save"])
        XCTAssertTrue(app.buttons["goal.save"].waitForNonExistence(timeout: 15))
        _ = openGoal(title)
        tapVisible(app.buttons["goal.record"])
        chooseMoneyAccount("loop.source", account: source)
        replaceMoneyField("loop.amount", with: "200")
        dismissMoneyKeyboard(); reviewMoney()
        let before = try faultStatus(arm: true)
        tapVisible(app.buttons["loop.confirm"])
        XCTAssertTrue(app.staticTexts["loop.error"].waitForExistence(timeout: 30))
        XCTAssertEqual(try faultStatus(arm: false), before + 1)
        app.terminate(); app.launch()
        tapVisible(app.buttons["loop.pending.retry"])
        XCTAssertTrue(app.buttons["loop.pending.retry"].waitForNonExistence(timeout: 20))
        assertGoal("DOP 200.00")
        XCTAssertEqual(app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'goal.activity.' AND identifier != 'goal.activity.back'")).count, 1)
        XCTAssertEqual(try faultStatus(arm: false), before + 1)
        capture("goal-transfer-recovered-once-after-relaunch")
        app.returnFromDetail("goal.close")
        openMoneyAccount(source); assertText("DOP 800.00")
        openMoneyAccount(destination); assertText("DOP 1,200.00")
    }

    func testExistingGoalHomeSearchSpanishAndReopen() throws {
        guard let title = ProcessInfo.processInfo.environment["ARGUS_TEST_SEARCH_QUERY"],
              let amount = ProcessInfo.processInfo.environment["ARGUS_TEST_GOAL_SUPPORTED"] else {
            throw XCTSkip("Requires the retained isolated goal journey and expected supported amount.")
        }
        try signIn()
        app.buttons["tab.home"].tap()
        let row = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'goal.row.home.' AND label CONTAINS %@", title)).firstMatch
        tapVisible(row); assertGoal(amount)
        verifyGoalSheetCancellation()
        capture("goal-home-recorded-progress")
        app.returnFromDetail("goal.close")
        verifyGoalSearch(title, supported: amount)
    }

    func testRetainedGoalSearchSpanishAndReopen() throws {
        guard let title = ProcessInfo.processInfo.environment["ARGUS_TEST_SEARCH_QUERY"],
              let amount = ProcessInfo.processInfo.environment["ARGUS_TEST_GOAL_SUPPORTED"] else {
            throw XCTSkip("Requires the retained isolated goal journey and expected supported amount.")
        }
        try signIn()
        _ = openGoal(title)
        assertGoal(amount)
        app.returnFromDetail("goal.close")
        verifyGoalSearch(title, supported: amount)
    }

    private func verifyGoalSheetCancellation() {
        for action in ["goal.link", "goal.allocate"] {
            tapVisible(app.buttons[action])
            let cancel = app.buttons["goal.action.cancel"]
            XCTAssertTrue(cancel.waitForExistence(timeout: 15))
            cancel.tap()
            XCTAssertTrue(cancel.waitForNonExistence(timeout: 5))
            XCTAssertTrue(app.buttons[action].isHittable)
        }
    }

    func prepareGoal(_ title: String, destination: MoneyAccount) {
        app.openPlanSurface()
        startPlan("goal")
        fillMoneyField("goal.name", with: title)
        fillMoneyField("goal.target", with: "2000")
        dismissMoneyKeyboard()
        chooseMoneyAccount("goal.destination", account: destination)
    }

    @discardableResult func openGoal(_ title: String) -> String {
        app.openPlanSurface()
        let row = planCards("goal", title).firstMatch
        XCTAssertTrue(row.waitForExistence(timeout: 15))
        let id = String(row.identifier.dropFirst("plan.card.goal.".count))
        tapVisible(row)
        XCTAssertTrue(app.descendants(matching: .any)["goal.detail"].staticTexts["goal.supported"].waitForExistence(timeout: 15))
        return id
    }

    func assertGoal(_ amount: String) {
        let value = app.descendants(matching: .any)["goal.detail"].staticTexts["goal.supported"]
        XCTAssertTrue(value.waitForExistence(timeout: 15))
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == %@", amount), object: value)], timeout: 15), .completed)
    }

    private func verifyGoalSearch(_ title: String, supported: String) {
        app.revealConnectedTabBar()
        app.buttons["tab.search"].tap()
        let query = app.textFields["search.query"]
        XCTAssertTrue(query.waitForExistence(timeout: 10)); query.tap()
        if app.buttons["search.clear"].exists { app.buttons["search.clear"].tap(); query.tap() }
        query.typeText(title + "\n")
        chooseSearchPlans()
        let hit = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'search.row.goal.' AND label CONTAINS %@", title)).firstMatch
        tapVisible(hit); assertGoal(supported)
        app.terminate(); app.launch(); assertGoal(supported)
        capture("goal-detail-restored-after-relaunch")
        app.returnFromDetail("goal.close")
        XCTAssertEqual(app.textFields["search.query"].value as? String, title)
        XCTAssertTrue(app.buttons["search.filter.plans"].isSelected)
        XCTAssertTrue(hit.waitForExistence(timeout: 15)); capture("goal-search-origin-restored")
        tapVisible(hit)
        app.terminate(); app.launchArguments = ["-AppleLanguages", "(es-419)", "-AppleLocale", "es_DO", "-appearancePreference", "light"]
        app.launch()
        XCTAssertTrue(app.staticTexts["goal.supported"].waitForExistence(timeout: 15))
        XCTAssertFalse(app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH 'goal.'")).firstMatch.exists)
        capture("goal-spanish-detail")
        app.returnFromDetail("goal.close")
    }
}
