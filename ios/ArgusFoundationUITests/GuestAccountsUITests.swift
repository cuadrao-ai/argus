import XCTest

/// Accounts in the on-device book: every type, exact digits per currency, unknown versus zero, the currency and type
/// locks, archive and restore, and a relaunch that changes nothing. No server is involved.
extension FinancialLoopUITests {
    private func guestRow(_ name: String) -> XCUIElement {
        app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'guest.account.row.' AND label CONTAINS %@", name)).firstMatch
    }

    private func fillAmount(_ text: String) {
        let amount = app.textFields["guest.account.amount"]
        dismissGuestKeyboard()
        amount.tap()
        amount.typeText(text)
    }

    private func closeKeyboard() { dismissGuestKeyboard() }

    private func chooseCurrency(_ code: String) {
        dismissGuestKeyboard()
        app.buttons["guest.account.currency"].tap()
        let search = app.searchFields.firstMatch
        XCTAssertTrue(search.waitForExistence(timeout: 10), "the currency picker searches")
        search.tap()
        search.typeText(code)
        let row = app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", code)).firstMatch
        XCTAssertTrue(row.waitForExistence(timeout: 5), code)
        row.tap()
        XCTAssertTrue(app.buttons["guest.account.currency"].waitForExistence(timeout: 5), "back on the account form")
        XCTAssertEqual(app.buttons["guest.account.currency"].label, "Currency, \(code)")
    }

    /// Fills and saves the shared account form. The caller opens it.
    private func saveAccount(type: String, name: String = "", currency: String? = nil, amount: String? = nil) {
        XCTAssertTrue(app.buttons["guest.account.type.\(type)"].waitForExistence(timeout: 10), "the type grid")
        app.buttons["guest.account.type.\(type)"].tap()
        if !name.isEmpty {
            let field = app.textFields["guest.account.name"]
            field.tap()
            field.typeText(name)
        }
        if let currency { chooseCurrency(currency) }
        if let amount { fillAmount(amount) }
        closeKeyboard()
        let save = app.buttons["guest.account.save"]
        XCTAssertTrue(save.isEnabled, "the form is valid")
        save.tap()
        XCTAssertTrue(save.waitForNonExistence(timeout: 10), "the sheet closes on save")
    }

    private func addGuestAccount(type: String, name: String = "", currency: String? = nil, amount: String? = nil) {
        tapVisible(app.buttons["accounts.add"])
        saveAccount(type: type, name: name, currency: currency, amount: amount)
    }

    func testGuestAccountsInManyCurrenciesKeepExactDigitsAndSurviveRelaunch() throws {
        launchSignedOut(arguments: ["--cuadrao-guest-book"])
        enterGuestBook()
        XCTAssertTrue(app.buttons["accounts.add"].exists, "the empty Home invites a first account")
        app.buttons["nav.add"].tap()
        XCTAssertTrue(app.buttons["add.tray.account"].waitForExistence(timeout: 5))
        for row in ["transaction", "plan", "group", "invite"] {
            XCTAssertFalse(app.buttons["add.tray." + row].exists, row + " is not in the book yet")
        }
        for row in ["scanCamera", "choosePhoto", "chooseFile"] {
            XCTAssertTrue(app.buttons["add.tray." + row].exists, row + " keeps a receipt on this iPhone")
        }
        capture("guest-add-tray")
        app.buttons["add.tray.account"].tap()
        XCTAssertEqual(app.buttons["guest.account.currency"].label, "Currency, DOP", "the first currency offered is the Dominican peso")
        saveAccount(type: "checking", name: "Everyday", amount: "1234.56")
        XCTAssertTrue(guestRow("Everyday").waitForExistence(timeout: 10))
        XCTAssertTrue(guestRow("Everyday").label.contains("1,234.56"), guestRow("Everyday").label)
        XCTAssertTrue(guestRow("Everyday").label.contains("DOP"))
        capture("guest-account-first")

        addGuestAccount(type: "cash", name: "Dollar cash", currency: "USD", amount: "15000")
        addGuestAccount(type: "savings", name: "Euro savings", currency: "EUR", amount: "12.34")
        addGuestAccount(type: "credit_card", name: "Card", currency: "USD", amount: "250.50")
        addGuestAccount(type: "checking", name: "Euro unknown", currency: "EUR")
        addGuestAccount(type: "savings", name: "Zero known", currency: "USD", amount: "0")
        XCTAssertTrue(guestRow("Dollar cash").label.contains("15,000.00"), "a dollar keeps two decimals: " + guestRow("Dollar cash").label)
        XCTAssertTrue(guestRow("Euro savings").label.contains("12.34"), "a euro keeps its cents: " + guestRow("Euro savings").label)
        XCTAssertTrue(guestRow("Card").label.contains("-250.50"), "a debt is stored owed: " + guestRow("Card").label)
        XCTAssertTrue(guestRow("Card").label.contains("owed"))
        XCTAssertTrue(guestRow("Euro unknown").label.contains("Balance unknown"), "blank is unknown: " + guestRow("Euro unknown").label)
        XCTAssertTrue(guestRow("Zero known").label.contains("0.00"), "zero is a known balance: " + guestRow("Zero known").label)
        XCTAssertFalse(guestRow("Zero known").label.contains("unknown"))
        capture("guest-accounts-many-currencies")
        let names = ["Everyday", "Dollar cash", "Euro savings", "Card", "Euro unknown", "Zero known"]
        let before = names.map { guestRow($0).label }

        app.terminate()
        app.launchArguments = ["-AppleLanguages", "(en)", "-AppleLocale", "en_US", "-appearancePreference", "light", "--cuadrao-guest-book"]
        app.launch()
        XCTAssertTrue(guestRow("Everyday").waitForExistence(timeout: 20), "the book reopens with its accounts")
        XCTAssertFalse(app.buttons["cuadrao.welcome.signin"].exists)
        XCTAssertEqual(before, names.map { guestRow($0).label }, "every amount, caption and unknown balance survived the relaunch")
        capture("guest-accounts-after-relaunch")
    }

