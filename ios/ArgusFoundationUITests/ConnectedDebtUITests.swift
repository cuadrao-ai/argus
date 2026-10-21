import XCTest

extension FinancialLoopUITests {
    func testConnectedDebtActualSplitCorrectionReturnAndRelaunch() throws {
        try signIn()
        let stamp = String(UUID().uuidString.prefix(5))
        let funding = createMoneyAccount("Debt funding " + stamp, type: "checking", amount: "2000")
        _ = createMoneyAccount("Loan " + stamp, type: "other_debt", amount: "1000")
        tapVisible(app.buttons["accounts.debt"])
        replaceMoneyField("debt.name", with: "Loan plan " + stamp)
        fillMoneyField("debt.amount", with: "500")
        dismissMoneyKeyboard(); chooseMoneyAccount("debt.source", account: funding)
        tapVisible(app.buttons["debt.save"])
        XCTAssertTrue(app.buttons["debt.save"].waitForNonExistence(timeout: 15))
        openDebt("Loan plan " + stamp)
        assertDebt("DOP -1,000.00")
        tapVisible(app.buttons["debt.record"])
        debtSplit(total: "350", principal: "300", interest: "40", fees: "10")
        reviewDebtPayment()
        if ProcessInfo.processInfo.environment["ARGUS_TEST_RESPONSE_LOSS_PROXY"] == "true" {
            let before = try faultStatus(arm: true)
            tapVisible(app.buttons["loop.confirm"])
            XCTAssertTrue(app.staticTexts["loop.error"].waitForExistence(timeout: 30))
            XCTAssertFalse(app.buttons["Cancel"].isEnabled)
            XCTAssertEqual(try faultStatus(arm: false), before + 1)
            capture("debt-committed-payment-response-lost")
            app.terminate(); app.launch()
            let pending = app.buttons["loop.pending.retry"]
            XCTAssertTrue(pending.waitForExistence(timeout: 20))
            capture("debt-pending-payment-retained-after-relaunch")
            tapVisible(pending)
            XCTAssertTrue(pending.waitForNonExistence(timeout: 20))
            assertDebt("DOP -700.00")
            XCTAssertEqual(app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'debt.activity.' AND identifier != 'debt.activity.back'")).count, 1)
            XCTAssertEqual(try faultStatus(arm: false), before + 1)
            capture("debt-payment-recovered-once")
        } else {
            tapVisible(app.buttons["loop.confirm"])
            XCTAssertTrue(app.buttons["loop.confirm"].waitForNonExistence(timeout: 15))
        }
        assertDebt("DOP -700.00")
        capture("debt-partial-actual-payment")
        let payment = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'debt.activity.' AND identifier != 'debt.activity.back'")).firstMatch
        tapVisible(payment); tapVisible(app.buttons["activity.correct"])
        debtSplit(total: "300", principal: "250", interest: "40", fees: "10")
        fillMoneyField("loop.reason", with: "Actual receipt correction")
        dismissMoneyKeyboard(); reviewDebtPayment(); tapVisible(app.buttons["loop.confirm"])
        XCTAssertTrue(app.buttons["loop.confirm"].waitForNonExistence(timeout: 15))
        app.swipeBack(); assertDebt("DOP -750.00")
        tapVisible(payment); tapVisible(app.buttons["activity.return"])
        assertReturnedMoneyDirection(from: "Loan " + stamp, to: funding.name)
        debtSplit(total: "100", principal: "80", interest: "15", fees: "5")
        reviewDebtPayment(); tapVisible(app.buttons["loop.confirm"])
        XCTAssertTrue(app.buttons["loop.confirm"].waitForNonExistence(timeout: 15))
        app.returnFromDetail("debt.activity.back"); assertDebt("DOP -830.00")
        capture("debt-return-preserves-original-payment")
        app.terminate(); app.launch()
        assertDebt("DOP -830.00")
        tapVisible(app.buttons["debt.record"])
        debtSplit(total: "300", principal: "280", interest: "15", fees: "5")
        reviewDebtPayment(); tapVisible(app.buttons["loop.confirm"])
        XCTAssertTrue(app.buttons["loop.confirm"].waitForNonExistence(timeout: 15))
        assertDebt("DOP -550.00")
        tapVisible(app.buttons["debt.link"])
        tapVisible(app.buttons["debt.action.cancel"])
        XCTAssertTrue(app.buttons["debt.record"].isHittable)
        choosePlanDetailAction("debt.edit")
        replaceMoneyField("debt.name", with: "Updated loan " + stamp)
        dismissMoneyKeyboard(); tapVisible(app.buttons["debt.save"])
        XCTAssertTrue(app.buttons["debt.save"].waitForNonExistence(timeout: 15))
        choosePlanDetailAction("debt.archive")
        app.buttons.matching(identifier: "debt.archive.confirm").firstMatch.tap()
        XCTAssertTrue(app.buttons["debt.restore"].waitForExistence(timeout: 15))
        tapVisible(app.buttons["debt.restore"]); assertDebt("DOP -550.00")
        app.returnFromDetail("debt.close")
        verifyDebtSearch("Updated loan " + stamp, balance: "DOP -550.00")
    }

    func testCardPlanPaymentAndActualReturnKeepExistingMoneyFlow() throws {
        try signIn()
        let stamp = String(UUID().uuidString.prefix(5))
        let bank = createMoneyAccount("Card funding " + stamp, type: "checking", amount: "1000")
        let card = createMoneyAccount("Card " + stamp, type: "credit_card", amount: "400")
        let note = "Recorded card payment " + stamp
        tapVisible(app.buttons["accounts.record"])
        tapVisible(app.buttons["loop.kind.card_payment"])
        chooseMoneyAccount("loop.source", account: bank)
        chooseMoneyAccount("loop.destination", account: card)
        fillMoneyField("loop.amount", with: "100")
        fillMoneyField("loop.note", with: note)
        dismissMoneyKeyboard(); reviewDebtPayment()
        tapVisible(app.buttons["loop.confirm"])
        XCTAssertTrue(app.buttons["loop.confirm"].waitForNonExistence(timeout: 15))
        assertText("DOP -300.00")
        openMoneyAccount(bank); assertText("DOP 900.00")
        openMoneyAccount(card)
        tapVisible(app.buttons["accounts.debt"])
        replaceMoneyField("debt.name", with: "Card plan " + stamp)
        fillMoneyField("debt.amount", with: "100")
        dismissMoneyKeyboard(); chooseMoneyAccount("debt.source", account: bank)
        tapVisible(app.buttons["debt.save"])
        XCTAssertTrue(app.buttons["debt.save"].waitForNonExistence(timeout: 15))
        openDebt("Card plan " + stamp)
        assertDebt("DOP -300.00")
        let payments = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'debt.activity.' AND identifier != 'debt.activity.back'"))
        XCTAssertEqual(payments.count, 0)
        tapVisible(app.buttons["debt.link"])
        let candidate = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'debt.candidate.' AND label CONTAINS %@", note)).firstMatch
        tapVisible(candidate)
        XCTAssertTrue(candidate.waitForNonExistence(timeout: 15))
        assertDebt("DOP -300.00")
        XCTAssertEqual(payments.count, 1)
        capture("card-existing-payment-linked-once")
        app.returnFromDetail("debt.close")
        openMoneyAccount(bank); assertText("DOP 900.00")
        openMoneyAccount(card); assertText("DOP -300.00")
        openDebt("Card plan " + stamp)
        tapVisible(app.buttons["debt.link"])
        XCTAssertTrue(app.staticTexts["debt.link.empty"].waitForExistence(timeout: 15))
        XCTAssertFalse(candidate.exists)
        tapVisible(app.buttons["debt.action.cancel"])
        let payment = payments.firstMatch
        tapVisible(payment); tapVisible(app.buttons["activity.return"])
        assertReturnedMoneyDirection(from: card.name, to: bank.name)
        XCTAssertFalse(app.textFields["loop.principal"].exists)
        fillMoneyField("loop.amount", with: "100"); dismissMoneyKeyboard()
        reviewDebtPayment(); tapVisible(app.buttons["loop.confirm"])
        XCTAssertTrue(app.buttons["loop.confirm"].waitForNonExistence(timeout: 15))
        app.returnFromDetail("debt.activity.back"); assertDebt("DOP -400.00")
        XCTAssertEqual(payments.count, 1)
        capture("card-linked-original-return-updates-plan")
        app.returnFromDetail("debt.close")
        openMoneyAccount(bank); assertText("DOP 1,000.00")
    }

    func testRetainedDebtHomeSearchSpanishAndBack() throws {
        guard let query = ProcessInfo.processInfo.environment["ARGUS_TEST_SEARCH_QUERY"] else { throw XCTSkip("Requires retained debt query") }
        try signIn()
        app.buttons["tab.home"].tap()
        let row = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'debt.row.home.' AND label CONTAINS %@", query)).firstMatch
        tapVisible(row)
        XCTAssertTrue(app.staticTexts["debt.recorded"].waitForExistence(timeout: 15))
        capture("debt-home-current-truth")
        app.returnFromDetail("debt.close")
        verifyDebtSearch(query, balance: nil)
    }

    private func reviewDebtPayment() {
        tapVisible(app.buttons["loop.review"])
        var answered = Set<String>()
        // These synthetic balances precede the payments: answer the server's
        // opening/check coverage controls explicitly, without confirming here.
        for _ in 0..<16 {
            if app.buttons["loop.confirm"].waitForExistence(timeout: 1) { break }
            let choices = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'loop.coverage.no.'")).allElementsBoundByIndex
            if let choice = choices.first(where: { !answered.contains($0.identifier) }) {
                answered.insert(choice.identifier)
                tapVisible(choice)
            }
        }
        XCTAssertTrue(app.buttons["loop.confirm"].waitForExistence(timeout: 15))
        capture("debt-canonical-money-preview")
    }
    private func assertReturnedMoneyDirection(from debt: String, to funding: String) {
        let from = app.buttons["loop.destination"]
        let to = app.buttons["loop.source"]
        XCTAssertTrue(from.waitForExistence(timeout: 15))
        XCTAssertTrue(to.waitForExistence(timeout: 15))
        XCTAssertTrue(from.label.hasPrefix("From") && from.label.contains(debt))
        XCTAssertTrue(to.label.hasPrefix("To") && to.label.contains(funding))
        XCTAssertLessThan(from.frame.minY, to.frame.minY)
    }

    private func debtSplit(total: String, principal: String, interest: String, fees: String) {
        for (id, amount) in [("loop.amount", total), ("loop.principal", principal), ("loop.interest", interest), ("loop.fees", fees)] { replaceMoneyField(id, with: amount) }
        dismissMoneyKeyboard()
    }
    private func openDebt(_ title: String) {
        app.openPlanSurface()
        let row = planCards("debt", title).firstMatch
        tapVisible(row)
        XCTAssertTrue(app.staticTexts["debt.recorded"].waitForExistence(timeout: 15))
    }
    private func assertDebt(_ amount: String) {
        let value = app.descendants(matching: .any)["debt.detail"].staticTexts["debt.recorded"]
        XCTAssertTrue(value.waitForExistence(timeout: 15))
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == %@", amount), object: value)], timeout: 15), .completed)
    }
    private func verifyDebtSearch(_ title: String, balance: String?) {
        app.buttons["tab.search"].tap()
        let query = app.textFields["search.query"]
        XCTAssertTrue(query.waitForExistence(timeout: 10)); query.tap()
        if app.buttons["search.clear"].exists { app.buttons["search.clear"].tap(); query.tap() }
        query.typeText(title + "\n")
        chooseSearchPlans()
        let hit = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'search.row.debt.' AND label CONTAINS %@", title)).firstMatch
        tapVisible(hit)
        if let balance { assertDebt(balance) }
        capture("debt-search-current-detail")
        app.returnFromDetail("debt.close")
        XCTAssertTrue(query.waitForExistence(timeout: 10))
        XCTAssertEqual(query.value as? String, title)
        XCTAssertTrue(app.buttons["search.filter.plans"].isSelected)
        XCTAssertTrue(hit.waitForExistence(timeout: 15))
        tapVisible(hit)
        app.terminate(); app.launch()
        XCTAssertTrue(app.staticTexts["debt.recorded"].waitForExistence(timeout: 15))
        app.returnFromDetail("debt.close")
        XCTAssertTrue(query.waitForExistence(timeout: 10))
        XCTAssertEqual(query.value as? String, title)
        XCTAssertTrue(app.buttons["search.filter.plans"].isSelected)
        XCTAssertTrue(hit.waitForExistence(timeout: 15))
        capture("debt-search-query-and-filter-restored")
    }
}
