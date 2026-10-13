import Foundation
import XCTest
@testable import ArgusSession
@testable import FinancialModels

/// A balance recorded at 09:00 cannot include a movement made at 10:01 the same day, so the app answers
/// "No, apply it" itself. A movement at or before the recorded balance is still asked.
@MainActor
final class CoverageAfterCheckTests: XCTestCase {
    private let account = UUID(uuidString: "6A1F0B8E-3C55-4C2E-9A7D-2F1B4C6D8E90")!
    private let opening = UUID(uuidString: "0B9C8D7E-6F5A-4B3C-8D2E-1F0A9B8C7D6E")!

    private func preview(asOf: String, included: Bool? = nil) throws -> FinancialActivityPreview {
        let observation: [String: Any] = ["observation_id": opening.uuidString, "kind": "opening", "as_of": asOf,
                                          "amount_minor": 100000, "amount": "1000.00", "time_zone": "America/Santo_Domingo",
                                          "included": included as Any? ?? NSNull()]
        let balance: [String: Any] = ["state": "known", "amount_minor": 100000, "amount": "1000.00", "as_of": asOf,
                                      "basis": "opening", "activity_since_tracking_minor": 0, "credit_minor": NSNull()]
        let json: [String: Any] = ["ready": false, "expected_versions": [account.uuidString: 1], "reviewed_request": NSNull(),
                                   "preview_token": NSNull(),
                                   "affected_accounts": [["account_id": account.uuidString, "currency": "DOP", "currency_fraction_digits": 2,
                                                          "before": balance, "after": NSNull(), "observations": [observation],
                                                          "unexplained_before": [:], "unexplained_after": NSNull()]]]
        return try JSONDecoder().decode(FinancialActivityPreview.self, from: JSONSerialization.data(withJSONObject: json))
    }

    private func at(_ text: String) throws -> Date { try XCTUnwrap(ISO8601DateFormatter().date(from: text)) }

    func testAMovementAfterTheRecordedBalanceIsAppliedWithoutAsking() throws {
        let answers = FinancialActivityEditor.answersAfterChecks(try preview(asOf: "2026-10-12T13:00:00Z"),
                                                                 movement: try at("2026-10-12T14:01:00Z"), answered: [])
        XCTAssertEqual(answers, [.init(accountId: account, observationId: opening, included: false)])
    }

    func testAMovementAtOrBeforeTheRecordedBalanceIsStillAsked() throws {
        let check = try preview(asOf: "2026-10-12T13:00:00Z")
        XCTAssertTrue(FinancialActivityEditor.answersAfterChecks(check, movement: try at("2026-10-12T12:30:00Z"), answered: []).isEmpty)
        XCTAssertTrue(FinancialActivityEditor.answersAfterChecks(check, movement: try at("2026-10-12T13:00:00Z"), answered: []).isEmpty)
    }

    func testAnAnswerThePersonGaveIsNeverReplaced() throws {
        let given = [FinancialAccountCoverage(accountId: account, observationId: opening, included: true)]
        XCTAssertTrue(FinancialActivityEditor.answersAfterChecks(try preview(asOf: "2026-10-12T13:00:00Z"),
                                                                 movement: try at("2026-10-12T14:01:00Z"), answered: given).isEmpty)
        XCTAssertTrue(FinancialActivityEditor.answersAfterChecks(try preview(asOf: "2026-10-12T13:00:00Z", included: true),
                                                                 movement: try at("2026-10-12T14:01:00Z"), answered: []).isEmpty)
    }

    func testTheQuestionKeyNamesOneAccountAndBalance() {
        XCTAssertEqual(FinancialActivityEditor.questionKey(account, opening), account.uuidString + "/" + opening.uuidString)
    }
}
