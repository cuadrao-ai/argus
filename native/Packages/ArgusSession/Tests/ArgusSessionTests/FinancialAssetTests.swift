import Foundation
import XCTest
@testable import ArgusSession

final class FinancialAssetTests: XCTestCase, @unchecked Sendable {
    func testAssetProjectionDecodesServerContributionAndUnknownSeparately() throws {
        let known = Data(#"{"personal_position_minor":33,"current_estimate":null,"estimates":[],"related_debt_account_id":null,"changes":[]}"#.utf8)
        let unknown = Data(#"{"personal_position_minor":null,"current_estimate":null,"estimates":[],"related_debt_account_id":null,"changes":[]}"#.utf8)
        XCTAssertEqual(try JSONDecoder().decode(FinancialAsset.self, from: known).personalPositionMinor, 33)
        XCTAssertNil(try JSONDecoder().decode(FinancialAsset.self, from: unknown).personalPositionMinor)
    }

    func testEstimateCommandKeepsSelectedRevisionAndProvenance() throws {
        let record = UUID()
        let command = FinancialAssetEstimateCommand(expectedVersion: 7, amount: "8100000", asOf: "2026-09-20T09:00:00-04:00", timeZone: "America/Santo_Domingo", estimateBasis: "Recent appraisal", reason: "Fixed typo", recordId: record, expectedRevision: 2, previewToken: "reviewed")
        let data = try JSONEncoder().encode(command)
        let decoded = try JSONDecoder().decode(FinancialAssetEstimateCommand.self, from: data)
        XCTAssertEqual(decoded, command)
        let body = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertEqual(body["record_id"] as? String, record.uuidString)
        XCTAssertEqual(body["expected_revision"] as? Int, 2)
        XCTAssertEqual(body["estimate_basis"] as? String, "Recent appraisal")
        XCTAssertEqual(body["amount"] as? String, "8100000")
    }

    func testRemovingDebtLinkEncodesExplicitNull() throws {
        let command = FinancialAssetDetailsCommand(expectedVersion: 3, ownershipShareBps: 3333, relatedDebtAccountId: nil)
        let body = try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder().encode(command)) as? [String: Any])
        XCTAssertTrue(body["related_debt_account_id"] is NSNull)
        XCTAssertEqual(body["ownership_share_bps"] as? Int, 3333)
    }

    func testPendingCreateSurvivesJournalRelaunchAndSendsExactRequest() async throws {
        let fixture = try AccountFixture()
        let identity = try await fixture.login()
        let owner = try XCTUnwrap(UUID(uuidString: identity.profile!.id))
        let command = CreateFinancialAccountRequest(type: "property", currency: "DOP", amount: "8000000", ownershipShareBps: 5000)
        let write = PendingFinancialConfirmation(ownerId: owner, originAccountId: nil, route: "financial-accounts", path: "", method: "POST", body: try JSONEncoder().encode(command), key: command.idempotencyKey)
        let storage = MemoryStore()
        try FinancialWriteJournal(storage: storage, prefix: "assets").begin(write, for: identity)
        await fixture.server.configure(failTransport: true)
        do { _ = try await fixture.client.sendAccountConfirmation(write, expectedIdentity: identity); XCTFail("Expected lost response") }
        catch { XCTAssertEqual(error as? SessionFailure, .unavailable) }
        let relaunched = FinancialWriteJournal(storage: storage, prefix: "assets")
        let recovered = try XCTUnwrap(relaunched.pending(for: identity))
        await fixture.server.configure()
        _ = try await fixture.client.sendAccountConfirmation(recovered, expectedIdentity: identity)
        let requests = await fixture.server.captured()
        XCTAssertEqual(requests.count, 2)
        XCTAssertEqual(requests[0].httpBody, requests[1].httpBody)
        XCTAssertEqual(requests[1].value(forHTTPHeaderField: "Idempotency-Key"), write.key.uuidString)
        try relaunched.clear(recovered, for: identity)
        XCTAssertNil(try relaunched.pending(for: identity))
    }

    func testMalformedPendingAssetPathIsRejectedBeforeSending() async throws {
        let fixture = try AccountFixture()
        let identity = try await fixture.login()
        let owner = try XCTUnwrap(UUID(uuidString: identity.profile!.id))
        let write = PendingFinancialConfirmation(ownerId: owner, originAccountId: UUID(), route: "financial-accounts", path: "/another/asset-details", method: "PUT", body: Data("{}".utf8), key: UUID())
        do { _ = try await fixture.client.sendAccountConfirmation(write, expectedIdentity: identity); XCTFail("Malformed path sent") }
        catch { XCTAssertEqual(error as? SessionFailure, .invalidResponse) }
        let requests = await fixture.server.captured()
        XCTAssertTrue(requests.isEmpty)
    }
}
