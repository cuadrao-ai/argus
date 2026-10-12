import XCTest
@testable import FinancialModels

final class GuestAccessPolicyTests: XCTestCase {
    func testTheBookNeverShowsWhileTheDoorIsClosedOrUnchosen() {
        for auth in [GuestAccessPolicy.AuthPhase.signedOut, .authenticated, .other] {
            for restored in [true, false] {
                XCTAssertEqual(GuestAccessPolicy.route(doorOpen: false, bookActive: true, restored: restored, auth: auth), .connected)
                XCTAssertEqual(GuestAccessPolicy.route(doorOpen: true, bookActive: false, restored: restored, auth: auth), .connected)
            }
        }
    }

    func testAnActiveBookWaitsForTheRestoreInsteadOfFlashingTheWelcome() {
        for auth in [GuestAccessPolicy.AuthPhase.signedOut, .authenticated, .other] {
            XCTAssertEqual(GuestAccessPolicy.route(doorOpen: true, bookActive: true, restored: false, auth: auth), .launching)
        }
    }

    func testOnlyASignedOutRestoredPersonIsRoutedIntoTheBook() {
        XCTAssertEqual(GuestAccessPolicy.route(doorOpen: true, bookActive: true, restored: true, auth: .signedOut), .guest)
        XCTAssertEqual(GuestAccessPolicy.route(doorOpen: true, bookActive: true, restored: true, auth: .authenticated), .connected,
                       "a signed-in person never lands in the book")
        XCTAssertEqual(GuestAccessPolicy.route(doorOpen: true, bookActive: true, restored: true, auth: .other), .connected)
    }

    func testTheBookHasNoAssistantSoTheThirdSlotIsAdd() {
        XCTAssertFalse(GuestAccessPolicy.hasAssistant)
        XCTAssertEqual(CuadraoNavigationSlot.slots(hasAssistant: GuestAccessPolicy.hasAssistant),
                       [.tab(.home), .tab(.plan), .add, .tab(.search), .tab(.profile)])
    }

    func testEverythingThatNeedsAServerIsRefused() {
        let refused: [GuestAccessPolicy.Capability] = [.assistant, .voiceCapture, .receipts, .files, .households, .invitations,
            .updates, .avatarPhoto, .sharing, .debts, .recurringBills, .forecast, .balanceChecks, .refunds]
        for capability in refused { XCTAssertFalse(GuestAccessPolicy.allows(capability), "\(capability)") }
        for capability in [GuestAccessPolicy.Capability.accounts, .movements, .plans, .search, .calculations, .appearance, .primaryCurrency, .deleteData] {
            XCTAssertTrue(GuestAccessPolicy.allows(capability), "\(capability)")
        }
        XCTAssertEqual(Set(refused).union([.accounts, .movements, .plans, .search, .calculations, .appearance, .primaryCurrency, .deleteData]).count,
                       GuestAccessPolicy.Capability.allCases.count, "every capability is decided")
    }

    func testTheTrayOffersOnlyBuiltRowsAndMovementsNeedAnAccount() {
        XCTAssertEqual(GuestAccessPolicy.addActions(activeAccounts: 0, built: [.accounts]), [.account])
        XCTAssertEqual(GuestAccessPolicy.addActions(activeAccounts: 0, built: [.accounts, .movements, .plans]), [.account], "movements and plans need an account")
        XCTAssertEqual(GuestAccessPolicy.addActions(activeAccounts: 2, built: [.accounts, .movements, .plans]), [.account, .transaction, .plan])
        XCTAssertTrue(GuestAccessPolicy.addActions(activeAccounts: 3, built: []).isEmpty)
        let offered = GuestAccessPolicy.addActions(activeAccounts: 5, built: [.accounts, .movements, .plans])
        XCTAssertTrue(offered.allSatisfy { !$0.isFileAction && $0 != .group && $0 != .invite }, "no receipts, group or invite row in the book")
    }
}
