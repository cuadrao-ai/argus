import XCTest

// One-off retained-demo driver. Uses existing journey helpers; never confirms a write.
extension FinancialLoopUITests {
    func testTransferLabelClarityWithoutSaving() throws {
        try signIn()
        func retained(_ name: String) -> MoneyAccount {
            app.buttons["tab.accounts"].tap()
            if app.buttons["accounts.back"].exists { scrollMoneyTop(); app.buttons["accounts.back"].tap() }
            let row = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'accounts.row.' AND label CONTAINS %@", name)).firstMatch
            XCTAssertTrue(row.waitForExistence(timeout: 15))
            return MoneyAccount(name: name, id: String(row.identifier.dropFirst("accounts.row.".count)))
        }
        let bank = retained("Transfer bank DBA3B")
        let cash = retained("Transfer cash DBA3B")
        let card = retained("Everyday card FC26C")
        func labels(_ from: String, _ to: String) {
            let source = app.staticTexts["loop.source.label"]
            let destination = app.staticTexts["loop.destination.label"]
            XCTAssertTrue(source.waitForExistence(timeout: 10))
            XCTAssertEqual(source.label, from); XCTAssertEqual(destination.label, to)
            XCTAssertTrue(source.isHittable); XCTAssertTrue(destination.isHittable)
            let body = app.scrollViews.containing(.button, identifier: "loop.source").firstMatch
            let names = body.staticTexts.matching(identifier: bank.name).allElementsBoundByIndex
            XCTAssertFalse(names.contains { $0.frame.maxY < source.frame.minY })
        }
        for (language, locale, appearance, from, to, cancel) in [
            ("en", "en_US", "dark", "From", "To", "Cancel"),
            ("es-419", "es_DO", "light", "Desde", "Hacia", "Cancelar")
        ] {
            app.terminate()
            app.launchArguments = ["-AppleLanguages", "(" + language + ")", "-AppleLocale", locale, "-appearancePreference", appearance]
            app.launch()
            openMoneyAccount(bank)
            tapVisible(app.buttons["accounts.record"])
            app.buttons["loop.kind.transfer"].tap()
            chooseMoneyAccount("loop.source", account: cash)
            chooseMoneyAccount("loop.destination", account: bank)
            XCTAssertTrue(app.buttons["loop.source"].label.contains(cash.name))
            XCTAssertTrue(app.buttons["loop.destination"].label.contains(bank.name))
            labels(from, to)
            fillMoneyField("loop.amount", with: "40"); dismissMoneyKeyboard()
            capture("transfer-labels-" + language + "-" + appearance)
            reviewMoney()
            assertText("DOP 185.00"); assertText("DOP 790.00")
            capture("transfer-labels-review-" + language + "-" + appearance)
            app.buttons[cancel].tap()
            XCTAssertTrue(app.buttons["accounts.record"].waitForExistence(timeout: 10))
            assertText("DOP 750.00")
            if language == "en" {
                inspectMoney("Cash withdrawal DBA3B")
                tapVisible(app.buttons["activity.correct"])
                labels(from, to)
                XCTAssertTrue(app.buttons["loop.source"].label.contains(bank.name))
                XCTAssertTrue(app.buttons["loop.destination"].label.contains(cash.name))
                capture("transfer-correction-labels-en-dark")
                app.buttons[cancel].tap()
                tapVisible(app.buttons["accounts.record"])
                app.buttons["loop.kind.expense"].tap()
                chooseMoneyAccount("loop.account", account: cash)
                XCTAssertTrue(app.buttons["loop.account"].label.contains(cash.name))
                capture("expense-picker-smoke-en-dark")
                app.buttons[cancel].tap()
                tapVisible(app.buttons["accounts.record"])
                app.buttons["loop.kind.card_payment"].tap()
                chooseMoneyAccount("loop.source", account: bank)
                chooseMoneyAccount("loop.destination", account: card)
                XCTAssertTrue(app.buttons["loop.source"].label.contains(bank.name))
                XCTAssertTrue(app.buttons["loop.destination"].label.contains(card.name))
                capture("card-picker-smoke-en-dark")
                app.buttons[cancel].tap()
            }
        }
        app.terminate(); try signIn()
        app.buttons["tab.home"].tap()
        XCTAssertTrue(app.staticTexts["home.netWorth.DOP"].waitForExistence(timeout: 10))
        capture("transfer-labels-final-home")
    }
}
