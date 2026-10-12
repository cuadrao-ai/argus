import XCTest

/// Search and calculations in the on-device book: a pure index over accounts, activity and plans, plan what-ifs from the
/// package's Decimal calculator, and per-currency totals. No server is involved.
extension FinancialLoopUITests {
    private func addAccount(type: String, name: String, currency: String? = nil, amount: String? = nil) {
        tapVisible(app.buttons["accounts.add"])
        XCTAssertTrue(app.buttons["guest.account.type.\(type)"].waitForExistence(timeout: 10))
        app.buttons["guest.account.type.\(type)"].tap()
        let field = app.textFields["guest.account.name"]
        field.tap()
        field.typeText(name)
        if let currency {
            app.buttons["guest.account.currency"].tap()
            let search = app.searchFields.firstMatch
            XCTAssertTrue(search.waitForExistence(timeout: 10))
            search.tap()
            search.typeText(currency)
            app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", currency)).firstMatch.tap()
            XCTAssertTrue(app.buttons["guest.account.currency"].waitForExistence(timeout: 5))
        }
        if let amount {
            app.textFields["guest.account.amount"].tap()
            app.textFields["guest.account.amount"].typeText(amount)
        }
        dismissGuestKeyboard()
        app.buttons["guest.account.save"].tap()
        XCTAssertTrue(app.buttons["guest.account.save"].waitForNonExistence(timeout: 10))
    }

    private func recordMovement(kind: String = "expense", amount: String, note: String, category: String? = nil) {
        app.buttons["nav.add"].tap()
        XCTAssertTrue(app.buttons["add.tray.transaction"].waitForExistence(timeout: 5))
        app.buttons["add.tray.transaction"].tap()
        XCTAssertTrue(app.buttons["guest.movement.save"].waitForExistence(timeout: 10))
        app.buttons["guest.movement.kind." + kind].tap()
        app.textFields["guest.movement.amount"].tap()
        app.textFields["guest.movement.amount"].typeText(amount)
        dismissGuestKeyboard()
        if let category {
            app.buttons["guest.movement.category"].tap()
            app.buttons[category].tap()
        }
        app.textFields["guest.movement.note"].tap()
        app.textFields["guest.movement.note"].typeText(note)
        dismissGuestKeyboard()
        app.buttons["guest.movement.save"].tap()
        XCTAssertTrue(app.buttons["guest.movement.save"].waitForNonExistence(timeout: 10))
    }

    private func createPlan(kind: String, name: String, target: String, monthly: String? = nil) {
        app.buttons["nav.add"].tap()
        XCTAssertTrue(app.buttons["add.tray.plan"].waitForExistence(timeout: 5))
        app.buttons["add.tray.plan"].tap()
        XCTAssertTrue(app.buttons["guest.plan.kind." + kind].waitForExistence(timeout: 10))
        app.buttons["guest.plan.kind." + kind].tap()
        for (id, text) in [("guest.plan.name", name), ("guest.plan.target", target), ("guest.plan.monthly", monthly ?? "")] where !text.isEmpty {
            let field = app.textFields[id]
            XCTAssertTrue(field.waitForExistence(timeout: 10), id)
            field.tap()
            field.typeText(text)
            dismissGuestKeyboard()
        }
        tapVisible(app.buttons["guest.plan.save"])
        XCTAssertTrue(app.buttons["guest.plan.save"].waitForNonExistence(timeout: 10))
    }

    private func search(_ text: String) {
        let field = app.textFields["search.query"]
        XCTAssertTrue(field.waitForExistence(timeout: 10))
        field.tap()
        field.typeText(text)
    }

    private func results(_ prefix: String) -> XCUIElementQuery {
        app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@", prefix))
    }

