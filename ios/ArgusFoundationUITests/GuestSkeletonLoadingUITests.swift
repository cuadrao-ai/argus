import XCTest

/// A real pending load shows grey blocks in the shape of the screen, and they leave when the content arrives.
extension FinancialLoopUITests {
    func testGuestBookShowsASkeletonWhileOpeningThenTheEmptyHome() {
        launchSignedOut(arguments: ["--cuadrao-guest-book", "--guest-slow-load"], language: "es-419")
        let guest = app.buttons["cuadrao.welcome.guest"]
        XCTAssertTrue(guest.waitForExistence(timeout: 10), "the welcome screen offers the book")
        guest.tap()
        let skeleton = app.descendants(matching: .any)["guest.loading"]
        XCTAssertTrue(skeleton.waitForExistence(timeout: 5), "blocks show while the book opens")
        XCTAssertEqual(skeleton.label, "Cargando")
        let image = XCTAttachment(screenshot: app.screenshot()); image.name = "guest-skeleton-light-es"; image.lifetime = .keepAlways; add(image)
        let empty = app.descendants(matching: .any)["guest.home.empty"]
        XCTAssertTrue(empty.waitForExistence(timeout: 15), "the empty Home replaces the blocks")
        XCTAssertFalse(skeleton.exists, "a settled screen never keeps its skeleton")
    }
}
