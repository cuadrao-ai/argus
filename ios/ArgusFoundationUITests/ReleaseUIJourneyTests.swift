import XCTest

final class ReleaseUIJourneyTests: XCTestCase {
    func testAvatarSaveCancelAndDefaultIcon() {
        let app = launch(spanish: true)
        capture(app, "profile-empty-circle-es")
        app.buttons["release.profile.avatar"].tap()
        XCTAssertTrue(app.buttons["release.avatar.sun"].waitForExistence(timeout: 4))
        app.buttons["release.avatar.sun"].tap()
        app.buttons["release.avatar.cancel"].tap()
        app.buttons["release.profile.avatar"].tap()
        XCTAssertTrue(app.buttons["release.avatar.none"].isSelected)
        app.buttons["release.avatar.moon"].tap()
        app.buttons["release.avatar.save"].tap()
        capture(app, "theme-tab-unframed-es")
        app.buttons["release.profile.avatar"].tap()
        XCTAssertTrue(app.buttons["release.avatar.moon"].isSelected)
        app.buttons["release.avatar.none"].tap()
        app.buttons["release.avatar.save"].tap()
        app.buttons["release.profile.avatar"].tap()
        XCTAssertTrue(app.buttons["release.avatar.none"].isSelected)
        capture(app, "avatar-default-restored-es")
    }

    func testAvatarEnglishLargeText() {
        let app = launch(spanish: false, large: true)
        app.buttons["release.profile.avatar"].tap()
        XCTAssertTrue(app.buttons["release.avatar.photo"].waitForExistence(timeout: 4))
        XCTAssertEqual(app.buttons["release.avatar.photo"].label, "Choose photo")
        app.buttons["release.avatar.initials"].tap()
        app.buttons["release.avatar.save"].tap()
        XCTAssertTrue(app.buttons["header.profile"].waitForExistence(timeout: 3))
        capture(app, "avatar-initials-large-en")
    }

    func testReleaseGatesHideAvatarEditingAndPhotos() {
        let debug = launch(spanish: false)
        debug.buttons["release.profile.avatar"].tap()
        XCTAssertTrue(debug.buttons["release.avatar.photo"].waitForExistence(timeout: 4), "DEBUG keeps photos")
        debug.terminate()
        let release = launch(spanish: false, extra: ["--cuadrao-release-gates"])
        let display = release.descendants(matching: .any)["release.profile.display"]
        XCTAssertTrue(display.waitForExistence(timeout: 4))
        XCTAssertEqual(display.label, "Alex")
        XCTAssertTrue(release.buttons["header.profile"].exists)
        XCTAssertFalse(release.buttons["release.profile.avatar"].exists, "Release gates hide the avatar editor entry")
        display.tap()
        XCTAssertFalse(release.buttons["release.avatar.photo"].waitForExistence(timeout: 1))
        XCTAssertFalse(release.buttons["release.avatar.save"].exists)
        capture(release, "profile-release-gates-en")
    }

    func testReleaseBarReplacesTheAssistantWithAddAndKeepsItCentered() {
        let debug = launch(spanish: false)
        XCTAssertTrue(debug.buttons["tab.argus"].waitForExistence(timeout: 4), "DEBUG keeps the assistant tab")
        XCTAssertFalse(debug.buttons["nav.add"].exists)
        debug.terminate()
        let release = launch(spanish: false, extra: ["--cuadrao-release-gates"])
        XCTAssertTrue(release.buttons["nav.add"].waitForExistence(timeout: 4))
        XCTAssertFalse(release.buttons["tab.argus"].exists, "Release has no assistant tab")
        let order = ["tab.home", "tab.plan", "nav.add", "tab.search", "header.profile"].map { release.buttons[$0] }
        for item in order { XCTAssertTrue(item.exists, item.identifier) }
        let centers = order.map(\.frame.midX)
        XCTAssertEqual(centers, centers.sorted(), "Home, Plan, +, Search, Profile run left to right")
        XCTAssertEqual(release.buttons["nav.add"].frame.midX, release.frame.midX, accuracy: 2, "the + sits at the center")
        XCTAssertEqual(release.buttons["nav.add"].label, "Add")
        capture(release, "release-bar-add-en")
    }

