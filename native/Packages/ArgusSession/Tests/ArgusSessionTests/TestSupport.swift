import Auth
import Foundation
import XCTest
@testable import ArgusSession

final class MemoryStore: AuthLocalStorage, @unchecked Sendable {
    private let lock = NSLock()
    private var values: [String: Data] = [:]
    var failWrites = false
    var failRemoves = false
    var failedWriteSuffix: String?
    var failedReadSuffix: String?
    func store(key: String, value: Data) throws {
        lock.lock(); defer { lock.unlock() }
        if failWrites || failedWriteSuffix.map({ key.hasSuffix($0) }) == true { throw SessionFailure.storageUnavailable }
        values[key] = value
    }
    func retrieve(key: String) throws -> Data? {
        lock.lock(); defer { lock.unlock() }
        if failedReadSuffix.map({ key.hasSuffix($0) }) == true { throw SessionFailure.storageUnavailable }
        return values[key]
    }
    func remove(key: String) throws {
        lock.lock(); defer { lock.unlock() }
        if failRemoves { throw SessionFailure.storageUnavailable }
        values[key] = nil
    }
}

actor RequestGate {
    private var started = false
    private var released = false
    private var starts: [CheckedContinuation<Void, Never>] = []
    private var releases: [CheckedContinuation<Void, Never>] = []
    func enter() async {
        started = true
        starts.forEach { $0.resume() }; starts.removeAll()
        if !released { await withCheckedContinuation { releases.append($0) } }
    }
    func waitUntilStarted() async {
        if !started { await withCheckedContinuation { starts.append($0) } }
    }
    func release() { released = true; releases.forEach { $0.resume() }; releases.removeAll() }
}

struct AuthorizedAppleChecker: AppleCredentialChecking {
    func state(for subject: String) async throws -> AppleCredentialState { .authorized }
}

