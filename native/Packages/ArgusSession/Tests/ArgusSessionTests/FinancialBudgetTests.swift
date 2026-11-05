import Foundation
import XCTest
@testable import ArgusSession

final class FinancialBudgetTests: XCTestCase {
    private func progress(spent: String, remaining: String, over: String) throws -> FinancialBudgetProgress {
        let id = UUID(), account = UUID()
        let raw = #"{"budget":{"id":"\#(id)","version":1,"name":"Groceries","limit_minor":15000,"limit":"150.00","currency":"DOP","currency_fraction_digits":2,"month":"2026-09","account_ids":["\#(account)"],"category_ids":["groceries"],"include_uncategorized":false,"archived":false},"period":{"month":"2026-09","time_zone":"America/Santo_Domingo","start_at":"2026-09-01T00:00:00-04:00","end_at_exclusive":"2026-10-01T00:00:00-04:00"},"gross_purchases_minor":"18000","refunds_minor":"2500","spent_minor":"\#(spent)","remaining_minor":"\#(remaining)","over_budget_minor":"\#(over)","contributors":[]}"#
        return try JSONDecoder().decode(FinancialBudgetProgress.self, from: Data(raw.utf8))
    }
    func testOverageAndNegativeNetDisplayWithoutRecomputingMoney() throws {
        let over = try progress(spent: "15500", remaining: "-500", over: "500")
        XCTAssertTrue(over.isOverBudget)
        XCTAssertEqual(over.remainingMinor, "-500")
        XCTAssertEqual(over.meterFraction, 1)
        let refund = try progress(spent: "-2500", remaining: "17500", over: "0")
        XCTAssertFalse(refund.isOverBudget)
        XCTAssertEqual(refund.spentMinor, "-2500")
        XCTAssertEqual(refund.meterFraction, 0)
    }
    func testBudgetSearchHitRetainsCanonicalIDAndLifecycle() throws {
        let budget = try progress(spent: "12000", remaining: "3000", over: "0").budget
        let definition = try JSONEncoder().encode(budget)
        let raw = Data("{\"kind\":\"budget\",\"budget\":".utf8) + definition + Data("}".utf8)
        let hit = try JSONDecoder().decode(FinancialSearchHit.self, from: raw)
        XCTAssertEqual(hit.recordID, budget.id)
        XCTAssertEqual(hit.kind, .budget)
        XCTAssertEqual(hit.amount, "150.00")
        XCTAssertFalse(hit.archived)
    }
    func testBudgetCreateAndLifecycleHaveDistinctVersionedPayloads() throws {
        let create = FinancialBudgetCommand(name: "Food", limit: "150.25", currency: "DOP", month: "2026-09",
            accountIds: [UUID()], categoryIds: [], includeUncategorized: true)
        let body = try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder().encode(create)) as? [String: Any])
        XCTAssertNil(body["expected_version"])
        XCTAssertEqual(body["limit"] as? String, "150.25")
        XCTAssertEqual(body["include_uncategorized"] as? Bool, true)
        let edit = FinancialBudgetLifecycleCommand(expectedVersion: 7, archived: true)
        let archived = try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder().encode(edit)) as? [String: Any])
        XCTAssertEqual(Set(archived.keys), ["expected_version", "archived"])
        XCTAssertEqual(archived["expected_version"] as? Int, 7)
        XCTAssertEqual(FinancialPlanOperation.editBudget(id: UUID(), version: 7).method, "PATCH")
    }
}
