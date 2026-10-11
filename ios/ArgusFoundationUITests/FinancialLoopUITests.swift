import XCTest
import UIKit
import UniformTypeIdentifiers

final class FinancialLoopUITests: XCTestCase {
    let app = XCUIApplication()

    func testAccountEntryOpensAfterScrollingHeaderOffscreen() throws {
        try signIn()
        openPersonalAccounts()
        let add = app.buttons["accounts.add"]
        for _ in 0..<5 {
            if add.frame.minY < 0 { break }
            app.scrollViews["screen.home"].swipeUp()
        }
        XCTAssertLessThan(add.frame.minY, app.frame.minY)
        capture("account-entry-header-offscreen")
        tapVisible(add)
        XCTAssertTrue(app.buttons["accounts.type.checking"].waitForExistence(timeout: 5))
        capture("account-entry-after-scroll")
        tapVisible(app.buttons["accounts.cancel"])
    }

    func testAccountEntryReopensAfterReturningFromDetails() throws {
        try signIn()
        openPersonalAccounts()
        let row = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH 'accounts.row.'")).firstMatch
        guard row.waitForExistence(timeout: 10) else {
            throw XCTSkip("Requires an existing synthetic account to revisit its details.")
        }
        for _ in 0..<3 {
            tapVisible(app.buttons["accounts.add"])
            XCTAssertTrue(app.buttons["accounts.type.checking"].waitForExistence(timeout: 5))
            let cancel = app.buttons["accounts.cancel"]
            tapVisible(cancel)
            XCTAssertTrue(cancel.waitForNonExistence(timeout: 5))
            tapVisible(row)
            XCTAssertTrue(app.buttons["accounts.record"].waitForExistence(timeout: 5))
            openPersonalAccounts()
        }
    }

    func testArchiveManagementRestoresSameAccount() throws {
        try signIn(fresh: true)
        let baseline = homeValue()
        app.openAccountsList()
        tapVisible(app.buttons["accounts.add"])
        app.buttons["accounts.type.checking"].tap()
        let nickname = "Archive review " + UUID().uuidString.prefix(6)
        app.textFields["accounts.nickname"].tap(); app.textFields["accounts.nickname"].typeText(nickname)
        app.textFields["accounts.amount"].tap(); app.textFields["accounts.amount"].typeText("125")
        app.dismissKeyboard(); app.buttons["accounts.save"].tap()
        assertText("DOP 125.00")
        tapVisible(app.accountBack)
        let original = app.buttons.matching(NSPredicate(format: "label CONTAINS %@", nickname)).firstMatch
        XCTAssertTrue(original.waitForExistence(timeout: 10))
        let originalID = original.identifier
        tapVisible(original)
        tapVisible(app.buttons["accounts.archive"])
        if !app.confirmAccountArchive() {
            for _ in 0..<5 { if app.accountBack.isHittable { break }; app.swipeDown() }
            app.accountBack.tap()
        }
        XCTAssertTrue(app.buttons[originalID].waitForNonExistence(timeout: 10))
        capture("archive-active-list")
        assertHome(baseline + 125)
        app.openAccountsList()
        for _ in 0..<5 { if app.buttons["accounts.manage"].isHittable { break }; app.swipeDown() }
        app.buttons["accounts.manage"].tap()
        let archived = app.buttons[originalID]
        XCTAssertTrue(archived.waitForExistence(timeout: 10))
        for _ in 0..<5 { if archived.isHittable { break }; app.swipeUp() }
        capture("archive-management")
        archived.tap()
        assertText("DOP 125.00")
        tapVisible(app.buttons["accounts.archive"])
        XCTAssertTrue(app.buttons["Archive account"].waitForExistence(timeout: 10)
            || app.buttons["accounts.archive"].waitForExistence(timeout: 2))
        for _ in 0..<5 { if app.accountBack.isHittable { break }; app.swipeDown() }
        if app.accountBack.waitForExistence(timeout: 3) {
            app.accountBack.tap()
        }
        // Connected may already show the restored row on Home after detail pop; tip still needs manage.back.
        if !app.buttons[originalID].waitForExistence(timeout: 3) {
            let manageBack = app.buttons["accounts.manage.back"]
            if manageBack.waitForExistence(timeout: 2), manageBack.isHittable {
                manageBack.tap()
            } else {
                app.openAccountsList()
            }
            XCTAssertTrue(app.buttons[originalID].waitForExistence(timeout: 10))
        }
        assertHome(baseline + 125)
    }

