import XCTest
import UIKit

extension FinancialLoopUITests {
    func testConsumerHomeScrollMechanismWithoutSaving() throws {
        try signIn()
        openPersonalAccounts()
        let add = app.buttons["accounts.add"]
        let scroll = app.scrollViews.containing(.button, identifier: "accounts.add").firstMatch
        XCTAssertTrue(scroll.waitForExistence(timeout: 5))
        let chart = app.descendants(matching: .any)["home-balance-chart"].firstMatch
        let navigation = ["tab.home", "tab.plan", "nav.add", "tab.search", "header.profile"]

        func trace(_ stage: String) {
            var elements: [(String, XCUIElement)] = [("app", app), ("scroll", scroll), ("add", add), ("chart", chart)]
            elements += navigation.map { ($0, app.buttons[$0]) }
            for (name, element) in elements where element.exists {
                print("CONSUMER_ENTRY label=\(stage).\(name) identifier=\(element.identifier) frame=\(element.frame)")
            }
            capture("consumer-entry-" + stage)
        }

        func waitForScrollToSettle() {
            var previous = add.frame
            var lastMovement = Date()
            let settled = NSPredicate { _, _ in
                let frame = add.frame
                if frame != previous { previous = frame; lastMovement = Date() }
                return Date().timeIntervalSince(lastMovement) > 0.5
            }
            XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: settled, object: nil)], timeout: 5), .completed)
        }

        trace("before")
        let topBars = app.navigationBars.allElementsBoundByIndex + app.statusBars.allElementsBoundByIndex
        let top = topBars.filter { $0.isHittable && $0.frame.intersects(scroll.frame) }
            .reduce(max(app.frame.minY, scroll.frame.minY)) { max($0, $1.frame.maxY) }
        let lowerControls = app.buttons.allElementsBoundByIndex
            + app.toolbars.allElementsBoundByIndex + app.tabBars.allElementsBoundByIndex
            + app.keyboards.allElementsBoundByIndex
        let bottom = lowerControls.reduce(min(app.frame.maxY, scroll.frame.maxY)) { edge, control in
            let frame = control.frame
            guard frame.intersects(scroll.frame), frame.intersects(app.frame),
                  control.elementType == .keyboard || frame.minY >= scroll.frame.midY else { return edge }
            let reference = control.identifier.isEmpty ? control.label : control.identifier
            let inScroll = scroll.descendants(matching: control.elementType)
                .matching(identifier: reference).allElementsBoundByIndex.contains { $0.frame == frame }
            guard !inScroll && control.isHittable else { return edge }
            return min(edge, frame.minY)
        }
        let start = app.coordinate(withNormalizedOffset: .zero)
            .withOffset(CGVector(dx: app.frame.width / 2, dy: (top + bottom) / 2 - app.frame.minY))
        let frame = add.frame
        let distance: CGFloat
        if frame.minY < top { distance = top - frame.minY + 24 }
        else if frame.maxY > bottom { distance = bottom - frame.maxY - 24 }
        else { distance = (top + bottom) / 2 - frame.midY }
        let limit = max(0, (bottom - top) / 2)
        XCTAssertGreaterThan(limit, 0)
        let movement = max(-limit, min(limit, distance))
        let end = start.withOffset(CGVector(dx: 0, dy: movement))
        for (label, point) in [("drag-start", start.screenPoint), ("drag-end", end.screenPoint)] {
            print("CONSUMER_ENTRY label=\(label) identifier=tapVisible frame=\(CGRect(origin: point, size: .zero))")
        }
        start.press(forDuration: 0.01, thenDragTo: end, withVelocity: .slow, thenHoldForDuration: 0.2)
        waitForScrollToSettle()
        trace("after-center-drag")

        scroll.swipeUp(velocity: .fast)
        waitForScrollToSettle()
        trace("after-standard-swipe")

        let navigationTop = navigation.map { app.buttons[$0] }
            .filter { $0.exists && $0.isHittable && $0.frame.intersects(app.frame) }
            .map { $0.frame.minY }.min() ?? app.frame.maxY
        if add.isHittable && app.frame.contains(add.frame) && add.frame.minY >= top && add.frame.maxY <= navigationTop {
            add.tap()
            let checking = app.buttons["accounts.type.checking"]
            XCTAssertTrue(checking.waitForExistence(timeout: 5))
            XCTAssertTrue(checking.isHittable)
            capture("consumer-entry-account-types")
            let cancel = app.buttons["accounts.cancel"]
            XCTAssertTrue(cancel.waitForExistence(timeout: 5))
            XCTAssertTrue(cancel.isHittable)
            cancel.tap()
            XCTAssertTrue(checking.waitForNonExistence(timeout: 5))
            trace("after-cancel")
        }
    }
}
