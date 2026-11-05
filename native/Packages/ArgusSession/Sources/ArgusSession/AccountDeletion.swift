import Foundation

/// The server result, never a prediction about operator or provider completion.
public enum AccountDeletionResult: Equatable, Sendable {
    case completed(ConfirmedAccountDeletion)
    case pending(userID: UUID)
    case uncertain(userID: UUID, retryAfter: Date?, canRetry: Bool, recovery: AccountDeletionRefusal?)
    case refused(AccountDeletionRefusal)
}

/// Only the session owner can issue this receipt after validated completion.
public struct ConfirmedAccountDeletion: Equatable, Sendable {
    public let userID: UUID
    public let initiatingRevision: UInt64
    let commandID: UUID
    init(userID: UUID, initiatingRevision: UInt64, commandID: UUID) {
        self.userID = userID; self.initiatingRevision = initiatingRevision; self.commandID = commandID
    }
}

public enum AccountDeletionRefusal: Equatable, Sendable, Codable {
    case freshAppleAuthorizationRequired
    case unavailable
    case forbidden
    case disabled
    case rateLimited(retryAfter: Date?)
    case invalidRequest
}

extension SessionController {
    /// The agreed fallback while the deletion command is off (404): a support ticket that the server
    /// binds to this session's account. It never records or implies deletion.
    public func requestAccountDeletionSupport(expectedIdentity: SessionSnapshot) async throws {
        struct Ticket: Encodable {
            let type = "account_deletion_request"
            let message = "Account deletion requested in the iOS app."
            let context = ["source": "ios_profile"]
        }
        _ = try await financialRequest(route: "feedback", method: "POST", body: encoded(Ticket()), expectedIdentity: expectedIdentity)
    }
}

struct AccountDeletionRequest: Encodable {
    let confirm = true
    let appleAuthorizationCode: String?
    enum CodingKeys: String, CodingKey { case confirm; case appleAuthorizationCode = "apple_authorization_code" }
    init(code: String?) throws {
        if let code {
            guard !code.isEmpty, code.utf8.count <= 512, code.allSatisfy(\.isASCII) else {
                throw SessionFailure.invalidResponse
            }
        }
        appleAuthorizationCode = code
    }
}

/// No token or one-time Apple code is persisted here. The existing session vault owns proof.
struct AccountDeletionJournal: Codable, Equatable, Sendable {
    enum Phase: String, Codable, Sendable { case uncertain, pending, completed }
    let id: UUID
    let userID: UUID
    let initiatingRevision: UInt64
    var phase: Phase
    var retryAfter: Date?
    var canRetry: Bool
    var recovery: AccountDeletionRefusal? = nil
}

enum AccountDeletionResponse {
    case done, pending
    case uncertain(retryAfter: Date?, canRetry: Bool)
    case refused(AccountDeletionRefusal)

    static func parse(_ data: Data, response: HTTPURLResponse, now: Date = Date()) -> Self {
        struct Body: Decodable { let status: String; let pending: [String] }
        struct Problem: Decodable { let code: String? }
        let status = response.statusCode
        let retry = retryAfter(response.value(forHTTPHeaderField: "Retry-After"), now: now)
        if status == 200 || status == 202 {
            guard let body = try? JSONDecoder().decode(Body.self, from: data) else {
                return .uncertain(retryAfter: retry, canRetry: true)
            }
            if status == 200, body.status == "done", body.pending.isEmpty { return .done }
            if status == 202, body.status == "in_progress" { return .pending }
            return .uncertain(retryAfter: retry, canRetry: true)
        }
        let code = (try? JSONDecoder().decode(Problem.self, from: data))?.code
        switch (status, code) {
        case (409, "apple_reauthorization_required"), (409, "apple_identity_mismatch"),
             (400, "apple_authorization_invalid"):
            return .refused(.freshAppleAuthorizationRequired)
        case (503, "account_deletion_unavailable"): return .refused(.unavailable)
        case (403, "account_deletion_not_allowed"): return .refused(.forbidden)
        case (404, _): return .refused(.disabled)
        case (429, _): return .refused(.rateLimited(retryAfter: retry))
        case (422, _): return .refused(.invalidRequest)
        case (401, _), (403, _): return .uncertain(retryAfter: retry, canRetry: false)
        default: return .uncertain(retryAfter: retry, canRetry: true)
        }
    }

    private static func retryAfter(_ raw: String?, now: Date) -> Date? {
        guard let raw else { return nil }
        if let seconds = TimeInterval(raw), seconds.isFinite, seconds >= 0 {
            return now.addingTimeInterval(seconds)
        }
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(secondsFromGMT: 0)
        formatter.dateFormat = "EEE, dd MMM yyyy HH:mm:ss zzz"
        return formatter.date(from: raw)
    }
}
