import XCTest

/// Opt-in presentation acceptance for the configured local auth app. These
/// checks never submit credentials, request CAPTCHA, or open a recovery URL.
final class AuthUITests: XCTestCase {
    private let app = XCUIApplication()

    private struct LanguageCase {
        let code: String
        let locale: String
        let email: String
        let password: String
        let name: String
        let signIn: String
        let createAccount: String
        let forgot: String
        let minimumPassword: String
    }

    private let languages: [LanguageCase] = [
        .init(code: "en", locale: "en_US", email: "Email address", password: "Password",
              name: "Name (optional)", signIn: "Sign in", createAccount: "Create account",
              forgot: "Forgot password?", minimumPassword: "At least 8 characters."),
        .init(code: "es-419", locale: "es_419", email: "Correo electrónico", password: "Contraseña",
              name: "Nombre (opcional)", signIn: "Iniciar sesión", createAccount: "Crear cuenta",
              forgot: "¿Olvidaste tu contraseña?", minimumPassword: "Al menos 8 caracteres.")
    ]

    override func tearDown() {
        app.terminate()
        super.tearDown()
    }

    func testBilingualAuthLayoutKeyboardAndAppearance() throws {
        guard ProcessInfo.processInfo.environment["ARGUS_TEST_AUTH_UI_ENABLED"] == "true" else {
            throw XCTSkip("Requires the explicitly configured local auth build.")
        }
        continueAfterFailure = false
        XCUIDevice.shared.orientation = .portrait
        for language in languages {
            for largeText in [false, true] {
                let appearance = largeText ? "dark" : "light"
                let scenario = "\(language.code)-\(appearance)-\(largeText ? "accessibilityXXXL" : "standard")"
                app.launchArguments = [
                    "-AppleLanguages", "(\(language.code))", "-AppleLocale", language.locale,
                    "-appearancePreference", appearance,
                    "-UIPreferredContentSizeCategoryName",
                    largeText ? "UICTContentSizeCategoryAccessibilityXXXL" : "UICTContentSizeCategoryL"
                ]
                app.launch()
                openProfile()
                if !app.textFields["auth.email"].waitForExistence(timeout: 10), app.buttons["auth.signOut"].exists {
                    throw XCTSkip("A signed-out local state is required; this test will not revoke an existing session.")
                }
                XCTAssertTrue(app.textFields["auth.email"].exists, "The opt-in auth build must expose a working signed-out form")
                try verifyEntry(language, scenario: scenario)
                verifySignupAndKeyboard(language, scenario: scenario)
                verifyAppearance(appearance, scenario: scenario)
                app.terminate()
            }
        }
    }

    /// The welcome screen is one brand composition and the two native actions: no repeated header, no tagline.
    func testWelcomeIsOneLockupAndTwoActions() throws {
        guard ProcessInfo.processInfo.environment["ARGUS_TEST_AUTH_UI_ENABLED"] == "true" else {
            throw XCTSkip("Requires the configured local auth build.")
        }
        for appearance in ["light", "dark"] {
            app.launchArguments = ["-AppleLanguages", "(en)", "-AppleLocale", "en_US", "-appearancePreference", appearance]
            app.launch()
            XCTAssertTrue(app.images["cuadrao.welcome.lockup"].waitForExistence(timeout: 15), "\(appearance): the lockup is shown")
            XCTAssertEqual(app.images.matching(identifier: "cuadrao.welcome.lockup").count, 1, "\(appearance): once")
            XCTAssertTrue(app.buttons["cuadrao.welcome.signup"].exists)
            XCTAssertTrue(app.buttons["cuadrao.welcome.signin"].exists)
            XCTAssertFalse(app.staticTexts["CUADRAO"].exists, "\(appearance): no repeated header lockup")
            XCTAssertFalse(app.staticTexts.containing(NSPredicate(format: "label CONTAINS[c] 'finances'")).firstMatch.exists, "\(appearance): no tagline")
            app.terminate()
        }
    }

    func testConnectedSignInFilledFieldsInBothAppearances() throws {
        guard ProcessInfo.processInfo.environment["ARGUS_TEST_AUTH_UI_ENABLED"] == "true" else {
            throw XCTSkip("Requires the configured local auth build.")
        }
        continueAfterFailure = false
        for appearance in ["light", "dark"] {
            app.launchArguments = ["-AppleLanguages", "(en)", "-AppleLocale", "en_US",
                                   "-appearancePreference", appearance]
            app.launch()
            openProfile()
            let email = app.textFields["auth.email"]
            let password = app.secureTextFields["auth.password"]
            XCTAssertTrue(email.waitForExistence(timeout: 10))
            email.tap(); email.typeText("contrast@example.test")
            password.tap(); password.typeText("Local-contrast-check")
            XCTAssertEqual(email.value as? String, "contrast@example.test")
            XCTAssertTrue(app.buttons["auth.submit"].isEnabled)
            capture("connected-\(appearance)-filled-fields")
            app.dismissKeyboard()
            try app.performAccessibilityAudit(for: [.contrast])
            capture("connected-\(appearance)-contrast")
            app.terminate()
        }
    }

