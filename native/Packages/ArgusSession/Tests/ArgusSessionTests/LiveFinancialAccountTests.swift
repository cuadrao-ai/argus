import Foundation
import XCTest
@testable import ArgusSession

/// Production Swift transport against lane-owned real auth/API/Postgres.
/// One login, own Keychain namespace, synthetic records retained for inspection.
final class LiveFinancialAccountTests: XCTestCase, @unchecked Sendable {
    func testLocalDurableAccountsThroughProductionClient() async throws {
        let fixture = try LocalSessionFixture.load()
        let client = try fixture.controller()
        var cleanupClient = client
        do {
            let identity = try await fixture.login(client, user: 0)
            let request = CreateFinancialAccountRequest(type: "credit_card", currency: "USD", nickname: "Swift debt proof", amount: "100.00", asOf: "2026-09-01T09:00:00-04:00", timeZone: "America/Santo_Domingo")
            let debt = try await client.createFinancialAccount(request, expectedIdentity: identity)
            XCTAssertEqual(debt.balance.amount, "-100.00")
            let replay = try await client.createFinancialAccount(request, expectedIdentity: identity)
            XCTAssertEqual(replay.id, debt.id)
            let zero = try await client.createFinancialAccount(.init(type: "checking", currency: "USD", nickname: "Swift zero proof", amount: "0"), expectedIdentity: identity)
            XCTAssertEqual(zero.balance.state, .known)
            XCTAssertEqual(zero.balance.amount, "0.00")
            let unknown = try await client.createFinancialAccount(.init(type: "cash", currency: "USD", nickname: "Swift unknown proof"), expectedIdentity: identity)
            XCTAssertEqual(unknown.balance.state, .unknown)
            XCTAssertNil(unknown.balance.amount)
            let renamed = try await client.updateFinancialAccount(id: unknown.id, request: .init(expectedVersion: unknown.version, nickname: ""), expectedIdentity: identity)
            XCTAssertNil(renamed.nickname)
            let initial = try await client.writeOpening(id: renamed.id, request: .init(expectedVersion: renamed.version, expectedRevision: nil, amount: "25.00", asOf: "2026-09-01T09:00:00-04:00", timeZone: "America/Santo_Domingo"), expectedIdentity: identity)
            XCTAssertEqual(initial.balance.amount, "25.00")
            let dateOnly = try await client.writeOpening(id: debt.id, request: .init(expectedVersion: debt.version, expectedRevision: debt.opening?.revision, asOf: "2026-09-02T09:00:00-04:00", reason: "Correct synthetic date"), expectedIdentity: identity)
            XCTAssertEqual(dateOnly.balance.amount, "-100.00")
            XCTAssertEqual(dateOnly.opening?.timeZone, debt.opening?.timeZone)
            let corrected = try await client.writeOpening(id: debt.id, request: .init(expectedVersion: dateOnly.version, expectedRevision: dateOnly.opening?.revision, amount: "120.00", reason: "Correct synthetic owed amount"), expectedIdentity: identity)
            XCTAssertEqual(corrected.balance.amount, "-120.00")
            XCTAssertEqual(corrected.opening?.asOf, dateOnly.opening?.asOf)
            XCTAssertEqual(corrected.opening?.revisions.count, 3)
            do {
                _ = try await client.writeOpening(id: debt.id, request: .init(expectedVersion: debt.version, expectedRevision: debt.opening?.revision, amount: "99.00", reason: "Stale correction"), expectedIdentity: identity)
                XCTFail("Stale viewed versions must fail")
            } catch { XCTAssertEqual(error as? SessionFailure, .rejected(status: 409, code: "stale_version")) }
            let archived = try await client.updateFinancialAccount(id: debt.id, request: .init(expectedVersion: corrected.version, archived: true), expectedIdentity: identity)
            XCTAssertTrue(archived.archived)
            let restored = try await client.updateFinancialAccount(id: debt.id, request: .init(expectedVersion: archived.version, archived: false), expectedIdentity: identity)
            XCTAssertFalse(restored.archived)
            // This controller receives only Keychain credentials, no financial cache.
            let relaunched = try fixture.controller()
            cleanupClient = relaunched
            let resumedIdentity = try await relaunched.restore()
            let reopened = try await relaunched.financialAccount(id: debt.id, expectedIdentity: resumedIdentity)
            XCTAssertEqual(reopened, restored)
            let listed = try await relaunched.financialAccounts(expectedIdentity: resumedIdentity)
            XCTAssertTrue(Set(listed.map(\.id)).isSuperset(of: [debt.id, zero.id, unknown.id]))
            let done = try await relaunched.signOut()
            XCTAssertEqual(done.phase, .signedOut)
        } catch {
            _ = try? await cleanupClient.signOut()
            throw error
        }
    }
}
