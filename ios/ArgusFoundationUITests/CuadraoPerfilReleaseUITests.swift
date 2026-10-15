import XCTest

/// Perfil as Release shows it (`--cuadrao-release-gates`): no development notes, example controls or avatar camera,
/// and "Eliminar cuenta" alone, last and red, still behind the typed confirmation.
extension FinancialLoopUITests {
    func testReleasePerfilShowsNoDevelopmentLeftovers() throws {
        try signIn()
        app.terminate()
        let dark = ProcessInfo.processInfo.environment["ARGUS_TEST_APPEARANCE"] == "dark"
        let look = dark ? "dark" : "light"
        app.launchArguments = ["-AppleLanguages", "(es-419)", "-AppleLocale", "es_DO",
                               "-appearancePreference", look, "--cuadrao-release-gates"]
        app.launch()
        continueAfterFailure = true
        app.openProfileSurface()
        let identity = app.buttons["cuadrao.profile.identity"]
        XCTAssertTrue(identity.waitForExistence(timeout: 15))
        capture("perfil-\(look)")
        XCTAssertFalse(app.buttons["cuadrao.profile.notifications"].exists, "Notificaciones only held example toggles")
        for route in ["preferences", "privacy", "help"] {
            XCTAssertTrue(app.buttons["cuadrao.profile." + route].exists, route)
        }
        if !dark {
            let avatar = CGRect(x: identity.frame.minX, y: identity.frame.midY - 38, width: 76, height: 76)
            XCTAssertEqual(app.colorCounts(in: avatar).green, 0, "the avatar is the Perfil icon, not the pine camera")
        }
        tapVisible(identity)
        XCTAssertTrue(app.buttons["cuadrao.profile.cancel"].waitForExistence(timeout: 5))
        capture("editar-perfil-\(look)")
        app.buttons["cuadrao.profile.cancel"].tap()

        tapVisible(app.buttons["cuadrao.profile.preferences"])
        XCTAssertTrue(app.buttons["cuadrao.appearance.light"].waitForExistence(timeout: 5))
        assertNoDevelopmentNote()
        XCTAssertTrue(app.descendants(matching: .any)["profile.primaryCurrency"].exists, "Moneda preferida stays")
        XCTAssertFalse(labelled("República Dominicana").exists, "República Dominicana")
        XCTAssertEqual(app.descendants(matching: .any)["cuadrao.profile.language"].label, "Idioma, Español", "Idioma is read-only information")
        capture("preferencias-\(look)")
        app.navigationBars.buttons.firstMatch.tap()

        tapVisible(app.buttons["cuadrao.profile.help"])
        XCTAssertTrue(app.descendants(matching: .any)["release.legal.terms"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.descendants(matching: .any)["release.legal.privacy"].exists)
        assertNoDevelopmentNote()
        XCTAssertFalse(app.buttons["Centro de ayuda"].exists, "a help center that only says it is not connected")
        XCTAssertFalse(app.buttons["Comentarios"].exists, "Comentarios only kept a draft on this iPhone")
        capture("ayuda-\(look)")
        app.navigationBars.buttons.firstMatch.tap()

        tapVisible(app.buttons["cuadrao.profile.privacy"])
        let delete = app.buttons["cuadrao.profile.deleteAccount"]
        XCTAssertTrue(delete.waitForExistence(timeout: 5))
        assertNoDevelopmentNote()
        for other in app.collectionViews.firstMatch.buttons.allElementsBoundByIndex where other.identifier != delete.identifier {
            XCTAssertLessThan(other.frame.maxY, delete.frame.minY, "Eliminar cuenta is the last group: " + other.label)
        }
        XCTAssertGreaterThan(app.colorCounts(in: delete.frame).red, 0, "Eliminar cuenta is system red")
        capture("datos-y-privacidad-\(look)")

        delete.tap()
        let next = app.buttons["identity.delete.continue"]
        XCTAssertTrue(next.waitForExistence(timeout: 10))
        reveal(next)
        XCTAssertGreaterThan(app.colorCounts(in: next.frame).red, 0, "Continuar is system red")
        capture("eliminar-cuenta-\(look)")
        next.tap()
        XCTAssertTrue(app.textFields["identity.delete.verification"].waitForExistence(timeout: 5))
        XCTAssertFalse(app.buttons["identity.delete.submit"].isEnabled, "deleting still waits for the typed confirmation")
        tapVisible(app.buttons["identity.delete.cancelVerification"])
        XCTAssertTrue(next.waitForExistence(timeout: 5))
    }

    func testGuestPerfilDeleteDataIsRed() throws {
        launchSignedOut(arguments: ["--cuadrao-guest-book"], language: "es-419")
        enterGuestBook()
        app.buttons["header.profile"].tap()
        app.buttons["guest.profile.privacy"].tap()
        let delete = app.buttons["guest.profile.delete"]
        XCTAssertTrue(delete.waitForExistence(timeout: 10))
        XCTAssertGreaterThan(app.colorCounts(in: delete.frame).red, 0, "Eliminar los datos de este iPhone is system red")
        capture("guest-datos-y-privacidad-light")
        delete.tap()
        XCTAssertTrue(app.alerts.firstMatch.staticTexts["¿Eliminar los datos de este iPhone?"].waitForExistence(timeout: 5))
        app.alerts.firstMatch.buttons["Cancelar"].tap()
        XCTAssertTrue(delete.waitForExistence(timeout: 5), "Cancelar keeps the book")
    }

    private func assertNoDevelopmentNote(file: StaticString = #filePath, line: UInt = #line) {
        XCTAssertFalse(labelled("Vista de desarrollo").exists, "no development note", file: file, line: line)
    }

    private func labelled(_ text: String) -> XCUIElement {
        app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS %@", text)).firstMatch
    }

    private func reveal(_ element: XCUIElement) {
        for _ in 0..<4 where !element.isHittable { app.swipeUp() }
    }
}
