import XCTest

extension FinancialLoopUITests {
    struct MoneyAccount {
        let name: String
        let id: String
    }

    enum RecordedSpending: Equatable {
        case currencyAbsent
        case noData
        case recorded(Decimal)
    }

    func testMoneyReplacementHandlesEmptyGroupedAndZeroAmounts() throws {
        try signIn()
        openPersonalAccounts()
        tapVisible(app.buttons["nav.add"])
        tapVisible(app.buttons["add.tray.transaction"])
        let amount = app.textFields["loop.amount"]
        XCTAssertTrue(amount.waitForExistence(timeout: 10))
        for (input, expected) in [("200", "200"), ("1100", "1,100"), ("0.00", "0.00"), ("250", "250")] {
            replaceMoneyField("loop.amount", with: input)
            XCTAssertEqual(amount.value as? String, expected)
        }
        dismissMoneyKeyboard()
        cancelEditor()
        XCTAssertTrue(amount.waitForNonExistence(timeout: 5))
    }

    func testRetainedHomeSurvivesReopening() throws {
        try signIn()
        let before = homeValue()
        app.terminate(); app.launch()
        assertHome(before)
        capture("retained-demo-home")
    }

    func testAccountAndActivityRowsOpenFromCenter() throws {
        try signIn()
        let name = "Tap " + String(UUID().uuidString.prefix(4))
        _ = createMoneyAccount(name, type: "cash", amount: "123")
        assertText("DOP 123.00")
        recordMoney(kind: "income", amount: "1", note: "Pay")
        inspectMoney("Pay")
        XCTAssertTrue(app.buttons["activity.correct"].isEnabled)
        capture("full-row-tap-opens-details")
        closeMoneyDetail()
    }

    func testIncomeSpendingRefundAndCorrections() throws {
        try signIn()
        let baseline = homeValue()
        let reporting = try homeRecordedSpending()
        let stamp = String(UUID().uuidString.prefix(5))
        let checking = createMoneyAccount("Daily money " + stamp, type: "checking", amount: "1000")
        recordMoney(kind: "income", amount: "1000", note: "Salary " + stamp)
        assertText("DOP 2,000.00")
        recordMoney(kind: "expense", amount: "250", note: "Groceries " + stamp)
        assertText("DOP 1,750.00")
        recordMoney(kind: "refund", amount: "50", note: "Returned groceries " + stamp, purchase: "Groceries " + stamp)
        assertText("DOP 1,800.00")
        try assertRecordedSpending(reporting, purchases: 250)
        openMoneyAccount(checking)
        for (note, amount, reason) in [("Salary ", "1100", "Include received commission"), ("Groceries ", "275", "Receipt correction"), ("Returned groceries ", "75", "Actual refund received")] {
            inspectMoney(note + stamp)
            tapVisible(app.buttons["activity.correct"])
            replaceMoneyField("loop.amount", with: amount)
            fillMoneyField("loop.reason", with: reason)
            dismissMoneyKeyboard(); confirmMoney()
        }
        assertText("DOP 1,900.00")
        inspectMoney("Returned groceries " + stamp)
        assertText("Actual refund received")
        capture("linked-refund-correction-history")
        closeMoneyDetail()
        assertHome(baseline + 1900)
        try assertRecordedSpending(reporting, purchases: 275)
        capture("income-spending-refund-home")
        app.terminate(); app.launch()
        openMoneyAccount(checking); assertText("DOP 1,900.00")
        assertText("Returned groceries " + stamp)
    }

