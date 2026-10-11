import XCTest

extension FinancialLoopUITests {
    func testRetainedBudgetCorrectionCancelAndNativeBack() throws {
        try signIn()
        openBudget("Food 4DE49")
        assertBudget(spent: "180.00", status: "30.00", over: true)
        let row = app.buttons.matching(NSPredicate(
            format: "identifier BEGINSWITH 'budget.activity.' AND label CONTAINS %@",
            "Card groceries 4DE49"
        )).firstMatch
        tapVisible(row)
        let amount = app.staticTexts["activity-detail-amount"]
        let corrected = XCTNSPredicateExpectation(
            predicate: NSPredicate { _, _ in
                amount.exists && amount.label == "DOP 60.00" && amount.isHittable
            }, object: nil
        )
        XCTAssertEqual(XCTWaiter.wait(for: [corrected], timeout: 15), .completed)
        capture("synthetic-retained-budget-corrected-activity")
        tapVisible(app.buttons["activity.correct"])
        XCTAssertTrue(app.textFields["loop.amount"].waitForExistence(timeout: 10))
        let modal = app.navigationBars["Correct entry"]
        XCTAssertTrue(modal.waitForExistence(timeout: 5))
        let back = app.navigationBars.buttons.matching(identifier: "BackButton").firstMatch
        XCTAssertFalse(back.exists && back.isHittable, "Native Back must be unavailable behind the correction sheet")
        capture("synthetic-retained-budget-correction-open")
        app.navigationBars.buttons["Cancel"].tap()
        app.swipeBack(cancel: true)
        XCTAssertFalse(modal.exists)
        XCTAssertTrue(amount.isHittable)
        XCTAssertEqual(amount.label, "DOP 60.00")
        capture("synthetic-retained-budget-cancelled-native-back")
        app.swipeBack()
        assertBudget(spent: "180.00", status: "30.00", over: true)
        capture("synthetic-retained-budget-native-back-complete")
    }
}
