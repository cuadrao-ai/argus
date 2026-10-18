import XCTest

/// The legal links read one owner, `CuadraoLegalURLs`, which is empty until the Cuadrao pages are published.
/// While it is empty no screen shows a legal link; `--cuadrao-legal-test-urls` (Debug only) fills it with test pages.
extension FinancialLoopUITests {
    private static let legalTestURLs = "--cuadrao-legal-test-urls"
    private static let acceptanceSentence = "Al continuar, aceptas los Términos y la Política de privacidad."

    private func launchLegal(testURLs: Bool, dark: Bool = false, spanish: Bool = true, arguments: [String] = []) {
        continueAfterFailure = false
        app.terminate()
        app.launchArguments = ["-AppleLanguages", spanish ? "(es-419)" : "(en)", "-AppleLocale", spanish ? "es_DO" : "en_US",
                               "-appearancePreference", dark ? "dark" : "light",
                               "--cuadrao-guest-book", "--cuadrao-guest-notices-seen", "--cuadrao-guest-reset",
                               "--age-confirmation-harness", "--age-legal-entry", "--age-reset"]
            + (testURLs ? [Self.legalTestURLs] : []) + arguments
        app.launch()
    }

    private func completeLegalAgeConfirmation() {
        let checkbox = app.descendants(matching: .any)["age.confirmation.checkbox"].firstMatch
        XCTAssertTrue(checkbox.waitForExistence(timeout: 8))
        let next = app.buttons["age.confirmation.continue"]
        XCTAssertFalse(next.isEnabled)
        checkbox.tap()
        next.tap()
        XCTAssertTrue(checkbox.waitForNonExistence(timeout: 8))
    }

    private func openGuestProfile() {
        let guest = app.buttons["cuadrao.welcome.guest"]
        XCTAssertTrue(guest.waitForExistence(timeout: 15))
        guest.tap()
        completeLegalAgeConfirmation()
        XCTAssertTrue(app.buttons["header.profile"].waitForExistence(timeout: 10))
        app.buttons["header.profile"].tap()
        XCTAssertTrue(app.descendants(matching: .any)["guest.profile"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.buttons["guest.profile.preferences"].waitForExistence(timeout: 5))
    }

    private func openSignUp() {
        let signUp = app.buttons["cuadrao.welcome.signup"]
        XCTAssertTrue(signUp.waitForExistence(timeout: 15))
        signUp.tap()
        completeLegalAgeConfirmation()
        XCTAssertTrue(app.buttons["cuadrao.signup.email"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.staticTexts["Crea tu cuenta."].exists || app.staticTexts["Create your account."].exists)
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
            XCTAssertFalse(app.staticTexts["cuadrao.signup.acceptance"].exists, "no acceptance sentence without both documents")
            capture("legal-registro-sin-enlaces-" + (dark ? "dark" : "light"))
        }
    }

    func testSignUpShowsTheLegalLinksFromTheOwner() throws {
        for spanish in [true, false] {
            launchLegal(testURLs: true, spanish: spanish)
            openSignUp()
            let acceptance = app.staticTexts["cuadrao.signup.acceptance"]
            XCTAssertTrue(acceptance.waitForExistence(timeout: 5))
            XCTAssertEqual(acceptance.label, spanish ? Self.acceptanceSentence
                : "By continuing, you agree to the Terms and Privacy Policy.")
            XCTAssertTrue(app.links[spanish ? "Términos" : "Terms"].exists)
            XCTAssertTrue(app.links[spanish ? "Política de privacidad" : "Privacy Policy"].exists)
            capture("legal-registro-con-enlaces-" + (spanish ? "es" : "en"))
        }
    }

    func testSignUpDocumentLinksOpenTheOwnerDestinations() throws {
        for document in ["Términos", "Política de privacidad"] {
            launchLegal(testURLs: true)
            openSignUp()
            let link = app.links[document]
            XCTAssertTrue(link.waitForExistence(timeout: 5))
            tapVisible(link)
            let safari = XCUIApplication(bundleIdentifier: "com.apple.mobilesafari")
            XCTAssertTrue(safari.wait(for: .runningForeground, timeout: 15))
            safari.terminate()
        }
    }

    func testSignUpHidesAcceptanceWhenOnlyOneDocumentExists() throws {
        for preview in [false, true] {
            for document in ["terms", "privacy"] {
                launchLegal(testURLs: false, arguments: ["--cuadrao-legal-test-\(document)-only"]
                    + (preview ? ["--cuadrao-design"] : []))
                if preview {
                    let signUp = app.buttons["Crear cuenta"]
                    XCTAssertTrue(signUp.waitForExistence(timeout: 15))
                    signUp.tap()
                    XCTAssertTrue(app.staticTexts["Crea tu cuenta."].waitForExistence(timeout: 10))
                } else {
                    openSignUp()
                }
                XCTAssertFalse(app.staticTexts["cuadrao.signup.acceptance"].exists)
                XCTAssertFalse(app.links["Términos"].exists)
                XCTAssertFalse(app.links["Política de privacidad"].exists)
            }
        }
    }

    func testSignUpRemainsReachableAtLargeTextSizes() throws {
        for size in ["UICTContentSizeCategoryL", "UICTContentSizeCategoryXXXL", "UICTContentSizeCategoryAccessibilityXXXL"] {
            launchLegal(testURLs: false, arguments: ["-UIPreferredContentSizeCategoryName", size])
            openSignUp()
            let title = app.staticTexts["Crea tu cuenta."]
            XCTAssertTrue(title.exists)
            capture("registro-texto-" + size)
            let email = app.buttons["cuadrao.signup.email"]
            tapVisible(email)
            XCTAssertTrue(app.textFields["auth.email"].waitForExistence(timeout: 5))
        }
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
