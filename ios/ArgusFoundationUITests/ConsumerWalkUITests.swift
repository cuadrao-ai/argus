import XCTest

/// Throwaway walk that captures the surfaces the founder's feedback names. Not committed.
extension FinancialLoopUITests {
    private func walkTabs(_ prefix: String) {
        XCTAssertTrue(app.buttons["nav.add"].waitForExistence(timeout: 20))
        sleep(4)
        capture(prefix + "-home-top")
        for _ in 0..<2 { app.swipeUp() }
        capture(prefix + "-home-scrolled")
        for _ in 0..<4 { app.swipeDown() }
        for (tab, name) in [("tab.plan", "plan"), ("tab.search", "search"), ("header.profile", "profile")] {
            for _ in 0..<4 { app.swipeDown() }
            app.buttons[tab].tap()
            sleep(3)
            capture("\(prefix)-\(name)-top")
            for _ in 0..<3 { app.swipeUp() }
            capture("\(prefix)-\(name)-bottom")
            for _ in 0..<5 { app.swipeDown() }
        }
    }

    func testConsumerWalkReorder() throws {
        try signIn()
        app.terminate()
        app.launchArguments = ["-AppleLanguages", "(en)", "-AppleLocale", "en_US", "--cuadrao-release-gates"]
        app.launch()
        XCTAssertTrue(app.buttons["nav.add"].waitForExistence(timeout: 20))
        sleep(4)
        for _ in 0..<2 { app.swipeUp() }
        func order() -> [String] {
            let rows = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'accounts.row.'")).allElementsBoundByIndex
            return rows.filter { $0.isHittable }.prefix(4).map { $0.label }
        }
        let before = order()
        let rows = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'accounts.row.'")).allElementsBoundByIndex.filter { $0.isHittable }
        XCTAssertGreaterThanOrEqual(rows.count, 2, "need two visible account rows")
        capture("walk-reorder-before")
        rows[0].press(forDuration: 1.2, thenDragTo: rows[1])
        sleep(1)
        capture("walk-reorder-after")
        let after = order()
        XCTContext.runActivity(named: "order before \(before) after \(after)") { _ in }
        XCTAssertNotEqual(before, after, "hold and drag reordered the accounts: \(before) -> \(after)")
    }

    func testConsumerWalkEmptyUser() throws {
        try signIn(fresh: true)
        app.terminate()
        app.launchArguments = ["-AppleLanguages", "(en)", "-AppleLocale", "en_US", "--cuadrao-release-gates"]
        app.launch()
        walkTabs("walk-empty")
    }

    func testConsumerWalkPopulatedUser() throws {
        try signIn()
        app.terminate()
        app.launchArguments = ["-AppleLanguages", "(en)", "-AppleLocale", "en_US", "--cuadrao-release-gates"]
        app.launch()
        walkTabs("walk-data")
    }
}
