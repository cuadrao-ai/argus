import Foundation
import XCTest
@testable import ArgusSession

final class FinancialDebtTests: XCTestCase {
    func testActualLoanAndReturnedComponentsRoundTripWithoutGuesses() throws {
        let source = UUID(), destination = UUID(), original = UUID()
        for kind in [FinancialActivityKind.debtPayment, .paymentReversal] {
            let command = FinancialActivityCommand(kind: kind, sourceAccountId: source, destinationAccountId: destination,
                amount: "350.00", occurredAt: "2026-09-30T12:00:00-04:00", timeZone: "America/Santo_Domingo",
                previewToken: "canonical-review", principal: "300.00", interest: "40.00", fees: "10.00",
                reversalOfActivityId: kind == .paymentReversal ? original : nil)
            let restored = try JSONDecoder().decode(FinancialActivityCommand.self, from: JSONEncoder().encode(command))
            XCTAssertEqual(restored, command)
            XCTAssertTrue(restored.kind.isPaired)
        }
        let missing = FinancialActivityCommand(kind: .debtPayment, amount: "10", occurredAt: "2026-09-30T12:00:00Z", timeZone: "UTC")
        let body = try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder().encode(missing)) as? [String: Any])
        XCTAssertTrue(body["principal"] is NSNull)
        XCTAssertTrue(body["interest"] is NSNull)
        XCTAssertTrue(body["fees"] is NSNull)
    }
    func testOptionalScenarioClearsExplicitlyWithoutChangingSchedule() throws {
        let command = FinancialDebtCommand(name: "Loan", debtAccountId: nil, sourceAccountId: nil, amount: nil,
            schedule: nil, assumptions: nil, expectedVersion: 4, effectiveDate: nil)
        let body = try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder().encode(command)) as? [String: Any])
        XCTAssertEqual(Set(body.keys), ["name", "assumptions", "expected_version"])
        XCTAssertTrue(body["assumptions"] is NSNull)
        let terms = FinancialDebtAssumptions(annualRatePercent: "12", recurringFees: "0", firstPeriodStart: "2026-09-30")
        XCTAssertTrue(try JSONDecoder().decode(FinancialDebtAssumptions.self, from: JSONEncoder().encode(terms)).noNewBorrowing)
    }
    func testDebtJournalRestoresExactOwnerTokenVersionAndBytes() throws {
        let id = UUID(), owner = UUID(), key = UUID()
        let operation = FinancialPlanOperation.recordDebt(id: id, version: 7)
        let bytes = Data(#"{"expected_version":7,"activity":{"kind":"debt_payment","principal":"300","interest":"40","fees":"10","amount":"350","preview_token":"unchanged"}}"#.utf8)
        let pending = PendingFinancialConfirmation(ownerId: owner, originAccountId: UUID(), route: "financial-plan", path: operation.path, method: operation.method, body: bytes, key: key, planOperation: operation)
        let restored = try JSONDecoder().decode(PendingFinancialConfirmation.self, from: JSONEncoder().encode(pending))
        XCTAssertEqual(restored, pending)
        XCTAssertEqual(restored.body, bytes)
        XCTAssertEqual(restored.ownerId, owner)
        XCTAssertTrue(try XCTUnwrap(restored.planOperation).recordsActivity)
        XCTAssertEqual(operation.path, "/debts/" + id.uuidString + "/payments")
        XCTAssertEqual(FinancialPlanOperation.editDebt(id: id, version: 7).method, "PATCH")
    }
    func testUnknownDebtSearchNeverUsesPlannedPaymentAsBalance() throws {
        let id = UUID()
        let raw = #"{"debt":{"id":"\#(id)","version":1,"debt_account_id":"\#(UUID())","name":"Unknown loan","currency":"DOP","currency_fraction_digits":2,"source_account_id":"\#(UUID())","amount_minor":50000,"amount":"500.00","schedule":{"cadence":"monthly","start_date":"2026-10-30","month_days":[]},"assumptions":null,"archived":false,"earliest_effective_date":"2026-09-30"},"balance":{"state":"unknown","amount_minor":null,"amount":null,"activity_since_tracking_minor":0},"state":"unknown","funding_pool":null,"payoff":{"state":"unavailable","reason":"balance_unknown"},"payments":[],"occurrences":[]}"#
        let progress = try JSONDecoder().decode(FinancialDebtProgress.self, from: Data(raw.utf8))
        let bytes = Data("{\"kind\":\"debt\",\"debt\":".utf8) + (try JSONEncoder().encode(progress)) + Data("}".utf8)
        let hit = try JSONDecoder().decode(FinancialSearchHit.self, from: bytes)
        XCTAssertEqual(hit.recordID, id)
        XCTAssertEqual(hit.kind, .debt)
        XCTAssertNil(hit.amount)
        XCTAssertEqual(progress.debt.amountMinor, 50000)
        XCTAssertNil(progress.payoff.payoffDate)
    }
}