    func testTransferAndWrongAccountCorrection() throws {
        try signIn()
        let baseline = homeValue()
        let reporting = try homeRecordedSpending()
        let stamp = String(UUID().uuidString.prefix(5))
        let checking = createMoneyAccount("Transfer bank " + stamp, type: "checking", amount: "1000")
        let cash = createMoneyAccount("Transfer cash " + stamp, type: "cash", amount: "100")
        openMoneyAccount(checking)
        recordMoney(kind: "expense", amount: "100", note: "Cash groceries " + stamp)
        recordMoney(kind: "transfer", amount: "200", note: "Cash withdrawal " + stamp, destination: cash)
        assertText("DOP 700.00")
        try assertRecordedSpending(reporting, purchases: 100)
        openMoneyAccount(cash); assertText("DOP 300.00")
        inspectMoney("Cash withdrawal " + stamp)
        assertText(checking.name); assertText(cash.name)
        capture("linked-transfer-details")
        tapVisible(app.buttons["activity.correct"])
        replaceMoneyField("loop.amount", with: "250")
        fillMoneyField("loop.reason", with: "Correct withdrawal amount")
        dismissMoneyKeyboard(); confirmMoney()
        assertText("DOP 350.00")
        openMoneyAccount(checking); assertText("DOP 650.00")
        inspectMoney("Cash groceries " + stamp)
        tapVisible(app.buttons["activity.correct"])
        chooseMoneyAccount("loop.account", account: cash)
        replaceMoneyField("loop.amount", with: "125")
        fillMoneyField("loop.reason", with: "Receipt was paid in cash")
        dismissMoneyKeyboard(); confirmMoney()
        assertText("DOP 750.00")
        XCTAssertTrue(app.staticTexts["activity.moved"].exists)
        capture("wrong-account-correction-history")
        openMoneyAccount(cash); assertText("DOP 225.00")
        assertHome(baseline + 975)
        try assertRecordedSpending(reporting, purchases: 125)
        app.terminate(); app.launch()
        openMoneyAccount(checking); assertText("DOP 750.00")
        openMoneyAccount(cash); assertText("DOP 225.00")
        inspectMoney("Cash withdrawal " + stamp)
        assertText("Correct withdrawal amount")
        closeMoneyDetail()
        capture("paired-records-preserved-after-reopen")
    }

    func testCardPaymentRefundAndCreditBalance() throws {
        try signIn()
        let baseline = homeValue()
        let reporting = try homeRecordedSpending()
        let stamp = String(UUID().uuidString.prefix(5))
        let checking = createMoneyAccount("Card funding " + stamp, type: "checking", amount: "1000")
        let card = createMoneyAccount("Everyday card " + stamp, type: "credit_card", amount: "300")
        recordMoney(kind: "expense", amount: "120", note: "Card purchase " + stamp)
        assertText("DOP -420.00")
        recordMoney(kind: "card_payment", amount: "200", note: "Card payment " + stamp, source: checking, destination: card)
        assertText("DOP -220.00")
        try assertRecordedSpending(reporting, purchases: 120)
        openMoneyAccount(checking); assertText("DOP 800.00")
        recordMoney(kind: "refund", amount: "50", note: "Returned card purchase " + stamp, purchase: "Card purchase " + stamp)
        assertText("DOP 850.00")
        inspectMoney("Card payment " + stamp)
        tapVisible(app.buttons["activity.correct"])
        replaceMoneyField("loop.amount", with: "250")
        fillMoneyField("loop.reason", with: "Correct payment amount")
        dismissMoneyKeyboard(); confirmMoney()
        assertText("DOP 800.00")
        openMoneyAccount(card); assertText("DOP -170.00")
        recordMoney(kind: "refund", amount: "200", note: "Earlier purchase refund " + stamp)
        assertText("DOP 30.00")
        assertText("Credit balance in your favor")
        capture("card-credit-after-refund")
        inspectMoney("Earlier purchase refund " + stamp)
        assertText("Purchase not linked")
        closeMoneyDetail()
        assertHome(baseline + 830)
        try assertRecordedSpending(reporting, purchases: 120)
        capture("card-payment-excluded-refund-net-delta")
        app.terminate(); app.launch()
        openMoneyAccount(card); assertText("DOP 30.00")
        openMoneyAccount(checking); assertText("DOP 800.00")
    }

