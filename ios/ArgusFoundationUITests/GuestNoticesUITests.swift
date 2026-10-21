import XCTest

/// The three things the guest book says about itself, each without staying on screen: a line on the first open, a
/// "Crear cuenta" button at the top of Perfil, and a half-height sheet after the first saved expense.
extension FinancialLoopUITests {
    private func noticeAccount() {
        tapVisible(app.buttons["accounts.add"])
        XCTAssertTrue(app.buttons["guest.account.type.cash"].waitForExistence(timeout: 10))
        app.buttons["guest.account.type.cash"].tap()
        dismissGuestKeyboard()
        app.textFields["guest.account.amount"].tap()
        app.textFields["guest.account.amount"].typeText("1000")
        dismissGuestKeyboard()
        app.buttons["guest.account.save"].tap()
        XCTAssertTrue(app.buttons["guest.account.save"].waitForNonExistence(timeout: 10))
    }

    /// Saves one typed expense. Returns once the movement's own sheet has closed.
    private func noticeExpense(_ amount: String) {
        app.buttons["nav.add"].tap()
        XCTAssertTrue(app.buttons["add.tray.transaction"].waitForExistence(timeout: 5))
        app.buttons["add.tray.transaction"].tap()
        XCTAssertTrue(app.buttons["guest.movement.save"].waitForExistence(timeout: 10))
        app.textFields["guest.movement.amount"].tap()
        app.textFields["guest.movement.amount"].typeText(amount)
        dismissGuestKeyboard()
        app.buttons["guest.movement.save"].tap()
        XCTAssertTrue(app.buttons["guest.movement.save"].waitForNonExistence(timeout: 10))
    }

    private func relaunchGuestWithoutReset(language: [String] = ["-AppleLanguages", "(en)", "-AppleLocale", "en_US"]) {
        app.terminate()
        app.launchArguments = language + ["-appearancePreference", "light", "--cuadrao-guest-book"]
        app.launch()
    }

    private var modeLine: XCUIElement { app.staticTexts["Guest mode · only on this iPhone. It doesn't sync or join any account."].firstMatch }
    private var artSlot: XCUIElement { app.descendants(matching: .any)["guest.firstsave.art"] }
    private var firstSaveTitle: XCUIElement { app.staticTexts["guest.firstsave.title"] }

    func testTheModeLineShowsOnTheFirstOpenOnlyAndDoesNotStay() throws {
        launchSignedOut(arguments: ["--cuadrao-guest-book", "--cuadrao-guest-notices"])
        enterGuestBook()
        XCTAssertTrue(modeLine.waitForExistence(timeout: 5), "said once on the first open")
        XCTAssertEqual(modeLine.label, "Guest mode · only on this iPhone. It doesn't sync or join any account.")
        XCTAssertTrue(modeLine.waitForNonExistence(timeout: 12), "it goes away by itself, nothing stays on screen")
        XCTAssertTrue(app.buttons["header.profile"].isHittable, "the tab bar is usable once the line is gone")
        app.buttons["header.profile"].tap()
        XCTAssertTrue(app.staticTexts["guest.profile.mode"].waitForExistence(timeout: 10), "Perfil opens after the line is gone")
        app.buttons["tab.home"].tap()
        relaunchGuestWithoutReset()
        XCTAssertTrue(app.descendants(matching: .any)["guest.home.empty"].waitForExistence(timeout: 20))
        XCTAssertFalse(modeLine.waitForExistence(timeout: 3), "never again")
    }

