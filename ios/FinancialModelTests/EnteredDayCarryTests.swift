import Foundation
import XCTest
import ArgusSession
@testable import FinancialModels

final class EnteredDayCarryTests: XCTestCase {
    func testReviewedRequestKeepsTheDecidedEntryDayForConfirm() throws {
        let reviewed: [String: Any] = [
            "kind": "expense", "account_id": "6a1f0b8e-3c55-4c2e-9a7d-2f1b4c6d8e90", "amount": "200",
            "occurred_at": "2026-10-12T23:59:40-04:00", "time_zone": "America/Santo_Domingo",
            "expected_versions": [String: Int](), "coverage": [Any](), "entered_on": "2026-10-12",
        ]
        var command = try JSONDecoder().decode(FinancialActivityCommand.self,
                                               from: JSONSerialization.data(withJSONObject: reviewed))
        XCTAssertEqual(command.enteredOn, "2026-10-12")
        command.previewToken = "token"
        let sent = try JSONSerialization.jsonObject(with: JSONEncoder().encode(command)) as? [String: Any]
        XCTAssertEqual(sent?["entered_on"] as? String, "2026-10-12")
    }

    func testANewCommandSendsNoEntryDay() throws {
        let command = FinancialActivityCommand(kind: .expense, amount: "200",
                                               occurredAt: "2026-10-12T10:00:00-04:00", timeZone: "America/Santo_Domingo")
        let sent = try JSONSerialization.jsonObject(with: JSONEncoder().encode(command)) as? [String: Any]
        XCTAssertNil(sent?["entered_on"])
    }
}
