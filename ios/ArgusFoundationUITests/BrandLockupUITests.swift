import XCTest

/// The invitation card and the chat empty state draw the same shared lockup as the welcome screen.
final class BrandLockupUITests: XCTestCase {
    func testInvitationPageOpensAndCapturesLockupEvidenceInLightAndDark() throws {
        continueAfterFailure = false
        for dark in [false, true] {
            let app = XCUIApplication()
            app.launchArguments = ["--cuadrao-release-ui", "-AppleLanguages", "(en)", "-AppleLocale", "en_US"] + (dark ? ["--release-dark"] : [])
            app.launch()
            XCTAssertTrue(app.buttons["release.review.invites"].waitForExistence(timeout: 10))
            app.buttons["release.review.invites"].tap()
            // The lockup is decorative on the invitation page (hidden from VoiceOver), so XCUI cannot see it: this test only opens
            // the page and keeps the screenshot as the evidence. It does not assert the lockup.
            XCTAssertTrue(app.buttons["Enter code"].waitForExistence(timeout: 10))
            app.buttons["Enter code"].tap()
            XCTAssertTrue(app.textFields.firstMatch.waitForExistence(timeout: 10), "the invitation entry page opened")
            capture(app, "brand-invitation-\(dark ? "dark" : "light")")
            app.terminate()
        }
    }

    func testChatEmptyStateShowsTheSharedLockupInLightAndDark() throws {
        continueAfterFailure = false
        for dark in [false, true] {
            let app = XCUIApplication()
            app.launchArguments = CuadraoPreviewLaunch.arguments + ["--design-english", "-cuadrao.design.appearance", dark ? "dark" : "light"]
            app.launch()
            XCTAssertTrue(app.buttons["tab.argus"].waitForExistence(timeout: 15))
            app.buttons["tab.argus"].tap()
            XCTAssertTrue(app.images["cuadrao.brand"].firstMatch.waitForExistence(timeout: 10), "the chat empty state shows the lockup")
            XCTAssertFalse(app.staticTexts["CUADRAO"].exists, "no old uppercase text lockup")
            capture(app, "brand-chat-empty-\(dark ? "dark" : "light")")
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
