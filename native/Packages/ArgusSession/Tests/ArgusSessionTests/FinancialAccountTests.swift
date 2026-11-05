import Auth
import Foundation
import XCTest
@testable import ArgusSession

final class FinancialAccountTests: XCTestCase, @unchecked Sendable {
    func testWirePrecisionUnknownZeroAndStoredDates() throws {
        for amount in [nil, "0.00", "-92233720368547758.08"] as [String?] {
            let account = try JSONDecoder().decode(FinancialAccount.self, from: AccountServer.account(amount: amount))
            XCTAssertEqual(account.balance.state, amount == nil ? .unknown : .known)
            XCTAssertEqual(account.balance.amount, amount)
            XCTAssertEqual(account.balance.amountMinor, amount == nil ? nil : amount == "0.00" ? 0 : Int64.min)
            XCTAssertEqual(account.opening?.asOf, amount == nil ? nil : "2026-09-01T09:00:00-04:00")
            XCTAssertEqual(account.opening?.timeZone, amount == nil ? nil : "America/Santo_Domingo")
        }
    }

    func testWriteBodiesKeepViewedVersionsAndOmitUnchangedDebtAmount() throws {
        let encoder = JSONEncoder()
        let dateOnly = WriteOpeningRequest(expectedVersion: 8, expectedRevision: 3, asOf: "2026-09-02T09:00:00-04:00", reason: "Date correction")
        let json = try XCTUnwrap(JSONSerialization.jsonObject(with: encoder.encode(dateOnly)) as? [String: Any])
        XCTAssertEqual(json["expected_version"] as? Int, 8)
        XCTAssertEqual(json["expected_revision"] as? Int, 3)
        XCTAssertNil(json["amount"])
        XCTAssertNil(json["time_zone"])
        let initial = try XCTUnwrap(JSONSerialization.jsonObject(with: encoder.encode(WriteOpeningRequest(expectedVersion: 2, expectedRevision: nil, amount: "100.00"))) as? [String: Any])
        XCTAssertTrue(initial["expected_revision"] is NSNull)
        XCTAssertEqual(initial["amount"] as? String, "100.00")
        let clear = try XCTUnwrap(JSONSerialization.jsonObject(with: encoder.encode(EditFinancialAccountRequest(expectedVersion: 9, nickname: ""))) as? [String: Any])
        XCTAssertEqual(clear["nickname"] as? String, "")
        XCTAssertNil(clear["currency"])
    }

    func testCreateLostResponseRetryKeepsExactBodyAndKey() async throws {
        let fixture = try AccountFixture()
        let identity = try await fixture.login()
        let request = CreateFinancialAccountRequest(type: "credit_card", currency: "USD", amount: "100.00", asOf: "2026-09-01T09:00:00-04:00", timeZone: "America/Santo_Domingo")
        await fixture.server.configure(failTransport: true)
        do { _ = try await fixture.client.createFinancialAccount(request, expectedIdentity: identity); XCTFail("Delivery unknown") }
        catch { XCTAssertEqual(error as? SessionFailure, .unavailable) }
        await fixture.server.configure()
        _ = try await fixture.client.createFinancialAccount(request, expectedIdentity: identity)
        let requests = await fixture.server.captured()
        XCTAssertEqual(requests.count, 2)
        XCTAssertEqual(requests[0].httpBody, requests[1].httpBody)
        XCTAssertEqual(requests[0].value(forHTTPHeaderField: "Idempotency-Key"), request.idempotencyKey.uuidString)
        XCTAssertEqual(requests[1].value(forHTTPHeaderField: "Idempotency-Key"), request.idempotencyKey.uuidString)
        XCTAssertTrue(requests.allSatisfy { $0.value(forHTTPHeaderField: "Cookie") == nil })
        XCTAssertNil((try JSONSerialization.jsonObject(with: XCTUnwrap(requests[0].httpBody)) as? [String: Any])?["idempotencyKey"])
    }

    func testConflictAndValidationRemainBoundedWithoutRetry() async throws {
        let fixture = try AccountFixture()
        let identity = try await fixture.login()
        for (status, code) in [(409, "stale_version"), (422, "amount_precision"), (403, "account_conversion_required"), (404, "financial_accounts_unavailable"), (422, "private server prose!")] {
            await fixture.server.configure(statuses: [status], code: code)
            do { _ = try await fixture.client.writeOpening(id: AccountServer.id, request: .init(expectedVersion: 1, expectedRevision: nil, amount: "1.001"), expectedIdentity: identity); XCTFail("Expected rejection") }
            catch { XCTAssertEqual(error as? SessionFailure, .rejected(status: status, code: code.contains(" ") ? nil : code)) }
        }
        let count = await fixture.server.captured().count
        XCTAssertEqual(count, 5)
    }