    /// The picker offers the approved currencies only, not the world list.
    func testGuestCurrencyPickerListsOnlyTheApprovedCurrencies() throws {
        launchSignedOut(arguments: ["--cuadrao-guest-book"])
        enterGuestBook()
        tapVisible(app.buttons["accounts.add"])
        app.buttons["guest.account.type.cash"].tap()
        dismissGuestKeyboard()
        app.buttons["guest.account.currency"].tap()
        func row(_ code: String) -> XCUIElement { app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", code)).firstMatch }
        XCTAssertTrue(row("DOP").waitForExistence(timeout: 10))
        let codes = app.buttons.matching(NSPredicate(format: "label MATCHES %@", "^[A-Z]{3}(,.*)?$|^[A-Z]{3} .*"))
        XCTAssertEqual(codes.count, 3, "DOP, USD and EUR, nothing else")
        for code in ["DOP", "USD", "EUR"] { XCTAssertTrue(row(code).exists, code) }
        for code in ["JPY", "KWD", "GBP", "MXN"] { XCTAssertFalse(row(code).exists, code) }
        capture("guest-currency-picker-approved-only")
    }

    func testGuestAmountFieldRefusesWhatTheCurrencyCannotHold() throws {
        launchSignedOut(arguments: ["--cuadrao-guest-book"])
        enterGuestBook()
        tapVisible(app.buttons["accounts.add"])
        app.buttons["guest.account.type.cash"].tap()
        chooseCurrency("USD")
        let amount = app.textFields["guest.account.amount"]
        dismissGuestKeyboard()
        amount.tap()
        amount.typeText("12.345")
        let error = app.staticTexts["amount-error"]
        XCTAssertTrue(error.waitForExistence(timeout: 5), "a dollar has two decimals")
        XCTAssertEqual(error.label, "Check decimal places for USD.")
        XCTAssertEqual(amount.value as? String, "12.34", "the third decimal was refused, nothing rounded")
        capture("guest-usd-two-decimals")
        XCTAssertFalse(app.buttons["guest.account.save"].isEnabled, "no save while the amount is wrong")
        amount.typeText(XCUIKeyboardKey.delete.rawValue)
        XCTAssertTrue(error.waitForNonExistence(timeout: 5), "a valid edit clears the error")
        closeKeyboard()
        app.buttons["guest.account.cancel"].tap()
        XCTAssertTrue(app.buttons["guest.account.save"].waitForNonExistence(timeout: 5))
        tapVisible(app.buttons["accounts.add"])
        app.buttons["guest.account.type.savings"].tap()
        chooseCurrency("EUR")
        let euro = app.textFields["guest.account.amount"]
        euro.tap()
        euro.typeText("12.12345")
        XCTAssertEqual(error.label, "Check decimal places for EUR.")
        XCTAssertEqual(euro.value as? String, "12.12", "a euro keeps two decimals, so the third digit was refused")
        capture("guest-eur-two-decimals")
        closeKeyboard()
        app.buttons["guest.account.cancel"].tap()
        XCTAssertTrue(app.buttons["guest.account.save"].waitForNonExistence(timeout: 5))
        XCTAssertTrue(app.descendants(matching: .any)["guest.home.empty"].exists, "Cancel saved nothing")
    }

    func testGuestAccountDetailLocksCurrencyArchivesAndRestores() throws {
        launchSignedOut(arguments: ["--cuadrao-guest-book"])
        enterGuestBook()
        addGuestAccount(type: "checking", name: "Locked", currency: "USD", amount: "100")
        addGuestAccount(type: "savings", name: "Open later", currency: "EUR")
        tapVisible(guestRow("Open later"))
        XCTAssertTrue(app.descendants(matching: .any)["guest.account.detail"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.staticTexts["No balance recorded"].exists)
        XCTAssertTrue(app.staticTexts["guest.account.empty"].exists, "an account with no movements shows the shared empty state")
        app.buttons["guest.account.edit"].tap()
        XCTAssertTrue(app.buttons["guest.account.currency"].waitForExistence(timeout: 10), "no balance yet, so the currency can still change")
        XCTAssertFalse(app.staticTexts["account-lock-note"].exists)
        fillAmount("50")
        closeKeyboard()
        app.buttons["guest.account.save"].tap()
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH 'Tracked since'")).firstMatch.waitForExistence(timeout: 10))
        XCTAssertEqual(app.staticTexts["guest.account.balance.EUR"].label, "EUR 50.00")
        capture("guest-account-detail-tracked")

        // Once a balance is stated the currency and the type stay.
        app.buttons["guest.account.edit"].tap()
        XCTAssertTrue(app.staticTexts["account-lock-note"].waitForExistence(timeout: 10))
        XCTAssertFalse(app.buttons["guest.account.currency"].exists, "the currency is fixed")
        XCTAssertFalse(app.buttons["guest.account.type.change"].isEnabled, "the type is fixed")
        capture("guest-account-edit-locked")
        let name = app.textFields["guest.account.name"]
        name.tap()
        name.typeText(" two")
        closeKeyboard()
        app.buttons["guest.account.save"].tap()
        XCTAssertTrue(app.staticTexts["account-detail-title"].waitForExistence(timeout: 10))
        XCTAssertEqual(app.staticTexts["account-detail-title"].label, "Open later two")

        // Archive from the detail, undo, archive again, restore from the archived list.
        app.buttons["guest.account.archive"].tap()
        app.buttons["accounts.archive.confirm"].tap()
        XCTAssertTrue(app.buttons["accounts.archived.undo"].waitForExistence(timeout: 10), "back on Home with Undo")
        XCTAssertFalse(guestRow("Open later").exists)
        XCTAssertTrue(app.buttons["guest.accounts.archived"].exists)
        capture("guest-account-archived-toast")
        app.buttons["accounts.archived.undo"].tap()
        XCTAssertTrue(guestRow("Open later").waitForExistence(timeout: 10), "Undo restored it")
        XCTAssertFalse(app.buttons["guest.accounts.archived"].exists)

        tapVisible(guestRow("Locked"))
        app.buttons["guest.account.archive"].tap()
        app.buttons["accounts.archive.confirm"].tap()
        XCTAssertTrue(app.buttons["guest.accounts.archived"].waitForExistence(timeout: 10))
        app.buttons["guest.accounts.archived"].tap()
        let restore = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'guest.account.restore.'")).firstMatch
        XCTAssertTrue(restore.waitForExistence(timeout: 10))
        capture("guest-archived-list")
        restore.tap()
        app.buttons["Done"].tap()
        XCTAssertTrue(guestRow("Locked").waitForExistence(timeout: 10), "restored where it was")
        XCTAssertTrue(guestRow("Locked").label.contains("100.00"), "balance kept: " + guestRow("Locked").label)
    }

    func testGuestAccountsInSpanishAndAssetShare() throws {
        launchSignedOut(arguments: ["--cuadrao-guest-book"], language: "es-419")
        enterGuestBook()
        XCTAssertTrue(app.staticTexts["Empieza con una cuenta."].exists)
        capture("guest-accounts-empty-es")
        tapVisible(app.buttons["accounts.add"])
        XCTAssertTrue(app.buttons["guest.account.type.checking"].waitForExistence(timeout: 10))
        capture("guest-account-form-es")
        saveAccount(type: "credit_card", name: "Tarjeta", amount: "100")
        XCTAssertTrue(guestRow("Tarjeta").label.contains("pendiente"), guestRow("Tarjeta").label)
        addGuestAccount(type: "savings", name: "Sin saldo")
        XCTAssertTrue(guestRow("Sin saldo").label.contains("Saldo desconocido"), guestRow("Sin saldo").label)
        capture("guest-accounts-es")
        tapVisible(guestRow("Tarjeta"))
        XCTAssertTrue(app.buttons["guest.account.archive"].waitForExistence(timeout: 10))
        XCTAssertEqual(app.buttons["guest.account.archive"].label, "Archivar cuenta")
        capture("guest-account-detail-es")
        app.buttons["guest.account.archive"].tap()
        XCTAssertTrue(app.buttons["accounts.archive.confirm"].waitForExistence(timeout: 10))
        app.buttons["accounts.archive.cancel"].tap()

        // An asset keeps the share the person owns.
        app.accountBack.tap()
        tapVisible(app.buttons["accounts.add"])
        app.buttons["guest.account.otherAssets"].tap()
        app.buttons["guest.account.type.property"].tap()
        app.buttons["guest.account.share"].tap()
        app.buttons["La mitad · 50%"].tap()
        fillAmount("100000")
        closeKeyboard()
        app.buttons["guest.account.save"].tap()
        XCTAssertTrue(guestRow("Propiedad").waitForExistence(timeout: 10))
        XCTAssertTrue(guestRow("Propiedad").label.contains("Tu parte: 50%"), guestRow("Propiedad").label)
    }

    /// Holding a row and dragging it reorders Home's accounts, and the order is part of the book, so it survives a relaunch.
    func testGuestAccountOrderIsKeptInTheBook() throws {
        launchSignedOut(arguments: ["--cuadrao-guest-book"])
        enterGuestBook()
        for name in ["First", "Second", "Third"] { addGuestAccount(type: "cash", name: name, amount: "1") }
        func order() -> [String] {
            ["First", "Second", "Third"].sorted { guestRow($0).frame.minY < guestRow($1).frame.minY }
        }
        XCTAssertEqual(order(), ["First", "Second", "Third"], "new accounts are added at the end")
        app.swipeUp()
        guestRow("Third").press(forDuration: 1.2, thenDragTo: guestRow("Second"))
        let moved = NSPredicate { _, _ in order() == ["First", "Third", "Second"] }
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: moved, object: nil)], timeout: 10), .completed,
                       "dragging Third onto the top of Second puts it before Second: \(order())")
        capture("guest-accounts-reordered")

        app.terminate()
        app.launchArguments = ["-AppleLanguages", "(en)", "-AppleLocale", "en_US", "-appearancePreference", "light", "--cuadrao-guest-book"]
        app.launch()
        XCTAssertTrue(guestRow("Third").waitForExistence(timeout: 20))
        XCTAssertEqual(order(), ["First", "Third", "Second"], "the order is saved in the book")
    }
    /// The sheet's Add button rides above the keyboard. While Name is being typed, the balance under it must stay visible
    /// and clear of the button, so a tap on the field never saves the account by mistake.
    func testGuestBalanceStaysClearOfAddWhileTypingAName() throws {
        launchSignedOut(arguments: ["--cuadrao-guest-book"])
        enterGuestBook()
        tapVisible(app.buttons["accounts.add"])
        XCTAssertTrue(app.buttons["guest.account.type.checking"].waitForExistence(timeout: 10))
        app.buttons["guest.account.type.checking"].tap()
        let name = app.textFields["guest.account.name"]
        name.tap()
        name.typeText("Main")
        XCTAssertTrue(app.keyboards.firstMatch.waitForExistence(timeout: 5))
        let amount = app.textFields["guest.account.amount"]
        let save = app.buttons["guest.account.save"]
        let clear = NSPredicate { _, _ in amount.frame.maxY <= save.frame.minY }
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: clear, object: nil)], timeout: 5), .completed,
                       "balance \(amount.frame) sits above Add \(save.frame)")
        capture("guest-account-balance-clear-of-add")
        amount.tap()
        amount.typeText("25")
        XCTAssertTrue(save.exists, "tapping the balance keeps the sheet open")
        XCTAssertEqual(amount.value as? String, "25")
    }
}
