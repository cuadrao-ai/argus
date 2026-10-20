import XCTest

final class AgeConfirmationUITests: XCTestCase {
    override func setUp() { continueAfterFailure = false }

    private func assertSignupAvailable(_ response: String) {
        let app = XCUIApplication()
        app.launchArguments = ["--age-confirmation-harness", "--age-legal-entry", "--age-response=\(response)",
                               "--cuadrao-guest-reset", "-AppleLanguages", "(es-419)", "-AppleLocale", "es_DO"]
        app.launch()
        let signup = app.buttons["cuadrao.welcome.signup"]
        XCTAssertTrue(signup.waitForExistence(timeout: 8))
        signup.tap()
        let emailChoice = app.buttons["cuadrao.signup.email"]
        XCTAssertTrue(emailChoice.waitForExistence(timeout: 5))
        emailChoice.tap()
        let email = app.textFields["auth.email"]
        XCTAssertTrue(email.waitForExistence(timeout: 5))
        email.tap()
        email.typeText("synthetic@example.test")
        let password = app.secureTextFields["auth.password"]
        password.coordinate(withNormalizedOffset: CGVector(dx: 1, dy: 0.5)).withOffset(CGVector(dx: 22, dy: 0)).tap()
        let visiblePassword = app.textFields["auth.password"]
        visiblePassword.tap()
        visiblePassword.typeText("synthetic-password")
        XCTAssertEqual(email.value as? String, "synthetic@example.test")
        XCTAssertEqual(visiblePassword.value as? String, "synthetic-password")
        visiblePassword.coordinate(withNormalizedOffset: CGVector(dx: 1, dy: 0.5)).withOffset(CGVector(dx: 22, dy: 0)).tap()
        let submit = app.buttons["auth.submit"]
        XCTAssertTrue(submit.isEnabled)
        XCTAssertFalse(app.descendants(matching: .any)["age.confirmation.checkbox"].firstMatch.exists)
        XCTAssertFalse(app.staticTexts["age.confirmation.refused"].exists)
        submit.tap()
        XCTAssertTrue(app.staticTexts["No pudimos conectar."].waitForExistence(timeout: 5))
        let screenshot = XCTAttachment(screenshot: app.screenshot())
        screenshot.name = "Signup available with \(response) age signal"
        screenshot.lifetime = .keepAlways
        add(screenshot)
        app.terminate()
    }

    func testGuestUnder18EntryAndRelaunchDoNotNeedAnAttestation() {
        let app = XCUIApplication()
        app.launchArguments = ["--age-confirmation-harness", "--age-legal-entry", "--age-response=under18",
                               "--cuadrao-guest-book", "--cuadrao-guest-reset", "--cuadrao-guest-notices-seen"]
        app.launch()
        XCTAssertTrue(app.buttons["cuadrao.welcome.guest"].waitForExistence(timeout: 8))
        app.buttons["cuadrao.welcome.guest"].tap()
        XCTAssertTrue(app.descendants(matching: .any)["guest.home.empty"].firstMatch.waitForExistence(timeout: 8))
        app.terminate()
        app.launchArguments.removeAll { $0 == "--cuadrao-guest-reset" }
        app.launch()
        XCTAssertTrue(app.descendants(matching: .any)["guest.home.empty"].firstMatch.waitForExistence(timeout: 8))
        let screenshot = XCTAttachment(screenshot: app.screenshot())
        screenshot.name = "Guest entry after under18 signal and relaunch"
        screenshot.lifetime = .keepAlways
        add(screenshot)
        app.terminate()
    }

    func testAdultSignalAllowsSignup() { assertSignupAvailable("adult") }
    func testUnder18SignalAllowsSignup() { assertSignupAvailable("under18") }
    func testUnknownSignalAllowsSignup() { assertSignupAvailable("unknown") }
    func testDeclinedSharingAllowsSignup() { assertSignupAvailable("declined") }
    func testUnsupportedSystemAllowsSignup() { assertSignupAvailable("older") }
    func testRequiredSharingFailureAllowsSignup() { assertSignupAvailable("required-error") }
    func testOptionalSharingFailureAllowsSignup() { assertSignupAvailable("optional-error") }
    func testCancelledRequestAllowsSignup() { assertSignupAvailable("cancelled") }
    func testPendingRequestDoesNotHoldSignup() { assertSignupAvailable("pending") }
}