    func testSpanishGuestToastWrapsAtLargeTextSizes() throws {
        for size in ["UICTContentSizeCategoryL", "UICTContentSizeCategoryXXXL", "UICTContentSizeCategoryAccessibilityXXXL"] {
            launchSignedOut(arguments: ["--cuadrao-guest-book", "--cuadrao-guest-notices", "-UIPreferredContentSizeCategoryName", size], language: "es-419")
            enterGuestBook()
            let line = app.staticTexts["Modo invitado · solo en este iPhone. No se sincroniza ni se une a ninguna cuenta."].firstMatch
            XCTAssertTrue(line.waitForExistence(timeout: 5))
            XCTAssertGreaterThanOrEqual(line.frame.minY, app.frame.minY)
            XCTAssertLessThanOrEqual(line.frame.maxY, app.frame.maxY)
            let close = app.buttons["toast.close"]
            XCTAssertEqual(close.label, "Cerrar")
            XCTAssertTrue(close.isHittable)
            capture("aviso-invitado-texto-" + size)
            close.tap()
            XCTAssertTrue(line.waitForNonExistence(timeout: 5))
        }
    }

    func testSpanishModeLineDoesNotReturnOnSecondLaunch() throws {
        launchSignedOut(arguments: ["--cuadrao-guest-book", "--cuadrao-guest-notices"], language: "es-419")
        enterGuestBook()
        let line = app.staticTexts["Modo invitado · solo en este iPhone. No se sincroniza ni se une a ninguna cuenta."].firstMatch
        XCTAssertTrue(line.waitForExistence(timeout: 5))
        XCTAssertTrue(line.waitForNonExistence(timeout: 12))
        relaunchGuestWithoutReset(language: ["-AppleLanguages", "(es-419)", "-AppleLocale", "es_DO"])
        XCTAssertTrue(app.descendants(matching: .any)["guest.home.empty"].waitForExistence(timeout: 20))
        XCTAssertFalse(line.waitForExistence(timeout: 3), "the note stays absent on second launch")
    }

    func testPerfilHasTheLineAndARealCreateAccountButton() throws {
        launchSignedOut(arguments: ["--cuadrao-guest-book", "--cuadrao-guest-notices"])
        enterGuestBook()
        app.buttons["header.profile"].tap()
        let line = app.staticTexts["guest.profile.mode"]
        XCTAssertTrue(line.waitForExistence(timeout: 10))
        XCTAssertEqual(line.label, "Guest mode · only on this iPhone")
        let create = app.buttons["guest.profile.signup"]
        XCTAssertTrue(create.exists)
        XCTAssertEqual(create.label, "Create account")
        XCTAssertGreaterThanOrEqual(create.frame.height, 44, "a 44 pt target")
        XCTAssertLessThan(line.frame.minY, create.frame.minY, "the line sits above the button")
        capture("guest-perfil-notice")
        create.tap()
        XCTAssertTrue(app.buttons["cuadrao.welcome.signup"].waitForExistence(timeout: 10), "the button leaves the book for the welcome screen")
    }

