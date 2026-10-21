import XCTest

extension FinancialLoopUITests {
    func testConnectedSearchOpensActualEditorsAndPreservesOrigin() throws {
        try signIn(fresh: true)
        let stamp = String(UUID().uuidString.prefix(6))
        let bank = createMoneyAccount("Search bank " + stamp, type: "checking", amount: "100")
        let note = "Search income " + stamp
        recordMoney(kind: "income", amount: "25", note: note)
        let bill = "Search bill " + stamp
        addPlanExpectation(bill, kind: "Bill", amount: "30", account: bank)
        searchFor(bank.name, kind: "account")
        chooseSearchCurrency("DOP")
        let bankRow = searchRow(bank.name)
        tapVisible(bankRow)
        // Connected keeps Home account detail mounted; scope in-detail chrome to search.detail.
        // AccountForm / expectation editors present as sheets outside that subtree.
        let searchDetail = app.descendants(matching: .any)["search.detail"]
        XCTAssertTrue(searchDetail.waitForExistence(timeout: 10))
        XCTAssertTrue(searchDetail.buttons["accounts.edit"].waitForExistence(timeout: 10))
        tapVisible(searchDetail.buttons["accounts.edit"])
        replaceMoneyField("accounts.nickname", with: "Revised bank " + stamp)
        dismissMoneyKeyboard(); tapVisible(app.buttons["accounts.save"])
        XCTAssertTrue(app.buttons["accounts.save"].waitForNonExistence(timeout: 15))
        searchBack()
        XCTAssertTrue(app.staticTexts["search.empty"].waitForExistence(timeout: 10))
        XCTAssertEqual(app.textFields["search.query"].value as? String, bank.name)
        XCTAssertTrue(app.staticTexts["search.filter-summary"].label.contains("DOP"))
        capture("search-account-edit-removes-old-match")

        searchFor(note, kind: "activity")
        let activityRow = searchRow(note)
        XCTAssertTrue(activityRow.waitForExistence(timeout: 10))
        let activityIdentifier = activityRow.identifier
        tapVisible(activityRow)
        XCTAssertTrue(searchDetail.waitForExistence(timeout: 10))
        tapVisible(searchDetail.buttons["activity.correct"])
        replaceMoneyField("loop.amount", with: "27")
        fillMoneyField("loop.reason", with: "Corrected income receipt")
        dismissMoneyKeyboard(); confirmPlanMoney()
        assertText("DOP 27.00")
        searchBack()
        let corrected = NSPredicate(format: "exists == true AND label CONTAINS '27.00'")
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: corrected, object: app.buttons[activityIdentifier])], timeout: 10), .completed)
        XCTAssertEqual(app.textFields["search.query"].value as? String, note)
        capture("search-activity-correction-return")

        searchFor(bill, kind: "expectation")
        tapVisible(searchRow(bill))
        XCTAssertTrue(app.textFields["plan.expectation.name"].waitForExistence(timeout: 10))
        replaceMoneyField("plan.expectation.amount", with: "35")
        dismissMoneyKeyboard(); tapVisible(app.buttons["plan.expectation.save"])
        XCTAssertTrue(app.textFields["plan.expectation.name"].waitForNonExistence(timeout: 15))
        let updated = NSPredicate(format: "label CONTAINS '35.00'")
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: updated, object: searchRow(bill))], timeout: 10), .completed)
        XCTAssertEqual(app.textFields["search.query"].value as? String, bill)
        capture("search-plan-expectation-editor-return")
        app.terminate()
        app.launchArguments = ["-AppleLanguages", "(es-419)", "-AppleLocale", "es_DO", "-appearancePreference", "light"]
        app.launch(); app.buttons["tab.search"].tap()
        XCTAssertTrue(searchRow(bill).waitForExistence(timeout: 20))
        XCTAssertEqual(app.textFields["search.query"].value as? String, bill)
        XCTAssertTrue(searchRow(bill).label.contains("35.00"))
        capture("search-spanish-light-relaunch")
    }

    func testSearchMultiplePagesKeepScrollOnBackAndRelaunch() throws {
        try signIn(fresh: true)
        let query: String
        if let seeded = ProcessInfo.processInfo.environment["ARGUS_TEST_SEARCH_QUERY"] { query = seeded }
        else {
            query = "Search pages " + String(UUID().uuidString.prefix(6))
            for index in 0..<23 { _ = createMoneyAccount(query + String(format: " %02d", index), type: "checking") }
        }
        searchFor(query, kind: "account")
        chooseSearchCurrency("DOP")
        let more = app.buttons["search.more"]
        for _ in 0..<16 { if more.isHittable { break }; app.scrollViews["search.results"].swipeUp() }
        tapVisible(more)
        XCTAssertTrue(more.waitForNonExistence(timeout: 15))
        app.scrollViews["search.results"].swipeUp()
        let visible = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'search.row.account.'")).allElementsBoundByIndex
            .filter { $0.isHittable && $0.frame.midY > 320 && $0.frame.midY < app.frame.height - 140 }
        let row = try XCTUnwrap(visible.last)
        let identifier = row.identifier
        let before = row.frame
        row.tap(); XCTAssertTrue(app.scrollViews["search.detail"].waitForExistence(timeout: 10))
        searchBack()
        assertSearchFrame(identifier, y: before.minY)
        XCTAssertEqual(app.textFields["search.query"].value as? String, query)
        XCTAssertTrue(app.staticTexts["search.filter-summary"].label.contains("DOP"))
        capture("search-second-page-exact-return")
        for attempt in 1...2 {
            app.terminate(); app.launch(); app.buttons["tab.search"].tap()
            assertSearchFrame(identifier, y: before.minY)
            XCTAssertFalse(app.buttons["search.more"].exists)
            capture("search-second-page-relaunch-\(attempt)")
        }
    }

    func testSearchOwnerSwitchClearsOriginAndResults() throws {
        try signIn(fresh: true)
        let name = "Private search " + String(UUID().uuidString.prefix(6))
        _ = createMoneyAccount(name, type: "checking")
        searchFor(name, kind: "account")
        XCTAssertTrue(searchRow(name).waitForExistence(timeout: 10))
        try signIn(fresh: true, user: "B")
        app.buttons["tab.search"].tap()
        XCTAssertTrue(app.textFields["search.query"].waitForExistence(timeout: 10))
        XCTAssertNotEqual(app.textFields["search.query"].value as? String, name)
        searchFor(name, kind: "account")
        XCTAssertTrue(app.staticTexts["search.empty"].waitForExistence(timeout: 10))
        XCTAssertFalse(searchRow(name).exists)
        capture("search-owner-isolation")
    }

    func testSearchLoadingRetryAndUnavailableDestination() throws {
        try requireResponseLossProxy()
        try signIn(fresh: true)
        let bank = createMoneyAccount("Search recovery " + String(UUID().uuidString.prefix(6)), type: "checking")
        searchFor(bank.name, kind: "account")
        XCTAssertTrue(searchRow(bank.name).waitForExistence(timeout: 10))
        try armSearchRead(path: "/api/v1/financial-search", status: 0, delay: 8000)
        app.buttons["search.filter.all"].tap()
        XCTAssertTrue(app.descendants(matching: .any)["search.loading"].waitForExistence(timeout: 5))
        capture("search-loading")
        XCTAssertTrue(app.descendants(matching: .any)["search.loading"].waitForNonExistence(timeout: 10))
        try armSearchRead(path: "/api/v1/financial-search", status: 503)
        app.buttons["search.filter.account"].tap()
        XCTAssertTrue(app.staticTexts["search.error"].waitForExistence(timeout: 10))
        capture("search-error-retry")
        app.buttons["search.retry"].tap()
        XCTAssertTrue(searchRow(bank.name).waitForExistence(timeout: 10))
        try armSearchRead(path: "/api/v1/financial-accounts/", status: 404)
        tapVisible(searchRow(bank.name))
        XCTAssertTrue(app.staticTexts["search.destination.error"].waitForExistence(timeout: 10))
        XCTAssertFalse(app.scrollViews["search.detail"].exists)
        XCTAssertEqual(app.textFields["search.query"].value as? String, bank.name)
        capture("search-unavailable-destination")
    }

    func testSearchAccountRemainsIndependentWhenSwitchingAccountsTabs() throws {
        try signIn(fresh: true)
        func activity(_ note: String) -> XCUIElement {
            app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'activity.row.' AND label CONTAINS %@", note)).firstMatch
        }
        let stamp = String(UUID().uuidString.prefix(6))
        let first = createMoneyAccount("Search tab A " + stamp, type: "checking", amount: "100")
        let firstNote = "Only account A " + stamp
        recordMoney(kind: "income", amount: "11", note: firstNote)
        let second = createMoneyAccount("Accounts tab B " + stamp, type: "checking", amount: "200")
        let secondNote = "Only account B " + stamp
        recordMoney(kind: "income", amount: "22", note: secondNote)
        searchFor(first.name, kind: "account")
        tapVisible(searchRow(first.name))
        XCTAssertTrue(activity(firstNote).waitForExistence(timeout: 10))
        searchBack()
        app.openAccountsList()
        assertText(second.name)
        XCTAssertTrue(activity(secondNote).waitForExistence(timeout: 10))
        XCTAssertFalse(activity(firstNote).exists)
        scrollMoneyTop(); app.accountBack.tap()
        app.buttons["tab.search"].tap()
        tapVisible(searchRow(first.name))
        assertText(first.name)
        XCTAssertTrue(activity(firstNote).waitForExistence(timeout: 10))
        XCTAssertFalse(app.staticTexts["search.destination.unavailable"].exists)
        searchBack()
        openMoneyAccount(second)
        XCTAssertTrue(activity(secondNote).waitForExistence(timeout: 10))
        app.buttons["tab.search"].tap()
        tapVisible(searchRow(first.name))
        XCTAssertTrue(activity(firstNote).waitForExistence(timeout: 10))
        XCTAssertFalse(activity(secondNote).exists)
        tapVisible(app.buttons["accounts.edit"])
        replaceMoneyField("accounts.nickname", with: first.name + " revised")
        dismissMoneyKeyboard(); tapVisible(app.buttons["accounts.save"])
        XCTAssertTrue(app.buttons["accounts.save"].waitForNonExistence(timeout: 15))
        searchBack()
        app.openAccountsList()
        assertText(second.name)
        XCTAssertTrue(activity(secondNote).waitForExistence(timeout: 10))
        app.buttons["tab.search"].tap()
        tapVisible(searchRow(first.name + " revised"))
        assertText(first.name + " revised")
        XCTAssertTrue(activity(firstNote).waitForExistence(timeout: 10))
        capture("search-accounts-independent-detail-identities")
    }

    func testSearchKeepsApprovedPerspectivesWithoutSampleResults() throws {
        try signIn(fresh: true)
        let account = createMoneyAccount("Search perspective " + String(UUID().uuidString.prefix(6)), type: "checking")
        searchFor(account.name, kind: "account")
        chooseSearchCurrency("DOP")
        XCTAssertTrue(searchRow(account.name).waitForExistence(timeout: 10))
        for kind in ["chats", "files"] {
            let button = app.buttons["search.filter." + kind]
            for _ in 0..<3 {
                if button.isHittable { break }
                app.scrollViews["search.kinds"].swipeLeft()
            }
            tapVisible(button)
            XCTAssertTrue(app.staticTexts["search.empty"].waitForExistence(timeout: 10))
            XCTAssertFalse(app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'search.row.'")).firstMatch.exists)
            XCTAssertEqual(app.textFields["search.query"].value as? String, account.name)
            XCTAssertFalse(app.descendants(matching: .any)["search.loading"].exists)
        }
        app.scrollViews["search.kinds"].swipeRight()
        tapVisible(app.buttons["search.filter.account"])
        XCTAssertTrue(searchRow(account.name).waitForExistence(timeout: 10))
        XCTAssertTrue(app.staticTexts["search.filter-summary"].label.contains("DOP"))
        capture("search-approved-perspectives-real-records-only")
    }

    private func searchFor(_ query: String, kind: String) {
        app.revealConnectedTabBar()
        app.buttons["tab.search"].tap()
        let field = app.textFields["search.query"]
        XCTAssertTrue(field.waitForExistence(timeout: 10))
        field.tap()
        if app.buttons["search.clear"].exists { app.buttons["search.clear"].tap(); field.tap() }
        field.typeText(query + "\n")
        if ["expectation", "budget", "goal", "debt"].contains(kind) {
            chooseSearchPlans()
        } else {
            app.buttons["search.filter." + kind].tap()
        }
    }
    private func searchRow(_ label: String) -> XCUIElement {
        app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'search.row.' AND label CONTAINS %@", label)).firstMatch
    }
    private func chooseSearchCurrency(_ currency: String) {
        app.buttons["search.filters"].tap()
        app.buttons["search.currency"].tap(); app.buttons[currency].tap()
        app.buttons["search.filters.done"].tap()
    }
    func chooseSearchPlans() {
        let summary = app.staticTexts["search.filter-summary"]
        let previousSummary = summary.exists ? summary.label : nil
        tapVisible(app.buttons["search.filter.plans"])
        XCTAssertTrue(app.buttons["search.filter.plans"].isSelected)
        XCTAssertEqual(summary.exists ? summary.label : nil, previousSummary,
                       "Changing perspective must preserve the currency filter")
    }
    func searchBack() {
        let detail = app.scrollViews["search.detail"]
        XCTAssertTrue(detail.waitForExistence(timeout: 10))
        tapVisible(app.navigationBars.buttons.element(boundBy: 0))
        XCTAssertTrue(detail.waitForNonExistence(timeout: 10))
    }
    private func assertSearchFrame(_ identifier: String, y: CGFloat) {
        let row = app.buttons[identifier]
        let restored = NSPredicate { _, _ in row.exists && row.isHittable && abs(row.frame.minY - y) < 3 }
        let result = XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: restored, object: nil)], timeout: 20)
        if result != .completed { capture("search-scroll-mismatch") }
        XCTAssertEqual(result, .completed, "Expected row y=\(y), actual=\(row.exists ? row.frame.minY : -1)")
    }
    private func armSearchRead(path: String, status: Int, delay: Int = 0) throws {
        let endpoint = try XCTUnwrap(ProcessInfo.processInfo.environment["ARGUS_TEST_FAULT_URL"])
            .replacingOccurrences(of: "/__fault", with: "/__read_fault")
        var request = URLRequest(url: try XCTUnwrap(URL(string: endpoint)))
        request.httpMethod = "POST"; request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: ["path_prefix": path, "status": status, "delay_ms": delay])
        let finished = expectation(description: "Arm one local read fault")
        var code: Int?
        URLSession.shared.dataTask(with: request) { _, response, _ in code = (response as? HTTPURLResponse)?.statusCode; finished.fulfill() }.resume()
        wait(for: [finished], timeout: 10)
        XCTAssertEqual(code, 200)
    }
}
