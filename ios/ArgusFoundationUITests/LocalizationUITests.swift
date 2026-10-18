import XCTest

final class LocalizationUITests: XCTestCase {
    func testUnknownDeviceLanguageUsesSpanishNativeCatalog() {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["--age-confirmation-harness", "--age-reset", "-AppleLanguages", "(fr)", "-AppleLocale", "fr_FR"]
        app.launch()
        let checkbox = app.descendants(matching: .any)["age.confirmation.checkbox"].firstMatch
        XCTAssertTrue(checkbox.waitForExistence(timeout: 15), "Offline age gate opened; this test must not skip")
        XCTAssertTrue(checkbox.label.contains("Confirmo que tengo 18 años o más."), checkbox.label)
        capture(app, name: "unknown-fr-native-spanish")
    }

    func testLaterSupportedDeviceLanguageUsesEnglishNativeCatalog() {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["--age-confirmation-harness", "--age-reset", "-AppleLanguages", "(fr,en)", "-AppleLocale", "fr_FR"]
        app.launch()
        let checkbox = app.descendants(matching: .any)["age.confirmation.checkbox"].firstMatch
        XCTAssertTrue(checkbox.waitForExistence(timeout: 15), "Offline age gate opened")
        XCTAssertTrue(checkbox.label.contains("I confirm that I am 18 or older."), checkbox.label)
        capture(app, name: "ordered-fr-en-native-english")
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