    func testTheFirstSaveSheetShowsOnceAndSwipesAway() throws {
        launchSignedOut(arguments: ["--cuadrao-guest-book", "--cuadrao-guest-notices"])
        enterGuestBook()
        noticeAccount()
        XCTAssertFalse(firstSaveTitle.exists, "saving an account is not the first expense")
        noticeExpense("250")
        XCTAssertTrue(firstSaveTitle.waitForExistence(timeout: 10), "after the first saved expense")
        XCTAssertEqual(firstSaveTitle.label, "Your expenses are only on this iPhone")
        let create = app.buttons["guest.firstsave.create"], later = app.buttons["guest.firstsave.later"]
        XCTAssertEqual(create.label, "Create account")
        XCTAssertEqual(later.label, "Not now")
        XCTAssertLessThan(create.frame.minY, later.frame.minY, "Create account first, Not now second")
        XCTAssertGreaterThanOrEqual(create.frame.height, 44)
        XCTAssertGreaterThanOrEqual(later.frame.height, 44)
        XCTAssertGreaterThan(firstSaveTitle.frame.minY, app.frame.height * 0.4, "the sheet is half height: its title sits in the lower half")
        XCTAssertTrue(app.buttons["Sheet Grabber"].exists, "a grabber")
        assertArtSlotAndButtonsFit()
        capture("guest-first-save-sheet")
        // Pull the sheet down to the bottom edge, as a person does. A swipe scoped to the title is too short to dismiss reliably.
        firstSaveTitle.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5))
            .press(forDuration: 0.05, thenDragTo: app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.98)),
                   withVelocity: .fast, thenHoldForDuration: 0)
        XCTAssertTrue(firstSaveTitle.waitForNonExistence(timeout: 5), "swipe to dismiss")
        XCTAssertTrue(app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'guest.movement.row.'")).firstMatch.waitForExistence(timeout: 5),
                      "the expense was saved, the sheet never stood in its way")
        noticeExpense("40")
        XCTAssertFalse(firstSaveTitle.waitForExistence(timeout: 3), "once only")
        relaunchGuestWithoutReset()
        XCTAssertTrue(app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'guest.movement.row.'")).firstMatch.waitForExistence(timeout: 20))
        XCTAssertFalse(firstSaveTitle.exists, "never again after a relaunch")
    }

    /// The empty art slot sits inside the sheet above the title, and nothing below it is pushed past the sheet or the screen.
    private func assertArtSlotAndButtonsFit(scheme: String = "light") {
        let create = app.buttons["guest.firstsave.create"], later = app.buttons["guest.firstsave.later"]
        XCTAssertTrue(artSlot.exists, "the empty art slot is in the sheet")
        XCTAssertGreaterThan(artSlot.frame.minY, app.frame.height * 0.4, "the slot is inside the half-height sheet, not behind it")
        XCTAssertLessThanOrEqual(artSlot.frame.maxY, firstSaveTitle.frame.minY, "the slot sits above the title")
        XCTAssertGreaterThan(artSlot.frame.height, 0, "the slot keeps room for the art")
        for button in [create, later] {
            XCTAssertGreaterThanOrEqual(button.frame.height, 44, "a 44 pt target")
            XCTAssertLessThanOrEqual(button.frame.maxY, app.frame.maxY, "inside the screen")
            XCTAssertTrue(button.isHittable, "reachable, never pushed off the sheet")
        }
        XCTAssertLessThan(create.frame.minY, later.frame.minY, "Create account first, Not now second")
        assertSheetFillsToItsBottom(scheme)
    }

    /// The color under the screenshot's pixel at a point, in 0...255 sRGB. The sheet's own material is a different
    /// color from the Welcome background, so the band under Not now shows up as a color difference.
    private func pixel(_ screenshot: XCUIScreenshot, atX x: CGFloat, y: CGFloat) -> [Int] {
        guard let cg = screenshot.image.cgImage else { return [] }
        let scale = CGFloat(cg.width) / app.frame.width
        var rgba = [UInt8](repeating: 0, count: 4)
        let context = CGContext(data: &rgba, width: 1, height: 1, bitsPerComponent: 8, bytesPerRow: 4,
                                space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)
        context?.draw(cg, in: CGRect(x: -x * scale, y: -(CGFloat(cg.height) - y * scale - 1), width: CGFloat(cg.width), height: CGFloat(cg.height)))
        return rgba.prefix(3).map(Int.init)
    }

    /// Under Not now the sheet is the same Welcome background as above the title, down to the sheet's bottom edge,
    /// in the scheme the app is showing. No grey sheet material band.
    private func assertSheetFillsToItsBottom(_ scheme: String = "light") {
        let later = app.buttons["guest.firstsave.later"]
        let shot = app.screenshot()
        let x = app.frame.midX
        let reference = pixel(shot, atX: x, y: artSlot.frame.midY)
        for y in [later.frame.maxY + 10, app.frame.maxY - 30] {
            let sample = pixel(shot, atX: x, y: y)
            XCTAssertEqual(sample.count, 3)
            XCTAssertTrue(zip(sample, reference).allSatisfy { abs($0 - $1) <= 3 },
                          "\(scheme): the sheet background reaches the bottom, at y=\(y) it is \(sample), above the title \(reference)")
        }
    }

    /// The same sheet in dark, in both languages: no grey band there either, and the captures are the dark screenshots.
    func testTheFirstSaveSheetFillsToItsBottomInDarkInBothLanguages() throws {
        for language in ["es-419", "en"] {
            launchSignedOut(arguments: ["--cuadrao-guest-book", "--cuadrao-guest-notices"], language: language)
            app.terminate()
            app.launchArguments = app.launchArguments.map { $0 == "light" ? "dark" : $0 }
            app.launch()
            enterGuestBook()
            noticeAccount()
            noticeExpense("250")
            XCTAssertTrue(firstSaveTitle.waitForExistence(timeout: 10), "\(language): the sheet shows after the first expense")
            assertArtSlotAndButtonsFit(scheme: "dark \(language)")
            capture("guest-first-save-sheet-\(language == "en" ? "en" : "es")-dark")
        }
    }

    func testNotNowClosesTheFirstSaveSheetAndCreateAccountLeavesForTheWelcome() throws {
        launchSignedOut(arguments: ["--cuadrao-guest-book", "--cuadrao-guest-notices"])
        enterGuestBook()
        noticeAccount()
        noticeExpense("90")
        XCTAssertTrue(firstSaveTitle.waitForExistence(timeout: 10))
        app.buttons["guest.firstsave.later"].tap()
        XCTAssertTrue(firstSaveTitle.waitForNonExistence(timeout: 5))
        XCTAssertTrue(app.buttons["nav.add"].exists, "back in the book")

        launchSignedOut(arguments: ["--cuadrao-guest-book", "--cuadrao-guest-notices"])
        enterGuestBook()
        noticeAccount()
        noticeExpense("90")
        XCTAssertTrue(firstSaveTitle.waitForExistence(timeout: 10), "a fresh book says it again")
        app.buttons["guest.firstsave.create"].tap()
        XCTAssertTrue(app.buttons["cuadrao.welcome.signup"].waitForExistence(timeout: 10))
    }

    /// The three notices in Spanish, for the screenshots.
    func testTheGuestNoticesInSpanish() throws {
        launchSignedOut(arguments: ["--cuadrao-guest-book", "--cuadrao-guest-notices"], language: "es-419")
        enterGuestBook()
        let line = app.staticTexts["Modo invitado · solo en este iPhone. No se sincroniza ni se une a ninguna cuenta."].firstMatch
        XCTAssertTrue(line.waitForExistence(timeout: 5))
        XCTAssertEqual(line.label, "Modo invitado · solo en este iPhone. No se sincroniza ni se une a ninguna cuenta.")
        capture("guest-notice-first-open-es")
        app.buttons["header.profile"].tap()
        XCTAssertTrue(app.staticTexts["guest.profile.mode"].waitForExistence(timeout: 10))
        XCTAssertEqual(app.staticTexts["guest.profile.mode"].label, "Modo invitado · solo en este iPhone", "Perfil keeps the locked label")
        XCTAssertTrue(app.buttons["guest.profile.signup"].waitForExistence(timeout: 5))
        XCTAssertFalse(app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS[c] 'Pasar tus datos'")).firstMatch.exists,
                       "moving the book to an account stays hidden in guest Perfil")
        XCTAssertEqual(app.buttons["guest.profile.signup"].label, "Crear cuenta")
        capture("guest-perfil-notice-es")
        app.buttons["tab.home"].tap()
        noticeAccount()
        noticeExpense("250")
        XCTAssertTrue(firstSaveTitle.waitForExistence(timeout: 10))
        XCTAssertEqual(firstSaveTitle.label, "Tus gastos solo están en este iPhone")
        XCTAssertEqual(app.buttons["guest.firstsave.later"].label, "Ahora no")
        XCTAssertEqual(app.buttons["guest.firstsave.create"].label, "Crear cuenta")
        assertArtSlotAndButtonsFit()
        capture("guest-first-save-sheet-es")
    }
}
