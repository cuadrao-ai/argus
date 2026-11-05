import Foundation
import XCTest
@testable import ArgusSession

final class FinancialGoalTests: XCTestCase {
    private func progress(_ supported: String?, state: String = "active") throws -> FinancialGoalProgress {
        let amount = supported.map { "\"" + $0 + "\"" } ?? "null"
        let raw = #"{"goal":{"id":"\#(UUID())","version":4,"name":"Emergency","currency":"DOP","currency_fraction_digits":2,"target_minor":100000,"target":"1000.00","target_date":"2026-12-01","destination_account_id":null,"contribution_plan":null,"allocations":[],"archived":false,"earliest_effective_date":"2026-09-30"},"assigned_minor":"90000","supported_minor":\#(amount),"independently_backed_minor":"20000","remaining_minor":null,"state":"\#(state)","reasons":[],"pools":[],"contributions":[],"components":[],"planned_minor":"10000","projected_minor":null,"projection_end_date":"2026-10-30"}"#
        return try JSONDecoder().decode(FinancialGoalProgress.self, from: Data(raw.utf8))
    }
    func testUnresolvedProgressHasNoMeterOrAssignedFallback() throws {
        let disputed = try progress(nil, state: "needs_review")
        XCTAssertNil(disputed.meterFraction)
        XCTAssertNil(disputed.supportedMinor)
        XCTAssertEqual(disputed.assignedMinor, "90000")
        XCTAssertEqual(disputed.independentlyBackedMinor, "20000")
        XCTAssertEqual(try progress("0").meterFraction, 0)
        XCTAssertEqual(try progress("60000").meterFraction, 0.6)
    }
    func testDateOnlyAndExplicitSetupClearingSurviveCommandEncoding() throws {
        let command = FinancialGoalCommand(name: "Trip", currency: nil, target: "1250.01", targetDate: "2026-12-01", destinationAccountId: nil, contributionPlan: nil, expectedVersion: 7)
        let body = try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder().encode(command)) as? [String: Any])
        XCTAssertEqual(body["target"] as? String, "1250.01")
        XCTAssertEqual(body["target_date"] as? String, "2026-12-01")
        XCTAssertEqual(body["expected_version"] as? Int, 7)
        XCTAssertTrue(body["destination_account_id"] is NSNull)
        XCTAssertTrue(body["contribution_plan"] is NSNull)
        XCTAssertNil(body["currency"])
    }
    func testGoalSearchKeepsGoalIdentityAndActualProgress() throws {
        let value = try progress("60000")
        let raw = Data("{\"kind\":\"goal\",\"goal\":".utf8) + (try JSONEncoder().encode(value)) + Data("}".utf8)
        let hit = try JSONDecoder().decode(FinancialSearchHit.self, from: raw)
        XCTAssertEqual(hit.kind, .goal)
        XCTAssertEqual(hit.recordID, value.id)
        guard case .goal(let found) = hit else { return XCTFail("Expected goal") }
        XCTAssertEqual(found.supportedMinor, "60000")
    }
    func testGoalJournalOperationRoundTripsExactCommandIdentity() throws {
        let id = UUID(), owner = UUID(), key = UUID()
        let operation = FinancialPlanOperation.recordGoal(id: id, version: 3)
        let body = Data(#"{"expected_version":3,"activity":{"preview_token":"reviewed","amount":"200.00"}}"#.utf8)
        let original = PendingFinancialConfirmation(ownerId: owner, originAccountId: UUID(), route: "financial-plan", path: operation.path, method: operation.method, body: body, key: key, planOperation: operation)
        let restored = try JSONDecoder().decode(PendingFinancialConfirmation.self, from: JSONEncoder().encode(original))
        XCTAssertEqual(restored, original)
        XCTAssertEqual(restored.body, body)
        XCTAssertEqual(restored.key, key)
        XCTAssertTrue(try XCTUnwrap(restored.planOperation).recordsActivity)
        XCTAssertEqual(operation.path, "/goals/" + id.uuidString + "/contributions")
        XCTAssertEqual(FinancialPlanOperation.allocateGoals.method, "PUT")
    }
}