    func testGuestSearchFindsAccountsActivityAndPlansWithoutCaseOrAccents() throws {
        launchSignedOut(arguments: ["--cuadrao-guest-book"], language: "es-419")
        enterGuestBook()
        addAccount(type: "checking", name: "Ahorros del Año", currency: "USD", amount: "1000")
        addAccount(type: "cash", name: "Efectivo", currency: "JPY", amount: "5000")
        recordMovement(amount: "12.34", note: "Café con leche", category: "Comida fuera")
        createPlan(kind: "goal", name: "Viaje a Japón", target: "1500", monthly: "250")
        for _ in 0..<3 { app.swipeDown(velocity: .fast) }
        app.buttons["tab.search"].tap()
        XCTAssertTrue(app.textFields["search.query"].waitForExistence(timeout: 10))
        XCTAssertFalse(app.buttons["search.filter.chats"].exists)
        XCTAssertFalse(app.buttons["search.filter.files"].exists)
        XCTAssertFalse(app.buttons["search.filter.memory"].exists, "the book has no chats, files or memory")
        for id in ["search.filter.all", "search.filter.account", "search.filter.activity", "search.filter.plans"] {
            XCTAssertTrue(app.buttons[id].exists, id)
        }
        XCTAssertEqual(results("guest.search.").count, 4, "everything is listed before a query")
        capture("guest-search-all-es")

        search("ANO")
        XCTAssertEqual(results("guest.search.account.").count, 1, "case and accents do not matter")
        XCTAssertEqual(results("guest.search.movement.").count, 0)
        app.buttons["search.clear"].tap()
        search("cafe")
        XCTAssertEqual(results("guest.search.movement.").count, 1, "Café is found by cafe")
        app.buttons["search.clear"].tap()
        search("japon")
        XCTAssertEqual(results("guest.search.plan.").count, 1)
        capture("guest-search-query-es")
        app.buttons["search.clear"].tap()
        search("12.34")
        XCTAssertEqual(results("guest.search.movement.").count, 1, "an amount is searchable as it is written")
        app.buttons["search.clear"].tap()

        // Scopes and the currency filter narrow the list.
        app.buttons["search.filter.activity"].tap()
        XCTAssertEqual(results("guest.search.").count, 1)
        app.buttons["search.filter.plans"].tap()
        XCTAssertEqual(results("guest.search.plan.").count, 1)
        app.buttons["search.filter.all"].tap()
        app.buttons["search.filters"].tap()
        XCTAssertTrue(app.buttons["Moneda"].waitForExistence(timeout: 5) || app.pickers.firstMatch.exists || app.staticTexts["Moneda"].exists)
        capture("guest-search-filters-es")
    }

    func testGuestSearchOpensAResultInItsOwnTabAndFiltersByCurrency() throws {
        launchSignedOut(arguments: ["--cuadrao-guest-book"])
        enterGuestBook()
        addAccount(type: "checking", name: "Main", currency: "USD", amount: "1000")
        addAccount(type: "cash", name: "Yen cash", currency: "JPY", amount: "5000")
        recordMovement(amount: "20", note: "Taxi", category: "Transport")
        createPlan(kind: "budget", name: "Food", target: "300")
        for _ in 0..<3 { app.swipeDown(velocity: .fast) }
        app.buttons["tab.search"].tap()
        XCTAssertEqual(results("guest.search.").count, 4)

        app.buttons["search.filters"].tap()
        let currency = app.buttons["Currency"].firstMatch
        XCTAssertTrue(currency.waitForExistence(timeout: 5))
        currency.tap()
        app.buttons["JPY"].firstMatch.tap()
        capture("guest-search-currency-filter")
        app.buttons["search.filters.done"].tap()
        XCTAssertEqual(results("guest.search.").count, 1, "only the yen account")
        XCTAssertTrue(app.staticTexts["search.filter-summary"].exists)
        app.buttons["Clear filters"].tap()
        XCTAssertEqual(results("guest.search.").count, 4)

        search("taxi")
        results("guest.search.movement.").firstMatch.tap()
        XCTAssertTrue(app.descendants(matching: .any)["guest.movement.detail"].waitForExistence(timeout: 10), "a movement opens on Home")
        XCTAssertEqual(app.staticTexts["guest.movement.title"].label, "Taxi")
        app.accountBack.tap()
        app.buttons["tab.search"].tap()
        app.buttons["search.clear"].tap()
        search("food")
        results("guest.search.plan.").firstMatch.tap()
        XCTAssertTrue(app.descendants(matching: .any)["guest.plan.detail"].waitForExistence(timeout: 10), "a plan opens on Plan")
        capture("guest-search-opened-plan")
    }

