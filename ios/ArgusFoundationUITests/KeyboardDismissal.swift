import XCTest

extension XCUIApplication {
    /// Closes the keyboard the way a person does, by tapping away from the field, and proves it closed.
    /// There is no Done control above the keyboard.
    func dismissKeyboard(file: StaticString = #filePath, line: UInt = #line) {
        guard keyboards.firstMatch.exists else { return }
        let title = navigationBars.firstMatch.staticTexts.firstMatch
        if title.exists && title.isHittable { title.tap() } else { coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5)).tap() }
        XCTAssertTrue(keyboards.firstMatch.waitForNonExistence(timeout: 3), "tapping away closes the keyboard", file: file, line: line)
    }
}
