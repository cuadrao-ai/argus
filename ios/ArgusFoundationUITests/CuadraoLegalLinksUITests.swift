import XCTest

/// The legal links read one owner, `CuadraoLegalURLs`, which is empty until the Cuadrao pages are published.
/// While it is empty no screen shows a legal link; `--cuadrao-legal-test-urls` (Debug only) fills it with test pages.
extension FinancialLoopUITests {
    private static let legalTestURLs = "--cuadrao-legal-test-urls"

    private func launchLegal(testURLs: Bool, dark: Bool = false) {
        continueAfterFailure = false
        app.terminate()
        app.launchArguments = ["-AppleLanguages", "(es-419)", "-AppleLocale", "es_DO",
                               "-appearancePreference", dark ? "dark" : "light",
                               "--cuadrao-guest-book", "--cuadrao-guest-notices-seen", "--cuadrao-guest-reset"]
            + (testURLs ? [Self.legalTestURLs] : [])
        app.launch()
    }

    private func openGuestProfile() {
        let guest = app.buttons["cuadrao.welcome.guest"]
        XCTAssertTrue(guest.waitForExistence(timeout: 15))
        guest.tap()
        XCTAssertTrue(app.buttons["header.profile"].waitForExistence(timeout: 10))
        app.buttons["header.profile"].tap()
        XCTAssertTrue(app.descendants(matching: .any)["guest.profile"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.buttons["guest.profile.preferences"].waitForExistence(timeout: 5))
    }

    private func openSignUp() {
        let signUp = app.buttons["cuadrao.welcome.signup"]
        XCTAssertTrue(signUp.waitForExistence(timeout: 15))
        signUp.tap()
        XCTAssertTrue(app.buttons["cuadrao.signup.email"].waitForExistence(timeout: 10))
    }

    func testGuestProfileHidesTheLegalLinksUntilThePagesArePublished() throws {
        for dark in [false, true] {
            launchLegal(testURLs: false, dark: dark)
            openGuestProfile()
            XCTAssertFalse(app.descendants(matching: .any)["guest.profile.terms"].exists)
            XCTAssertFalse(app.descendants(matching: .any)["guest.profile.legal"].exists)
            XCTAssertFalse(app.staticTexts["Acerca de Cuadrao"].exists, "no empty group")
            capture("legal-guest-profile-sin-enlaces-" + (dark ? "dark" : "light"))
        }
    }

    func testGuestProfileShowsTheLegalLinksFromTheOwnerAndOpensThem() throws {
        launchLegal(testURLs: true)
        openGuestProfile()
        let terms = app.descendants(matching: .any)["guest.profile.terms"]
        XCTAssertTrue(terms.waitForExistence(timeout: 5))
        XCTAssertTrue(app.descendants(matching: .any)["guest.profile.legal"].exists)
        capture("legal-guest-profile-con-enlaces")
        tapVisible(terms)
        let safari = XCUIApplication(bundleIdentifier: "com.apple.mobilesafari")
        XCTAssertTrue(safari.wait(for: .runningForeground, timeout: 15), "the terms link opens the owner's URL")
        safari.terminate()
    }

    func testSignUpHidesTheLegalLinksUntilThePagesArePublished() throws {
        for dark in [false, true] {
            launchLegal(testURLs: false, dark: dark)
            openSignUp()
            XCTAssertFalse(app.descendants(matching: .any)["cuadrao.signup.terms"].exists)
            XCTAssertFalse(app.descendants(matching: .any)["cuadrao.signup.privacy"].exists)
            capture("legal-registro-sin-enlaces-" + (dark ? "dark" : "light"))
        }
    }

    func testSignUpShowsTheLegalLinksFromTheOwner() throws {
        launchLegal(testURLs: true)
        openSignUp()
        XCTAssertTrue(app.descendants(matching: .any)["cuadrao.signup.terms"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.descendants(matching: .any)["cuadrao.signup.privacy"].exists)
        capture("legal-registro-con-enlaces")
    }

    /// Needs the isolated synthetic identity; the first run records the Profile screenshots.
    func testConnectedProfileShowsTheUnavailableLineUntilThePagesArePublished() throws {
        try signIn()
        for look in ["light", "dark"] {
            app.terminate()
            app.launchArguments = ["-AppleLanguages", "(es-419)", "-AppleLocale", "es_DO", "-appearancePreference", look,
                                   "--cuadrao-release-gates"]
            app.launch()
            app.openProfileSurface()
            tapVisible(app.buttons["cuadrao.profile.help"])
            XCTAssertTrue(app.staticTexts["Los enlaces no están disponibles en este momento."].waitForExistence(timeout: 5))
            XCTAssertFalse(app.descendants(matching: .any)["release.legal.terms"].exists)
            XCTAssertFalse(app.descendants(matching: .any)["release.legal.privacy"].exists)
            capture("legal-perfil-sin-enlaces-" + look)
        }
    }

    func testConnectedProfileShowsTheLegalLinksFromTheOwner() throws {
        try signIn()
        app.terminate()
        app.launchArguments = ["-AppleLanguages", "(es-419)", "-AppleLocale", "es_DO", "-appearancePreference", "light",
                               "--cuadrao-release-gates", Self.legalTestURLs]
        app.launch()
        app.openProfileSurface()
        tapVisible(app.buttons["cuadrao.profile.help"])
        XCTAssertTrue(app.descendants(matching: .any)["release.legal.terms"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.descendants(matching: .any)["release.legal.privacy"].exists)
        XCTAssertFalse(app.staticTexts["Los enlaces no están disponibles en este momento."].exists)
    }
}
