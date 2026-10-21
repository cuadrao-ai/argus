import XCTest

/// Shared navigation for tip FoundationShell and Connected Cuadrao chrome.
extension XCUIApplication {
    var usesConnectedChrome: Bool {
        buttons["cuadrao.welcome.signin"].exists
            || buttons["cuadrao.welcome.signup"].exists
            || buttons["cuadrao.signin.emailChoice"].exists
            || buttons["cuadrao.signup.email"].exists
            // Signed-in Connected: tip Accounts tab is absent; profile is a tab, not a sheet.
            || (buttons["tab.home"].exists && buttons["header.profile"].exists && !buttons["tab.accounts"].exists)
    }

    /// Connected hides `CuadraoNavigationBar` while Home owns a pushed account detail.
    func revealConnectedTabBar() {
        for _ in 0..<6 {
            if buttons["tab.home"].exists && buttons["tab.home"].isHittable { return }
            let nativeBack = navigationBars.buttons.matching(identifier: "BackButton").firstMatch
            if nativeBack.waitForExistence(timeout: 1) {
                nativeBack.tap()
                continue
            }
            if buttons["accounts.back"].waitForExistence(timeout: 1) {
                buttons["accounts.back"].tap()
                continue
            }
            if buttons["activity.back"].waitForExistence(timeout: 1) {
                buttons["activity.back"].tap()
                continue
            }
            if buttons["household.back"].waitForExistence(timeout: 1) {
                buttons["household.back"].tap()
                continue
            }
            if buttons["accounts.manage.back"].waitForExistence(timeout: 1) {
                buttons["accounts.manage.back"].tap()
                continue
            }
            if buttons["sheet.close"].waitForExistence(timeout: 1) {
                buttons["sheet.close"].tap()
                continue
            }
            if buttons["nav.add"].exists && buttons["nav.add"].isHittable,
               let visibleScroll = scrollViews.allElementsBoundByIndex.first(where: { $0.isHittable }) {
                visibleScroll.swipeDown()
                continue
            }
            break
        }
    }

    func openHomeSurface() {
        let home = scrollViews["screen.home"]
        if home.exists && home.isHittable { return }
        revealConnectedTabBar()
        if home.exists && home.isHittable { return }
        let homeTab = buttons["tab.home"]
        guard homeTab.waitForExistence(timeout: 10), homeTab.isHittable else {
            XCTFail("Home tab must be visible before opening Home")
            return
        }
        homeTab.tap()
    }

    func openPlanSurface() {
        revealConnectedTabBar()
        XCTAssertTrue(buttons["tab.plan"].waitForExistence(timeout: 10))
        buttons["tab.plan"].tap()
    }

    var archivedUndo: XCUIElement { buttons["accounts.archived.undo"] }

    /// Archiving is reviewed first. Connected Home then returns to the list and offers Undo; the tip shell keeps the detail with Restore.
    @discardableResult
    func confirmAccountArchive(file: StaticString = #filePath, line: UInt = #line) -> Bool {
        let confirm = buttons["accounts.archive.confirm"]
        XCTAssertTrue(confirm.waitForExistence(timeout: 10), "archive asks for review before the write", file: file, line: line)
        confirm.tap()
        if archivedUndo.waitForExistence(timeout: 10) { return true }
        let spanish = ProcessInfo.processInfo.environment["ARGUS_TEST_LANGUAGE"] == "es-419"
        XCTAssertTrue(buttons[spanish ? "Restaurar cuenta" : "Restore account"].waitForExistence(timeout: 5), file: file, line: line)
        return false
    }

    var accountBack: XCUIElement {
        let native = navigationBars.buttons.matching(identifier: "BackButton").firstMatch
        return native.exists ? native : buttons["accounts.back"]
    }

    func returnFromDetail(_ legacyIdentifier: String) {
        let nativeBack = navigationBars.buttons.matching(identifier: "BackButton").firstMatch
        let back = nativeBack.waitForExistence(timeout: 2) ? nativeBack : buttons[legacyIdentifier]
        guard waitForHittableBack(back) else { return }
        back.tap()
    }

    private func waitForHittableBack(_ back: XCUIElement) -> Bool {
        let ready = XCTNSPredicateExpectation(
            predicate: NSPredicate { _, _ in back.exists && back.isHittable }, object: nil
        )
        guard XCTWaiter.wait(for: [ready], timeout: 10) == .completed else {
            XCTFail("Back must be hittable before leaving the detail")
            return false
        }
        return true
    }

    func swipeBack(cancel: Bool = false) {
        let back = navigationBars.buttons.matching(identifier: "BackButton").firstMatch
        guard waitForHittableBack(back) else { return }
        coordinate(withNormalizedOffset: CGVector(dx: 0.005, dy: 0.5)).press(
            forDuration: 0.05,
            thenDragTo: coordinate(withNormalizedOffset: CGVector(dx: cancel ? 0.15 : 0.9, dy: 0.5)),
            withVelocity: .slow,
            thenHoldForDuration: 0.4
        )
    }

    /// Accounts live on Home in Connected; tip keeps a dedicated Accounts tab.
    func openAccountsList() {
        if buttons["tab.accounts"].waitForExistence(timeout: 2) {
            revealConnectedTabBar()
            buttons["tab.accounts"].tap()
        } else {
            openHomeSurface()
        }
        if buttons["accounts.back"].waitForExistence(timeout: 1) {
            buttons["accounts.back"].tap()
        }
    }

    /// Signed-out Connected welcome → email form; tip uses header.profile sheet.
    func openSignedOutAuthEntry(createAccount: Bool = false) {
        if buttons["cuadrao.welcome.signin"].waitForExistence(timeout: 3)
            || buttons["cuadrao.welcome.signup"].exists {
            if createAccount {
                buttons["cuadrao.welcome.signup"].tap()
                XCTAssertTrue(buttons["cuadrao.signup.email"].waitForExistence(timeout: 10))
                buttons["cuadrao.signup.email"].tap()
            } else {
                buttons["cuadrao.welcome.signin"].tap()
                XCTAssertTrue(buttons["cuadrao.signin.emailChoice"].waitForExistence(timeout: 10))
                buttons["cuadrao.signin.emailChoice"].tap()
            }
            return
        }
        XCTAssertTrue(buttons["header.profile"].waitForExistence(timeout: 10))
        buttons["header.profile"].tap()
        if createAccount, buttons["auth.createAccount"].waitForExistence(timeout: 3) {
            buttons["auth.createAccount"].tap()
        }
    }

    /// Connected Profile asks before signing out; the tip account section signs out directly.
    func confirmSignOutIfAsked() {
        let alert = alerts.firstMatch
        guard alert.waitForExistence(timeout: 3) else { return }
        let confirm = alert.buttons.matching(identifier: "auth.signOut.confirm").firstMatch
        if confirm.exists { confirm.tap(); return }
        alert.buttons.matching(NSPredicate(format: "label IN %@", ["Sign out", "Cerrar sesión"])).firstMatch.tap()
    }

    func openProfileSurface() {
        if buttons["header.profile"].waitForExistence(timeout: 3) {
            buttons["header.profile"].tap()
            return
        }
        openSignedOutAuthEntry()
    }
}

extension FinancialLoopUITests {
    func openAccountsTab() {
        app.openAccountsList()
    }

    func openPersonalAccounts() {
        app.openAccountsList()
        let personal = app.buttons["household.personal"]
        if personal.waitForExistence(timeout: 2) { tapVisible(personal) }
        XCTAssertTrue(app.buttons["accounts.add"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.staticTexts["home-chart-loading"].firstMatch.waitForNonExistence(timeout: 45))
    }
}