    func testFinancial401UsesExistingRefreshAndSecond401RetiresIdentity() async throws {
        let fixture = try AccountFixture()
        let identity = try await fixture.login()
        await fixture.server.configure(statuses: [401, 200])
        _ = try await fixture.client.financialAccounts(expectedIdentity: identity)
        let count = await fixture.server.auth.count("/token")
        XCTAssertEqual(count, 1)
        await fixture.server.configure(statuses: [401, 401])
        do { _ = try await fixture.client.financialAccounts(expectedIdentity: identity); XCTFail("Auth expired") }
        catch { XCTAssertEqual(error as? SessionFailure, .unauthorized) }
        let after = await fixture.client.snapshot()
        XCTAssertNil(after.profile)
        XCTAssertNotEqual(after.revision, identity.revision)
    }

    func testRetiredIdentityRejectsLateSuccessAndFailureAndUnsentOldDraft() async throws {
        for fail in [false, true] {
            let fixture = try AccountFixture()
            let identity = try await fixture.login()
            let gate = RequestGate()
            await fixture.server.configure(failTransport: fail, gate: gate)
            let old = Task { try await fixture.client.financialAccounts(expectedIdentity: identity) }
            await gate.waitUntilStarted()
            _ = try await fixture.client.signOut()
            _ = try await fixture.login(email: "bob@example.test")
            await gate.release()
            do { _ = try await old.value; XCTFail("Old response must be retired") }
            catch { XCTAssertEqual(error as? SessionFailure, .staleOperation) }
            do { _ = try await fixture.client.createFinancialAccount(.init(type: "checking", currency: "USD"), expectedIdentity: identity); XCTFail("Old form must never send as Bob") }
            catch { XCTAssertEqual(error as? SessionFailure, .staleOperation) }
            let count = await fixture.server.captured().count
            XCTAssertEqual(count, 1)
        }
    }
}

struct AccountFixture {
    let server: AccountServer
    let client: SessionController
    init() throws {
        let server = AccountServer()
        self.server = server
        let config = try SessionConfiguration(argusAPIURL: URL(string: "https://api.example.test")!, supabaseURL: URL(string: "https://auth.example.test")!, publicAnonKey: "sb_publishable_test", keychainService: UUID().uuidString)
        client = try SessionController(configuration: config, storage: MemoryStore(), fetch: { try await server.send($0) })
    }
    func login(email: String = "alice@example.test") async throws -> SessionSnapshot {
        try await client.login(email: email, password: "synthetic-password", captchaToken: "synthetic-captcha")
    }
}

actor AccountServer {
    static let id = UUID()
    let auth = AuthServer()
    var statuses: [Int] = []
    var code = "stale_version"
    var failTransport = false
    var gate: RequestGate?
    var requests: [URLRequest] = []
    func configure(statuses: [Int] = [], code: String = "stale_version", failTransport: Bool = false, gate: RequestGate? = nil) {
        self.statuses = statuses; self.code = code; self.failTransport = failTransport; self.gate = gate
    }
    func captured() -> [URLRequest] { requests }
    func send(_ request: URLRequest) async throws -> (Data, URLResponse) {
        guard request.url!.path.contains("/financial-accounts") else { return try await auth.send(request) }
        requests.append(request)
        let shouldFail = failTransport
        if let gate { await gate.enter() }
        if shouldFail { throw URLError(.networkConnectionLost) }
        let status = statuses.isEmpty ? 200 : statuses.removeFirst()
        let bytes: Data
        if status != 200 {
            bytes = try JSONSerialization.data(withJSONObject: ["code": code, "detail": "Never expose this server prose"])
        } else if request.httpMethod == "GET" && request.url!.lastPathComponent == "financial-accounts" {
            bytes = Data("{\"accounts\":[".utf8) + Self.account(amount: "0.00") + Data("]}".utf8)
        } else { bytes = Self.account(amount: "0.00") }
        return (bytes, HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil, headerFields: nil)!)
    }
    static func account(amount: String?) -> Data {
        let nilValue = NSNull()
        let minor: Any = amount == nil ? nilValue : amount == "0.00" ? Int64(0) : Int64.min
        let instant = "2026-09-01T09:00:00-04:00"
        let revision: [String: Any] = ["revision": 1, "amount_minor": minor, "amount": amount as Any? ?? nilValue, "as_of": instant, "time_zone": "America/Santo_Domingo", "reason": nilValue, "recorded_at": instant, "recorded_by": nilValue]
        var opening = revision
        opening["record_id"] = UUID().uuidString
        opening["revisions"] = [revision]
        return try! JSONSerialization.data(withJSONObject: ["id": id.uuidString, "type": "credit_card", "nature": "liability", "currency": "USD", "currency_fraction_digits": 2, "nickname": nilValue, "archived": false, "ownership_share_bps": 10000, "version": 1, "created_at": instant, "updated_at": instant, "balance": ["state": amount == nil ? "unknown" : "known", "amount_minor": minor, "amount": amount as Any? ?? nilValue, "as_of": amount == nil ? nilValue as Any : instant, "basis": amount == nil ? nilValue as Any : "opening", "activity_since_tracking_minor": 0], "opening": amount == nil ? nilValue as Any : opening])
    }
}