actor AuthServer {
    let alice = UUID()
    let bob = UUID()
    var users: [String: UUID] = [:]
    var accessUsers: [String: UUID] = [:]
    var refreshUsers: [String: UUID] = [:]
    var requests: [URLRequest] = []
    var meStatuses: [Int] = []
    var logoutStatus = 204
    var refreshStatus = 200
    var refreshErrorCode = "refresh_token_not_found"
    var confirmationRequired = true
    var meGate: RequestGate?
    var refreshGate: RequestGate?
    var mismatchedProfile = false
    var expired = false
    var idTokenStatus = 200
    var idTokenErrorCode = "bad_jwt"
    var anonymousIdToken = false
    var captureStatus = 204
    var captureGate: RequestGate?
    var captureCode: String?
    var appleSubject: String?
    var currencyOverride: String?
    var displayName: String? = "Sample"
    var preferredName: String?
    var nameInitializationClosed = true
    var appleNameStatuses: [Int] = []
    var loseAppleNameResponse = false
    var appleNameGate: RequestGate?
    var idTokenGate: RequestGate?

    func configure(meStatuses: [Int] = [], logoutStatus: Int = 204, refreshStatus: Int = 200, refreshErrorCode: String = "refresh_token_not_found", mismatch: Bool = false, expired: Bool = false) {
        self.meStatuses = meStatuses
        self.logoutStatus = logoutStatus
        self.refreshStatus = refreshStatus
        self.refreshErrorCode = refreshErrorCode
        self.mismatchedProfile = mismatch
        self.expired = expired
    }
    func configureIdToken(status: Int = 200, errorCode: String = "bad_jwt", anonymous: Bool = false) {
        idTokenStatus = status
        idTokenErrorCode = errorCode
        anonymousIdToken = anonymous
    }
    func configureAppleName(statuses: [Int] = [], displayName: String? = nil, closed: Bool = false, loseResponse: Bool = false) {
        appleNameStatuses = statuses; self.displayName = displayName
        nameInitializationClosed = closed; loseAppleNameResponse = loseResponse
    }
    func holdAppleName(_ gate: RequestGate) { appleNameGate = gate }
    func holdIdToken(_ gate: RequestGate) { idTokenGate = gate }
    func configureCapture(status: Int, code: String? = nil) { captureStatus = status; captureCode = code }
    func holdCapture(_ gate: RequestGate) { captureGate = gate }
    func configureApple(subject: String?) { appleSubject = subject }
    func holdMe(_ gate: RequestGate) { meGate = gate }
    func holdRefresh(_ gate: RequestGate) { refreshGate = gate }
    func count(_ suffix: String) -> Int { requests.filter { $0.url!.path.hasSuffix(suffix) }.count }
    func captured() -> [URLRequest] { requests }

    func send(_ request: URLRequest) async throws -> (Data, URLResponse) {
        requests.append(request)
        let url = request.url!
        let body = (try? JSONSerialization.jsonObject(with: request.httpBody ?? Data())) as? [String: Any] ?? [:]
        let bearer = request.value(forHTTPHeaderField: "Authorization")?.replacingOccurrences(of: "Bearer ", with: "") ?? ""
        let path = url.path
        if path.hasSuffix("/auth/login") || path.hasSuffix("/auth/signup") {
            if path.hasSuffix("/signup") && confirmationRequired {
                return response(url, 200, ["session": NSNull(), "user": ["id": alice.uuidString]])
            }
            let id = body["email"] as? String == "bob@example.test" ? bob : alice
            return response(url, 200, ["session": makeSession(id), "user": user(id)])
        }
        if path.hasSuffix("/token"), url.query?.contains("grant_type=id_token") == true {
            if let idTokenGate { await idTokenGate.enter() }
            if idTokenStatus != 200 {
                return response(url, idTokenStatus, ["error_code": idTokenErrorCode, "msg": "Synthetic failure"])
            }
            let id = body["id_token"] as? String == Self.bobIdToken ? bob : alice
            if body["provider"] as? String == "apple", appleSubject == nil { appleSubject = "canonical-apple-subject" }
            return response(url, 200, makeSession(id, anonymous: anonymousIdToken))
        }
        if path.hasSuffix("/me/apple-name") {
            if let appleNameGate { await appleNameGate.enter() }
            let status = appleNameStatuses.isEmpty ? 200 : appleNameStatuses.removeFirst()
            guard status == 200 else { return response(url, status, ["code": "apple_name_unavailable"]) }
            if !nameInitializationClosed, displayName == nil {
                displayName = body["display_name"] as? String
                nameInitializationClosed = true
            }
            if loseAppleNameResponse { loseAppleNameResponse = false; throw URLError(.networkConnectionLost) }
            return response(url, 200, profileEnvelope(accessUsers[bearer] ?? alice))
        }
        if path.hasSuffix("/auth/apple/authorization-code") {
            if let captureGate { await captureGate.enter() }
            return response(url, captureStatus, captureCode.map { ["code": $0] } ?? (captureStatus == 404 ? ["detail": "Not Found"] : [:]))
        }
        if path.hasSuffix("/token") {
            if let gate = refreshGate { await gate.enter() }
            if refreshStatus != 200 {
                return response(url, refreshStatus, ["error_code": refreshStatus == 400 ? refreshErrorCode : "unexpected_failure", "msg": "Synthetic failure"])
            }
            let id = refreshUsers[body["refresh_token"] as? String ?? ""] ?? alice
            return response(url, 200, makeSession(id))
        }
        if path.hasSuffix("/user") { return response(url, 200, user(accessUsers[bearer] ?? alice)) }
        if path.hasSuffix("/logout") { return response(url, logoutStatus, ["msg": "Synthetic response"]) }
        if path.hasSuffix("/me") {
            let id = mismatchedProfile ? bob : (accessUsers[bearer] ?? alice)
            if let gate = meGate { await gate.enter() }
            let status = meStatuses.isEmpty ? 200 : meStatuses.removeFirst()
            if status == 200, request.httpMethod == "PATCH" {
                if body.keys.contains("currency_override") { currencyOverride = body["currency_override"] as? String }
                if let name = body["display_name"] as? String { displayName = name }
                if let name = body["preferred_name"] as? String { preferredName = name.trimmingCharacters(in: .whitespaces).isEmpty ? nil : name }
            }
            return response(url, status, status == 200 ? profileEnvelope(id) : ["code": "unauthorized"])
        }
        return response(url, 404, [:])
    }

    private func profileEnvelope(_ id: UUID) -> [String: Any] {
        var envelope: [String: Any] = ["user": ["id": id.uuidString, "email": "sample@example.test", "display_name": displayName as Any? ?? NSNull(), "preferred_name": preferredName as Any? ?? NSNull(), "language": "en", "currency": currencyOverride ?? "DOP", "currency_override": currencyOverride as Any? ?? NSNull()]]
        if let appleSubject { envelope["apple_identity"] = ["subject": appleSubject] }
        return envelope
    }

    static let aliceIdToken = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJhbGljZSJ9.c2lnbmF0dXJl"
    static let bobIdToken = "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJib2IifQ.c2lnbmF0dXJl"

    func sessionData(anonymous: Bool = false) throws -> Data {
        let raw = makeSession(alice, anonymous: anonymous)
        let decoder = JSONDecoder(); decoder.dateDecodingStrategy = .iso8601; decoder.keyDecodingStrategy = .convertFromSnakeCase
        let session = try decoder.decode(Session.self, from: JSONSerialization.data(withJSONObject: raw))
        return try JSONEncoder().encode(session)
    }

    private func makeSession(_ id: UUID, anonymous: Bool = false) -> [String: Any] {
        let expiry = Date().timeIntervalSince1970 + (expired ? -60 : 3600)
        let raw: [String: Any] = ["exp": expiry, "sub": id.uuidString, "nonce": UUID().uuidString]
        let payload = try! JSONSerialization.data(withJSONObject: raw).base64EncodedString().replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_").replacingOccurrences(of: "=", with: "")
        let access = "header.\(payload).signature"
        let refresh = UUID().uuidString
        accessUsers[access] = id; refreshUsers[refresh] = id
        return ["access_token": access, "refresh_token": refresh, "token_type": "bearer", "expires_in": 3600, "expires_at": expiry, "user": user(id, anonymous: anonymous)]
    }

    private func user(_ id: UUID, anonymous: Bool = false) -> [String: Any] {
        ["id": id.uuidString, "aud": "authenticated", "role": "authenticated", "email": "sample@example.test", "is_anonymous": anonymous, "app_metadata": [:], "user_metadata": [:], "created_at": "2026-09-28T00:00:00Z", "updated_at": "2026-09-28T00:00:00Z"]
    }
    private func response(_ url: URL, _ status: Int, _ json: [String: Any]) -> (Data, URLResponse) {
        (try! JSONSerialization.data(withJSONObject: json), HTTPURLResponse(url: url, statusCode: status, httpVersion: "HTTP/1.1", headerFields: ["Content-Type": "application/json", "Set-Cookie": "sb-auth-token=fixture; Path=/"])!)
    }
}

