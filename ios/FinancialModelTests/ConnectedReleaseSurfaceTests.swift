import Foundation
import XCTest
import ArgusSession
@testable import FinancialModels

final class ConnectedReleaseSurfaceTests: XCTestCase {
    func testReleaseBarIsHomePlanAddSearchProfileAndAddIsNotATab() {
        let slots = CuadraoNavigationSlot.slots(hasAssistant: false)
        XCTAssertEqual(slots, [.tab(.home), .tab(.plan), .add, .tab(.search), .tab(.profile)])
        XCTAssertFalse(slots.contains(.tab(.assistant)), "the assistant is unreachable without an assistant")
    }

    func testAddSitsInTheMiddleSlot() {
        XCTAssertEqual(CuadraoNavigationSlot.slots(hasAssistant: false).firstIndex(of: .add), 2)
    }

    func testAssistantBuildsKeepTheAssistantTabAndHaveNoAdd() {
        let slots = CuadraoNavigationSlot.slots(hasAssistant: true)
        XCTAssertEqual(slots, CuadraoTab.allCases.map { .tab($0) })
        XCTAssertFalse(slots.contains(.add))
    }

    func testSlidingMapsAFingerToTheSlotUnderIt() {
        XCTAssertEqual(CuadraoNavigationSlot.index(forX: 0, width: 300, count: 5), 0)
        XCTAssertEqual(CuadraoNavigationSlot.index(forX: 119, width: 300, count: 5), 1)
        XCTAssertEqual(CuadraoNavigationSlot.index(forX: 150, width: 300, count: 5), 2)
        XCTAssertEqual(CuadraoNavigationSlot.index(forX: 299, width: 300, count: 5), 4)
        XCTAssertEqual(CuadraoNavigationSlot.index(forX: -20, width: 300, count: 5), 0)
        XCTAssertEqual(CuadraoNavigationSlot.index(forX: 900, width: 300, count: 5), 4)
        XCTAssertEqual(CuadraoNavigationSlot.index(forX: 10, width: 0, count: 5), 0)
    }

    func testTheTrayOffersOnlyWhatIsRealInThisBuild() {
        XCTAssertEqual(
            CuadraoAddAction.available(receiptsConnected: false, householdsAvailable: false, inHousehold: false),
            [.account, .transaction, .plan]
        )
        XCTAssertEqual(
            CuadraoAddAction.available(receiptsConnected: false, householdsAvailable: true, inHousehold: false),
            [.account, .transaction, .plan, .group]
        )
        XCTAssertEqual(
            CuadraoAddAction.available(receiptsConnected: true, householdsAvailable: true, inHousehold: true),
            [.account, .transaction, .plan, .group, .invite, .scanCamera, .choosePhoto, .chooseFile]
        )
    }

    func testAddWithNoAccountStartsTheFirstAccount() throws {
        guard case .createAccount = ConnectedAddMovement.target(for: [], loaded: true) else { return XCTFail("expected createAccount") }
    }

    func testAddWithOneAccountOpensItsEditor() throws {
        let only = try account()
        guard case .record(let chosen) = ConnectedAddMovement.target(for: [only], loaded: true) else { return XCTFail("expected record") }
        XCTAssertEqual(chosen.id, only.id)
    }

    func testAddWithSeveralAccountsOfOneCurrencyOpensTheFirstMoneyAccountInTheirOrder() throws {
        let first = try account(), second = try account()
        guard case .record(let chosen) = ConnectedAddMovement.target(for: [first, second], loaded: true) else { return XCTFail("expected record") }
        XCTAssertEqual(chosen.id, first.id)
    }

    func testAddWithAccountsInMoreThanOneCurrencyOpensThePrimaryCurrencyAccountWithoutAsking() throws {
        let dop = try account(), usd = try account(currency: "USD")
        guard case .record(let chosen) = ConnectedAddMovement.target(for: [dop, usd], loaded: true, preferredCurrency: "USD") else { return XCTFail("expected record") }
        XCTAssertEqual(chosen.id, usd.id, "the person's primary currency decides, not the list order")
        guard case .record(let lowercase) = ConnectedAddMovement.target(for: [dop, usd], loaded: true, preferredCurrency: "usd") else { return XCTFail("expected record") }
        XCTAssertEqual(lowercase.id, usd.id, "the currency code is compared without case")
    }

    func testAddFallsBackToTheFirstMoneyAccountWhenThePrimaryCurrencyHasNoneOrIsUnknown() throws {
        let dop = try account(), usd = try account(currency: "USD")
        guard case .record(let none) = ConnectedAddMovement.target(for: [dop, usd], loaded: true, preferredCurrency: "EUR") else { return XCTFail("expected record") }
        XCTAssertEqual(none.id, dop.id)
        guard case .record(let unknown) = ConnectedAddMovement.target(for: [dop, usd], loaded: true) else { return XCTFail("expected record") }
        XCTAssertEqual(unknown.id, dop.id)
        let card = try account(currency: "USD", nature: "liability", type: "credit_card")
        guard case .record(let money) = ConnectedAddMovement.target(for: [card, dop], loaded: true, preferredCurrency: "USD") else { return XCTFail("expected record") }
        XCTAssertEqual(money.id, dop.id, "a card in the primary currency is not a starting account while a money account exists")
    }

    func testAMoneyAccountIsPreferredOverALiabilityAsTheStartingAccount() throws {
        let card = try account(nature: "liability", type: "credit_card"), cash = try account()
        guard case .record(let chosen) = ConnectedAddMovement.target(for: [card, cash], loaded: true) else { return XCTFail("expected record") }
        XCTAssertEqual(chosen.id, cash.id)
    }

    func testAddBeforeAccountsHaveLoadedLoadsThemInsteadOfStartingAFirstAccount() throws {
        guard case .loadAccounts = ConnectedAddMovement.target(for: [], loaded: false) else { return XCTFail("expected loadAccounts") }
        guard case .loadAccounts = ConnectedAddMovement.target(for: [try account()], loaded: false) else { return XCTFail("expected loadAccounts") }
    }

    private func account(currency: String = "DOP", nature: String = "asset", type: String = "checking") throws -> FinancialAccount {
        let opening: [String: Any] = ["record_id": UUID().uuidString, "revision": 1, "kind": "opening", "amount_minor": 100,
            "observed_amount_minor": 100, "amount": "1.00", "as_of": "2026-10-06T08:00:00-04:00", "time_zone": "America/Santo_Domingo",
            "recorded_at": "2026-10-06T12:00:00Z", "source": "manual", "revisions": []]
        let body: [String: Any] = ["id": UUID().uuidString, "type": type, "nature": nature, "currency": currency,
            "currency_fraction_digits": 2, "nickname": NSNull(), "archived": false, "ownership_share_bps": 10000, "version": 1,
            "created_at": "2026-10-06T08:00:00-04:00", "updated_at": "2026-10-06T12:00:00Z", "opening": opening,
            "balance": ["state": "known", "amount_minor": 100, "amount": "1.00", "as_of": "2026-10-06T08:00:00-04:00",
                        "activity_since_tracking_minor": 0], "asset": NSNull()]
        return try JSONDecoder().decode(FinancialAccount.self, from: JSONSerialization.data(withJSONObject: body))
    }
}
