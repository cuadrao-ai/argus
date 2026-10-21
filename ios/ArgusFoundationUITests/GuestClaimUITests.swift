import XCTest

/// "Pasar tus datos a tu cuenta", driven against the claim harness: a stand-in server and a book in a temporary folder.
/// No account and no network are needed.
final class GuestClaimUITests: XCTestCase {
    let app = XCUIApplication()

    private func launch(_ extra: [String] = [], spanish: Bool = true) {
        continueAfterFailure = false
        app.terminate()
        let locale = spanish ? ["-AppleLanguages", "(es-419)", "-AppleLocale", "es_DO"] : ["-AppleLanguages", "(en)", "-AppleLocale", "en_US"]
        app.launchArguments = ["--guest-claim-harness", "-appearancePreference", "light"] + locale + extra
        app.launch()
        XCTAssertTrue(element("guest.claim.start").waitForExistence(timeout: 20), "the preview opens")
    }

    private func element(_ id: String) -> XCUIElement { app.descendants(matching: .any).matching(identifier: id).firstMatch }

    private func capture(_ name: String) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }

    func testThePreviewSaysWhatWillMoveBeforeAnythingMoves() throws {
        launch()
        XCTAssertEqual(element("guest.claim.accounts").label, "3 cuentas")
        XCTAssertEqual(element("guest.claim.movements").label, "3 movimientos")
        XCTAssertTrue(element("guest.claim.renamed").label.contains("2 cuentas ya tienen ese nombre"), element("guest.claim.renamed").label)
        XCTAssertTrue(element("guest.claim.renamed").label.contains("(invitado)"))
        XCTAssertTrue(element("guest.claim.staying").label.contains("1 meta o presupuesto"), element("guest.claim.staying").label)
        XCTAssertFalse(element("guest.claim.progress").exists, "nothing moves before the person taps")
        XCTAssertFalse(element("guest.claim.finished").exists)
        capture("claim-preview-es")
    }

    func testMovingShowsProgressThenWhatMovedAndKeepsTheCopy() throws {
        launch()
        element("guest.claim.start").tap()
        XCTAssertTrue(element("guest.claim.progress").waitForExistence(timeout: 10), "progress while it moves")
        capture("claim-progress-es")
        XCTAssertTrue(element("guest.claim.finished").waitForExistence(timeout: 30))
        XCTAssertEqual(element("guest.claim.finished").label.contains("3 cuentas y 3 movimientos"), true, element("guest.claim.finished").label)
        XCTAssertTrue(element("guest.claim.discard").exists, "the copy is still on the iPhone until the person discards it")
        XCTAssertFalse(element("guest.claim.start").exists, "nothing is left to move")
        capture("claim-finished-es")
    }

    func testAStoppedClaimSaysSoAndRetryContinuesFromWhereItStopped() throws {
        launch(["--guest-claim-fail-after", "1"])
        element("guest.claim.start").tap()
        XCTAssertTrue(element("guest.claim.stopped").waitForExistence(timeout: 30))
        XCTAssertTrue(element("guest.claim.stopped").label.contains("Lo que ya pasó no se repite"), element("guest.claim.stopped").label)
        XCTAssertTrue(element("guest.claim.retry").exists)
        capture("claim-stopped-es")
    }

    func testAMovementTheServerRefusesStaysAndIsCounted() throws {
        launch(["--guest-claim-refuse-note", "Pay"])
        element("guest.claim.start").tap()
        XCTAssertTrue(element("guest.claim.finished").waitForExistence(timeout: 30))
        XCTAssertTrue(element("guest.claim.finished").label.contains("2 movimientos"), element("guest.claim.finished").label)
        XCTAssertTrue(element("guest.claim.refused").label.contains("1 movimiento no se pudo pasar"), element("guest.claim.refused").label)
    }

    func testDiscardAsksOnceAndCancelKeepsEverything() throws {
        launch()
        element("guest.claim.discard").tap()
        let alert = app.alerts.firstMatch
        XCTAssertTrue(alert.waitForExistence(timeout: 5), "one question before anything is deleted")
        XCTAssertTrue(alert.staticTexts["¿Descartar los datos de invitado?"].exists)
        capture("claim-discard-ask-es")
        alert.buttons["Cancelar"].tap()
        XCTAssertTrue(alert.waitForNonExistence(timeout: 5))
        XCTAssertTrue(element("guest.claim.start").exists, "cancel changed nothing")
        XCTAssertFalse(element("guest.claim.discarded").exists)

        element("guest.claim.discard").tap()
        XCTAssertTrue(app.alerts.buttons.matching(identifier: "guest.claim.discard.confirm").firstMatch.waitForExistence(timeout: 5))
        app.alerts.buttons.matching(identifier: "guest.claim.discard.confirm").firstMatch.tap()
        XCTAssertTrue(element("guest.claim.discarded").waitForExistence(timeout: 10))
        XCTAssertFalse(element("guest.claim.start").exists)
        capture("claim-discarded-es")
    }

    func testTheEnglishCopyFollowsTheSpanish() throws {
        launch(spanish: false)
        XCTAssertEqual(element("guest.claim.accounts").label, "3 accounts")
        XCTAssertTrue(element("guest.claim.renamed").label.contains("Name (guest)"), element("guest.claim.renamed").label)
        XCTAssertEqual(app.buttons["guest.claim.start"].label, "Move to my account")
        XCTAssertEqual(app.buttons["guest.claim.discard"].label, "Discard")
        capture("claim-preview-en")
    }
}