    func testGuestGoalWhatIfStatesAssumptionsAndAppliesOnlyOnRequest() throws {
        launchSignedOut(arguments: ["--cuadrao-guest-book"])
        enterGuestBook()
        addAccount(type: "checking", name: "Main", currency: "USD", amount: "1000")
        createPlan(kind: "goal", name: "Trip", target: "1200", monthly: "100")
        app.buttons["tab.plan"].tap()
        app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'guest.plan.row.'")).firstMatch.tap()
        XCTAssertTrue(app.staticTexts["guest.whatif.estimate"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.staticTexts["guest.whatif.disclosure"].label.hasPrefix("Assumptions"), app.staticTexts["guest.whatif.disclosure"].label)
        XCTAssertFalse(app.buttons["guest.whatif.apply"].exists, "nothing to apply until an amount is tried")
        let before = app.staticTexts["guest.whatif.estimate"].label
        capture("guest-whatif-start")

        app.buttons["guest.whatif.in6"].tap()
        XCTAssertEqual(app.staticTexts["guest.whatif.amount"].label, "USD 200.00", "1200 over 6 months")
        XCTAssertNotEqual(app.staticTexts["guest.whatif.estimate"].label, before)
        XCTAssertTrue(app.staticTexts["guest.whatif.difference"].label.hasSuffix("earlier"), app.staticTexts["guest.whatif.difference"].label)
        capture("guest-whatif-six-months")
        app.buttons["guest.whatif.reset"].tap()
        XCTAssertEqual(app.staticTexts["guest.whatif.estimate"].label, before, "Reset puts the experiment back")
        app.buttons["guest.whatif.in12"].tap()
        XCTAssertEqual(app.staticTexts["guest.whatif.amount"].label, "USD 100.00")
        XCTAssertFalse(app.buttons["guest.whatif.apply"].exists, "twelve months is today's pace: nothing changes")
        app.buttons["guest.whatif.in3"].tap()
        XCTAssertEqual(app.staticTexts["guest.whatif.amount"].label, "USD 400.00")
        app.buttons["guest.whatif.apply"].tap()
        XCTAssertTrue(app.buttons["guest.whatif.apply"].waitForNonExistence(timeout: 5), "applied: the plan's monthly amount is 400 now")
        app.buttons["plan-detail-options"].tap()
        app.buttons["guest.plan.edit"].tap()
        XCTAssertEqual(app.textFields["guest.plan.monthly"].value as? String, "400.00")
    }

    func testGuestBudgetPaceAndTotalsPerCurrency() throws {
        launchSignedOut(arguments: ["--cuadrao-guest-book"])
        enterGuestBook()
        addAccount(type: "checking", name: "Main", currency: "USD", amount: "1000")
        addAccount(type: "credit_card", name: "Card", currency: "USD", amount: "250.50")
        addAccount(type: "cash", name: "Unknown", currency: "USD")
        addAccount(type: "cash", name: "Yen cash", currency: "JPY", amount: "5000")
        recordMovement(amount: "90", note: "Groceries run", category: "Groceries")
        createPlan(kind: "budget", name: "Month", target: "1000")
        app.buttons["tab.plan"].tap()
        app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'guest.plan.row.'")).firstMatch.tap()
        XCTAssertTrue(app.staticTexts["guest.whatif.pace"].waitForExistence(timeout: 10), "a budget reads its pace so far")
        XCTAssertTrue(app.staticTexts["guest.whatif.disclosure"].label.hasPrefix("Simple projection"), app.staticTexts["guest.whatif.disclosure"].label)
        XCTAssertTrue(app.staticTexts["guest.whatif.verdict"].exists)
        capture("guest-whatif-budget")
        app.accountBack.tap()

        app.buttons["tab.home"].tap()
        for _ in 0..<3 { app.swipeDown(velocity: .fast) }
        app.buttons["home-history-expand"].tap()
        XCTAssertTrue(app.staticTexts["guest.totals.net"].waitForExistence(timeout: 10) || app.descendants(matching: .any)["guest.totals"].waitForExistence(timeout: 10))
        tapVisible(app.staticTexts["guest.totals.net"])
        XCTAssertEqual(app.staticTexts["guest.totals.assets"].label, "910.00", "1000 less the 90 spent")
        XCTAssertEqual(app.staticTexts["guest.totals.owed"].label, "250.50")
        XCTAssertEqual(app.staticTexts["guest.totals.net"].label, "659.50")
        XCTAssertTrue(app.staticTexts["guest.totals.unknown"].exists, "the unknown account is counted, not guessed")
        capture("guest-totals-usd")
    }
}