    private func verifyEntry(_ language: LanguageCase, scenario: String) throws {
        XCTAssertEqual(app.textFields["auth.email"].label, language.email)
        XCTAssertEqual(app.secureTextFields["auth.password"].label, language.password)
        XCTAssertEqual(app.buttons["auth.submit"].label, language.signIn)
        XCTAssertEqual(app.buttons["auth.forgotPassword"].label, language.forgot)
        XCTAssertFalse(app.buttons["auth.submit"].isEnabled)
        XCTAssertFalse(app.staticTexts["auth.confirmation"].exists)
        capture("\(scenario)-sign-in")
        if app.buttons["auth.createAccount"].exists {
            try app.performAccessibilityAudit(for: [.hitRegion, .sufficientElementDescription, .trait, .contrast]) { issue in
                issue.auditType == .contrast && issue.element?.identifier == "sheet.close"
            }
            for control in [app.textFields["auth.email"], app.secureTextFields["auth.password"],
                            app.buttons["auth.submit"], app.buttons["auth.createAccount"],
                            app.buttons["auth.forgotPassword"]] {
                assertReachableControl(control)
            }
        } else {
            // Connected Cuadrao email form: tip create-account control lives on the prior chooser.
            for control in [app.textFields["auth.email"], app.secureTextFields["auth.password"],
                            app.buttons["auth.submit"], app.buttons["auth.forgotPassword"]] {
                assertReachableControl(control)
            }
        }
        capture("\(scenario)-sign-in-actions")
    }

    private func verifySignupAndKeyboard(_ language: LanguageCase, scenario: String) {
        if !app.buttons["auth.createAccount"].exists {
            // Connected signup uses a separate registration screen without tip auth.name.
            capture("\(scenario)-signup-connected-skipped-tip-form")
            return
        }
        let modeSwitch = app.buttons["auth.createAccount"]
        reveal(modeSwitch)
        modeSwitch.tap()
        let name = app.textFields["auth.name"]
        XCTAssertTrue(name.waitForExistence(timeout: 5))
        XCTAssertEqual(name.label, language.name)
        assertReachableControl(name)
        capture("\(scenario)-signup")
        XCTAssertEqual(app.buttons["auth.submit"].label, language.createAccount)
        XCTAssertFalse(app.buttons["auth.submit"].isEnabled)
        let requirement = app.staticTexts[language.minimumPassword]
        reveal(requirement)
        XCTAssertTrue(requirement.isHittable)
        XCTAssertFalse(app.staticTexts["auth.confirmation"].exists)
        capture("\(scenario)-signup-requirements")

        let email = app.textFields["auth.email"]
        reveal(email)
        email.tap()
        email.typeText("layout")
        XCTAssertTrue(app.keyboards.firstMatch.waitForExistence(timeout: 5))
        XCTAssertEqual(email.value as? String, "layout")
        XCTAssertTrue(email.isHittable)
        XCTAssertLessThanOrEqual(email.frame.maxY, app.keyboards.firstMatch.frame.minY + 1)
        XCTAssertFalse(app.buttons["auth.submit"].isEnabled)
        capture("\(scenario)-signup-keyboard")
        XCTAssertTrue(app.buttons["sheet.close"].isHittable)
        app.buttons["sheet.close"].tap()
        openProfile()
        XCTAssertTrue(app.textFields["auth.email"].waitForExistence(timeout: 5))
        XCTAssertFalse(app.textFields["auth.name"].exists)
        XCTAssertFalse(app.buttons["auth.submit"].isEnabled)
    }

    private func verifyAppearance(_ appearance: String, scenario: String) {
        let preferences = app.buttons["profile.preferences"]
        if !preferences.waitForExistence(timeout: 3) {
            // Connected signed-out email form has no profile preferences sheet.
            capture("\(scenario)-preferences-connected-signed-out")
            return
        }
        reveal(preferences)
        preferences.tap()
        let choice = app.buttons["appearance.\(appearance)"]
        XCTAssertTrue(choice.waitForExistence(timeout: 5))
        XCTAssertTrue(choice.isSelected)
        let resolved = app.staticTexts["appearance.resolved"]
        reveal(resolved)
        XCTAssertEqual(resolved.value as? String, appearance)
        capture("\(scenario)-preferences")
        if app.buttons["sheet.close"].exists {
            app.buttons["sheet.close"].tap()
            XCTAssertTrue(app.buttons["tab.home"].isSelected)
        }
    }

    private func openProfile() {
        app.openProfileSurface()
    }

    private func assertReachableControl(_ element: XCUIElement, scroll: Bool = true) {
        if scroll { reveal(element) }
        XCTAssertTrue(element.exists)
        XCTAssertFalse(element.label.isEmpty)
        XCTAssertGreaterThanOrEqual(element.frame.width + 0.000_001, 44)
        XCTAssertGreaterThanOrEqual(element.frame.height + 0.000_001, 44)
        XCTAssertTrue(element.isHittable)
        XCTAssertGreaterThanOrEqual(element.frame.minX, app.frame.minX - 1)
        XCTAssertLessThanOrEqual(element.frame.maxX, app.frame.maxX + 1)
    }

    private func reveal(_ element: XCUIElement) {
        // The sheet's scroll view is the one containing this destination's
        // control, excluding the mounted but inactive shell tab scroll views.
        let reference = element.identifier.isEmpty ? element.label : element.identifier
        let scrollView = app.scrollViews.containing(element.elementType, identifier: reference).firstMatch
        for _ in 0..<10 {
            if element.isHittable { return }
            guard scrollView.exists else { break }
            if element.frame.maxY < scrollView.frame.minY + 1 {
                scrollView.swipeDown()
            } else {
                scrollView.swipeUp()
            }
        }
        XCTAssertTrue(element.isHittable, "Expected the control to be reachable by scrolling")
    }

    private func capture(_ name: String) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = "auth-layout-\(name)"
        attachment.lifetime = .keepAlways
        add(attachment)
    }
}
