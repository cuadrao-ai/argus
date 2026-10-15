import XCTest

final class CuadraoCollectionUITests: XCTestCase {
    func testGroupPeopleOwnerAndRemovalReview() {
        continueAfterFailure = false
        let app = launch()
        app.buttons["tab.plan"].tap()
        app.segmentedControls.buttons["En grupo"].tap()
        app.buttons["group-card-trip"].tap()
        app.buttons["group-people-open"].tap()
        XCTAssertTrue(app.buttons["group-invite"].waitForExistence(timeout: 3))
        assertPeopleOnly(app)
        let own = member(app, "Tú")
        reveal(app, own)
        own.swipeLeft()
        XCTAssertFalse(app.buttons["group-remove-Tú"].exists)
        let ana = member(app, "Ana")
        reveal(app, ana)
        ana.swipeLeft()
        XCTAssertTrue(app.buttons["group-remove-Ana"].waitForExistence(timeout: 3))
        let (red, green) = app.colorCounts(in: app.buttons["group-remove-Ana"].frame)
        XCTAssertGreaterThan(red, 20, "removing a member is a destructive swipe, so it is red")
        XCTAssertEqual(green, 0, "no brand-green pixels in the remove action")
        XCTAssertFalse(app.buttons["group-remove-confirm"].exists)
        app.buttons["group-remove-Ana"].tap()
        XCTAssertFalse(app.buttons["group-remove-confirm"].isEnabled)
        shot(app, "group-outstanding-removal-review")
        app.buttons["Cancelar"].tap()
        XCTAssertTrue(member(app, "Ana").exists)
        app.buttons["group-invite"].tap()
        reveal(app, app.buttons["group-invite-preview"])
        app.buttons["group-invite-preview"].tap()
        reveal(app, app.buttons["group-invite-accept"])
        app.buttons["group-invite-accept"].tap()
        app.buttons["Cerrar"].tap()
        let mar = member(app, "Mar")
        reveal(app, mar)
        XCTAssertFalse(app.buttons["group-remove-Mar"].exists)
        shot(app, "group-people-owner")
        mar.swipeLeft()
        app.buttons["group-remove-Mar"].tap()
        XCTAssertTrue(app.buttons["group-remove-confirm"].isEnabled)
        app.buttons["group-remove-confirm"].tap()
        XCTAssertFalse(member(app, "Mar").exists)
        XCTAssertTrue(app.buttons["Participaron antes"].exists)
    }
    func testMemberRoleAndLegacyControls() {
        continueAfterFailure = false
        let app = launch(extra: ["--group-member", "--legacy-collection", "--design-english"])
        app.buttons["tab.plan"].tap()
        app.segmentedControls.buttons["Together"].tap()
        XCTAssertFalse(app.buttons["Edit"].exists)
        app.buttons["group-card-trip"].tap()
        app.buttons["group-people-open"].tap()
        XCTAssertFalse(app.buttons["group-invite"].exists)
        assertPeopleOnly(app)
        let ana = member(app, "Ana")
        reveal(app, ana)
        ana.press(forDuration: 1)
        XCTAssertFalse(app.buttons["group-remove-Ana"].exists)
        shot(app, "group-people-member-en")
    }
    func testMemberRoleHasNoNativeRemovalEnglishDark() {
        continueAfterFailure = false
        let app = launch(dark: true, extra: ["--group-member", "--design-english"])
        app.buttons["tab.plan"].tap()
        app.segmentedControls.buttons["Together"].tap()
        app.buttons["group-card-trip"].tap()
        app.buttons["group-people-open"].tap()
        assertPeopleOnly(app)
        let ana = member(app, "Ana")
        reveal(app, ana)
        let rowX = ana.frame.minX
        ana.swipeLeft()
        let rowAtRest = NSPredicate { _, _ in abs(ana.frame.minX - rowX) < 1 }
        expectation(for: rowAtRest, evaluatedWith: nil)
        waitForExpectations(timeout: 3)
        XCTAssertFalse(app.buttons["group-remove-Ana"].exists)
        XCTAssertFalse(app.buttons["group-remove-confirm"].exists)
        XCTAssertFalse(app.buttons["group-invite"].exists)
        shot(app, "group-people-member-native-en-dark")
    }
    func testOwnerLegacyRemovalMenu() {
        continueAfterFailure = false
        let app = launch(extra: ["--legacy-collection", "--design-english"])
        app.buttons["tab.plan"].tap()
        app.segmentedControls.buttons["Together"].tap()
        app.buttons["group-card-trip"].tap()
        app.buttons["group-people-open"].tap()
        assertPeopleOnly(app)
        let ana = member(app, "Ana")
        reveal(app, ana)
        ana.press(forDuration: 1)
        app.buttons["group-remove-Ana"].tap()
        XCTAssertFalse(app.buttons["group-remove-confirm"].isEnabled)
        app.buttons["Cancel"].tap()
        XCTAssertTrue(member(app, "Ana").exists)
    }
    func testPersonalPlanSwipeEditArchiveRestore() {
        continueAfterFailure = false
        let app = launch()
        app.buttons["tab.plan"].tap()
        let card = app.buttons["plan-row-goal-personal"]
        reveal(app, card)
        card.swipeRight()
        app.buttons["Editar"].tap()
        XCTAssertTrue(app.textFields["plan-name"].waitForExistence(timeout: 3))
        app.buttons["Cancelar"].tap()
        card.swipeLeft()
        shot(app, "plan-swipe-archive")
        app.buttons["Archivar"].tap()
        XCTAssertFalse(card.exists)
        reveal(app, app.buttons["plan-archives"])
        app.buttons["plan-archives"].tap()
        shot(app, "plan-archive-recovery")
        XCTAssertTrue(app.buttons["Retomar"].waitForExistence(timeout: 3))
        app.buttons["Retomar"].tap()
    }
    func testGroupNativeReorderPersistenceAndRecovery() {
        continueAfterFailure = false
        let app = launch()
        app.buttons["tab.plan"].tap(); app.segmentedControls.buttons["En grupo"].tap()
        let trip = app.buttons["group-card-trip"], saving = app.buttons["group-card-saving"]
        reveal(app, saving)
        let source = trip.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.75))
        source.press(forDuration: 0.7, thenDragTo: saving.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.8)))
        app.swipeDown()
        XCTAssertLessThan(saving.frame.minY, trip.frame.minY)
        shot(app, "groups-reordered")
        app.terminate(); app.launchArguments = CuadraoPreviewLaunch.arguments + ["-cuadrao.design.appearance", "light"]; app.launch()
        app.buttons["tab.plan"].tap(); app.segmentedControls.buttons["En grupo"].tap()
        XCTAssertLessThan(saving.frame.minY, trip.frame.minY)
        saving.swipeLeft(); app.buttons["Archivar"].tap()
        reveal(app, app.buttons["group-archives"]); app.buttons["group-archives"].tap()
        XCTAssertTrue(app.buttons["Retomar"].waitForExistence(timeout: 3)); app.buttons["Retomar"].tap()
    }
    private func assertPeopleOnly(_ app: XCUIApplication) {
        XCTAssertFalse(app.buttons["group-add-receipt"].exists)
        XCTAssertFalse(app.buttons["group-open-chat"].exists)
        XCTAssertFalse(app.buttons["group-add-expense"].exists)
        XCTAssertFalse(app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH %@ OR label BEGINSWITH %@", "Vista previa local", "Local preview")).firstMatch.exists)
        XCTAssertFalse(app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@", "receipt-card-")).firstMatch.exists)
        XCTAssertFalse(app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@", "group-remove-")).firstMatch.exists)
    }
    private func member(_ app: XCUIApplication, _ name: String) -> XCUIElement {
        app.descendants(matching: .any).matching(identifier: "group-member-" + name).firstMatch
    }
    private func launch(dark: Bool = false, extra: [String] = []) -> XCUIApplication {
        let app = XCUIApplication.cuadraoPreview()
        app.launchArguments = CuadraoPreviewLaunch.arguments + ["--plan-reset", "--receipt-reset", "-cuadrao.design.appearance", dark ? "dark" : "light"] + extra
        app.launch(); return app
    }
    private func reveal(_ app: XCUIApplication, _ element: XCUIElement) {
        for _ in 0..<10 {
            if element.isHittable && element.frame.minY > 80 && element.frame.maxY < app.frame.maxY - 110 { return }
            let down = !element.exists || element.frame.minY > app.frame.midY
            app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: down ? 0.65 : 0.35)).press(forDuration: 0.01,
                thenDragTo: app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: down ? 0.4 : 0.6)))
        }
        XCTAssertTrue(element.isHittable)
    }
    private func shot(_ app: XCUIApplication, _ name: String) {
        let attachment = XCTAttachment(screenshot: app.screenshot()); attachment.name = name; attachment.lifetime = .keepAlways; add(attachment)
    }
}