    func testDeletionSharedConsequencesEnglish() {
        let app = launch(spanish: false)
        app.buttons["release.review.identity"].tap()
        app.buttons["identity.gallery.delete"].tap()
        XCTAssertTrue(app.staticTexts["identity.delete.sharedConsequences"].waitForExistence(timeout: 3))
        XCTAssertEqual(app.staticTexts["identity.delete.sharedConsequences"].label,
            "In plans you share, your amounts stay so everyone else's numbers still add up, but without your name: you'll show as \"Former member.\" Your receipts and notes are deleted. Anything you owe or are owed is closed in the app, not marked as paid. Plans you created pass to whoever has been in each one longest, except shared debt plans, which are closed and stay view-only.",
            "Iris's founder-locked copy, verbatim")
    }

    func testDeletionConfirmationPendingAndFinish() {
        let app = launch(spanish: true)
        app.buttons["release.review.identity"].tap()
        app.buttons["identity.gallery.delete"].tap()
        XCTAssertTrue(app.staticTexts["identity.delete.sharedConsequences"].waitForExistence(timeout: 3))
        XCTAssertEqual(app.staticTexts["identity.delete.sharedConsequences"].label,
            "En los planes que compartes, tus montos se quedan para que las cuentas de los demás sigan cuadrando, pero sin tu nombre: aparecerás como «Exmiembro». Tus recibos y notas se borran. Lo que debes o te deben queda cerrado en la app, no marcado como pagado. Los planes que creaste pasan a la persona que lleva más tiempo en cada uno, salvo los planes de deuda compartidos, que se cierran y quedan solo para consulta.",
            "Iris's founder-locked copy, verbatim")
        let next = app.buttons["identity.delete.continue"]
        reveal(next, in: app)
        next.tap()
        let field = app.textFields["identity.delete.verification"]
        reveal(field, in: app)
        field.tap(); field.typeText("DELETE")
        let submit = app.buttons["identity.delete.submit"]
        reveal(submit, in: app); submit.tap()
        XCTAssertFalse(app.buttons["identity.delete.complete"].exists)
        app.buttons["identity.delete.fixtureStates"].tap()
        app.buttons["Pendiente"].tap()
        XCTAssertTrue(app.staticTexts["identity.delete.inProgress"].waitForExistence(timeout: 3))
        XCTAssertFalse(app.buttons["identity.delete.complete"].exists, "In progress never shows the finished state")
        XCTAssertTrue(app.buttons["identity.delete.pendingDone"].exists)
        capture(app, "deletion-pending-es")
        app.buttons["identity.delete.fixtureStates"].tap()
        app.buttons["Completada"].tap()
        app.buttons["identity.delete.complete"].tap()
        XCTAssertTrue(app.staticTexts["Sesión cerrada"].waitForExistence(timeout: 3))
    }

    func testSocialCancellationAndNameRecovery() {
        let app = launch(spanish: false)
        app.buttons["release.review.identity"].tap()
        app.buttons["identity.gallery.social"].tap()
        app.buttons["identity.social.apple"].tap()
        XCTAssertTrue(app.descendants(matching: .any).matching(identifier: "identity.social.loading").firstMatch.waitForExistence(timeout: 3))
        app.buttons["identity.social.fixtureStates"].tap()
        app.buttons["Cancelled"].tap()
        XCTAssertTrue(app.staticTexts["identity.social.cancelled"].waitForExistence(timeout: 3))
        XCTAssertTrue(app.staticTexts["identity.social.pendingInvite"].exists)
        app.buttons["identity.social.fixtureStates"].tap()
        app.buttons["Missing name"].tap()
        let name = app.textFields["identity.social.name"]
        XCTAssertTrue(name.waitForExistence(timeout: 3))
        name.tap(); name.typeText("Alex")
        app.buttons["identity.social.saveName"].tap()
        XCTAssertFalse(app.buttons["identity.social.complete"].exists)
        capture(app, "social-name-en")
    }

