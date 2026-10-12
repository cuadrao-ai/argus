import XCTest

/// Goals and budgets in the on-device book: the shared plan editor with only the two kinds the book has, a goal's progress
/// from contributions typed by hand, a budget counting this month's expenses in its scope. No server is involved.
extension FinancialLoopUITests {
    private func guestRow(_ name: String) -> XCUIElement {
        app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'guest.account.row.' AND label CONTAINS %@", name)).firstMatch
    }

    private func planRow(_ name: String) -> XCUIElement {
        app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'guest.plan.row.' AND label CONTAINS %@", name)).firstMatch
    }

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

    private func recordExpense(_ amount: String, category: String, account: String? = nil, note: String) {
        app.buttons["nav.add"].tap()
        XCTAssertTrue(app.buttons["add.tray.transaction"].waitForExistence(timeout: 5))
        app.buttons["add.tray.transaction"].tap()
        XCTAssertTrue(app.buttons["guest.movement.save"].waitForExistence(timeout: 10))
        app.textFields["guest.movement.amount"].tap()
        app.textFields["guest.movement.amount"].typeText(amount)
        dismissGuestKeyboard()
        app.buttons["guest.movement.category"].tap()
        app.buttons[category].tap()
        app.textFields["guest.movement.note"].tap()
        app.textFields["guest.movement.note"].typeText(note)
        dismissGuestKeyboard()
        app.buttons["guest.movement.save"].tap()
        XCTAssertTrue(app.buttons["guest.movement.save"].waitForNonExistence(timeout: 10))
    }

    private func disclosure(_ title: String) -> XCUIElement {
        app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", title)).firstMatch
    }

    private func fill(_ identifier: String, _ text: String) {
        let field = app.textFields[identifier]
        XCTAssertTrue(field.waitForExistence(timeout: 10), identifier)
        field.tap()
        field.typeText(text)
    }

