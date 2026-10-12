import XCTest

final class CuadraoSkeletonToastUITests: XCTestCase {
    private func gallery(dark: Bool = false) -> XCUIApplication {
        let app = XCUIApplication.cuadraoPreview()
        app.launchArguments = CuadraoPreviewLaunch.arguments + ["--design-gallery", "-cuadrao.design.appearance", dark ? "dark" : "light"]
        app.launch()
        return app
    }

    private func reveal(_ app: XCUIApplication, _ element: XCUIElement) {
        for _ in 0..<14 { if element.isHittable { return }; app.swipeUp() }
        XCTAssertTrue(element.isHittable)
    }

    /// A running shimmer keeps the app from ever going idle, so a test freezes it first, as a person with Reduce Motion does.
    func testSkeletonShowsInTheRealLayoutAndStaysStillWithReducedMotion() {
        continueAfterFailure = false
        let app = gallery()
        app.switches["gallery-reduce-motion"].tap()
        let rows = app.descendants(matching: .any)["gallery-skeleton-rows"]
        reveal(app, rows)
        XCTAssertTrue(["Loading", "Cargando"].contains(rows.label), "VoiceOver hears one loading label, not the blocks")
        shot(app, "skeleton-rows-light-es")
        let home = app.descendants(matching: .any)["gallery-skeleton-home"]
        reveal(app, home)
        shot(app, "skeleton-home-reduced-motion-es")
    }

    func testToastAnnouncesOffersUndoAndClearsItself() {
        continueAfterFailure = false
        let app = gallery(dark: true)
        let show = app.buttons["gallery-toast-show"]
        reveal(app, show)
        show.tap()
        let undo = app.buttons["gallery-toast-undo"]
        XCTAssertTrue(undo.waitForExistence(timeout: 3))
        XCTAssertEqual(undo.label, "Deshacer")
        shot(app, "toast-dark-es")
        undo.tap()
        XCTAssertTrue(undo.waitForNonExistence(timeout: 3), "Undo closes the toast")
        show.tap()
        XCTAssertTrue(undo.waitForExistence(timeout: 3))
        XCTAssertTrue(undo.waitForNonExistence(timeout: 9), "the toast clears itself after about five seconds")
    }

    func testToastAndSkeletonHoldAtLargestTextSize() {
        continueAfterFailure = false
        let app = gallery()
        app.switches["gallery-large-text"].tap()
        let show = app.buttons["gallery-toast-show"]
        reveal(app, show)
        show.tap()
        XCTAssertTrue(app.buttons["gallery-toast-undo"].waitForExistence(timeout: 3))
        shot(app, "toast-large-text-es")
    }

    private func shot(_ app: XCUIApplication, _ name: String) {
        let image = XCTAttachment(screenshot: app.screenshot()); image.name = name; image.lifetime = .keepAlways; add(image)
    }
}