    func testInviteFullStateAndQRSharing() {
        let app = launch(spanish: true)
        app.buttons["release.review.invites"].tap()
        app.buttons["release.invites.gallery.gate.full"].tap()
        XCTAssertTrue(app.staticTexts["release.inviteGate.status.full"].waitForExistence(timeout: 3))
        XCTAssertTrue(app.buttons["release.inviteGate.waitlist"].exists)
        capture(app, "invitation-full-es")
        app.navigationBars.buttons.element(boundBy: 0).tap()
        let personal = app.buttons["release.invites.gallery.personal"]
        reveal(personal, in: app); personal.tap()
        XCTAssertTrue(app.staticTexts["release.personalInvites.remaining"].waitForExistence(timeout: 3))
        capture(app, "personal-invitation-es")
    }

    func testInvitationProminentLabelsLightAndDark() {
        for dark in [false, true] {
            let app = launch(spanish: true, dark: dark)
            let suffix = dark ? "dark-es" : "light-es"
            app.buttons["release.review.invites"].tap()
            let personal = app.buttons["release.invites.gallery.personal"]
            reveal(personal, in: app); personal.tap()
            let personalCreate = app.buttons["release.personalInvites.create"]
            XCTAssertTrue(personalCreate.waitForExistence(timeout: 3))
            reveal(personalCreate, in: app)
            XCTAssertTrue(personalCreate.isEnabled)
            capture(app, "invitation-create-" + suffix)
            app.navigationBars.buttons.element(boundBy: 0).tap()
            let group = app.buttons["release.invites.gallery.group.create"]
            reveal(group, in: app); group.tap()
            let create = app.buttons["release.groupInvite.create"]
            reveal(create, in: app)
            capture(app, "invitation-group-link-" + suffix)
            app.terminate()
        }
    }

    func testUpdatesNoDataAndReadOnlyHistory() {
        let app = launch(spanish: true)
        app.buttons["release.review.updates"].tap()
        XCTAssertTrue(app.buttons["updates-row-0"].waitForExistence(timeout: 3))
        app.buttons["updates-row-0"].tap()
        capture(app, "bill-notice-es")
        app.navigationBars.buttons.element(boundBy: 0).tap()
        app.buttons["updates-gallery-truth"].tap()
        XCTAssertTrue(app.staticTexts["Sin datos"].waitForExistence(timeout: 3))
        let history = app.descendants(matching: .any).matching(identifier: "release-moved-history-note").firstMatch
        reveal(history, in: app)
        capture(app, "no-data-moved-history-es")
        XCTAssertFalse(app.buttons["Editar"].exists)
    }

    func testPhotoCropAndTabAvatarInDarkAppearance() {
        let app = launch(spanish: false, dark: true)
        app.buttons["release.profile.avatar"].tap()
        app.buttons["release.avatar.photo"].tap()
        let photo = app.images.matching(identifier: "PXGGridLayout-Info").firstMatch
        XCTAssertTrue(photo.waitForExistence(timeout: 8))
        photo.tap()
        XCTAssertTrue(app.buttons["cuadrao.profile.crop.use"].waitForExistence(timeout: 8))
        capture(app, "photo-crop-dark-en")
        app.buttons["cuadrao.profile.crop.use"].tap()
        XCTAssertTrue(app.buttons["release.avatar.save"].waitForExistence(timeout: 5))
        app.buttons["release.avatar.save"].tap()
        XCTAssertTrue(app.buttons["header.profile"].waitForExistence(timeout: 3))
        capture(app, "photo-tab-dark-en")
        app.buttons["release.profile.avatar"].tap()
        XCTAssertTrue(app.buttons["Reposition photo"].waitForExistence(timeout: 3))
    }

