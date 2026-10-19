import XCTest

final class AgeConfirmationUITests: XCTestCase {
    override func setUp() { continueAfterFailure = false }

    private func assertSignupAvailable(_ response: String) {
        let app = XCUIApplication()
        app.launchArguments = ["--age-confirmation-harness", "--age-response=\(response)",
                               "-AppleLanguages", "(es-419)", "-AppleLocale", "es_DO"]
        app.launch()
        XCTAssertTrue(app.staticTexts["age.harness.allowed"].waitForExistence(timeout: 5))
        XCTAssertFalse(app.descendants(matching: .any)["age.confirmation.checkbox"].firstMatch.exists)
        XCTAssertFalse(app.staticTexts["age.confirmation.refused"].exists)
        XCTAssertFalse(app.staticTexts["age.confirmation.error"].exists)
        let signup = app.buttons["age.harness.signup"]
        XCTAssertTrue(signup.isEnabled)
        signup.tap()
        XCTAssertTrue(app.staticTexts["age.harness.submitted"].waitForExistence(timeout: 3))
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