struct SessionFixture {
    let server = AuthServer()
    let storage = MemoryStore()
    let configuration: SessionConfiguration
    init() throws {
        configuration = try SessionConfiguration(argusAPIURL: URL(string: "https://api.example.test")!, supabaseURL: URL(string: "https://auth.example.test")!, publicAnonKey: "sb_publishable_test", keychainService: UUID().uuidString)
    }
    func controller(appleChecker: any AppleCredentialChecking = AuthorizedAppleChecker()) throws -> SessionController {
        try SessionController(configuration: configuration, storage: storage, appleChecker: appleChecker, fetch: { [server] in try await server.send($0) })
    }
    func login(_ controller: SessionController, email: String = "alice@example.test") async throws -> SessionSnapshot {
        try await controller.login(email: email, password: "synthetic-password", captchaToken: "synthetic-captcha")
    }
}

enum MoneyActivityWireFixture {
    static let amountMinor: Int64 = 1250
    static let amount = "12.50"
    static func detail(source: UUID, destination: UUID, kind: FinancialActivityKind = .transfer, redacted: Bool) throws -> FinancialActivityDetail {
        let sourceLeg: [String: Any] = ["record_id": UUID().uuidString, "record_revision": 1, "account_id": source.uuidString, "role": "source", "balance_movement_minor": -amountMinor, "coverage": []]
        let destinationLeg: [String: Any] = ["record_id": UUID().uuidString, "record_revision": 1, "account_id": destination.uuidString, "role": "destination", "balance_movement_minor": kind == .debtPayment ? -1000 : amountMinor, "coverage": []]
        let full: [String: Any] = [
            "activity_id": UUID().uuidString, "revision": 1, "kind": kind.rawValue,
            "amount_minor": redacted ? NSNull() : amountMinor, "amount": redacted ? NSNull() : amount,
            "currency": "DOP", "currency_fraction_digits": 2, "occurred_at": "2026-10-01T12:00:00Z", "time_zone": "America/Santo_Domingo",
            "note": redacted ? NSNull() : "Source owner note", "category_id": NSNull(), "source_id": NSNull(),
            "purchase_activity_id": NSNull(), "purchase_revision": NSNull(), "reason": redacted ? NSNull() : "Source owner correction",
            "recorded_at": "2026-10-01T12:00:00Z", "recorded_by": redacted ? NSNull() : UUID().uuidString,
            "principal_minor": !redacted && kind == .debtPayment ? 1000 : NSNull(),
            "interest_minor": !redacted && kind == .debtPayment ? 200 : NSNull(),
            "fees_minor": !redacted && kind == .debtPayment ? 50 : NSNull(),
            "legs": redacted ? [destinationLeg] : [sourceLeg, destinationLeg]
        ]
        return try JSONDecoder().decode(FinancialActivityDetail.self, from: JSONSerialization.data(withJSONObject: full))
    }
}
