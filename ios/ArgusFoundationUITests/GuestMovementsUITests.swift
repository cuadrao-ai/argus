import XCTest

/// Movements in the on-device book: expense, income and same-currency transfer, derived balances, edit, delete with Undo,
/// archived accounts, the balance chart and spending with coverage. No server is involved.
extension FinancialLoopUITests {
    private func guestRow(_ name: String) -> XCUIElement {
        app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'guest.account.row.' AND label CONTAINS %@", name)).firstMatch
    }

    private func movementRow(_ text: String) -> XCUIElement {
        app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'guest.movement.row.' AND label CONTAINS %@", text)).firstMatch
    }

    private func closeKeyboard() { dismissGuestKeyboard() }

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
        closeKeyboard()
        app.buttons["guest.account.save"].tap()
        XCTAssertTrue(app.buttons["guest.account.save"].waitForNonExistence(timeout: 10))
    }

    /// Opens the movement sheet from the + tray.
    private func openMovementSheet() {
        app.buttons["nav.add"].tap()
        XCTAssertTrue(app.buttons["add.tray.transaction"].waitForExistence(timeout: 5), "the tray offers Transaction once an account exists")
        app.buttons["add.tray.transaction"].tap()
        XCTAssertTrue(app.buttons["guest.movement.save"].waitForExistence(timeout: 10))
    }

    private func chooseAccount(_ identifier: String, _ name: String) {
        app.buttons[identifier].tap()
        let option = app.buttons[name]
        XCTAssertTrue(option.waitForExistence(timeout: 5), name)
        option.tap()
    }

    private func saveMovement() {
        closeKeyboard()
        let save = app.buttons["guest.movement.save"]
        XCTAssertTrue(save.isEnabled, "the movement is valid")
        save.tap()
        XCTAssertTrue(save.waitForNonExistence(timeout: 10), "the sheet closes on save")
    }

    func testGuestMovementsMoveMoneyDeriveBalancesEditDeleteAndUndo() throws {
        launchSignedOut(arguments: ["--cuadrao-guest-book"])
        enterGuestBook()
        app.buttons["nav.add"].tap()
        XCTAssertTrue(app.buttons["add.tray.account"].waitForExistence(timeout: 5))
        XCTAssertFalse(app.buttons["add.tray.transaction"].exists, "no Transaction row until there is an account")
        app.buttons["nav.add"].tap()
        addAccount(type: "checking", name: "Main", currency: "USD", amount: "1000")
        addAccount(type: "savings", name: "Savings", currency: "USD", amount: "500")
        addAccount(type: "checking", name: "Euro", currency: "EUR", amount: "100")
        XCTAssertEqual(app.staticTexts["guest.netBalance.USD"].label, "1,500.00", "the net balance of the preferred first currency")
        XCTAssertTrue(app.buttons["home-chart-currency"].exists, "two currencies, so a chooser")
        capture("guest-home-overview")

        // An expense lowers the account and the total.
        openMovementSheet()
        XCTAssertTrue(app.buttons["guest.movement.kind.expense"].isSelected)
        XCTAssertTrue(app.descendants(matching: .any)["guest.movement.date"].exists)
        let amount = app.textFields["guest.movement.amount"]
        amount.tap()
        amount.typeText("12.34")
        closeKeyboard()
        app.buttons["guest.movement.category"].tap()
        app.buttons["Dining out"].tap()
        let note = app.textFields["guest.movement.note"]
        note.tap()
        note.typeText("Coffee")
        capture("guest-movement-sheet")
        saveMovement()
        XCTAssertTrue(movementRow("Coffee").waitForExistence(timeout: 10))
        XCTAssertTrue(movementRow("Coffee").label.contains("12.34 USD"), movementRow("Coffee").label)
        XCTAssertTrue(guestRow("Main").label.contains("987.66"), guestRow("Main").label)
        XCTAssertEqual(app.staticTexts["guest.netBalance.USD"].label, "1,487.66")

        // An income raises another account.
        openMovementSheet()
        app.buttons["guest.movement.kind.income"].tap()
        XCTAssertFalse(app.buttons["guest.movement.category"].exists, "only expenses have a category")
        chooseAccount("guest.movement.account", "Savings")
        app.textFields["guest.movement.amount"].tap()
        app.textFields["guest.movement.amount"].typeText("50")
        saveMovement()
        XCTAssertTrue(guestRow("Savings").label.contains("550.00"), guestRow("Savings").label)
        XCTAssertEqual(app.staticTexts["guest.netBalance.USD"].label, "1,537.66")

        // A transfer moves money between two accounts of one currency and changes no total.
        openMovementSheet()
        app.buttons["guest.movement.kind.transfer"].tap()
        XCTAssertTrue(app.buttons["guest.movement.destination"].waitForExistence(timeout: 5))
        XCTAssertEqual(app.buttons["guest.movement.destination"].label, "Savings", "the first other account in the same currency")
        app.buttons["guest.movement.destination"].tap()
        XCTAssertFalse(app.buttons["Euro"].exists, "a euro account is not offered as the destination of a dollar transfer")
        app.buttons["Savings"].firstMatch.tap()
        app.textFields["guest.movement.amount"].tap()
        app.textFields["guest.movement.amount"].typeText("200")
        saveMovement()
        XCTAssertTrue(guestRow("Main").label.contains("787.66"), guestRow("Main").label)
        XCTAssertTrue(guestRow("Savings").label.contains("750.00"), guestRow("Savings").label)
        XCTAssertEqual(app.staticTexts["guest.netBalance.USD"].label, "1,537.66", "a transfer leaves the total alone")
        capture("guest-accounts-after-movements")

        // Edit through the detail.
        movementRow("Coffee").tap()
        XCTAssertTrue(app.descendants(matching: .any)["guest.movement.detail"].waitForExistence(timeout: 10))
        XCTAssertEqual(app.staticTexts["guest.movement.title"].label, "Coffee")
        capture("guest-movement-detail")
        app.buttons["guest.movement.edit"].tap()
        XCTAssertTrue(app.buttons["guest.movement.save"].waitForExistence(timeout: 10))
        let edited = app.textFields["guest.movement.amount"]
        XCTAssertEqual(edited.value as? String, "12.34", "the form opens on the stored amount")
        edited.coordinate(withNormalizedOffset: CGVector(dx: 0.98, dy: 0.5)).tap()
        edited.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: 5))
        edited.typeText("20")
        saveMovement()
        app.accountBack.tap()
        XCTAssertTrue(guestRow("Main").label.contains("780.00"), guestRow("Main").label)

        // Delete with Undo, from the detail.
        movementRow("Coffee").tap()
        app.buttons["guest.movement.delete"].tap()
        XCTAssertTrue(app.buttons["guest.undo"].waitForExistence(timeout: 10), "deleted, with Undo")
        XCTAssertFalse(movementRow("Coffee").exists)
        XCTAssertTrue(guestRow("Main").label.contains("800.00"), "a deleted movement stops counting: " + guestRow("Main").label)
        capture("guest-movement-deleted")
        app.buttons["guest.undo"].tap()
        XCTAssertTrue(movementRow("Coffee").waitForExistence(timeout: 10))
        XCTAssertTrue(guestRow("Main").label.contains("780.00"))

        // The account's own history, and no new activity on an archived account.
        guestRow("Savings").tap()
        XCTAssertTrue(app.buttons["guest.account.record"].waitForExistence(timeout: 10), "an account offers Add transaction")
        XCTAssertTrue(movementRow("50.00 USD").exists, "its income is listed")
        XCTAssertTrue(movementRow("200.00").exists, "so is the transfer it received")
        capture("guest-account-history")
        app.buttons["guest.account.archive"].tap()
        app.buttons["accounts.archive.confirm"].tap()
        XCTAssertTrue(app.buttons["accounts.archived.undo"].waitForExistence(timeout: 10))
        openMovementSheet()
        app.buttons["guest.movement.account"].tap()
        XCTAssertFalse(app.buttons["Savings"].exists, "an archived account takes no new movements")
        app.buttons["Main"].firstMatch.tap()
        app.buttons["Cancel"].tap()
        XCTAssertTrue(app.buttons["guest.movement.save"].waitForNonExistence(timeout: 5))

        // Everything survives a relaunch.
        let before = ["Main", "Euro"].map { guestRow($0).label }
        app.terminate()
        app.launchArguments = ["-AppleLanguages", "(en)", "-AppleLocale", "en_US", "-appearancePreference", "light", "--cuadrao-guest-book"]
        app.launch()
        XCTAssertTrue(guestRow("Main").waitForExistence(timeout: 20))
        XCTAssertEqual(before, ["Main", "Euro"].map { guestRow($0).label })
        XCTAssertTrue(movementRow("Coffee").exists, "the movements are still there")
    }

    func testGuestMovementsInSpanish() throws {
        launchSignedOut(arguments: ["--cuadrao-guest-book"], language: "es-419")
        enterGuestBook()
        tapVisible(app.buttons["accounts.add"])
        app.buttons["guest.account.type.cash"].tap()
        app.textFields["guest.account.name"].tap()
        app.textFields["guest.account.name"].typeText("Efectivo")
        app.textFields["guest.account.amount"].tap()
        app.textFields["guest.account.amount"].typeText("500")
        closeKeyboard()
        app.buttons["guest.account.save"].tap()
        XCTAssertTrue(app.buttons["guest.account.save"].waitForNonExistence(timeout: 10))
        app.buttons["nav.add"].tap()
        app.buttons["add.tray.transaction"].tap()
        XCTAssertTrue(app.buttons["guest.movement.save"].waitForExistence(timeout: 10))
        XCTAssertEqual(app.buttons["guest.movement.kind.expense"].label, "Gasto")
        XCTAssertEqual(app.buttons["guest.movement.kind.income"].label, "Ingreso")
        XCTAssertEqual(app.buttons["guest.movement.kind.transfer"].label, "Transferencia")
        XCTAssertEqual(app.buttons["guest.movement.save"].label, "Guardar")
        app.textFields["guest.movement.amount"].tap()
        app.textFields["guest.movement.amount"].typeText("75.50")
        app.textFields["guest.movement.note"].tap()
        app.textFields["guest.movement.note"].typeText("Mercado")
        closeKeyboard()
        capture("guest-movement-sheet-es")
        saveMovement()
        XCTAssertTrue(movementRow("Mercado").waitForExistence(timeout: 10))
        XCTAssertTrue(movementRow("Mercado").label.contains("75.50 DOP"), movementRow("Mercado").label)
        XCTAssertTrue(guestRow("Efectivo").label.contains("424.50"), guestRow("Efectivo").label)
        XCTAssertTrue(app.staticTexts["Movimientos"].exists)
        capture("guest-home-es")
        movementRow("Mercado").tap()
        XCTAssertEqual(app.buttons["guest.movement.delete"].label, "Eliminar movimiento")
        capture("guest-movement-detail-es")
        app.buttons["guest.movement.delete"].tap()
        XCTAssertEqual(app.buttons["guest.undo"].label, "Deshacer")
    }

    // MARK: A book with history

    private struct SeededBook {
        let directory: URL
        let data: Data

        /// Two dollar accounts opened 45 and 3 days ago, a euro account that was never given a balance, and spending on
        /// both dollar accounts over the last 40 days.
        init(now: Date = Date()) throws {
            directory = FileManager.default.temporaryDirectory.appendingPathComponent("guest-seed-" + UUID().uuidString, isDirectory: true)
            let formatter = ISO8601DateFormatter()
            func stamp(_ days: Double) -> String { formatter.string(from: now.addingTimeInterval(-days * 86_400)) }
            let main = UUID().uuidString, savings = UUID().uuidString, euro = UUID().uuidString
            func account(_ id: String, _ kind: String, _ currency: String, _ name: String, opening: (Int, Double)?) -> String {
                let open = opening.map { #","opening":{"amountMinor":\#($0.0),"asOf":"\#(stamp($0.1))","timeZone":"America/Santo_Domingo"}"# } ?? ""
                return #"{"id":"\#(id)","kind":"\#(kind)","currency":"\#(currency)","digits":2,"nickname":"\#(name)","archived":false,"ownershipShareBps":10000,"createdAt":"\#(stamp(45))"\#(open)}"#
            }
            func expense(_ account: String, _ minor: Int, _ days: Double, _ category: String, _ note: String) -> String {
                #"{"id":"\#(UUID().uuidString)","kind":"expense","accountID":"\#(account)","amountMinor":\#(minor),"occurredAt":"\#(stamp(days))","timeZone":"America/Santo_Domingo","note":"\#(note)","category":"\#(category)","deleted":false,"createdAt":"\#(stamp(days))"}"#
            }
            let accounts = [account(main, "checking", "USD", "Main", opening: (100_000, 45)),
                            account(savings, "savings", "USD", "Savings", opening: (50_000, 3)),
                            account(euro, "cash", "EUR", "Euro cash", opening: nil)]
            let movements = [expense(main, 10_000, 40, "groceries", "Old groceries"), expense(main, 4_000, 20, "dining", "Dinner"),
                             expense(main, 2_500, 2, "transport", "Taxi"), expense(savings, 1_000, 1, "dining", "Lunch")]
            let book = #"{"schemaVersion":1,"revision":9,"settings":{"primaryCurrency":"USD"},"accounts":[\#(accounts.joined(separator: ","))],"movements":[\#(movements.joined(separator: ","))]}"#
            data = Data(book.utf8)
        }

        func write() throws {
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            try data.write(to: directory.appendingPathComponent("book.json"))
        }
    }

    func testGuestBalanceChartAndSpendingCoverageFromABookWithHistory() throws {
        let seeded = try SeededBook()
        // The app reads the folder when the person opens the book, so it is written after the reset at launch.
        launchSignedOut(arguments: ["--cuadrao-guest-book", "--cuadrao-guest-directory", seeded.directory.path])
        let guest = app.buttons["cuadrao.welcome.guest"]
        XCTAssertTrue(guest.waitForExistence(timeout: 10))
        try seeded.write()
        guest.tap()
        XCTAssertTrue(guestRow("Main").waitForExistence(timeout: 20), "the seeded book opened")
        // 1000 - 100 - 40 - 25 = 835 on Main; 500 - 10 = 490 on Savings.
        XCTAssertTrue(guestRow("Main").label.contains("835.00"), guestRow("Main").label)
        XCTAssertTrue(guestRow("Savings").label.contains("490.00"), guestRow("Savings").label)
        XCTAssertTrue(guestRow("Euro cash").label.contains("Balance unknown"))
        XCTAssertTrue(app.descendants(matching: .any)["home-balance-chart"].waitForExistence(timeout: 10), "a line, because the balance spans several days")
        XCTAssertEqual(app.staticTexts["guest.netBalance.USD"].label, "1,325.00")
        capture("guest-home-chart")

        app.buttons["home-history-expand"].tap()
        XCTAssertTrue(app.descendants(matching: .any)["guest.insights"].waitForExistence(timeout: 10))
        let calendar = Calendar.current
        let coverage = Date().addingTimeInterval(-3 * 86_400)
        if calendar.isDate(coverage, equalTo: Date(), toGranularity: .month) {
            XCTAssertTrue(app.staticTexts["guest.spending.coverage"].waitForExistence(timeout: 10), "coverage begins inside this month")
        }
        XCTAssertTrue(app.descendants(matching: .any)["guest.spending.category.transport"].waitForExistence(timeout: 10), "this month's taxi")
        capture("guest-insights-this-month")
        let previous = app.buttons["guest.insights.previous"]
        if previous.isEnabled {
            previous.tap()
            let noData = app.descendants(matching: .any)["guest.spending.noData"]
            let recorded = app.descendants(matching: .any)["guest.spending.category.groceries"]
            XCTAssertTrue(noData.waitForExistence(timeout: 10) || recorded.exists || app.descendants(matching: .any)["guest.spending.category.dining"].exists,
                          "an earlier month is either not covered or shows only what was recorded")
            capture("guest-insights-earlier-month")
        }
        app.buttons["Done"].tap()
        XCTAssertTrue(guestRow("Main").waitForExistence(timeout: 10))
    }
}