    func testDeletionCodeResendClearsOldCode() {
        let app = launch(spanish: false)
        app.buttons["release.review.identity"].tap()
        app.buttons["identity.gallery.delete"].tap()
        app.buttons["identity.delete.fixtureStates"].tap()
        app.buttons["Code"].tap()
        app.buttons["identity.delete.fixtureStates"].tap()
        app.buttons["Verification rejected"].tap()
        let field = app.textFields["identity.delete.verification"]
        reveal(field, in: app); field.tap(); field.typeText("123456")
        let resend = app.buttons["identity.delete.resend"]
        reveal(resend, in: app); resend.tap()
        XCTAssertFalse(app.buttons["identity.delete.submit"].exists)
        app.buttons["identity.delete.fixtureStates"].tap()
        app.buttons["Code sent"].tap()
        XCTAssertFalse(app.buttons["identity.delete.submit"].isEnabled)
        app.buttons["identity.delete.cancelVerification"].tap()
        XCTAssertFalse(app.textFields["identity.delete.verification"].exists)
        capture(app, "verification-cancelled-en")
    }

    func testAIConsentCanBeDeclined() {
        let app = launch(spanish: false)
        app.buttons["release.review.identity"].tap()
        app.buttons["identity.gallery.ai"].tap()
        XCTAssertTrue(app.buttons["identity.ai.allow"].waitForExistence(timeout: 3))
        capture(app, "ai-consent-en")
        app.buttons["identity.ai.decline"].tap()
        XCTAssertTrue(app.buttons["identity.gallery.ai"].waitForExistence(timeout: 3))
    }

    func testFullPreviewSharesProfileAvatarWithNavigation() {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["--cuadrao-design", "--cuadrao-home", "-AppleLanguages", "(es)", "-AppleLocale", "es_DO"]
        app.launch()
        XCTAssertTrue(app.buttons["header.profile"].waitForExistence(timeout: 8))
        app.buttons["header.profile"].tap()
        XCTAssertTrue(app.buttons["cuadrao.profile.identity"].waitForExistence(timeout: 4))
        capture(app, "full-profile-empty-es")
        app.buttons["cuadrao.profile.identity"].tap()
        XCTAssertTrue(app.buttons["cuadrao.profile.photo.choose"].waitForExistence(timeout: 3))
        let moon = app.buttons["cuadrao.profile.avatar.moon"]
        reveal(moon, in: app); moon.tap()
        app.buttons["cuadrao.profile.save"].tap()
        capture(app, "full-profile-theme-es")
        app.buttons["cuadrao.profile.identity"].tap()
        let selected = app.buttons["cuadrao.profile.avatar.moon"]
        reveal(selected, in: app)
        XCTAssertTrue(selected.isSelected)
        app.buttons["cuadrao.profile.cancel"].tap()
        app.buttons["tab.home"].tap()
        XCTAssertTrue(app.staticTexts["home-greeting"].waitForExistence(timeout: 3))
        capture(app, "full-home-theme-es")
    }

    private func reveal(_ element: XCUIElement, in app: XCUIApplication) {
        for _ in 0..<8 {
            if element.exists && element.isHittable { return }
            app.swipeUp()
        }
        XCTAssertTrue(element.exists)
    }

    private func launch(spanish: Bool, large: Bool = false, dark: Bool = false, extra: [String] = []) -> XCUIApplication {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["--cuadrao-release-ui", "-AppleLanguages", spanish ? "(es)" : "(en)", "-AppleLocale", spanish ? "es_DO" : "en_US"] + extra
        if dark { app.launchArguments += ["--release-dark"] }
        if large { app.launchArguments += ["-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"] }
        app.launch()
        XCTAssertTrue(app.buttons["release.review.identity"].waitForExistence(timeout: 6))
        return app
    }

    private func capture(_ app: XCUIApplication, _ name: String) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name; attachment.lifetime = .keepAlways; add(attachment)
    }
}
