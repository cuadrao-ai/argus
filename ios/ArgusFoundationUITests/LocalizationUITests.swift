import XCTest

final class LocalizationUITests: XCTestCase {
    func testUnknownDeviceLanguageUsesSpanishNativeCatalog() {
        checkSignInSubmit(languages: "fr", region: "fr_FR", label: "Iniciar sesión", name: "unknown-fr-native-spanish")
    }

    func testLaterSupportedDeviceLanguageUsesEnglishNativeCatalog() {
        checkSignInSubmit(languages: "fr,en", region: "fr_FR", label: "Sign in", name: "ordered-fr-en-native-english")
    }

    func testEnglishDeviceLanguageUsesEnglishHelperCatalog() {
        checkHome(language: "en", region: "en_GB", home: "Home", plan: "Plan")
    }

    func testSpanishDeviceLanguageUsesSpanishHelperCatalog() {
        checkHome(language: "es", region: "es_ES", home: "Inicio", plan: "Plan")
    }

    func testUnknownDeviceLanguageUsesSpanishHelperCatalog() {
        checkHome(language: "fr", region: "fr_FR", home: "Inicio", plan: "Plan")
    }

    func testLaterSupportedDeviceLanguageUsesEnglishHelperCatalog() {
        checkHome(language: "fr,en", region: "fr_FR", home: "Home", plan: "Plan")
    }

    func testManualPreviewLanguageSelectionOverridesDeviceLanguage() {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["--cuadrao-design", "--design-gallery", "-AppleLanguages", "(en)", "-AppleLocale", "en_GB"]
        app.launch()
        let picker = app.segmentedControls["gallery-language"]
        XCTAssertTrue(picker.waitForExistence(timeout: 15), "Offline reference gallery opened")
        XCTAssertEqual(app.switches["gallery-dark"].label, "Oscuro")
        picker.buttons.element(boundBy: 1).tap()
        XCTAssertEqual(app.switches["gallery-dark"].label, "Dark")
        picker.buttons.element(boundBy: 0).tap()
        XCTAssertEqual(app.switches["gallery-dark"].label, "Oscuro")
        capture(app, name: "manual-preview-language")
    }

    /// The sign-in button's accessibility label is `Text("auth.signIn")`, read by SwiftUI from the catalog with the
    /// system's language fallback, so it proves the native lookup rather than `CuadraoCopy`.
    private func checkSignInSubmit(languages: String, region: String, label: String, name: String) {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["--age-confirmation-harness", "--age-legal-entry", "--cuadrao-guest-reset",
                               "-AppleLanguages", "(\(languages))", "-AppleLocale", region]
        app.launch()
        let signIn = app.buttons["cuadrao.welcome.signin"]
        XCTAssertTrue(signIn.waitForExistence(timeout: 15), "Offline welcome opened; this test must not skip")
        signIn.tap()
        let emailChoice = app.buttons["cuadrao.signin.emailChoice"]
        XCTAssertTrue(emailChoice.waitForExistence(timeout: 10))
        emailChoice.tap()
        let submit = app.buttons["auth.submit"]
        XCTAssertTrue(submit.waitForExistence(timeout: 10))
        XCTAssertEqual(submit.label, label)
        capture(app, name: name)
    }

    private func checkHome(language: String, region: String, home: String, plan: String) {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["--cuadrao-release-ui"] + ["-AppleLanguages", "(\(language))", "-AppleLocale", region]
        app.launch()
        XCTAssertTrue(app.buttons["tab.home"].waitForExistence(timeout: 15), "Offline design Home opened; this test must not skip")
        XCTAssertEqual(app.buttons["tab.home"].label, home)
        XCTAssertEqual(app.buttons["tab.plan"].label, plan)
        capture(app, name: "home-\(language)-\(region)")
    }

    private func capture(_ app: XCUIApplication, name: String) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }
}
