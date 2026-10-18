import XCTest

final class AgeConfirmationUITests: XCTestCase {
    private var app: XCUIApplication!
    private var suite: String!

    override func setUp() {
        continueAfterFailure = false
        app = XCUIApplication()
        suite = "local.cuadrao.age-ui.\(UUID().uuidString)"
    }

    private func launch(_ response: String, reset: Bool = true) {
        app.launchArguments = ["--age-confirmation-harness", "--age-response=\(response)",
                               "-ageHarnessSuite", suite, "-AppleLanguages", "(es-419)", "-AppleLocale", "es_DO"]
            + (reset ? ["--age-reset"] : [])
        app.launch()
    }

    private func confirm() {
        let checkbox = app.descendants(matching: .any)["age.confirmation.checkbox"].firstMatch
        XCTAssertTrue(checkbox.waitForExistence(timeout: 8))
        XCTAssertEqual(checkbox.label, "Confirmo que tengo 18 años o más.")
        XCTAssertFalse(app.buttons["age.confirmation.continue"].isEnabled)
        checkbox.tap()
        app.buttons["age.confirmation.continue"].tap()
    }

    private func snapshot(_ name: String) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }

    func testOlderSystemRequiresCheckboxAndRetainsTimestampThroughConversionAndRelaunch() {
        launch("older")
        confirm()
        XCTAssertTrue(app.staticTexts["age.harness.allowed"].waitForExistence(timeout: 5))
        let timestamp = app.staticTexts["age.harness.timestamp"].label
        XCTAssertNotEqual(timestamp, "missing")
        app.buttons["age.harness.conversion"].tap()
        XCTAssertTrue(app.staticTexts["age.harness.allowed"].waitForExistence(timeout: 5))
        XCTAssertFalse(app.descendants(matching: .any)["age.confirmation.checkbox"].firstMatch.exists)
        XCTAssertEqual(app.staticTexts["age.harness.timestamp"].label, timestamp)
        app.terminate()
        launch("older", reset: false)
        XCTAssertTrue(app.staticTexts["age.harness.allowed"].waitForExistence(timeout: 5))
        XCTAssertFalse(app.descendants(matching: .any)["age.confirmation.checkbox"].firstMatch.exists)
        XCTAssertEqual(app.staticTexts["age.harness.timestamp"].label, timestamp)
        snapshot("Retained confirmation after relaunch")
    }

    func testUnder18HasApprovedRefusalAndTermsWithoutRetry() {
        launch("under18")
        confirm()
        XCTAssertTrue(app.staticTexts["age.confirmation.refused"].waitForExistence(timeout: 5))
        XCTAssertEqual(app.staticTexts["age.confirmation.refused"].label,
            "Cuadrao es para personas de 18 años o más, así que por ahora no puedes usar la app.")
        XCTAssertFalse(app.buttons["age.confirmation.continue"].exists)
        XCTAssertFalse(app.staticTexts["age.harness.allowed"].exists)
        XCTAssertTrue(app.links["age.confirmation.terms"].exists || app.buttons["age.confirmation.terms"].exists)
        snapshot("Under 18 refusal")
    }

    func testRequiredSharingDeclineUsesApprovedRecovery() {
        launch("declined")
        confirm()
        XCTAssertTrue(app.staticTexts["age.confirmation.error"].waitForExistence(timeout: 5))
        XCTAssertEqual(app.staticTexts["age.confirmation.error"].label, "Para continuar, comparte tu rango de edad con Cuadrao.")
        XCTAssertEqual(app.buttons["age.confirmation.continue"].label, "Compartir rango de edad")
        XCTAssertFalse(app.descendants(matching: .any)["age.confirmation.checkbox"].firstMatch.exists)
        XCTAssertFalse(app.staticTexts["age.harness.allowed"].exists)
        snapshot("Required sharing declined")
    }

    func testRequiredSharingErrorUsesApprovedRetry() {
        launch("required-error")
        confirm()
        XCTAssertTrue(app.staticTexts["age.confirmation.error"].waitForExistence(timeout: 5))
        XCTAssertEqual(app.staticTexts["age.confirmation.error"].label, "No pudimos confirmar tu rango de edad. Inténtalo de nuevo.")
        XCTAssertEqual(app.buttons["age.confirmation.continue"].label, "Intentar de nuevo")
        XCTAssertFalse(app.descendants(matching: .any)["age.confirmation.checkbox"].firstMatch.exists)
        XCTAssertFalse(app.staticTexts["age.harness.allowed"].exists)
        snapshot("Required sharing failed")
    }

    func testOptionalSharingErrorAllowsExplicitAttestation() {
        launch("optional-error")
        confirm()
        XCTAssertTrue(app.staticTexts["age.harness.allowed"].waitForExistence(timeout: 5))
    }
}
