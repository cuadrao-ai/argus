import XCTest

extension FinancialLoopUITests {
    func testConnectedProfileUsesRealIdentityAndApprovedDestinations() throws {
        try signIn()
        app.terminate()
        app.launchArguments = ["-AppleLanguages", "(en)", "-AppleLocale", "en_US"]
        app.launch()
        XCTAssertTrue(app.buttons["header.profile"].waitForExistence(timeout: 15))
        app.openProfileSurface()
        let email = try XCTUnwrap(ProcessInfo.processInfo.environment["ARGUS_TEST_EMAIL"])
        let identity = app.buttons["cuadrao.profile.identity"]
        XCTAssertTrue(identity.waitForExistence(timeout: 5))
        XCTAssertTrue(identity.label.contains(email))
        XCTAssertFalse(identity.label.contains("alex@example.com"))
        for route in ["preferences", "personalization", "notifications", "security", "privacy", "usage", "help"] {
            XCTAssertTrue(app.buttons["cuadrao.profile." + route].exists, route)
        }
        capture("connected-profile-full-groups")

        tapVisible(identity)
        XCTAssertTrue(app.buttons["cuadrao.profile.photo.choose"].waitForExistence(timeout: 5))
        let name = app.textFields["cuadrao.profile.name"]
        XCTAssertTrue(name.isEnabled)
        let preferred = app.textFields["cuadrao.profile.preferred"]
        let chosen = "Synthetic " + String(UUID().uuidString.prefix(4))
        name.tap(); name.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: 80) + "Synthetic Person")
        preferred.tap(); preferred.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: 60) + chosen)
        tapVisible(app.buttons["cuadrao.profile.avatar.moon"])
        app.buttons["cuadrao.profile.save"].tap()
        XCTAssertTrue(identity.waitForExistence(timeout: 15))
        XCTAssertTrue(identity.label.contains(email))
        XCTAssertTrue(identity.label.contains("Synthetic Person"))
        app.terminate(); app.launch()
        XCTAssertTrue(app.staticTexts["home-greeting"].waitForExistence(timeout: 15))
        XCTAssertEqual(app.staticTexts["home-greeting"].label, "Hello, " + chosen)
        app.openProfileSurface()
        XCTAssertTrue(identity.waitForExistence(timeout: 10))
        XCTAssertTrue(identity.label.contains("Synthetic Person"))

        tapVisible(app.buttons["cuadrao.profile.preferences"])
        XCTAssertTrue(app.navigationBars["Preferences"].waitForExistence(timeout: 5))
        XCTAssertFalse(app.buttons["tab.home"].exists)
        for appearance in ["light", "dark", "system"] {
            let choice = app.buttons["cuadrao.appearance." + appearance]
            tapVisible(choice)
            XCTAssertTrue(choice.isSelected)
        }
        app.navigationBars.buttons.firstMatch.tap()
        XCTAssertTrue(app.buttons["tab.home"].waitForExistence(timeout: 5))

        tapVisible(app.buttons["cuadrao.profile.privacy"])
        tapVisible(app.buttons["Files"])
        XCTAssertTrue(app.navigationBars["Files"].waitForExistence(timeout: 5))
        XCTAssertFalse(app.buttons["tab.home"].exists)
        app.navigationBars.buttons.firstMatch.tap()
        XCTAssertTrue(app.navigationBars["Data and privacy"].waitForExistence(timeout: 5))
        app.navigationBars.buttons.firstMatch.tap()
        XCTAssertTrue(app.buttons["tab.home"].waitForExistence(timeout: 5))

        tapVisible(app.buttons["cuadrao.profile.help"])
        XCTAssertFalse(app.descendants(matching: .any)["release.legal.terms"].exists, "legal links wait for the published pages")
        XCTAssertFalse(app.descendants(matching: .any)["release.legal.privacy"].exists)
        tapVisible(app.buttons["Feedback"])
        XCTAssertTrue(app.navigationBars["Feedback"].waitForExistence(timeout: 5))
        XCTAssertFalse(app.buttons["tab.home"].exists)
        app.navigationBars.buttons.firstMatch.tap()
        app.navigationBars.buttons.firstMatch.tap()
        tapVisible(app.buttons["auth.signOut"])
        app.alerts.firstMatch.buttons["Cancel"].tap()
        XCTAssertTrue(app.buttons["auth.signOut"].waitForExistence(timeout: 5))
        tapVisible(app.buttons["auth.signOut"])
        app.confirmSignOutIfAsked()
        XCTAssertTrue(app.buttons["cuadrao.welcome.signin"].waitForExistence(timeout: 20))
    }

    func testConnectedProfileReleaseGatesKeepSupportedSettings() throws {
        try signIn()
        app.terminate()
        app.launchArguments.append("--cuadrao-release-gates")
        app.launch()
        app.openProfileSurface()
        let identity = app.buttons["cuadrao.profile.identity"]
        XCTAssertTrue(identity.waitForExistence(timeout: 10))
        tapVisible(identity)
        XCTAssertTrue(app.textFields["cuadrao.profile.name"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.textFields["cuadrao.profile.name"].isEnabled)
        XCTAssertTrue(app.textFields["cuadrao.profile.preferred"].isEnabled)
        XCTAssertFalse(app.buttons["cuadrao.profile.photo.choose"].exists, "Avatar editing stays out of release")
        app.buttons["cuadrao.profile.cancel"].tap()
        for route in ["personalization", "notifications", "security", "usage"] {
            XCTAssertFalse(app.buttons["cuadrao.profile." + route].exists, route)
        }
        for route in ["preferences", "privacy", "help"] {
            XCTAssertTrue(app.buttons["cuadrao.profile." + route].exists, route)
        }
        tapVisible(app.buttons["cuadrao.profile.privacy"])
        for title in ["Memory", "Shared conversations", "Removed activity"] {
            XCTAssertFalse(app.buttons[title].exists, title)
        }
        XCTAssertFalse(app.buttons["Files"].exists, "no stored files in the free tier yet")
        XCTAssertFalse(app.buttons["Conversations"].exists, "no AI chats in the free tier")
        XCTAssertFalse(app.staticTexts["Your data"].exists, "and no empty Your data header is left behind")
        app.navigationBars.buttons.firstMatch.tap()
        tapVisible(app.buttons["cuadrao.profile.preferences"])
        XCTAssertFalse(app.buttons["More options"].exists)
        XCTAssertTrue(app.buttons["cuadrao.appearance.light"].exists)
        capture("connected-profile-release-gates")
    }
}