    func testMoneyReconciliationCurrenciesAndSpanish() throws {
        try signIn()
        let baseline = homeValue()
        let stamp = String(UUID().uuidString.prefix(5))
        let bank = createMoneyAccount("Checked bank " + stamp, type: "checking", amount: "1000")
        let wallet = createMoneyAccount("Checked cash " + stamp, type: "cash", amount: "500")
        checkMoneyBalance("500")
        openMoneyAccount(bank)
        checkMoneyBalance("940")
        tapVisible(app.buttons["accounts.record"])
        app.buttons["loop.kind.transfer"].tap()
        chooseMoneyAccount("loop.destination", account: wallet)
        fillMoneyField("loop.amount", with: "60")
        fillMoneyField("loop.note", with: "Late withdrawal " + stamp)
        dismissMoneyKeyboard()
        confirmMoney(answersByAccount: [bank.id.lowercased(): [false, true]])
        assertText("DOP 940.00")
        assertText("Still unexplained DOP 0.00")
        capture("per-account-reconciliation")
        openMoneyAccount(wallet)
        assertText("DOP 560.00")
        assertHome(baseline + 1500)
        let dollarsBefore = try homeRecordedSpending(currency: "USD")
        let dollarBalance = app.staticTexts["home.netWorth.USD"]
        let dollarBalanceBefore = dollarBalance.exists ? dollarBalance.label : nil
        let dollars = createMoneyAccount("Blank dollars " + stamp, type: "checking", currency: "USD")
        assertText("USD 0.00")
        recordMoney(kind: "income", amount: "100", note: "Dollar income " + stamp)
        assertText("USD 100.00")
        recordMoney(kind: "refund", amount: "25", note: "Foreign return " + stamp)
        assertText("USD 125.00")
        inspectMoney("Foreign return " + stamp)
        assertText("Purchase not linked")
        closeMoneyDetail()
        assertHome(baseline + 1500)
        let dollarsAfter = try homeRecordedSpending(currency: "USD")
        XCTAssertEqual(dollarsAfter, dollarsBefore == .currencyAbsent ? .noData : dollarsBefore)
        XCTAssertTrue(dollarBalance.waitForExistence(timeout: 10))
        XCTAssertNotEqual(dollarBalance.label, dollarBalanceBefore ?? "—",
                          "A blank dollar account starts at a recorded 0.00, so its income counts in USD only")
        capture("separate-currency-zero-start-balance")
        app.terminate(); app.launch()
        openMoneyAccount(dollars); assertText("USD 125.00")
        openMoneyAccount(bank); assertText("DOP 940.00")
        app.terminate()
        app.launchArguments = ["-AppleLanguages", "(es-419)", "-AppleLocale", "es_DO", "-appearancePreference", "light"]
        app.launch()
        openMoneyAccount(bank)
        tapVisible(app.buttons["accounts.record"])
        XCTAssertTrue(app.buttons["loop.kind.income"].waitForExistence(timeout: 10))
        app.buttons["loop.kind.income"].tap()
        capture("income-spanish-light")
        XCTAssertFalse(app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH 'loop.'")).firstMatch.exists)
        app.buttons["Cancelar"].tap()
        app.terminate()
        try signIn()
        assertHome(baseline + 1500)
    }

    func checkMoneyBalance(_ amount: String) {
        tapVisible(app.buttons["accounts.check"])
        fillMoneyField("loop.amount", with: amount)
        dismissMoneyKeyboard()
        tapVisible(app.buttons["loop.review"])
        XCTAssertTrue(app.buttons["loop.confirm"].waitForExistence(timeout: 10))
        tapVisible(app.buttons["loop.confirm"])
        if !app.buttons["accounts.record"].waitForExistence(timeout: 10) {
            capture("navigation-failed")
            print("MONEY_UI_STATE " + app.debugDescription)
            XCTFail("Account tap should open selected details")
        }
    }

    func testPendingMoneyWriteRemainsIsolatedAcrossIdentities() throws {
        try requireResponseLossProxy()
        let stamp = String(UUID().uuidString.prefix(5))
        try signIn(fresh: true, user: "B")
        let other = createMoneyAccount("Isolated B " + stamp, type: "checking", amount: "321")
        let otherHome = homeValue()
        try signIn(fresh: true)
        let owner = createMoneyAccount("Pending A " + stamp, type: "checking", amount: "100")
        let note = "Isolated pending income " + stamp
        let droppedBefore = try interruptMoneyIncome(note: note)
        capture("isolation-a-committed-response-lost")
        app.terminate(); app.launch()
        XCTAssertTrue(app.buttons["loop.pending.retry"].waitForExistence(timeout: 20))
        capture("isolation-a-pending-before-switch")

        try signIn(fresh: true, user: "B")
        app.openAccountsList()
        // B's own persisted row is the positive load barrier for absence claims.
        XCTAssertTrue(app.buttons["accounts.row." + other.id].waitForExistence(timeout: 20))
        XCTAssertFalse(app.buttons["accounts.row." + owner.id].exists)
        XCTAssertFalse(app.buttons["loop.pending.retry.accounts"].exists)
        openMoneyAccount(other); assertText("DOP 321.00")
        capture("isolation-b-own-account-loaded")
        assertHome(otherHome)
        XCTAssertFalse(app.buttons["loop.pending.retry"].exists)
        capture("isolation-b-home-without-a-pending")

        try signIn(fresh: true)
        XCTAssertTrue(app.buttons["loop.pending.retry"].waitForExistence(timeout: 20))
        capture("isolation-a-pending-restored")
        try recoverMoneyIncome(owner, note: note, droppedBefore: droppedBefore)
        capture("isolation-a-recovered-once-after-reopen")
    }

    func testCommittedResponseLossSurvivesRelaunch() throws {
        try requireResponseLossProxy()
        try signIn()
        let stamp = String(UUID().uuidString.prefix(5))
        let account = createMoneyAccount("Recovery " + stamp, type: "checking", amount: "100")
        let note = "Recovered income " + stamp
        let before = try interruptMoneyIncome(note: note)
        capture("committed-response-lost")
        app.terminate(); app.launch()
        try recoverMoneyIncome(account, note: note, droppedBefore: before)
    }

    func requireResponseLossProxy() throws {
        guard ProcessInfo.processInfo.environment["ARGUS_TEST_RESPONSE_LOSS_PROXY"] == "true" else {
            throw XCTSkip("Requires explicit local response-loss proxy build on 58512.")
        }
    }

    func interruptMoneyIncome(note: String) throws -> Int {
        tapVisible(app.buttons["accounts.record"])
        app.buttons["loop.kind.income"].tap()
        fillMoneyField("loop.amount", with: "25")
        fillMoneyField("loop.note", with: note)
        dismissMoneyKeyboard()
        reviewMoney()
        let before = try faultStatus(arm: true)
        tapVisible(app.buttons["loop.confirm"])
        XCTAssertTrue(app.staticTexts["loop.error"].waitForExistence(timeout: 30))
        XCTAssertFalse(app.buttons["Cancel"].isEnabled)
        return before
    }

    func recoverMoneyIncome(_ account: MoneyAccount, note: String, droppedBefore: Int) throws {
        let pending = app.buttons["loop.pending.retry"]
        XCTAssertTrue(pending.waitForExistence(timeout: 20))
        capture("pending-recovery-after-relaunch")
        tapVisible(pending)
        let cleared = NSPredicate(format: "exists == false")
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: cleared, object: pending)], timeout: 20), .completed)
        openMoneyAccount(account)
        assertText("DOP 125.00")
        let records = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'activity.row.' AND label CONTAINS %@", note))
        XCTAssertEqual(records.count, 1)
        let recordID = records.firstMatch.identifier
        XCTAssertEqual(try faultStatus(arm: false), droppedBefore + 1)
        app.terminate(); app.launch()
        openMoneyAccount(account); assertText("DOP 125.00")
        XCTAssertTrue(app.buttons[recordID].exists)
        XCTAssertEqual(records.count, 1)
        capture("same-key-recovery-once")
    }

    func faultStatus(arm: Bool) throws -> Int {
        let finished = expectation(description: "Local fault proxy responds")
        var dropped: Int?
        var failure: Error?
        let endpoint = ProcessInfo.processInfo.environment["ARGUS_TEST_FAULT_URL"] ?? "http://127.0.0.1:58512/__fault"
        var request = URLRequest(url: try XCTUnwrap(URL(string: endpoint)))
        request.httpMethod = arm ? "POST" : "GET"
        URLSession.shared.dataTask(with: request) { data, response, error in
            failure = error
            if let data, let body = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                dropped = body["dropped"] as? Int
            }
            finished.fulfill()
        }.resume()
        wait(for: [finished], timeout: 10)
        if let failure { throw failure }
        return try XCTUnwrap(dropped)
    }

    func selectHomeMoneyCurrency(_ currency: String) -> Bool {
        let balance = app.staticTexts["home.netWorth." + currency]
        if balance.exists { return true }
        let picker = app.buttons["home-chart-currency"]
        guard picker.exists else { return false }
        let current = app.scrollViews["screen.home"].staticTexts
            .matching(NSPredicate(format: "identifier BEGINSWITH 'home.netWorth.'")).firstMatch
        let currentCurrency = String(current.identifier.dropFirst("home.netWorth.".count))
        tapVisible(picker)
        let option = app.buttons.matching(NSPredicate(format: "label == %@ AND identifier != 'home-chart-currency'", currency)).firstMatch
        if !option.waitForExistence(timeout: 3) {
            let selected = app.buttons.matching(NSPredicate(format: "label == %@ AND identifier != 'home-chart-currency'", currentCurrency)).firstMatch
            XCTAssertTrue(selected.waitForExistence(timeout: 3))
            selected.tap()
            return false
        }
        option.tap()
        XCTAssertTrue(balance.waitForExistence(timeout: 10))
        return true
    }

    func homeRecordedSpending(currency: String = "DOP") throws -> RecordedSpending {
        openPersonalAccounts()
        app.openHomeSurface()
        guard selectHomeMoneyCurrency(currency) else { return .currencyAbsent }
        tapVisible(app.buttons["home-history-expand"])
        tapVisible(app.buttons["home-insight-metric"])
        let activity = app.buttons["Activity"]
        XCTAssertTrue(activity.waitForExistence(timeout: 5))
        activity.tap()
        let amount = app.staticTexts["home-spending-total"]
        XCTAssertTrue(amount.waitForExistence(timeout: 10))
        let label = amount.label
        tapVisible(app.buttons["home-history-done"])
        XCTAssertTrue(app.buttons["home-history-expand"].waitForExistence(timeout: 5))
        if label == "No data" { return .noData }
        let exact = label.replacingOccurrences(of: ",", with: "").trimmingCharacters(in: .whitespaces)
        return .recorded(try XCTUnwrap(Decimal(string: exact, locale: Locale(identifier: "en_US_POSIX")),
            "Home should show recorded spending or No data for " + currency))
    }

    func assertRecordedSpending(_ baseline: RecordedSpending, purchases: Decimal) throws {
        let actual = try homeRecordedSpending()
        switch baseline {
        case .recorded(let amount):
            XCTAssertEqual(actual, .recorded(amount + purchases))
        case .currencyAbsent, .noData:
            guard case .recorded(let amount) = actual else {
                XCTFail("Home should show the purchases recorded during this test")
                return
            }
            XCTAssertEqual(amount, purchases)
        }
    }

    func createMoneyAccount(_ name: String, type: String, amount: String? = nil, negative: Bool = false, currency: String = "DOP") -> MoneyAccount {
        openPersonalAccounts()
        if app.accountBack.exists { scrollMoneyTop(); app.accountBack.tap() }
        tapVisible(app.buttons["accounts.add"])
        tapVisible(app.buttons["accounts.type." + type])
        fillMoneyField("accounts.nickname", with: name)
        if currency != "DOP" {
            dismissMoneyKeyboard()
            tapVisible(app.buttons["accounts.currency"])
            // The currency list shows each code with its name.
            let option = app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", currency)).firstMatch
            XCTAssertTrue(option.waitForExistence(timeout: 5))
            option.tap()
        }
        if let amount {
            fillMoneyField("accounts.amount", with: amount)
            if negative { app.buttons["accounts.amount.sign"].tap() }
        }
        dismissMoneyKeyboard()
        tapVisible(app.buttons["accounts.save"])
        if !app.buttons["accounts.record"].waitForExistence(timeout: 15) {
            print("MONEY_UI_STATE " + app.debugDescription)
            XCTFail("Saved activity or account should return to account details")
        }
        scrollMoneyTop(); app.accountBack.tap()
        let row = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'accounts.row.' AND label CONTAINS %@", name)).firstMatch
        XCTAssertTrue(row.waitForExistence(timeout: 10))
        let result = MoneyAccount(name: name, id: String(row.identifier.dropFirst("accounts.row.".count)))
        tapVisible(row)
        return result
    }

    func openMoneyAccount(_ account: MoneyAccount) {
        app.openAccountsList()
        if app.accountBack.exists { scrollMoneyTop(); app.accountBack.tap() }
        tapVisible(app.buttons["accounts.row." + account.id])
        if !app.buttons["accounts.record"].waitForExistence(timeout: 10) {
            capture("navigation-failed")
            print("MONEY_UI_STATE " + app.debugDescription)
            XCTFail("Account tap should open selected details")
        }
    }

    func recordMoney(kind: String, amount: String, note: String, source: MoneyAccount? = nil, destination: MoneyAccount? = nil, purchase: String? = nil) {
        tapVisible(app.buttons["accounts.record"])
        let kindButton = app.buttons["loop.kind." + kind]
        XCTAssertTrue(kindButton.waitForExistence(timeout: 10))
        if !kindButton.isHittable { app.scrollViews.firstMatch.swipeLeft() }
        kindButton.tap()
        if let source { chooseMoneyAccount("loop.source", account: source) }
        if let destination { chooseMoneyAccount("loop.destination", account: destination) }
        fillMoneyField("loop.amount", with: amount)
        dismissMoneyKeyboard()
        if let purchase {
            tapVisible(app.buttons["loop.purchase"])
            let option = app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@ AND label CONTAINS %@ AND NOT identifier BEGINSWITH 'loop.' AND NOT identifier BEGINSWITH 'activity.'", purchase, " · ")).firstMatch
            XCTAssertTrue(option.waitForExistence(timeout: 5))
            option.tap()
        }
        fillMoneyField("loop.note", with: note)
        dismissMoneyKeyboard()
        confirmMoney()
    }

    func chooseMoneyAccount(_ identifier: String, account: MoneyAccount) {
        let picker = app.buttons[identifier]
        if picker.label.contains(account.name) { return }
        tapVisible(picker)
        let option = app.buttons.matching(NSPredicate(format: "label == %@ AND NOT identifier BEGINSWITH 'loop.' AND NOT identifier BEGINSWITH 'accounts.'", account.name)).firstMatch
        let menu = app.collectionViews.element(boundBy: app.collectionViews.count - 1)
        XCTAssertTrue(menu.waitForExistence(timeout: 5))
        for _ in 0..<40 {
            if option.exists && option.isHittable { break }
            let visibleOptions = menu.buttons.allElementsBoundByIndex.filter(\.isHittable)
            guard !visibleOptions.isEmpty else {
                XCTFail("The account menu has no visible options")
                return
            }
            let start = visibleOptions[visibleOptions.count / 2]
                .coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5))
            start.press(forDuration: 0.05, thenDragTo: start.withOffset(CGVector(dx: 0, dy: -100)),
                        withVelocity: .slow, thenHoldForDuration: 0.2)
        }
        XCTAssertTrue(option.waitForExistence(timeout: 5))
        option.tap()
    }

    func fillMoneyField(_ identifier: String, with value: String) {
        dismissMoneyKeyboard()
        let field = moneyField(identifier)
        tapVisible(field); field.typeText(value)
    }

    func replaceMoneyField(_ identifier: String, with value: String) {
        dismissMoneyKeyboard()
        let field = moneyField(identifier)
        tapVisible(field)
        let old = field.value as? String ?? ""
        if !old.isEmpty {
            field.press(forDuration: 1.1)
            let selectAll = app.menuItems["Select All"]
            if selectAll.waitForExistence(timeout: 3) {
                selectAll.tap()
            } else {
                guard old == field.placeholderValue else {
                    XCTFail("The field must offer Select All before replacing its text")
                    return
                }
                field.tap()
            }
            XCTAssertTrue(app.keyboards.firstMatch.exists)
        }
        field.typeText(value)
    }

    func moneyField(_ identifier: String) -> XCUIElement {
        let field = app.textFields[identifier]
        let view = app.textViews[identifier]
        let appeared = XCTNSPredicateExpectation(predicate: NSPredicate { _, _ in field.exists || view.exists }, object: nil)
        XCTAssertEqual(XCTWaiter.wait(for: [appeared], timeout: 10), .completed)
        return field.exists ? field : view
    }

    func dismissMoneyKeyboard() {
        app.dismissKeyboard()
    }

    func reviewMoney(answersByAccount: [String: [Bool]] = [:]) {
        tapVisible(app.buttons["loop.review"])
        var answered = Set<String>()
        var accountAnswers = [String: Int]()
        for _ in 0..<16 {
            if app.buttons["loop.confirm"].waitForExistence(timeout: 1) { break }
            let choices = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'loop.coverage.no.'")).allElementsBoundByIndex
            guard let choice = choices.first(where: { !answered.contains($0.identifier) }) else { continue }
            let questionID = choice.identifier
            let pieces = questionID.split(separator: ".")
            let account = pieces.count >= 5 ? String(pieces[3]).lowercased() : ""
            let index = accountAnswers[account, default: 0]
            let answers = answersByAccount[account] ?? []
            let include = index < answers.count && answers[index]
            let identifier = include ? questionID.replacingOccurrences(of: ".no.", with: ".yes.") : questionID
            let target = app.buttons[identifier]
            tapVisible(target)
            let selected = NSPredicate { [app] _, _ in
                app.buttons["loop.confirm"].exists || (target.exists && target.isSelected)
            }
            guard XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: selected, object: nil)], timeout: 10) == .completed else {
                XCTFail("The coverage answer was not selected: " + identifier)
                return
            }
            answered.insert(questionID)
            accountAnswers[account] = index + 1
        }
        XCTAssertTrue(app.buttons["loop.confirm"].waitForExistence(timeout: 10))
        capture("personal-money-review")
    }

    func confirmMoney(answersByAccount: [String: [Bool]] = [:]) {
        reviewMoney(answersByAccount: answersByAccount)
        tapVisible(app.buttons["loop.confirm"])
        if !app.buttons["accounts.record"].waitForExistence(timeout: 15) {
            print("MONEY_UI_STATE " + app.debugDescription)
            XCTFail("Saved activity or account should return to account details")
        }
    }

    func inspectMoney(_ note: String) {
        let row = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'activity.row.' AND label CONTAINS %@", note)).firstMatch
        tapVisible(row)
        XCTAssertTrue(app.buttons["activity.correct"].waitForExistence(timeout: 10))
    }

    func closeMoneyDetail() { app.buttons["Close"].tap() }

    func scrollMoneyTop() {
        for _ in 0..<8 {
            if app.accountBack.isHittable { break }
            app.swipeDown()
        }
    }
}
