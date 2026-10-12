import XCTest

/// Accounts in the on-device book: every type, exact digits per currency, unknown versus zero, the currency and type
/// locks, archive and restore, and a relaunch that changes nothing. No server is involved.
extension FinancialLoopUITests {
    private func guestRow(_ name: String) -> XCUIElement {
        app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'guest.account.row.' AND label CONTAINS %@", name)).firstMatch
    }

    private func fillAmount(_ text: String) {
        let amount = app.textFields["guest.account.amount"]
        amount.tap()
        amount.typeText(text)
    }

    private func closeKeyboard() { dismissGuestKeyboard() }

    private func chooseCurrency(_ code: String) {
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
        for row in ["transaction", "plan", "scanCamera", "choosePhoto", "chooseFile", "group", "invite"] {
            XCTAssertFalse(app.buttons["add.tray." + row].exists, row + " is not in the book yet")
        }
        capture("guest-add-tray")
        app.buttons["add.tray.account"].tap()
        XCTAssertEqual(app.buttons["guest.account.currency"].label, "Currency, DOP", "the first currency offered is the Dominican peso")
        saveAccount(type: "checking", name: "Everyday", amount: "1234.56")
        XCTAssertTrue(guestRow("Everyday").waitForExistence(timeout: 10))
        XCTAssertTrue(guestRow("Everyday").label.contains("1,234.56"), guestRow("Everyday").label)
        XCTAssertTrue(guestRow("Everyday").label.contains("DOP"))
        capture("guest-account-first")

        addGuestAccount(type: "cash", name: "Yen cash", currency: "JPY", amount: "15000")
        addGuestAccount(type: "savings", name: "Dinar savings", currency: "KWD", amount: "12.345")
        addGuestAccount(type: "credit_card", name: "Card", currency: "USD", amount: "250.50")
        addGuestAccount(type: "checking", name: "Euro unknown", currency: "EUR")
        addGuestAccount(type: "savings", name: "Zero known", currency: "USD", amount: "0")
        XCTAssertTrue(guestRow("Yen cash").label.contains("15,000"), "a 0-digit currency has no decimals: " + guestRow("Yen cash").label)
        XCTAssertFalse(guestRow("Yen cash").label.contains("15,000."))
        XCTAssertTrue(guestRow("Dinar savings").label.contains("12.345"), "a 3-digit currency keeps three: " + guestRow("Dinar savings").label)
        XCTAssertTrue(guestRow("Card").label.contains("-250.50"), "a debt is stored owed: " + guestRow("Card").label)
        XCTAssertTrue(guestRow("Card").label.contains("owed"))
        XCTAssertTrue(guestRow("Euro unknown").label.contains("Balance unknown"), "blank is unknown: " + guestRow("Euro unknown").label)
        XCTAssertTrue(guestRow("Zero known").label.contains("0.00"), "zero is a known balance: " + guestRow("Zero known").label)
        XCTAssertFalse(guestRow("Zero known").label.contains("unknown"))
        capture("guest-accounts-many-currencies")
        let names = ["Everyday", "Yen cash", "Dinar savings", "Card", "Euro unknown", "Zero known"]
        let before = names.map { guestRow($0).label }

        app.terminate()
        app.launchArguments = ["-AppleLanguages", "(en)", "-AppleLocale", "en_US", "-appearancePreference", "light", "--cuadrao-guest-book"]
        app.launch()
        XCTAssertTrue(guestRow("Everyday").waitForExistence(timeout: 20), "the book reopens with its accounts")
        XCTAssertFalse(app.buttons["cuadrao.welcome.signin"].exists)
        XCTAssertEqual(before, names.map { guestRow($0).label }, "every amount, caption and unknown balance survived the relaunch")
        capture("guest-accounts-after-relaunch")
    }

    func testGuestAmountFieldRefusesWhatTheCurrencyCannotHold() throws {
        launchSignedOut(arguments: ["--cuadrao-guest-book"])
        enterGuestBook()
        tapVisible(app.buttons["accounts.add"])
        app.buttons["guest.account.type.cash"].tap()
        chooseCurrency("JPY")
        let amount = app.textFields["guest.account.amount"]
        amount.tap()
        amount.typeText("12.5")
        let error = app.staticTexts["amount-error"]
        XCTAssertTrue(error.waitForExistence(timeout: 5), "a yen has no decimals")
        XCTAssertEqual(error.label, "Check decimal places for JPY.")
        XCTAssertEqual(amount.value as? String, "12.", "the digit was refused, nothing rounded")
        capture("guest-jpy-no-decimals")
        XCTAssertFalse(app.buttons["guest.account.save"].isEnabled, "no save while the amount is wrong")
        amount.typeText(XCUIKeyboardKey.delete.rawValue)
        XCTAssertTrue(error.waitForNonExistence(timeout: 5), "a valid edit clears the error")
        closeKeyboard()
        app.buttons["guest.account.cancel"].tap()
        XCTAssertTrue(app.buttons["guest.account.save"].waitForNonExistence(timeout: 5))
        tapVisible(app.buttons["accounts.add"])
        app.buttons["guest.account.type.savings"].tap()
        chooseCurrency("KWD")
        let dinar = app.textFields["guest.account.amount"]
        dinar.tap()
        dinar.typeText("12.12345")
        XCTAssertEqual(error.label, "Check decimal places for KWD.")
        XCTAssertEqual(dinar.value as? String, "12.123", "dinar keeps three decimals, so the fourth digit was refused")
        capture("guest-kwd-three-decimals")
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
        guestRow("Open later").tap()
        XCTAssertTrue(app.descendants(matching: .any)["guest.account.detail"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.staticTexts["No balance recorded"].exists)
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

        guestRow("Locked").tap()
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
        guestRow("Tarjeta").tap()
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
        guestRow("Third").coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).press(forDuration: 1.0, thenDragTo: guestRow("Second").coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.1)))
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
}
