import Foundation
import XCTest
import ArgusSession
@testable import FinancialModels

/// Founder walk steps 10 to 12: the kind drafts own every rule, so the editor's hint and the save check never disagree.
@MainActor
final class PlanReadinessTests: XCTestCase {
    private let locale = Locale(identifier: "es_DO")
    private let bank = UUID(), cash = UUID(), card = UUID()

    func testBudgetStepTenNamesEachMissingChoiceThenIsReady() {
        var plan = CanvasPlan(name: "", kind: .budget)
        var details = ConnectedPlanDetails()
        let draft = FinancialBudgetDraft(month: "2026-10", currency: "DOP")
        func missing() -> ConnectedPlanMissing? {
            ConnectedPlanMapping.apply(plan, details, to: draft, digits: 2, locale: locale); return draft.missing
        }
        XCTAssertEqual(missing(), .name)
        plan.name = String(repeating: "c", count: 101)
        XCTAssertEqual(missing(), .nameTooLong)
        plan.name = "Comida"
        XCTAssertEqual(missing(), .amount)
        plan.target = 5000
        XCTAssertEqual(missing(), .accounts)
        details.accountIDs = [bank, cash, card]
        XCTAssertEqual(missing(), .categories)
        details.categoryIDs = ["groceries"]
        XCTAssertNil(missing())
        XCTAssertTrue(draft.ready)
    }

    func testGoalStepElevenNeedsNoAccountsWithoutAMonthlyAmount() {
        var plan = CanvasPlan(name: "Viaje", kind: .goal)
        var details = ConnectedPlanDetails()
        let draft = FinancialGoalDraft(start: "2026-10-13", currency: "DOP")
        func missing() -> ConnectedPlanMissing? {
            ConnectedPlanMapping.apply(plan, details, to: draft, digits: 2, locale: locale); return draft.missing
        }
        XCTAssertEqual(missing(), .amount)
        plan.target = 20000
        XCTAssertNil(missing())
        plan.monthly = 1000
        XCTAssertEqual(missing(), .destination)
        details.destinationID = bank
        XCTAssertEqual(missing(), .source)
        details.sourceID = bank
        XCTAssertEqual(missing(), .sameAccount)
        details.sourceID = cash
        XCTAssertNil(missing())
        XCTAssertTrue(draft.ready)
    }

    func testDebtEstimateNamesRateAndFees() throws {
        let draft = FinancialDebtDraft(account: try account(card, type: "credit_card"), start: "2026-10-13")
        XCTAssertEqual(draft.missing, .monthly)
        draft.amount = "1,000.00"
        XCTAssertEqual(draft.missing, .source)
        draft.sourceID = bank
        XCTAssertNil(draft.missing)
        draft.estimate = true
        XCTAssertEqual(draft.missing, .rate)
        draft.rate = "18.5"
        XCTAssertEqual(draft.missing, .fees)
        draft.fees = "0"
        XCTAssertNil(draft.missing)
        XCTAssertTrue(draft.ready)
    }

    func testEveryReasonHasSpanishAndEnglishText() {
        let all: [ConnectedPlanMissing] = [.name, .nameTooLong, .amount, .monthly, .debtAccount, .accounts, .categories, .destination,
                                           .source, .sameAccount, .rate, .fees, .loading, .planUnavailable]
        for reason in all {
            XCTAssertNotEqual(reason.hint(spanish: true), reason.hint(spanish: false))
            XCTAssertFalse(reason.hint(spanish: true).contains("—"))
        }
    }

    private func account(_ id: UUID, type: String) throws -> FinancialAccount {
        let body: [String: Any] = ["id": id.uuidString, "type": type, "nature": "liability", "currency": "DOP", "currency_fraction_digits": 2,
            "nickname": "BoFa", "archived": false, "ownership_share_bps": 10000, "version": 1, "created_at": "2026-10-13T12:00:00Z",
            "updated_at": "2026-10-13T12:00:00Z", "opening": NSNull(),
            "balance": ["state": "unknown", "activity_since_tracking_minor": 0], "asset": NSNull()]
        return try JSONDecoder().decode(FinancialAccount.self, from: JSONSerialization.data(withJSONObject: body))
    }
}
