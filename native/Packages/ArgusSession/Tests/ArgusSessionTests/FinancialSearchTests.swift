import Foundation
import XCTest
@testable import ArgusSession

final class FinancialSearchTests: XCTestCase {
    func testTypedRowsKeepLogicalIdentityAndCanonicalMoneyWithoutCrossKindCollision() throws {
        let id = UUID().uuidString
        let date = "2026-09-01T12:00:00Z"
        let account: [String: Any] = ["id": id, "type": "cash", "nature": "asset", "currency": "DOP",
            "currency_fraction_digits": 2, "archived": true, "ownership_share_bps": 10000, "version": 1,
            "created_at": date, "updated_at": date,
            "balance": ["state": "unknown", "activity_since_tracking_minor": 0]]
        let legs: [[String: Any]] = ["source", "destination"].map { role in
            ["record_id": UUID().uuidString, "record_revision": 2, "account_id": UUID().uuidString,
             "role": role, "balance_movement_minor": role == "source" ? -100 : 100, "coverage": []]
        }
        let activity: [String: Any] = ["activity_id": id, "revision": 2, "kind": "transfer", "amount_minor": 100,
            "amount": "1.00", "currency": "DOP", "currency_fraction_digits": 2,
            "occurred_at": date, "time_zone": "UTC", "recorded_at": date, "legs": legs]
        let expectation: [String: Any] = ["id": id, "version": 1, "kind": "bill", "title": "Expected payment",
            "currency": "DOP", "currency_fraction_digits": 2, "amount_minor": 200, "amount": "2.00",
            "archived": true, "earliest_effective_date": "2026-09-29",
            "schedule": ["cadence": "once", "start_date": "2027-09-29", "month_days": []]]
        let raw: [String: Any] = ["items": [["kind": "account", "account": account],
            ["kind": "activity", "activity": activity, "archived": false],
            ["kind": "expectation", "expectation": expectation]], "next_cursor": "opaque+/="]
        let page = try JSONDecoder().decode(FinancialSearchPage.self, from: JSONSerialization.data(withJSONObject: raw))
        XCTAssertEqual(page.items.map(\.recordID), Array(repeating: UUID(uuidString: id)!, count: 3))
        XCTAssertEqual(Set(page.items.map(\.id)).count, 3)
        XCTAssertEqual(page.items.map(\.amount), [nil, "1.00", "2.00"])
        XCTAssertEqual(page.items.map(\.archived), [true, false, true])
        XCTAssertEqual(page.nextCursor, "opaque+/=")
    }

    func testUnsupportedOrMismatchedDestinationCannotFallbackToAnotherPayload() {
        for raw in [#"{"kind":"document","account":{}}"#, #"{"kind":"account","activity":{}}"#] {
            XCTAssertThrowsError(try JSONDecoder().decode(FinancialSearchHit.self, from: Data(raw.utf8)))
        }
    }
}