    func testAccountEntryKeepsUnknownAndSignedBalances() throws {
        try signIn()
        app.openAccountsList()
        XCTAssertTrue(app.buttons["accounts.add"].waitForExistence(timeout: 10))
        app.buttons["accounts.add"].tap()
        XCTAssertTrue(app.buttons["accounts.type.checking"].waitForExistence(timeout: 5))
        capture("account-entry-types")
        app.buttons["accounts.type.checking"].tap()
        XCTAssertTrue(app.buttons["accounts.type.change"].exists)
        XCTAssertFalse(app.textFields["accounts.share"].exists)
        XCTAssertFalse(app.datePickers["accounts.date"].exists)
        let nickname = "Unknown account " + UUID().uuidString.prefix(6)
        app.textFields["accounts.nickname"].tap()
        app.textFields["accounts.nickname"].typeText(nickname)
        app.buttons["accounts.save"].tap()
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "Balance unknown")).firstMatch.waitForExistence(timeout: 10))
        capture("unknown-balance")
        record(amount: "10", note: "Spending before a known balance")
        assertText("Balance unknown")
        tapVisible(app.buttons["accounts.opening"])
        let amount = app.textFields["accounts.amount"]
        XCTAssertTrue(amount.waitForExistence(timeout: 5))
        amount.tap(); amount.typeText("25.50")
        app.buttons["accounts.amount.sign"].tap()
        XCTAssertEqual(amount.value as? String, "-25.50")
        app.dismissKeyboard()
        capture("signed-balance-entry")
        app.buttons["accounts.save"].tap()
        XCTAssertTrue(app.buttons["opening.coverage.yes"].waitForExistence(timeout: 10))
        capture("unknown-to-known-coverage")
        tapVisible(app.buttons["opening.coverage.yes"])
        XCTAssertTrue(app.buttons["loop.edit"].waitForExistence(timeout: 10))
        app.buttons["accounts.save"].tap()
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "DOP -25.50")).firstMatch.waitForExistence(timeout: 10))
        app.terminate(); app.launch()
        app.openAccountsList()
        tapVisible(app.buttons.matching(NSPredicate(format: "label CONTAINS %@", nickname)).firstMatch)
        XCTAssertTrue(app.staticTexts.matching(NSPredicate(format: "label CONTAINS %@", "DOP -25.50")).firstMatch.waitForExistence(timeout: 10))
        capture("account-preserved-after-reopen")
    }

    func testCompleteFinancialLoop() throws {
        try signIn()
        let baseline = homeValue()
        app.openAccountsList()
        if app.accountBack.exists { app.accountBack.tap() }
        tapVisible(app.buttons["accounts.add"])
        app.buttons["accounts.type.checking"].tap()
        let nickname = "Daily loop " + UUID().uuidString.prefix(6)
        app.textFields["accounts.nickname"].tap(); app.textFields["accounts.nickname"].typeText(nickname)
        app.textFields["accounts.amount"].tap(); app.textFields["accounts.amount"].typeText("10000")
        app.dismissKeyboard(); app.buttons["accounts.save"].tap()
        assertText("DOP 10,000.00")
        record(amount: "2000", note: "Loop groceries")
        assertText("DOP 8,000.00")
        capture("expense-updated-account")
        assertHome(baseline + 8000)
        XCUIDevice.shared.press(.home); app.activate()
        assertHome(baseline + 8000)
        assertText("Loop groceries")
        capture("connected-home-after-expense")
        // Activity-row ids live on account detail; Home recent activity opens the account only.
        app.openAccountsList()
        tapVisible(app.buttons.matching(NSPredicate(format: "label CONTAINS %@", nickname)).firstMatch)
        let row = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@", "activity.row.")).firstMatch
        tapVisible(row)
        app.buttons["activity.correct"].tap()
        XCTAssertTrue(app.textFields["loop.amount"].waitForExistence(timeout: 5))
        let amount = app.textFields["loop.amount"]
        amount.tap(); amount.press(forDuration: 1.2)
        if app.menuItems["Select All"].waitForExistence(timeout: 1) { app.menuItems["Select All"].tap() }
        else { amount.tap(withNumberOfTaps: 3, numberOfTouches: 1) }
        amount.typeText("2500")
        let reason = app.textFields["loop.reason"]
        reason.tap(); reason.typeText("Receipt correction")
        app.dismissKeyboard()
        reviewAndConfirm()
        assertText("DOP 7,500.00")
        tapVisible(app.buttons["accounts.check"])
        app.textFields["loop.amount"].tap(); app.textFields["loop.amount"].typeText("7000")
        app.dismissKeyboard(); app.buttons["loop.review"].tap()
        XCTAssertTrue(app.buttons["loop.confirm"].waitForExistence(timeout: 10))
        capture("checked-balance-review")
        app.buttons["loop.confirm"].tap()
        assertText("DOP 7,000.00")
        // Residuals only credit activity newly covered since the prior observation.
        // Include in the check, not the opening — same shape as PersonalMoneyUITests.
        record(amount: "500", note: "Already in checked balance", coverageAnswers: [false, true])
        ensureAccountDetail(nickname: nickname)
        assertAccountBalance("DOP 7,000.00")
        assertText("Still unexplained DOP 0.00")
        assertText("Difference DOP -500.00")
        assertHome(baseline + 7000)
        app.openAccountsList()
        capture("late-expense-not-double-counted")
        app.terminate(); app.launch(); app.openAccountsList()
        let account = app.buttons.matching(NSPredicate(format: "label CONTAINS %@", nickname)).firstMatch
        tapVisible(account)
        assertAccountBalance("DOP 7,000.00")
        assertText("Already in checked balance")
        capture("financial-loop-preserved-after-reopen")
    }

    func testSpanishConnectedCheckReview() throws {
        guard ProcessInfo.processInfo.environment["ARGUS_TEST_EMAIL"] != nil else { throw XCTSkip("Requires isolated financial stack.") }
        try signIn()
        app.terminate()
        app.launchArguments = ["-AppleLanguages", "(es-419)", "-AppleLocale", "es_DO", "-appearancePreference", "dark"]
        app.launch()
        XCTAssertTrue(app.staticTexts["home.netWorth.DOP"].waitForExistence(timeout: 15))
        capture("connected-home-spanish")
        app.openAccountsList()
        let account = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@", "accounts.row.")).firstMatch
        tapVisible(account)
        tapVisible(app.buttons["accounts.check"])
        app.textFields["loop.amount"].tap(); app.textFields["loop.amount"].typeText("50")
        app.dismissKeyboard()
        app.buttons["loop.review"].tap()
        XCTAssertTrue(app.buttons["loop.confirm"].waitForExistence(timeout: 10))
        XCTAssertFalse(app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH %@", "loop.")).firstMatch.exists)
        capture("checked-balance-review-spanish")
        app.buttons["Cancelar"].tap()
    }

    func record(amount: String, note: String, coverageAnswers: [Bool] = []) {
        tapVisible(app.buttons["accounts.record"])
        XCTAssertTrue(app.textFields["loop.amount"].waitForExistence(timeout: 5))
        app.textFields["loop.amount"].tap(); app.textFields["loop.amount"].typeText(amount)
        app.textFields["loop.note"].tap(); app.textFields["loop.note"].typeText(note)
        app.dismissKeyboard()
        reviewAndConfirm(coverageAnswers: coverageAnswers)
    }

    func reviewAndConfirm(coverageAnswers: [Bool] = []) {
        tapVisible(app.buttons["loop.review"])
        // Activity editor: loop.coverage.{yes|no}.<accountId>.<observationId>
        // Balance/opening editor: loop.coverage.{yes|no}.<kind>.<observationId>
        // Observations appear in order (opening then check). Use the .no. row as the
        // stable probe, then tap yes/no from coverageAnswers — all-no when empty.
        var answered = Set<String>()
        var answerIndex = 0
        for _ in 0..<8 {
            if app.buttons["loop.confirm"].waitForExistence(timeout: 2) { break }
            let matches = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@", "loop.coverage.no."))
            var tapped = false
            for index in 0..<matches.count {
                let probe = matches.element(boundBy: index)
                let probeId = probe.identifier
                guard !probeId.isEmpty, !answered.contains(probeId), probe.exists else { continue }
                let include = answerIndex < coverageAnswers.count && coverageAnswers[answerIndex]
                answerIndex += 1
                let targetId = include
                    ? probeId.replacingOccurrences(of: ".no.", with: ".yes.")
                    : probeId
                tapVisible(app.buttons[targetId])
                answered.insert(probeId)
                tapped = true
                _ = app.buttons["loop.confirm"].waitForExistence(timeout: 4)
                break
            }
            if tapped { continue }
            let opening = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@", "loop.coverage.no.opening.")).firstMatch
            if opening.waitForExistence(timeout: 1), !answered.contains(opening.identifier) {
                let include = answerIndex < coverageAnswers.count && coverageAnswers[answerIndex]
                answerIndex += 1
                let targetId = include
                    ? opening.identifier.replacingOccurrences(of: ".no.", with: ".yes.")
                    : opening.identifier
                tapVisible(app.buttons[targetId])
                answered.insert(opening.identifier)
            }
        }
        XCTAssertTrue(app.buttons["loop.confirm"].waitForExistence(timeout: 10))
        capture("expense-review")
        tapVisible(app.buttons["loop.confirm"])
        // accounts.record can exist under the sheet; require confirm gone + record hittable.
        let dismissed = NSPredicate { [app] _, _ in
            !app.buttons["loop.confirm"].exists
                && app.buttons["accounts.record"].exists
                && app.buttons["accounts.record"].isHittable
        }
        XCTAssertEqual(
            XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: dismissed, object: nil)], timeout: 15),
            .completed
        )
    }

    func assertHome(_ expected: Decimal) {
        openPersonalAccounts()
        app.openHomeSurface()
        XCTAssertTrue(selectHomeMoneyCurrency("DOP"))
        let value = app.staticTexts["home.netWorth.DOP"]
        let predicate = NSPredicate { _, _ in
            guard value.exists else { return false }
            let exact = value.label.replacingOccurrences(of: "DOP", with: "").replacingOccurrences(of: ",", with: "").trimmingCharacters(in: .whitespaces)
            return Decimal(string: exact, locale: Locale(identifier: "en_US_POSIX")) == expected
        }
        XCTAssertEqual(XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: predicate, object: nil)], timeout: 12), .completed)
    }

    func homeValue() -> Decimal {
        openPersonalAccounts()
        app.openHomeSurface()
        _ = selectHomeMoneyCurrency("DOP")
        let value = app.staticTexts["home.netWorth.DOP"]
        // A new identity has no DOP account yet: its recorded DOP net worth is zero, not a failure.
        if !value.waitForExistence(timeout: 10) {
            XCTAssertTrue(app.buttons["accounts.add"].waitForExistence(timeout: 5), "Home must show a net worth or the add-account entry")
            return 0
        }
        let exact = value.label.replacingOccurrences(of: "DOP", with: "").replacingOccurrences(of: ",", with: "").trimmingCharacters(in: .whitespaces)
        guard let parsed = Decimal(string: exact, locale: Locale(identifier: "en_US_POSIX")) else { XCTFail("Home must expose a numeric amount"); return 0 }
        return parsed
    }

    func ensureAccountDetail(nickname: String) {
        let detail = app.descendants(matching: .any)["screen.accounts"]
        let balance = app.descendants(matching: .any)["accounts.balance.DOP"]
        if detail.waitForExistence(timeout: 2), balance.waitForExistence(timeout: 2) { return }
        app.openAccountsList()
        tapVisible(app.buttons.matching(NSPredicate(format: "label CONTAINS %@", nickname)).firstMatch)
        XCTAssertTrue(app.descendants(matching: .any)["screen.accounts"].waitForExistence(timeout: 10))
    }

    func assertAccountBalance(_ value: String) {
        let balance = app.descendants(matching: .any)["accounts.balance.DOP"]
        XCTAssertTrue(balance.waitForExistence(timeout: 12), "accounts.balance.DOP missing")
        let predicate = NSPredicate { _, _ in balance.exists && balance.label.contains(value) }
        XCTAssertEqual(
            XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: predicate, object: nil)], timeout: 8),
            .completed,
            "balance label \(balance.label) missing \(value)"
        )
    }

    func assertText(_ value: String) {
        let predicate = NSPredicate(format: "label CONTAINS %@", value)
        // Connected keeps inactive tabs in the tree (opacity 0). Prefer the
        // visible account/home surfaces so Search ghosts with bad frames lose.
        for screenID in ["screen.accounts", "screen.home"] {
            let screen = app.descendants(matching: .any)[screenID]
            guard screen.exists else { continue }
            if screen.staticTexts.matching(predicate).firstMatch.waitForExistence(timeout: 4) { return }
            if screen.descendants(matching: .any).matching(predicate).firstMatch.waitForExistence(timeout: 2) { return }
        }
        let staticText = app.staticTexts.matching(predicate).firstMatch
        if staticText.waitForExistence(timeout: 4) { return }
        XCTAssertTrue(app.descendants(matching: .any).matching(predicate).firstMatch.waitForExistence(timeout: 4))
    }
    func tapVisible(_ element: XCUIElement) {
        XCTAssertTrue(element.waitForExistence(timeout: 10))
        let reference = element.identifier.isEmpty ? element.label : element.identifier
        let toolbarControl = app.navigationBars.descendants(matching: element.elementType)
            .matching(identifier: reference).firstMatch
        if toolbarControl.exists && toolbarControl.frame == element.frame && element.isHittable {
            element.tap()
            return
        }
        let scrollView = app.scrollViews.containing(element.elementType, identifier: reference).firstMatch
        if !scrollView.exists {
            guard element.isHittable && app.frame.contains(element.frame) else {
                XCTFail("The fixed control is not visible: " + reference)
                return
            }
            element.tap()
            return
        }
        let topBars = app.navigationBars.allElementsBoundByIndex + app.statusBars.allElementsBoundByIndex
        let top = topBars.filter { $0.isHittable && $0.frame.intersects(scrollView.frame) }
            .reduce(max(app.frame.minY, scrollView.frame.minY)) { max($0, $1.frame.maxY) }
        let lowerControls = app.buttons.allElementsBoundByIndex
            + app.toolbars.allElementsBoundByIndex + app.tabBars.allElementsBoundByIndex
            + app.keyboards.allElementsBoundByIndex
        let bottom = lowerControls.reduce(min(app.frame.maxY, scrollView.frame.maxY)) { edge, control in
            let frame = control.frame
            guard frame.intersects(scrollView.frame), frame.intersects(app.frame),
                  control.elementType == .keyboard || frame.minY >= scrollView.frame.midY else { return edge }
            let controlReference = control.identifier.isEmpty ? control.label : control.identifier
            let inScroll = scrollView.descendants(matching: control.elementType)
                .matching(identifier: controlReference).allElementsBoundByIndex
                .contains { $0.frame == frame }
            guard !inScroll && control.isHittable else { return edge }
            return min(edge, frame.minY)
        }
        var scrolled = false
        for _ in 0..<12 {
            let frame = element.frame
            if element.isHittable && frame.minY >= top && frame.maxY <= bottom { break }
            let distance: CGFloat
            if frame.minY < top { distance = top - frame.minY + 24 }
            else if frame.maxY > bottom { distance = bottom - frame.maxY - 24 }
            else { distance = (top + bottom) / 2 - frame.midY }
            let limit = max(0, (bottom - top) / 2)
            guard limit > 0 else { break }
            let movement = max(-limit, min(limit, distance))
            let startY = top + (bottom - top) * (movement < 0 ? 0.75 : 0.25)
            let start = app.coordinate(withNormalizedOffset: .zero)
                .withOffset(CGVector(dx: app.frame.width / 2, dy: startY - app.frame.minY))
            start.press(forDuration: 0.01, thenDragTo: start.withOffset(CGVector(dx: 0, dy: movement)),
                        withVelocity: .slow, thenHoldForDuration: 0.2)
            scrolled = true
        }
        if scrolled {
            var previous = element.frame
            var lastMovement = Date()
            let settled = NSPredicate { _, _ in
                let frame = element.frame
                if frame != previous { previous = frame; lastMovement = Date() }
                return Date().timeIntervalSince(lastMovement) > 0.5
            }
            guard XCTWaiter.wait(for: [XCTNSPredicateExpectation(predicate: settled, object: nil)], timeout: 5) == .completed else {
                XCTFail("The control did not stop moving: " + reference)
                return
            }
        }
        guard element.isHittable && element.frame.minY >= top && element.frame.maxY <= bottom else {
            XCTFail("The control could not reach the visible scroll area: " + reference)
            return
        }
        element.tap()
    }
    func signIn(fresh: Bool = false, user: String = "A") throws {
        let environment = ProcessInfo.processInfo.environment
        let suffix = try XCTUnwrap(["A": "", "B": "_B", "C": "_C"][user],
                                   "Unknown synthetic identity")
        guard let email = environment["ARGUS_TEST_EMAIL" + suffix], let password = environment["ARGUS_TEST_PASSWORD" + suffix] else {
            throw XCTSkip("Requires isolated synthetic API and registered identity.")
        }
        continueAfterFailure = false
        app.launchArguments = ["-AppleLanguages", "(en)", "-AppleLocale", "en_US", "-appearancePreference", "dark"]
        app.launch()
        if app.buttons["budget.close"].waitForExistence(timeout: 2) {
            app.buttons["budget.close"].tap()
            XCTAssertTrue(app.descendants(matching: .any)["budget.detail"].waitForNonExistence(timeout: 10))
        }
        if app.buttons["goal.close"].waitForExistence(timeout: 2) {
            app.buttons["goal.close"].tap()
            XCTAssertTrue(app.descendants(matching: .any)["goal.detail"].waitForNonExistence(timeout: 10))
        }
        if app.buttons["debt.close"].waitForExistence(timeout: 2) {
            app.buttons["debt.close"].tap()
            XCTAssertTrue(app.descendants(matching: .any)["debt.detail"].waitForNonExistence(timeout: 10))
        }
        app.revealConnectedTabBar()
        let connected = app.usesConnectedChrome
            || app.buttons["cuadrao.welcome.signin"].waitForExistence(timeout: 2)
        if connected {
            if app.buttons["header.profile"].waitForExistence(timeout: 2) {
                app.buttons["header.profile"].tap()
                if fresh, app.buttons["auth.signOut"].waitForExistence(timeout: 3) {
                    tapVisible(app.buttons["auth.signOut"])
                    app.confirmSignOutIfAsked()
                    XCTAssertTrue(app.buttons["cuadrao.welcome.signin"].waitForExistence(timeout: 20))
                }
            }
            if !app.buttons["auth.signOut"].waitForExistence(timeout: 2) {
                app.openSignedOutAuthEntry()
                let emailField = app.textFields["auth.email"]
                XCTAssertTrue(emailField.waitForExistence(timeout: 10))
                emailField.tap(); emailField.typeText(email)
                let passwordField = app.secureTextFields["auth.password"]
                passwordField.tap()
                UIPasteboard.general.setItems([[UTType.utf8PlainText.identifier: password]],
                                             options: [.localOnly: true, .expirationDate: Date().addingTimeInterval(60)])
                passwordField.press(forDuration: 1.2)
                let paste = app.menuItems["Paste"]
                if paste.waitForExistence(timeout: 3) { paste.tap() }
                else { app.buttons["Paste"].tap() }
                let permission = app.alerts.buttons["Allow Paste"]
                if permission.waitForExistence(timeout: 1) { permission.tap() }
                UIPasteboard.general.items = []
                app.buttons["auth.submit"].tap()
                XCTAssertTrue(app.buttons["header.profile"].waitForExistence(timeout: 30))
                app.buttons["header.profile"].tap()
                XCTAssertTrue(app.buttons["auth.signOut"].waitForExistence(timeout: 10))
            }
            app.revealConnectedTabBar()
            XCTAssertTrue(app.buttons["tab.home"].waitForExistence(timeout: 10))
            app.buttons["tab.home"].tap()
            return
        }
        app.buttons["header.profile"].tap()
        if !app.buttons["auth.signOut"].waitForExistence(timeout: 3), !app.textFields["auth.email"].exists {
            app.buttons["header.profile"].tap()
        }
        if fresh, app.buttons["auth.signOut"].waitForExistence(timeout: 2) { app.buttons["auth.signOut"].tap() }
        if !app.buttons["auth.signOut"].waitForExistence(timeout: 5) {
            let emailField = app.textFields["auth.email"]
            XCTAssertTrue(emailField.waitForExistence(timeout: 10))
            emailField.tap(); emailField.typeText(email)
            let passwordField = app.secureTextFields["auth.password"]
            passwordField.tap()
            UIPasteboard.general.setItems([[UTType.utf8PlainText.identifier: password]],
                                         options: [.localOnly: true, .expirationDate: Date().addingTimeInterval(60)])
            passwordField.press(forDuration: 1.2)
            let paste = app.menuItems["Paste"]
            if paste.waitForExistence(timeout: 3) { paste.tap() }
            else { app.buttons["Paste"].tap() }
            let permission = app.alerts.buttons["Allow Paste"]
            if permission.waitForExistence(timeout: 1) { permission.tap() }
            UIPasteboard.general.items = []
            app.buttons["auth.submit"].tap()
            XCTAssertTrue(app.buttons["auth.signOut"].waitForExistence(timeout: 30))
        }
        if app.buttons["sheet.close"].waitForExistence(timeout: 2) {
            app.buttons["sheet.close"].tap()
        } else if app.buttons["tab.home"].exists {
            // Connected profile is a tab destination, not a dismissible tip sheet.
            app.buttons["tab.home"].tap()
        }
    }

    func capture(_ name: String) {
        let screenshot = app.screenshot()
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent("argus-personal-money", isDirectory: true)
        do {
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            try screenshot.pngRepresentation.write(to: directory.appendingPathComponent(name + ".png"))
        } catch { XCTFail("Could not retain screenshot evidence") }
        let attachment = XCTAttachment(screenshot: screenshot)
        attachment.name = name; attachment.lifetime = .keepAlways
        add(attachment)
    }
}
