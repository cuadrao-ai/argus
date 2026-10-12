import XCTest

/// "Probar sin cuenta": the on-device book. None of these journeys needs the server; they run in the shared class
/// so the same launcher and synthetic stack can start them. Every launch passes `--cuadrao-guest-book`, the
/// development door; the release-set test proves the door is shut without it.
extension FinancialLoopUITests {
    /// Starts the app signed out. A session left by an earlier journey is signed out first.
    /// Closes the keyboard by tapping away, on the navigation bar's title. A build that still has a keyboard Done is closed
    /// with it as a fallback, so this works before and after that control goes.
    func dismissGuestKeyboard() {
        guard app.keyboards.firstMatch.exists else { return }
        let title = app.navigationBars.firstMatch.staticTexts.firstMatch
        if title.exists { title.tap() }
        if app.keyboards.firstMatch.waitForNonExistence(timeout: 1) { return }
        if app.buttons["Done"].firstMatch.exists { app.buttons["Done"].firstMatch.tap() }
    }

    func launchSignedOut(arguments: [String], language: String = "en", reset: Bool = true) {
        continueAfterFailure = false
        app.terminate()
        let locale = language == "es-419" ? ["-AppleLanguages", "(es-419)", "-AppleLocale", "es_DO"]
                                          : ["-AppleLanguages", "(en)", "-AppleLocale", "en_US"]
        app.launchArguments = locale + ["-appearancePreference", "light"] + arguments + (reset ? ["--cuadrao-guest-reset"] : [])
        app.launch()
        if !app.buttons["cuadrao.welcome.signin"].waitForExistence(timeout: 8), app.buttons["header.profile"].exists {
            app.buttons["header.profile"].tap()
            tapVisible(app.buttons["auth.signOut"])
            app.confirmSignOutIfAsked()
            XCTAssertTrue(app.buttons["cuadrao.welcome.signin"].waitForExistence(timeout: 20), "signed out to the welcome screen")
        }
    }

    func enterGuestBook() {
        let guest = app.buttons["cuadrao.welcome.guest"]
        XCTAssertTrue(guest.waitForExistence(timeout: 10), "the welcome screen offers the book")
        guest.tap()
        XCTAssertTrue(app.descendants(matching: .any)["guest.home.empty"].waitForExistence(timeout: 10), "the empty book's Home")
    }

    func testGuestBookWelcomeActionEmptyHomeAndProfile() throws {
        launchSignedOut(arguments: ["--cuadrao-guest-book"])
        let guest = app.buttons["cuadrao.welcome.guest"]
        XCTAssertTrue(guest.waitForExistence(timeout: 10))
        XCTAssertEqual(guest.label, "Try without an account")
        let signIn = app.buttons["cuadrao.welcome.signin"]
        XCTAssertGreaterThanOrEqual(guest.frame.height, 44, "a 44 pt target")
        XCTAssertGreaterThan(guest.frame.minY, signIn.frame.maxY, "under Sign in")
        XCTAssertLessThan(guest.frame.minY - signIn.frame.maxY, 20, "12 pt under Sign in")
        XCTAssertEqual(guest.frame.midX, signIn.frame.midX, accuracy: 2)
        capture("guest-welcome")

        guest.tap()
        XCTAssertTrue(app.descendants(matching: .any)["guest.home.empty"].waitForExistence(timeout: 10))
        XCTAssertEqual(app.staticTexts["home-greeting"].label, "Hello")
        XCTAssertTrue(app.staticTexts["guest.home.space"].exists)
        XCTAssertEqual(app.staticTexts["guest.home.space"].label, "This iPhone")
        XCTAssertTrue(app.staticTexts["Start with one account."].exists)
        for id in ["tab.home", "tab.plan", "nav.add", "tab.search", "header.profile"] { XCTAssertTrue(app.buttons[id].exists, id) }
        XCTAssertFalse(app.buttons["tab.argus"].exists, "the book has no assistant tab, even in a development build")
        XCTAssertFalse(app.buttons["cuadrao.updates.open"].exists, "no Updates bell")
        capture("guest-empty-home")

        app.buttons["header.profile"].tap()
        XCTAssertTrue(app.descendants(matching: .any)["guest.profile"].waitForExistence(timeout: 10))
        for id in ["guest.profile.signup", "guest.profile.signin", "guest.profile.preferences", "guest.profile.privacy"] {
            XCTAssertTrue(app.buttons[id].waitForExistence(timeout: 5), id)
        }
        XCTAssertEqual(app.staticTexts["guest.profile.notice"].label, "Your book on this iPhone is still here; it was not uploaded.")
        capture("guest-profile")
        for tab in ["tab.plan", "tab.search"] {
            app.buttons[tab].tap()
            XCTAssertTrue(app.buttons["tab.home"].waitForExistence(timeout: 5), tab)
        }
        app.buttons["header.profile"].tap()
        XCTAssertTrue(app.buttons["guest.profile.preferences"].waitForExistence(timeout: 5))
    }

