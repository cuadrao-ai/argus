import Foundation
import XCTest
@testable import ArgusSession

final class FinancialLoopTests: XCTestCase, @unchecked Sendable {
    func testDestinationOnlyOriginalKeepsAmountUnknownWhileSourceOwnerKeepsFullFacts() throws {
        let source = UUID(), destination = UUID()
        let redacted = try MoneyActivityWireFixture.detail(source: source, destination: destination, kind: .debtPayment, redacted: true)
        XCTAssertNil(redacted.amount); XCTAssertNil(redacted.amountMinor); XCTAssertNil(redacted.principalMinor)
        XCTAssertNil(redacted.note); XCTAssertNil(redacted.reason); XCTAssertNil(redacted.recordedBy)
        XCTAssertEqual(redacted.legs.map(\.accountId), [destination]); XCTAssertEqual(redacted.legs[0].balanceMovementMinor, -1000)
        XCTAssertFalse(redacted.originalAmountAvailable)
        let full = try MoneyActivityWireFixture.detail(source: source, destination: destination, kind: .debtPayment, redacted: false)
        XCTAssertEqual(full.amount, MoneyActivityWireFixture.amount); XCTAssertEqual(full.amountMinor, MoneyActivityWireFixture.amountMinor)
        XCTAssertEqual(full.principalMinor, 1000); XCTAssertNotNil(full.note); XCTAssertTrue(full.originalAmountAvailable)
        XCTAssertEqual(full.legs.map(\.accountId), [source, destination])
    }
    func testHomePreservesAggregateBeyondInt64AndUnknownCoverage() throws {
        let raw = #"{"currencies":[{"currency":"DOP","currency_fraction_digits":2,"cash_minor":"18446744073709551614","other_assets_minor":"0","assets_minor":"18446744073709551614","debts_minor":"0","net_worth_minor":"18446744073709551614","known_accounts":2,"unknown_accounts":1,"recorded_spending_minor":"50","as_of":null}],"recent_activity":[],"recorded_at":"2026-09-29T12:00:00Z"}"#
        let home = try JSONDecoder().decode(FinancialHome.self, from: Data(raw.utf8))
        XCTAssertEqual(home.currencies.first?.netWorthMinor, "18446744073709551614")
        XCTAssertEqual(home.currencies.first?.unknownAccounts, 1)
    }

    func testExpensePreviewPreservesUnknownAndUnansweredObservation() throws {
        let observation = UUID()
        let raw = #"{"account_version":3,"ready":false,"observations":[{"observation_id":"\#(observation)","kind":"opening_balance","as_of":"2026-09-29T08:00:00-04:00","amount_minor":100000,"amount":"1000.00","included":null}],"before":{"state":"unknown","amount_minor":null,"amount":null,"as_of":null,"basis":null,"activity_since_tracking_minor":-1000},"after":null,"preview_token":null}"#
        let preview = try JSONDecoder().decode(ExpensePreview.self, from: Data(raw.utf8))
        XCTAssertFalse(preview.ready)
        XCTAssertNil(preview.observations.first?.included)
        XCTAssertNil(preview.before.amount)
        XCTAssertNil(preview.after)
    }

    func testUncertainExpenseRetryReusesExactBodyKeyAndCurrentIdentity() async throws {
        let fixture = try LoopFixture()
        let identity = try await fixture.login()
        let key = UUID()
        let request = ExpenseRequest(expectedVersion: 7, amount: "123.45", occurredAt: "2026-09-29T08:00:00-04:00",
                                     timeZone: "America/Santo_Domingo", note: "Synthetic", previewToken: "accepted-preview")
        for status in [500, 408] {
            await fixture.server.configure(status: status)
            do { _ = try await fixture.client.saveExpense(accountId: key, request: request, key: key, expectedIdentity: identity); XCTFail("Response must remain uncertain") }
            catch { XCTAssertEqual(error as? SessionFailure, status == 500 ? .unavailable : .rejected(status: 408, code: nil)) }
        }
        let requests = await fixture.server.captured()
        XCTAssertEqual(requests.count, 2)
        XCTAssertEqual(requests[0].httpBody, requests[1].httpBody)
        XCTAssertEqual(requests[0].value(forHTTPHeaderField: "Idempotency-Key"), key.uuidString)
        XCTAssertEqual(requests[1].value(forHTTPHeaderField: "Idempotency-Key"), key.uuidString)
        let body = try XCTUnwrap(try JSONSerialization.jsonObject(with: XCTUnwrap(requests[0].httpBody)) as? [String: Any])
        XCTAssertEqual(body["preview_token"] as? String, "accepted-preview")
        XCTAssertEqual(body["expected_version"] as? Int, 7)
    }

