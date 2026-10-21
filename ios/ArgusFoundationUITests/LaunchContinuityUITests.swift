import XCTest

/// The launch frame, the held launch screen and the welcome screen draw one logo in one place, so nothing jumps
/// between them. Needs no account: a signed-out cold start with the session check held for a few seconds.
final class LaunchContinuityUITests: XCTestCase {
    private let holdMs = 6000

    func testHeldLaunchLogoSitsWhereTheWelcomeLogoDrawsInLightAndDark() throws {
        continueAfterFailure = false
        for dark in [false, true] {
            let app = XCUIApplication()
            app.launchArguments = ["-AppleLanguages", "(es)", "-AppleLocale", "es_419",
                                   "-cuadraoRestoreDelayMs", "\(holdMs)",
                                   "-appearancePreference", dark ? "dark" : "light"]
            app.launch()
            let any = app.descendants(matching: .any)
            let hold = any["app.launching.lockup"]
            XCTAssertTrue(hold.waitForExistence(timeout: 5), "the launch screen holds (dark: \(dark))")
            let held = hold.frame
            capture(app, "launch-hold-\(dark ? "dark" : "light")")
            XCTAssertFalse(app.buttons["cuadrao.welcome.signin"].exists, "sign-in never draws while the launch screen holds")
            XCTAssertFalse(app.buttons["cuadrao.welcome.signup"].exists)

            let welcome = any["cuadrao.welcome.lockup"]
            XCTAssertTrue(welcome.waitForExistence(timeout: 30), "the welcome screen opens (dark: \(dark))")
            XCTAssertTrue(app.buttons["cuadrao.welcome.signin"].waitForExistence(timeout: 10))
            XCTAssertFalse(hold.exists, "the launch screen is gone once the welcome screen draws")
            capture(app, "launch-welcome-\(dark ? "dark" : "light")")

            let drawn = welcome.frame
            // The held image is the lockup on a taller transparent canvas with the lockup at its top edge.
            XCTAssertEqual(held.minY, drawn.minY, accuracy: 1, "the logo keeps its vertical position (dark: \(dark))")
            XCTAssertEqual(held.midX, drawn.midX, accuracy: 1, "the logo keeps its horizontal position (dark: \(dark))")
            XCTAssertEqual(held.width, drawn.width, accuracy: 1, "the logo keeps its size (dark: \(dark))")
            app.terminate()
        }
    }

    private func capture(_ app: XCUIApplication, _ name: String) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }
}
