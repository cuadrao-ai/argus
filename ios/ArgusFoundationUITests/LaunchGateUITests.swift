import XCTest

extension FinancialLoopUITests {
    /// A signed-in cold start shows the launch screen and then Home. Sign-in and sign-up never draw, not even for a frame.
    /// The restore is held for six seconds (XCUITest launch alone takes about two), as a slow hosted /me would, so a flash cannot hide between polls.
    func testSignedInColdStartNeverDrawsSignIn() throws {
        try signIn()
        app.launchArguments += ["-cuadraoRestoreDelayMs", "6000"]
        let welcome = [app.buttons["cuadrao.welcome.signin"], app.buttons["cuadrao.welcome.signup"],
                       app.buttons["cuadrao.signin.emailChoice"], app.buttons["cuadrao.signup.email"]]
        for attempt in 1...5 {
            app.terminate()
            app.launch()
            XCTAssertTrue(app.descendants(matching: .any)["app.launching"].exists, "launch screen holds on cold start \(attempt)")
            let deadline = Date().addingTimeInterval(60)
            while !app.buttons["tab.home"].exists && Date() < deadline {
                XCTAssertFalse(welcome.contains { $0.exists }, "sign-in drew on signed-in cold start \(attempt)")
            }
            XCTAssertTrue(app.buttons["tab.home"].exists, "Home opens on signed-in cold start \(attempt)")
            XCTAssertFalse(welcome.contains { $0.exists }, "sign-in drew beside Home on cold start \(attempt)")
        }
    }
}