    func testGuestBookPreferredCurrencySurvivesRelaunchAndAccountEntryKeepsTheBook() throws {
        launchSignedOut(arguments: ["--cuadrao-guest-book"])
        enterGuestBook()
        app.buttons["header.profile"].tap()
        app.buttons["guest.profile.preferences"].tap()
        let currency = app.buttons["guest.profile.currency"]
        XCTAssertTrue(currency.waitForExistence(timeout: 10))
        XCTAssertEqual(currency.value as? String ?? "", "")
        currency.tap()
        let euro = app.buttons["guest.currency.EUR"]
        XCTAssertTrue(euro.waitForExistence(timeout: 10), "the server's currencies, priority first")
        XCTAssertTrue(app.buttons["guest.currency.DOP"].exists)
        XCTAssertTrue(app.buttons["guest.currency.USD"].exists)
        capture("guest-currency-picker")
        euro.tap()
        XCTAssertTrue(app.buttons["guest.profile.currency"].waitForExistence(timeout: 5), "the picker closed on a choice")
        XCTAssertEqual(app.buttons["guest.profile.currency"].value as? String, "EUR")

        // Relaunch without a reset: the person lands in the book, not on the welcome screen.
        app.terminate()
        app.launchArguments = ["-AppleLanguages", "(en)", "-AppleLocale", "en_US", "-appearancePreference", "light", "--cuadrao-guest-book"]
        app.launch()
        XCTAssertTrue(app.descendants(matching: .any)["guest.home.empty"].waitForExistence(timeout: 20), "straight into the book")
        XCTAssertFalse(app.buttons["cuadrao.welcome.signin"].exists, "no welcome flash")
        capture("guest-relaunch-home")
        app.buttons["header.profile"].tap()
        app.buttons["guest.profile.preferences"].tap()
        XCTAssertEqual(app.buttons["guest.profile.currency"].value as? String, "EUR", "the book survived the relaunch")
        app.accountBack.tap()

        // Create account / Sign in leave the book untouched and say so; the book is still one tap away.
        app.buttons["guest.profile.signup"].tap()
        XCTAssertTrue(app.buttons["cuadrao.welcome.signup"].waitForExistence(timeout: 10), "the ordinary welcome")
        XCTAssertTrue(app.buttons["cuadrao.welcome.guest"].exists)
        app.buttons["cuadrao.welcome.guest"].tap()
        XCTAssertTrue(app.descendants(matching: .any)["guest.home.empty"].waitForExistence(timeout: 10))
        app.buttons["header.profile"].tap()
        app.buttons["guest.profile.preferences"].tap()
        XCTAssertEqual(app.buttons["guest.profile.currency"].value as? String, "EUR", "leaving and returning changed nothing")
    }