    func testGuestGoalProgressComesFromContributionsTypedByHand() throws {
        launchSignedOut(arguments: ["--cuadrao-guest-book"])
        enterGuestBook()
        addAccount(type: "checking", name: "Main", currency: "USD", amount: "1000")
        app.buttons["tab.plan"].tap()
        XCTAssertTrue(app.descendants(matching: .any)["guest.plan"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.staticTexts["Make my first plan"].exists || app.buttons["Make my first plan"].exists, "the empty Plan invites a first plan")
        capture("guest-plan-empty")

        app.buttons["plan-create"].tap()
        XCTAssertTrue(app.buttons["guest.plan.kind.goal"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.buttons["guest.plan.kind.budget"].exists)
        XCTAssertFalse(app.buttons["guest.plan.kind.debt"].exists, "the book has no debt plans")
        fill("guest.plan.name", "Trip")
        dismissGuestKeyboard()
        fill("guest.plan.target", "1500")
        dismissGuestKeyboard()
        fill("guest.plan.monthly", "250")
        dismissGuestKeyboard()
        capture("guest-plan-editor-goal")
        app.buttons["guest.plan.save"].tap()
        XCTAssertTrue(planRow("Trip").waitForExistence(timeout: 10))
        XCTAssertTrue(planRow("Trip").label.contains("USD 0.00"), planRow("Trip").label)
        XCTAssertTrue(planRow("Trip").label.contains("Goal: USD 1,500.00"), planRow("Trip").label)
        capture("guest-plan-card-goal")

        planRow("Trip").tap()
        XCTAssertTrue(app.buttons["guest.plan.contribute"].waitForExistence(timeout: 10))
        XCTAssertEqual(app.staticTexts["guest.plan.amount"].label, "USD 0.00")
        app.buttons["guest.plan.contribute"].tap()
        XCTAssertTrue(app.textFields["guest.contribution.amount"].waitForExistence(timeout: 10))
        fill("guest.contribution.amount", "300")
        dismissGuestKeyboard()
        app.buttons["guest.contribution.save"].tap()
        XCTAssertTrue(app.buttons["guest.contribution.save"].waitForNonExistence(timeout: 10))
        XCTAssertEqual(app.staticTexts["guest.plan.amount"].label, "USD 300.00")
        XCTAssertEqual(app.staticTexts["guest.plan.percent"].label, "20%")
        XCTAssertEqual(app.staticTexts["guest.plan.remaining"].label, "Left USD 1,200.00")
        app.buttons["guest.plan.contribute"].tap()
        fill("guest.contribution.amount", "150.50")
        dismissGuestKeyboard()
        app.buttons["guest.contribution.save"].tap()
        XCTAssertTrue(app.buttons["guest.contribution.save"].waitForNonExistence(timeout: 10))
        XCTAssertEqual(app.staticTexts["guest.plan.amount"].label, "USD 450.50")
        XCTAssertEqual(app.staticTexts["guest.plan.percent"].label, "30%")
        capture("guest-plan-detail-goal")

        // Deleting a contribution takes it out of the progress, and Undo brings it back.
        let rows = app.descendants(matching: .any).matching(NSPredicate(format: "identifier BEGINSWITH 'guest.contribution.row.'"))
        XCTAssertTrue(rows.firstMatch.waitForExistence(timeout: 5), "the contributions are listed")
        rows.firstMatch.swipeLeft()
        XCTAssertTrue(app.buttons["guest.contribution.swipe.delete"].waitForExistence(timeout: 5))
        app.buttons["guest.contribution.swipe.delete"].tap()
        XCTAssertTrue(app.buttons["guest.undo"].waitForExistence(timeout: 10))
        XCTAssertNotEqual(app.staticTexts["guest.plan.amount"].label, "USD 450.50")
        app.buttons["guest.undo"].tap()
        XCTAssertTrue(app.staticTexts["guest.plan.amount"].waitForExistence(timeout: 5))
        XCTAssertEqual(app.staticTexts["guest.plan.amount"].label, "USD 450.50")

        // Everything is in the book: a relaunch changes nothing.
        app.terminate()
        app.launchArguments = ["-AppleLanguages", "(en)", "-AppleLocale", "en_US", "-appearancePreference", "light", "--cuadrao-guest-book"]
        app.launch()
        XCTAssertTrue(app.buttons["tab.plan"].waitForExistence(timeout: 20))
        app.buttons["tab.plan"].tap()
        XCTAssertTrue(planRow("Trip").waitForExistence(timeout: 10))
        XCTAssertTrue(planRow("Trip").label.contains("USD 450.50"), planRow("Trip").label)

        // Archive keeps it, with Undo, and a list to restore it from.
        planRow("Trip").tap()
        app.buttons["plan-detail-options"].tap()
        app.buttons["guest.plan.archive"].tap()
        XCTAssertTrue(app.buttons["guest.undo"].waitForExistence(timeout: 10), "back on the Plan tab with Undo")
        XCTAssertFalse(planRow("Trip").exists)
        XCTAssertTrue(app.buttons["plan-archives"].exists)
        capture("guest-plan-archived")
        app.buttons["guest.undo"].tap()
        XCTAssertTrue(planRow("Trip").waitForExistence(timeout: 10))
    }

    func testGuestBudgetCountsThisMonthsExpensesInItsScope() throws {
        launchSignedOut(arguments: ["--cuadrao-guest-book"])
        enterGuestBook()
        addAccount(type: "checking", name: "Main", currency: "USD", amount: "1000")
        addAccount(type: "savings", name: "Savings", currency: "USD", amount: "500")
        let mainID = guestRowID("Main") ?? ""
        XCTAssertFalse(mainID.isEmpty)

        app.buttons["nav.add"].tap()
        XCTAssertTrue(app.buttons["add.tray.plan"].waitForExistence(timeout: 5), "the tray offers Plan once an account exists")
        app.buttons["add.tray.plan"].tap()
        XCTAssertTrue(app.buttons["guest.plan.kind.budget"].waitForExistence(timeout: 10))
        app.buttons["guest.plan.kind.budget"].tap()
        XCTAssertFalse(app.textFields["guest.plan.monthly"].exists, "a budget has a limit, not a monthly contribution")
        fill("guest.plan.name", "Food")
        dismissGuestKeyboard()
        fill("guest.plan.target", "300")
        dismissGuestKeyboard()
        tapVisible(disclosure("Accounts"))
        tapVisible(app.buttons["guest.plan.scope.account." + mainID])
        tapVisible(disclosure("Categories"))
        tapVisible(app.buttons["guest.plan.scope.category.groceries"])
        tapVisible(app.buttons["guest.plan.scope.category.dining"])
        capture("guest-plan-editor-budget-scope")
        tapVisible(app.buttons["guest.plan.save"])
        XCTAssertTrue(app.buttons["guest.plan.save"].waitForNonExistence(timeout: 10))

        recordExpense("40", category: "Groceries", note: "Market")
        recordExpense("20", category: "Transport", note: "Taxi")
        recordExpense("15", category: "Dining out", note: "Lunch")
        app.buttons["tab.plan"].tap()
        XCTAssertTrue(planRow("Food").waitForExistence(timeout: 10))
        XCTAssertTrue(planRow("Food").label.contains("USD 55.00"), "groceries and dining count, transport does not: " + planRow("Food").label)
        capture("guest-plan-card-budget")
        planRow("Food").tap()
        XCTAssertTrue(app.staticTexts["guest.plan.remaining"].waitForExistence(timeout: 10))
        XCTAssertEqual(app.staticTexts["guest.plan.amount"].label, "USD 55.00")
        XCTAssertEqual(app.staticTexts["guest.plan.remaining"].label, "Left USD 245.00")
        XCTAssertEqual(app.staticTexts["guest.plan.percent"].label, "18%")
        capture("guest-plan-detail-budget")
    }

    func testGuestPlansInSpanish() throws {
        launchSignedOut(arguments: ["--cuadrao-guest-book"], language: "es-419")
        enterGuestBook()
        addAccount(type: "checking", name: "Principal", currency: "USD", amount: "1000")
        app.buttons["tab.plan"].tap()
        XCTAssertTrue(app.descendants(matching: .any)["guest.plan"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.staticTexts["Lo que viene"].exists)
        XCTAssertTrue(app.buttons["Crear mi primer plan"].exists || app.staticTexts["Crear mi primer plan"].exists)
        capture("guest-plan-empty-es")
        app.buttons["plan-create"].tap()
        XCTAssertEqual(app.buttons["guest.plan.kind.goal"].label, "Meta")
        XCTAssertEqual(app.buttons["guest.plan.kind.budget"].label, "Mi mes")
        fill("guest.plan.name", "Viaje")
        dismissGuestKeyboard()
        fill("guest.plan.target", "1500")
        dismissGuestKeyboard()
        fill("guest.plan.monthly", "250")
        dismissGuestKeyboard()
        capture("guest-plan-editor-goal-es")
        app.buttons["guest.plan.save"].tap()
        XCTAssertTrue(planRow("Viaje").waitForExistence(timeout: 10))
        XCTAssertTrue(planRow("Viaje").label.contains("Meta: USD 1,500.00"), planRow("Viaje").label)
        capture("guest-plan-card-goal-es")
        planRow("Viaje").tap()
        XCTAssertEqual(app.buttons["guest.plan.contribute"].label, "Añadir aporte")
        app.buttons["guest.plan.contribute"].tap()
        fill("guest.contribution.amount", "300")
        dismissGuestKeyboard()
        app.buttons["guest.contribution.save"].tap()
        XCTAssertTrue(app.buttons["guest.contribution.save"].waitForNonExistence(timeout: 10))
        XCTAssertEqual(app.staticTexts["guest.plan.remaining"].label, "Falta USD 1,200.00")
        XCTAssertEqual(app.staticTexts["guest.plan.percent"].label, "20%")
        capture("guest-plan-detail-goal-es")
    }

    /// The plan screens stay usable at the largest accessibility text size: nothing needed is out of reach.
    func testGuestPlansAtLargeText() throws {
        launchSignedOut(arguments: ["--cuadrao-guest-book", "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"])
        enterGuestBook()
        addAccount(type: "checking", name: "Main", currency: "USD", amount: "1000")
        for _ in 0..<4 { app.swipeDown(velocity: .fast) }
        app.buttons["tab.plan"].tap()
        XCTAssertTrue(app.descendants(matching: .any)["guest.plan"].waitForExistence(timeout: 10))
        capture("guest-plan-empty-large")
        app.buttons["plan-create"].tap()
        XCTAssertTrue(app.buttons["guest.plan.kind.goal"].waitForExistence(timeout: 10))
        fill("guest.plan.name", "Trip")
        dismissGuestKeyboard()
        fill("guest.plan.target", "1500")
        dismissGuestKeyboard()
        fill("guest.plan.monthly", "250")
        dismissGuestKeyboard()
        capture("guest-plan-editor-large")
        XCTAssertTrue(app.buttons["guest.plan.save"].isHittable, "Create plan stays reachable at large text")
        app.buttons["guest.plan.save"].tap()
        XCTAssertTrue(planRow("Trip").waitForExistence(timeout: 10))
        capture("guest-plan-card-large")
        planRow("Trip").tap()
        XCTAssertTrue(app.buttons["guest.plan.contribute"].waitForExistence(timeout: 10))
        tapVisible(app.buttons["guest.plan.contribute"])
        XCTAssertTrue(app.textFields["guest.contribution.amount"].waitForExistence(timeout: 10))
        capture("guest-contribution-large")
        XCTAssertTrue(app.buttons["guest.contribution.save"].exists)
    }

    /// The id suffix of an account row, to name its scope toggle.
    private func guestRowID(_ name: String) -> String? {
        let identifier = guestRow(name).identifier
        return identifier.isEmpty ? nil : identifier.replacingOccurrences(of: "guest.account.row.", with: "")
    }
}
