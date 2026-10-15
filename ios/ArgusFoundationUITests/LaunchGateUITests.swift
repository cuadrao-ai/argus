import XCTest

extension FinancialLoopUITests {
    private var welcome: [XCUIElement] {
        [app.buttons["cuadrao.welcome.signin"], app.buttons["cuadrao.welcome.signup"],
         app.buttons["cuadrao.signin.emailChoice"], app.buttons["cuadrao.signup.email"]]
    }

    /// Polls until `done` holds, failing the moment sign-in or sign-up draws.
    private func waitWithoutSignIn(until done: () -> Bool, timeout: TimeInterval, _ message: String) {
        let deadline = Date().addingTimeInterval(timeout)
        while !done() && Date() < deadline {
            XCTAssertFalse(welcome.contains { $0.exists }, message)
        }
        XCTAssertTrue(done(), message)
    }

    /// A signed-in cold start shows the launch screen and then Home. Sign-in and sign-up never draw, not even for a frame.
    /// The restore is held for six seconds (XCUITest launch alone takes about two), as a slow hosted /me would.
    func testSignedInColdStartNeverDrawsSignIn() throws {
        try signIn()
        app.launchArguments += ["-cuadraoRestoreDelayMs", "6000"]
        for attempt in 1...5 {
            app.terminate()
            app.launch()
            XCTAssertTrue(app.descendants(matching: .any)["app.launching"].exists, "launch screen holds on cold start \(attempt)")
            waitWithoutSignIn(until: { app.buttons["tab.home"].exists }, timeout: 60, "signed-in cold start \(attempt) reaches Home without sign-in")
            XCTAssertFalse(welcome.contains { $0.exists }, "sign-in drew beside Home on cold start \(attempt)")
        }
    }

    /// A check slower than one second shows the quiet loader; past the deadline it says so and offers Reintentar,
    /// never an endless spinner and never sign-in. When the check ends, Home opens.
    func testHungSessionCheckShowsLoaderThenReintentarNeverSignIn() throws {
        try signIn()
        app.launchArguments += ["-cuadraoRestoreDelayMs", "14000"]
        app.terminate()
        app.launch()
        let any = app.descendants(matching: .any)
        waitWithoutSignIn(until: { any["app.launching.loader"].exists }, timeout: 5, "a slow check shows the loader")
        waitWithoutSignIn(until: { any["app.unreachable.retry"].exists }, timeout: 15, "past the deadline it offers Reintentar")
        XCTAssertTrue(any["app.unreachable.message"].exists)
        app.buttons["app.unreachable.retry"].tap()
        waitWithoutSignIn(until: { app.buttons["tab.home"].exists }, timeout: 60, "Home opens when the check ends")
    }

    /// Signed out, a cold start goes from the launch screen straight to sign-in, never through Home.
    func testSignedOutColdStartGoesStraightToSignIn() throws {
        try signIn()
        XCTAssertTrue(app.buttons["header.profile"].waitForExistence(timeout: 10))
        app.buttons["header.profile"].tap()
        XCTAssertTrue(app.buttons["auth.signOut"].waitForExistence(timeout: 10))
        tapVisible(app.buttons["auth.signOut"])
        app.confirmSignOutIfAsked()
        XCTAssertTrue(app.buttons["cuadrao.welcome.signin"].waitForExistence(timeout: 20))
        for attempt in 1...2 {
            app.terminate()
            app.launch()
            let deadline = Date().addingTimeInterval(20)
            while !app.buttons["cuadrao.welcome.signin"].exists && Date() < deadline {
                XCTAssertFalse(app.buttons["tab.home"].exists, "Home drew on signed-out cold start \(attempt)")
            }
            XCTAssertTrue(app.buttons["cuadrao.welcome.signin"].exists, "sign-in opens on signed-out cold start \(attempt)")
            XCTAssertFalse(app.buttons["tab.home"].exists)
        }
    }
}
