import XCTest

/// Perfil names the app's language ("Español", "English"), never a raw code. The row is information, so it is not
/// a button: the app follows the iPhone's language and changing it happens in iOS Settings.
extension FinancialLoopUITests {
    private static let rawCodes: Set<String> = ["es", "en", "es-419", "es_419", "es-DO", "es_DO", "en-US", "en_US"]

    func testGuestPreferencesNameTheLanguageSpanish() throws { try checkGuestLanguageRow(language: "es-419", label: "Idioma", value: "Español") }

    func testGuestPreferencesNameTheLanguageEnglish() throws { try checkGuestLanguageRow(language: "en", label: "Language", value: "English") }

    func testReleasePreferencesNameTheLanguage() throws {
        try signIn()
        for (language, label, value) in [("es-419", "Idioma", "Español"), ("en", "Language", "English")] {
            app.terminate()
            let locale = language == "es-419" ? ["-AppleLocale", "es_DO"] : ["-AppleLocale", "en_US"]
            let look = ProcessInfo.processInfo.environment["ARGUS_TEST_APPEARANCE"] == "dark" ? "dark" : "light"
            app.launchArguments = ["-AppleLanguages", "(\(language))"] + locale + ["-appearancePreference", look, "--cuadrao-release-gates"]
            app.launch()
            continueAfterFailure = true
            app.openProfileSurface()
            XCTAssertTrue(app.buttons["cuadrao.profile.identity"].waitForExistence(timeout: 15))
            assertNoRawLanguageCode()
            tapVisible(app.buttons["cuadrao.profile.preferences"])
            XCTAssertTrue(app.buttons["cuadrao.appearance.light"].waitForExistence(timeout: 5))
            assertLanguageRow(id: "cuadrao.profile.language", label: label, value: value)
            assertNoRawLanguageCode()
            perfilIdiomaCapture("preferencias-idioma-\(language)-\(look)")
        }
    }

    private func checkGuestLanguageRow(language: String, label: String, value: String) throws {
        let look = ProcessInfo.processInfo.environment["ARGUS_TEST_APPEARANCE"] == "dark" ? "dark" : "light"
        launchSignedOut(arguments: ["--cuadrao-guest-book", "-appearancePreference", look], language: language)
        continueAfterFailure = true
        enterGuestBook()
        app.buttons["header.profile"].tap()
        XCTAssertTrue(app.buttons["guest.profile.preferences"].waitForExistence(timeout: 10))
        assertNoRawLanguageCode()
        app.buttons["guest.profile.preferences"].tap()
        XCTAssertTrue(app.buttons["guest.profile.currency"].waitForExistence(timeout: 5))
        assertLanguageRow(id: "guest.profile.language", label: label, value: value)
        assertNoRawLanguageCode()
        perfilIdiomaCapture("guest-preferencias-idioma-\(language)-\(look)")
    }

    private func assertLanguageRow(id: String, label: String, value: String, file: StaticString = #filePath, line: UInt = #line) {
        let row = app.descendants(matching: .any)[id]
        XCTAssertTrue(row.waitForExistence(timeout: 5), "the language row exists", file: file, line: line)
        XCTAssertTrue(row.label.contains(label), "label \(row.label)", file: file, line: line)
        XCTAssertTrue(row.label.contains(value) || (row.value as? String)?.contains(value) == true,
                      "value \(row.label) / \(String(describing: row.value))", file: file, line: line)
        XCTAssertNotEqual(row.elementType, .button, "the row is information, not a control", file: file, line: line)
        XCTAssertFalse(app.buttons[id].exists, "no button carries the row's identifier", file: file, line: line)
        XCTAssertFalse(app.buttons.matching(NSPredicate(format: "label CONTAINS %@", value)).firstMatch.exists,
                       "no button offers \(value)", file: file, line: line)
        XCTAssertFalse(app.pickers.firstMatch.exists, "no picker", file: file, line: line)
    }

    private func assertNoRawLanguageCode(file: StaticString = #filePath, line: UInt = #line) {
        let shown = app.staticTexts.allElementsBoundByIndex.map(\.label) + app.buttons.allElementsBoundByIndex.map(\.label)
            + app.staticTexts.allElementsBoundByIndex.compactMap { $0.value as? String }
        for text in shown { XCTAssertFalse(Self.rawCodes.contains(text), "raw language code on screen: \(text)", file: file, line: line) }
    }

    private func perfilIdiomaCapture(_ name: String) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }
}
