import XCTest

final class CuadraoConsistencyUITests: XCTestCase {
    func testMoneyEntryAndBlankCreationSpanish() {
        continueAfterFailure = false
        let app = XCUIApplication.cuadraoPreview()
        app.launchArguments = CuadraoPreviewLaunch.arguments + ["--plan-reset", "-cuadrao.design.appearance", "light"]
        app.launch(); app.buttons["tab.plan"].tap(); app.buttons["plan-create"].tap()
        let target = app.textFields["plan-target"]
        XCTAssertEqual(target.value as? String, "0.00")
        app.textFields["plan-name"].tap(); app.textFields["plan-name"].typeText("Un plan propio\n")
        XCTAssertFalse(app.buttons["plan-save"].isEnabled)
        target.tap(); target.typeText("1250.5")
        XCTAssertEqual(target.value as? String, "1,250.5")
        app.dismissKeyboard()
        XCTAssertEqual(target.value as? String, "1,250.50")
        replace(target, "12.345")
        XCTAssertTrue(app.staticTexts["plan-target-error"].exists)
        XCTAssertEqual(target.value as? String, "12.34")
        XCTAssertFalse(app.buttons["plan-save"].isEnabled)
        shot(app, "money-precision-error-es")
        replace(target, "9999999.99")
        XCTAssertFalse(app.staticTexts["plan-target-error"].exists)
        target.typeText("9")
        XCTAssertTrue(app.staticTexts["plan-target-error"].exists)
        replace(target, "10000000")
        XCTAssertTrue(app.staticTexts["plan-target-error"].exists)
        replace(target, "2500")
        app.dismissKeyboard()
        let monthly = app.textFields["plan-monthly"]
        monthly.tap(); monthly.typeText("500")
        app.dismissKeyboard()
        XCTAssertEqual(monthly.value as? String, "500.00")
        XCTAssertTrue(app.buttons["plan-save"].isEnabled)
        shot(app, "money-valid-plan-es")
        app.buttons["plan-save"].tap()
        XCTAssertTrue(app.buttons["plan-detail-options"].waitForExistence(timeout: 3))
    }
    func testReferenceGalleryAndSharedAccountsBehavior() {
        continueAfterFailure = false
        let app = XCUIApplication.cuadraoPreview(); app.launchArguments = CuadraoPreviewLaunch.arguments + ["--design-gallery"]; app.launch()
        shot(app, "gallery-light-es")
        app.segmentedControls["gallery-language"].buttons["English"].tap()
        app.switches["gallery-dark"].tap()
        app.switches["gallery-large-text"].tap()
        shot(app, "gallery-dark-large-en")
        app.switches["gallery-large-text"].tap()
        let account = app.textFields["cuadrao-amount"]
        reveal(app, account); account.tap(); account.typeText("1250.5")
        XCTAssertEqual(account.value as? String, "1,250.5")
        app.dismissKeyboard()
        XCTAssertEqual(account.value as? String, "1,250.50")
        let plan = app.textFields["gallery-plan-amount"]
        reveal(app, plan); plan.tap(); plan.typeText("1250.5")
        app.dismissKeyboard()
        XCTAssertEqual(plan.value as? String, account.value as? String)
        shot(app, "gallery-money-dark-en")
        for _ in 0..<4 { app.swipeDown() }
        app.switches["gallery-large-text"].tap()
        reveal(app, plan)
        shot(app, "gallery-money-large-en")
    }
    func testSurfaceTypographySpanish() {
        continueAfterFailure = false
        let app = XCUIApplication.cuadraoPreview(); app.launchArguments = CuadraoPreviewLaunch.arguments + ["--plan-reset", "-cuadrao.design.appearance", "light"]; app.launch()
        shot(app, "home-type-es")
        app.buttons["tab.plan"].tap()
        XCTAssertEqual(app.staticTexts["plan-heading"].label, "Lo que viene")
        XCTAssertFalse(app.staticTexts["Lo que viene, lo hacemos."].exists)
        shot(app, "plan-type-es")
        app.buttons["tab.argus"].tap(); shot(app, "chat-type-es")
        app.buttons["tab.search"].tap(); shot(app, "search-type-es")
        app.buttons["header.profile"].tap(); shot(app, "profile-type-es")
    }
    func testEmptyAndLoadingGallery() {
        continueAfterFailure = false
        let app = XCUIApplication.cuadraoPreview()
        app.launchArguments = CuadraoPreviewLaunch.arguments + ["--design-gallery", "--design-english", "-cuadrao.design.appearance", "dark"]
        app.launch()
        app.switches["gallery-large-text"].tap()
        app.switches["gallery-reduce-motion"].tap()
        let empty = app.staticTexts["Your story starts here"]
        for _ in 0..<12 { if empty.isHittable { break }; app.swipeUp() }
        XCTAssertTrue(empty.isHittable)
        shot(app, "gallery-empty-dark-large-en")
        let unavailable = app.staticTexts["Part of the story is missing"]
        for _ in 0..<8 { if unavailable.isHittable { break }; app.swipeUp() }
        XCTAssertTrue(unavailable.isHittable)
        shot(app, "gallery-unavailable-dark-large-en")
        let loading = app.staticTexts["Gathering your history"]
        for _ in 0..<5 { if loading.isHittable { break }; app.swipeUp() }
        XCTAssertTrue(loading.isHittable)
        shot(app, "gallery-loading-dark-large-en")
    }
    private func replace(_ field: XCUIElement, _ text: String) {
        field.coordinate(withNormalizedOffset: CGVector(dx: 0.98, dy: 0.5)).tap()
        field.typeText(String(repeating: XCUIKeyboardKey.delete.rawValue, count: (field.value as? String ?? "").count + 2))
        field.typeText(text)
    }
    private func reveal(_ app: XCUIApplication, _ field: XCUIElement) {
        for _ in 0..<6 { if field.isHittable && field.frame.maxY < app.frame.maxY - 90 { return }; app.swipeUp() }
        XCTAssertTrue(field.isHittable)
    }
    private func shot(_ app: XCUIApplication, _ name: String) {
        let image = XCTAttachment(screenshot: app.screenshot()); image.name = name; image.lifetime = .keepAlways; add(image)
    }
}