    func testActivityCursorIsQueryNotEncodedIntoPath() async throws {
        let fixture = try LoopFixture()
        let identity = try await fixture.login()
        let account = UUID()
        _ = try await fixture.client.financialActivity(accountId: account, cursor: "opaque+/=value", expectedIdentity: identity)
        let requests = await fixture.server.captured()
        let request = try XCTUnwrap(requests.first)
        XCTAssertEqual(request.url?.path, "/api/v1/financial-accounts/" + account.uuidString + "/activity")
        let components = URLComponents(url: try XCTUnwrap(request.url), resolvingAgainstBaseURL: false)
        XCTAssertEqual(components?.queryItems?.first?.value, "opaque+/=value")
    }

    func testForegroundProfileReadDoesNotBlockFinancialHome() async throws {
        let fixture = try LoopFixture()
        let identity = try await fixture.login()
        let gate = RequestGate()
        await fixture.server.auth.holdMe(gate)
        let foreground = Task { try await fixture.client.profile() }
        await gate.waitUntilStarted()
        let home = try await fixture.client.financialHome(expectedIdentity: identity)
        XCTAssertTrue(home.currencies.isEmpty)
        await gate.release()
        _ = try await foreground.value
    }

    func testOldFinancialHomeResponseCannotEnterNewOwnerSession() async throws {
        let fixture = try LoopFixture()
        let identity = try await fixture.login()
        let gate = RequestGate()
        await fixture.server.configure(gate: gate)
        let old = Task { try await fixture.client.financialHome(expectedIdentity: identity) }
        await gate.waitUntilStarted()
        _ = try await fixture.client.signOut()
        _ = try await fixture.login(email: "bob@example.test")
        await gate.release()
        do { _ = try await old.value; XCTFail("Old owner response must be retired") }
        catch { XCTAssertEqual(error as? SessionFailure, .staleOperation) }
    }
}

private struct LoopFixture {
    let server = LoopServer()
    let client: SessionController
    init() throws {
        let config = try SessionConfiguration(argusAPIURL: URL(string: "https://api.example.test")!,
            supabaseURL: URL(string: "https://auth.example.test")!, publicAnonKey: "sb_publishable_test", keychainService: UUID().uuidString)
        let server = self.server
        client = try SessionController(configuration: config, storage: MemoryStore(), fetch: { try await server.send($0) })
    }
    func login(email: String = "alice@example.test") async throws -> SessionSnapshot {
        try await client.login(email: email, password: "synthetic-password", captchaToken: "synthetic-captcha")
    }
}

private actor LoopServer {
    let auth = AuthServer()
    var requests: [URLRequest] = []
    var status = 200
    var gate: RequestGate?
    func configure(status: Int = 200, gate: RequestGate? = nil) { self.status = status; self.gate = gate }
    func captured() -> [URLRequest] { requests }
    func send(_ request: URLRequest) async throws -> (Data, URLResponse) {
        guard request.url!.path.contains("/financial-") else { return try await auth.send(request) }
        requests.append(request)
        if let gate { await gate.enter() }
        let data = request.url!.path.hasSuffix("/financial-home")
            ? Data(#"{"currencies":[],"recent_activity":[],"recorded_at":"2026-09-29T12:00:00Z"}"#.utf8)
            : Data(#"{"items":[],"next_cursor":null}"#.utf8)
        return (data, HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil, headerFields: nil)!)
    }
}