    func testGuestBookDeleteDataRemovesTheBook() throws {
        launchSignedOut(arguments: ["--cuadrao-guest-book"])
        enterGuestBook()
        app.buttons["header.profile"].tap()
        app.buttons["guest.profile.preferences"].tap()
        app.buttons["guest.profile.currency"].tap()
        app.buttons["guest.currency.USD"].tap()
        app.accountBack.tap()
        app.buttons["guest.profile.privacy"].tap()
        let delete = app.buttons["guest.profile.delete"]
        XCTAssertTrue(delete.waitForExistence(timeout: 10))
        XCTAssertEqual(delete.label, "Delete this iPhone's data")
        capture("guest-delete-data")
        delete.tap()
        let alert = app.alerts.firstMatch
        XCTAssertTrue(alert.waitForExistence(timeout: 5))
        XCTAssertTrue(alert.staticTexts["Delete this iPhone's data?"].exists)
        capture("guest-delete-confirm")
        alert.buttons["Cancel"].tap()
        XCTAssertTrue(delete.waitForExistence(timeout: 5), "Cancel keeps the book")
        delete.tap()
        alert.buttons["guest.delete.confirm"].firstMatch.tap()
        XCTAssertTrue(app.buttons["cuadrao.welcome.signin"].waitForExistence(timeout: 10), "back on the welcome screen")
        capture("guest-after-delete")

        // A new book starts empty: the preferred currency is gone.
        app.buttons["cuadrao.welcome.guest"].tap()
        XCTAssertTrue(app.descendants(matching: .any)["guest.home.empty"].waitForExistence(timeout: 10))
        app.buttons["header.profile"].tap()
        app.buttons["guest.profile.preferences"].tap()
        XCTAssertEqual(app.buttons["guest.profile.currency"].value as? String ?? "", "", "nothing survived the delete")

        // And a relaunch does not reopen the deleted book.
        app.terminate()
        app.launchArguments = ["-AppleLanguages", "(en)", "-AppleLocale", "en_US", "-appearancePreference", "light", "--cuadrao-guest-book"]
        app.launch()
        XCTAssertTrue(app.descendants(matching: .any)["guest.home.empty"].waitForExistence(timeout: 20), "the fresh book is the active one")
    }

    func testGuestBookInSpanish() throws {
        launchSignedOut(arguments: ["--cuadrao-guest-book"], language: "es-419")
        let guest = app.buttons["cuadrao.welcome.guest"]
        XCTAssertTrue(guest.waitForExistence(timeout: 10))
        XCTAssertEqual(guest.label, "Probar sin cuenta")
        capture("guest-welcome-es")
        guest.tap()
        XCTAssertTrue(app.descendants(matching: .any)["guest.home.empty"].waitForExistence(timeout: 10))
        XCTAssertEqual(app.staticTexts["home-greeting"].label, "Hola")
        XCTAssertEqual(app.staticTexts["guest.home.space"].label, "Este iPhone")
        XCTAssertTrue(app.staticTexts["Empieza con una cuenta."].exists)
        capture("guest-empty-home-es")
        app.buttons["header.profile"].tap()
        XCTAssertEqual(app.staticTexts["guest.profile.notice"].label, "Tu libro de este iPhone sigue aquí; no se subió.")
        XCTAssertEqual(app.buttons["guest.profile.signup"].label, "Crear cuenta")
        capture("guest-profile-es")
        app.buttons["guest.profile.privacy"].tap()
        XCTAssertEqual(app.buttons["guest.profile.delete"].label, "Eliminar los datos de este iPhone")
        app.buttons["guest.profile.delete"].tap()
        XCTAssertTrue(app.alerts.firstMatch.staticTexts["¿Eliminar los datos de este iPhone?"].waitForExistence(timeout: 5))
        capture("guest-delete-confirm-es")
        app.alerts.firstMatch.buttons["Cancelar"].tap()
    }

    /// The release set does not open the door: the welcome screen keeps its two actions and nothing else.
    func testReleaseSetWelcomeHasNoGuestAction() throws {
        launchSignedOut(arguments: ["--cuadrao-release-gates"], reset: false)
        XCTAssertTrue(app.buttons["cuadrao.welcome.signup"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.buttons["cuadrao.welcome.signin"].exists)
        XCTAssertFalse(app.buttons["cuadrao.welcome.guest"].exists, "no third action without the guest door")
        XCTAssertFalse(app.staticTexts["Try without an account"].exists)
        capture("guest-release-welcome-two-actions")
    }
}
